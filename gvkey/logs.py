"""日志模块.

整个应用的日志都走这里：
- 同时输出到 UI 内存队列（用于面板上的滚动显示）和文件（%APPDATA%/GameVoiceKey/logs/）
- 日志按天轮转（gvk-YYYY-MM-DD.log）
- 自带一份 'trigger' 表，专门记录语音->按键的命中情况
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# ============================================================
# 默认日志目录：%APPDATA%/GameVoiceKey/logs/
# ============================================================

def user_data_dir() -> Path:
    """用户数据根目录。"""

    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home())
    return Path(base) / "GameVoiceKey"


def logs_dir() -> Path:
    """日志目录。"""

    p = user_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ============================================================
# 内存广播：把日志行同步推送给 UI
# ============================================================


class _MemoryHandler(logging.Handler):
    """把日志往内存队列里放一份，供 UI 订阅。"""

    def __init__(self, maxlen: int = 2000) -> None:
        super().__init__()
        self._records: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._subscribers: list[list[dict[str, Any]]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": self.format(record),
            }
        except Exception:  # noqa: BLE001
            return
        with self._lock:
            self._records.append(entry)
            # 推给订阅者（每条追加一份，订阅者 200 条滑动窗口）
            for sub in self._subscribers:
                sub.append(entry)
                if len(sub) > 200:
                    del sub[:-200]

    def recent(self, n: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._records)[-n:]

    def subscribe(self) -> list[dict[str, Any]]:
        """订阅一份实时队列（视图），UI 拿到这个 list 后 poll 它即可。"""

        sub: list[dict[str, Any]] = []
        with self._lock:
            # 启动时补一段历史，避免界面一开始是空的
            sub.extend(self._records[-50:])
            self._subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: list[dict[str, Any]]) -> None:
        with self._lock:
            if sub in self._subscribers:
                self._subscribers.remove(sub)


_memory = _MemoryHandler()


# ============================================================
# 初始化 logger
# ============================================================


def setup_logging(level: str = "INFO") -> logging.Logger:
    """初始化全局 logger，重复调用是幂等的。"""

    logger = logging.getLogger("gvkey")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False  # 不要冒到 root（避免被 IDE 抓走）

    # 先清掉已有的 handler（幂等）
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 文件输出：按天命名 + 轮转
    try:
        logfile = logs_dir() / f"gvk-{datetime.now():%Y-%m-%d}.log"
        file_h = RotatingFileHandler(
            logfile,
            maxBytes=2 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_h.setFormatter(fmt)
        logger.addHandler(file_h)
    except Exception as exc:  # noqa: BLE001
        # 日志失败不能阻塞程序
        sys.stderr.write(f"[gvkey] 日志初始化失败: {exc}\n")

    # 控制台（开发期用）
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 内存广播（UI 用）
    _memory.setFormatter(fmt)
    logger.addHandler(_memory)

    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("gvkey")


# 触发记录专用：UI 的「语音触发统计」页读这个
_TRIGGER_HISTORY: deque[dict[str, Any]] = deque(maxlen=1000)
_TRIGGER_LOCK = threading.Lock()


def record_trigger(
    *,
    profile: str,
    phrase: str,
    key: str,
    success: bool,
    extra: dict[str, Any] | None = None,
) -> None:
    """记录一次触发（成功 / 失败都记）。"""

    entry: dict[str, Any] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "profile": profile,
        "phrase": phrase,
        "key": key,
        "success": success,
    }
    if extra:
        entry.update(extra)
    with _TRIGGER_LOCK:
        _TRIGGER_HISTORY.append(entry)
    get_logger().info(
        "trigger %s profile=%s phrase=%r key=%s",
        "✓" if success else "✗",
        profile,
        phrase,
        key,
    )


def trigger_history(n: int = 200) -> list[dict[str, Any]]:
    with _TRIGGER_LOCK:
        return list(_TRIGGER_HISTORY)[-n:]


def trigger_stats() -> dict[str, int]:
    """返回统计信息：成功 / 失败 / 总数。"""

    with _TRIGGER_LOCK:
        total = len(_TRIGGER_HISTORY)
        success = sum(1 for e in _TRIGGER_HISTORY if e.get("success"))
    return {
        "total": total,
        "success": success,
        "fail": total - success,
    }


def export_triggers(path: str | os.PathLike) -> None:
    """导出触发记录为 jsonl。"""

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for e in trigger_history(10_000):
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
