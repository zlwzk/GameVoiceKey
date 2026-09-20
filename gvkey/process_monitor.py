"""进程监控 + 窗口焦点.

ProcessMonitor:
- 周期性扫描系统中指定 game 进程（按 profile 库匹配）
- 提供「当前匹配 Profile」信号
- 在游戏关闭瞬间清空匹配，避免桌面误触发

ForegroundTracker:
- 跟踪当前前台窗口 PID（用于「仅游戏前台生效」判断）
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

import psutil

from .logs import get_logger

LOGGER = get_logger()


@dataclass
class ForegroundInfo:
    pid: int
    hwnd: int
    title: str
    class_name: str
    process_name: str


class ForegroundTracker:
    """通过 psutil 拿当前前台进程基本信息。"""

    def __init__(self) -> None:
        self._last = ForegroundInfo(0, 0, "", "", "")

    def current(self) -> ForegroundInfo:
        try:
            hwnd = self._get_foreground_hwnd()
            pid = self._get_pid_from_hwnd(hwnd) if hwnd else 0
            title = self._get_window_text(hwnd) if hwnd else ""
            cls = self._get_class_name(hwnd) if hwnd else ""
            proc_name = ""
            if pid:
                try:
                    proc_name = psutil.Process(pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc_name = ""
            self._last = ForegroundInfo(pid=pid, hwnd=hwnd, title=title, class_name=cls, process_name=proc_name)
        except Exception:  # noqa: BLE001
            # tracker 必须容错，不能让 GUI 崩
            pass
        return self._last

    @staticmethod
    def _get_foreground_hwnd() -> int:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return int(user32.GetForegroundWindow())
        except Exception:  # noqa: BLE001
            return 0

    @staticmethod
    def _get_pid_from_hwnd(hwnd: int) -> int:
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return int(pid.value)
        except Exception:  # noqa: BLE001
            return 0

    @staticmethod
    def _get_window_text(hwnd: int) -> str:
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _get_class_name(hwnd: int) -> str:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            return buf.value
        except Exception:  # noqa: BLE001
            return ""


class ProcessMonitor:
    """周期性扫描进程 → 找出匹配 Profile → 通知回调.

    调度：
- scan_interval_ms：扫描轮询周期
- on_match(profile, info)：找到匹配时回调（info 含前台信息）
- on_unmatch()：失去匹配时回调（一般由扫描器检测到匹配进程消失时触发）
    """

    def __init__(self, store_provider: Callable[[], list], scan_interval_ms: int = 1500) -> None:
        self._store_provider = store_provider
        self._interval_ms = max(300, int(scan_interval_ms))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_pid: int | None = None
        self._match_callbacks: list[Callable] = []
        self._unmatch_callbacks: list[Callable] = []
        self._whitelist: list[str] = []
        self._blacklist: list[str] = []

    def subscribe_match(self, cb: Callable) -> None:
        self._match_callbacks.append(cb)

    def subscribe_unmatch(self, cb: Callable) -> None:
        self._unmatch_callbacks.append(cb)

    def set_whitelist(self, names: list[str]) -> None:
        self._whitelist = [n.lower().rstrip(".exe") for n in names if n.strip()]

    def set_blacklist(self, names: list[str]) -> None:
        self._blacklist = [n.lower().rstrip(".exe") for n in names if n.strip()]

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ProcessMonitor",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info("ProcessMonitor 启动 (interval=%dms)", self._interval_ms)

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t:
            t.join(timeout=2)
        LOGGER.info("ProcessMonitor 已停止")

    def set_interval(self, ms: int) -> None:
        self._interval_ms = max(300, int(ms))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._scan_once()
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("扫描异常: %s", exc)
            # 用 sleep 块可被 Event 早醒
            self._stop.wait(self._interval_ms / 1000.0)

    def _scan_once(self) -> None:
        profiles = self._store_provider()
        if not profiles:
            return
        # 收集所有候选项的 process name 大写
        proc_targets: dict[str, list] = {}
        for p in profiles:
            if not p.enabled:
                continue
            for proc in p.processes:
                key = proc.lower().rstrip(".exe")
                if key:
                    proc_targets.setdefault(key, []).append(p)
        if not proc_targets:
            return
        # 扫描所有进程
        found_pid: int | None = None
        matched_proc: str | None = None
        matched_profiles: list = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info.get("name") or "").lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if not name:
                continue
            key = name.rstrip(".exe")
            if key in self._blacklist:
                continue
            if self._whitelist and key not in self._whitelist:
                # 如果配置了白名单，只扫白名单
                continue
            candidates = proc_targets.get(key)
            if candidates:
                found_pid = int(proc.info["pid"])
                matched_proc = key
                matched_profiles = candidates
                break  # 找到第一个匹配
        if found_pid is None:
            if self._current_pid is not None:
                LOGGER.info("匹配进程已退出，恢复待机")
                self._current_pid = None
                matched_proc = None
                for cb in list(self._unmatch_callbacks):
                    try:
                        cb()
                    except Exception as exc:  # noqa: BLE001
                        LOGGER.warning("unmatch callback error: %s", exc)
            return
        if found_pid != self._current_pid:
            self._current_pid = found_pid
            fg = ForegroundTracker().current()
            info = {"pid": found_pid, "proc": matched_proc, "fg": fg.__dict__}
            # 多游戏匹配时，优先选置顶 + 最新
            chosen = sorted(
                matched_profiles,
                key=lambda p: (
                    not getattr(p, "pin", False),
                    -time.mktime(time.strptime(p.last_modified, "%Y-%m-%dT%H:%M:%S")) if p.last_modified else 0,
                ),
            )[0]
            LOGGER.info("检测到游戏进程: %s (pid=%d) -> 配置: %s", matched_proc, found_pid, chosen.name)
            for cb in list(self._match_callbacks):
                try:
                    cb(chosen, info)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("match callback error: %s", exc)
