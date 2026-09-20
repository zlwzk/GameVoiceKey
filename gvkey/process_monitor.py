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


def normalize_process_name(name: str) -> str:
    """把进程名归一化成「小写、无 .exe」，用于存进 Profile.processes 与比较。

    **不要用 ``str.rstrip(".exe")``** —— rstrip 是按字符集裁剪的，
    ``"gvkprobe".rstrip(".exe")`` 会得到 ``"gvkprob"``（把结尾的 e 也啃掉了），
    于是「同一个进程」在存取两侧算出不同的名字，表现为**反复新建重复配置**。
    """

    key = (name or "").strip().lower()
    if key.endswith(".exe"):
        key = key[:-4]
    return key.strip()


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
        self._whitelist = [normalize_process_name(n) for n in names if n.strip()]

    def set_blacklist(self, names: list[str]) -> None:
        self._blacklist = [normalize_process_name(n) for n in names if n.strip()]

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
                key = normalize_process_name(proc)
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
            key = normalize_process_name(name)
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


# ============================================================
# 「当前游玩的游戏」候选进程枚举
# ============================================================
#
# 用于「让用户主动选择当前在玩的游戏」这一交互：
# 只列出**有可见窗口**的进程 —— 后台服务、驱动、系统组件都不会出现，
# 剩下的基本就是用户眼前看得见的程序，从中挑游戏一目了然。
# ============================================================


@dataclass
class RunningApp:
    """一个「用户看得见」的运行程序。"""

    pid: int
    process: str  # 小写、不含 .exe，用于写入 Profile.processes
    display: str  # 原始进程名（带 .exe），用于展示
    title: str  # 主窗口标题
    path: str  # exe 完整路径（可能为空，权限不足时）

    @property
    def pretty(self) -> str:
        return self.title or self.display


# 这些窗口类是系统外壳 / 输入法 / 托盘，不是用户玩的东西
_SHELL_WINDOW_CLASSES = {
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Progman",
    "WorkerW",
    "ForegroundStaging",
    "TaskManagerWindow",
    "MultitaskingViewFrame",
    "XamlExplorerHostIslandWindow",
    "Windows.Internal.Shell.TabProxyWindow",
    "ApplicationManager_DesktopShellWindow",
}

# 这些进程属于 Windows 自身
_SHELL_PROCESSES = {
    "explorer", "searchapp", "searchhost", "shellexperiencehost",
    "startmenuexperiencehost", "textinputhost", "applicationframehost",
    "systemsettings", "dwm", "winlogon", "csrss", "smss", "services",
    "lsass", "svchost", "runtimebroker", "conhost", "sihost", "taskhostw",
    "ctfmon", "fontdrvhost", "spoolsv", "audiodg", "registry",
    "memcompression", "securityhealthservice", "securityhealthsystray",
    "widgets", "widgetservice", "lockapp", "useroobebroker", "dllhost",
    "wmiprvse", "taskmgr", "mmgaserver", "crashpad_handler",
}

# 我们自己的进程
_SELF_PROCESSES = {"gamevoicekey", "python", "pythonw", "python3"}


def _enum_top_windows() -> list[tuple[int, int, str, str]]:
    """枚举所有「可见且有标题」的顶层窗口。

    返回 ``[(hwnd, pid, title, class_name), ...]``。
    非 Windows 或调用失败时返回空列表（调用方需要容错）。
    """

    if os.name != "nt":
        return []

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
    except Exception:  # noqa: BLE001
        return []

    collected: list[tuple[int, int, str, str]] = []

    try:
        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _callback(hwnd, _lparam):  # type: ignore[no-untyped-def]
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").strip()
                if not title:
                    return True
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                collected.append((int(hwnd), int(pid.value), title, cls_buf.value or ""))
            except Exception:  # noqa: BLE001
                pass
            return True

        user32.EnumWindows(enum_proc(_callback), 0)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("枚举窗口失败: %s", exc)
        return []

    return collected


def list_running_apps(*, include_system: bool = False, limit: int = 200) -> list[RunningApp]:
    """列出候选程序（默认过滤掉 Windows 自身组件）。

    同一进程名只保留一条（优先保留有窗口标题的那条），按名称排序。
    任何异常都吞掉并返回已经收集到的部分，保证 UI 不会崩。
    """

    by_name: dict[str, RunningApp] = {}

    for _hwnd, pid, title, cls in _enum_top_windows():
        if not include_system and cls in _SHELL_WINDOW_CLASSES:
            continue
        try:
            proc = psutil.Process(pid)
            raw = (proc.name() or "").strip()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception:  # noqa: BLE001
            continue
        if not raw:
            continue

        key = normalize_process_name(raw)
        if not include_system and (key in _SHELL_PROCESSES or key in _SELF_PROCESSES):
            continue

        path = ""
        try:
            path = proc.exe() or ""
        except Exception:  # noqa: BLE001
            path = ""

        old = by_name.get(key)
        # 同一进程多个窗口：优先保留标题更长的（通常是主窗口）
        if old is None or len(title) > len(old.title):
            by_name[key] = RunningApp(pid=pid, process=key, display=raw, title=title, path=path)

    apps = sorted(by_name.values(), key=lambda a: a.display.lower())
    return apps[:limit]


def is_probably_game(app: RunningApp) -> bool:
    """粗判「像不像游戏」（仅用于在列表里把它们排前面，不做过滤）。

    判断依据：exe 路径里有常见游戏平台目录，或进程名排除掉常见办公/浏览器。
    """

    path = (app.path or "").lower()
    if any(marker in path for marker in (
        "\\steamapps\\common\\", "\\steam\\", "\\epic games\\", "\\riot games\\",
        "\\ubisoft\\", "\\origin\\", "\\ea games\\", "\\battle.net\\",
        "\\wegame\\", "\\gog galaxy\\", "\\games\\",
    )):
        return True
    return False

