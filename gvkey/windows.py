"""Windows 平台工具.

- 开机自启（写入注册表 Run 键）
- 全屏窗口检测
- 屏蔽前台窗口（让悬浮窗更平滑）

这些是平台相关操作。如果不是 Windows，提供 no-op 实现，方便开发。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

from .logs import get_logger

LOGGER = get_logger()

IS_WINDOWS = sys.platform == "win32"


# ============================================================
# 开机自启
# ============================================================


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(app_name: str, exe_path: str, args: str = "") -> bool:
    """写入 Windows 注册表 Run 键。

    exe_path: 启动用的 exe（开发期可以是 python.exe + 脚本绝对路径）
    args: 额外参数，比如 --minimized
    """

    if not IS_WINDOWS:
        LOGGER.warning("非 Windows，跳过 autostart")
        return False
    try:
        import winreg  # type: ignore
        cmd = f'"{exe_path}"'
        if args:
            cmd += f" {args}"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
        LOGGER.info("已写入开机自启: %s -> %s", app_name, cmd)
        return True
    except Exception as exc:
        LOGGER.warning("设置开机自启失败: %s", exc)
        return False


def remove_autostart(app_name: str) -> bool:
    if not IS_WINDOWS:
        return False
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        LOGGER.info("已删除开机自启: %s", app_name)
        return True
    except Exception as exc:
        LOGGER.warning("删除开机自启失败: %s", exc)
        return False


def get_autostart(app_name: str) -> str | None:
    if not IS_WINDOWS:
        return None
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, app_name)
            return value
    except FileNotFoundError:
        return None
    except Exception:
        return None


# ============================================================
# 全屏检测（用于悬浮窗自动切紧凑模式）
# ============================================================


def is_current_fullscreen() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        mon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        mi = wintypes.MONITORINFO()
        mi.cbSize = ctypes.sizeof(wintypes.MONITORINFO)
        user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        m = mi.rcMonitor
        # 窗口铺满整屏，且没有标题栏高度差 → 全屏
        return (rect.left <= m.left and rect.top <= m.top
                and rect.right >= m.right and rect.bottom >= m.bottom)
    except Exception:
        return False


# ============================================================
# 鼠标穿透（悬浮窗 WS_EX_TRANSPARENT）
# ============================================================


def apply_click_through(hwnd: int, enabled: bool) -> bool:
    """给一个 hwnd 切换 WS_EX_TRANSPARENT 风格（鼠标穿透）。"""

    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_LAYERED = 0x00080000
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enabled:
            style = style | WS_EX_TRANSPARENT | WS_EX_LAYERED
        else:
            style = style & ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        return True
    except Exception:
        return False


def set_window_pos_topmost(hwnd: int) -> None:
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        user32 = ctypes.windll.user32
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    except Exception:
        pass


def set_window_pos_bottomright(hwnd: int) -> None:
    """把悬浮窗移到屏幕右下角（兜底位置）。"""

    if not IS_WINDOWS:
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        x = screen_w - w - 24
        y = screen_h - h - 48
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        user32.SetWindowPos(hwnd, 0, x, y, 0, 0,
                            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
    except Exception:
        pass


# ============================================================
# 自动启动的可执行文件路径
# ============================================================


def current_exe_path() -> str:
    """返回当前 exe 绝对路径（PyInstaller 打包后是 sys.executable）。"""

    if getattr(sys, "frozen", False):
        return sys.executable
    # dev: 用 pythonw.exe + 当前 main 入口
    main = sys.argv[0] if sys.argv else __file__
    py = Path(sys.executable)
    return f'"{py}" "{Path(main).resolve()}"'
