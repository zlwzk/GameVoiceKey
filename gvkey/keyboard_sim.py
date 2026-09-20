"""全局快捷键监听 + 按键 / 鼠标模拟.

- 按键定义字符串格式: 'F1', 'Ctrl+1', 'Shift+A', 'Alt+F4', 'LMB', 'RMB', 'MMB',
  'WheelUp', 'WheelDown', 'WheelLeft', 'WheelRight'
- 解析后内部用 pynput 做注入（背后是 ctypes SendInput），低延迟
- 全局热键注册用 keyboard 库（hotkey 名跟 keyboard 的语法一致）
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

try:
    from pynput.keyboard import Controller as KbController  # type: ignore
    from pynput.keyboard import Key as KbKey
    from pynput.mouse import Controller as MouseController  # type: ignore
    from pynput.mouse import Button as MouseButton
    _HAVE_PYNPUT = True
except Exception:
    _HAVE_PYNPUT = False

try:
    import keyboard as _kb_lib  # type: ignore
    _HAVE_KEYBOARD = True
except Exception:
    _HAVE_KEYBOARD = False

from .logs import get_logger

LOGGER = get_logger()


# ============================================================
# 按键字符串 -> 内部对象
# ============================================================


@dataclass
class ParsedKey:
    is_mouse: bool = False
    is_wheel: bool = False
    modifiers: tuple = ()
    key: str = ""
    wheel_delta: int = 0


_PYNPUT_KEY_MAP: dict[str, str] = {
    "esc": "escape", "escape": "escape",
    "tab": "tab",
    "space": "space", "space_bar": "space",
    "enter": "enter", "return": "enter",
    "backspace": "backspace",
    "delete": "delete", "del": "delete",
    "insert": "insert", "ins": "insert",
    "home": "home",
    "end": "end",
    "page_up": "pageup", "pageup": "pageup", "pgup": "pageup",
    "page_down": "pagedown", "pagedown": "pagedown", "pgdn": "pagedown",
    "left": "left", "right": "right", "up": "up", "down": "down",
    "caps_lock": "capslock", "capslock": "capslock",
    "num_lock": "numlock", "numlock": "numlock",
    "scroll_lock": "scrolllock", "scrolllock": "scrolllock",
    "print_screen": "printscreen", "printscreen": "printscreen",
    "shift": "shift", "shift_l": "lshift", "shift_r": "rshift",
    "ctrl": "ctrl", "ctrl_l": "lctrl", "ctrl_r": "rctrl",
    "alt": "alt", "alt_l": "lalt", "alt_r": "ralt",
    "alt_gr": "ralt",
    "cmd": "lwin", "cmd_l": "lwin", "cmd_r": "rwin",
    "win": "lwin", "win_l": "lwin", "win_r": "rwin",
    "menu": "menu",
    "pause": "pause",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4", "f5": "f5", "f6": "f6",
    "f7": "f7", "f8": "f8", "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
    "f13": "f13", "f14": "f14", "f15": "f15", "f16": "f16", "f17": "f17",
    "f18": "f18", "f19": "f19", "f20": "f20", "f21": "f21", "f22": "f22",
    "f23": "f23", "f24": "f24",
}

_MOD_NAMES = {"ctrl", "shift", "alt", "win", "lwin", "rwin", "lctrl", "rctrl",
              "lshift", "rshift", "lalt", "ralt"}

_MOUSE_BUTTONS = {
    "LMB": "left", "RMB": "right", "MMB": "middle", "X1": "x1", "X2": "x2",
    "MOUSE_LEFT": "left", "MOUSE_RIGHT": "right", "MOUSE_MIDDLE": "middle",
}

_WHEELS = {
    "WHEELUP": ("wheel", -1),
    "WHEELDOWN": ("wheel", 1),
    "WHEELUP_LEFT": ("hscroll", -1),
    "WHEELDOWN_LEFT": ("hscroll", 1),
}


def parse_key(spec: str) -> ParsedKey:
    s = (spec or "").strip()
    if not s:
        return ParsedKey()
    upper = s.upper().replace(" ", "")

    if upper in _MOUSE_BUTTONS:
        return ParsedKey(is_mouse=True, key=_MOUSE_BUTTONS[upper])
    if upper in _WHEELS:
        axis, delta = _WHEELS[upper]
        return ParsedKey(is_wheel=True, wheel_delta=delta, key=axis)

    parts = [p.strip().lower() for p in s.split("+") if p.strip()]
    if not parts:
        return ParsedKey()
    modifiers: list[str] = []
    main = ""
    for p in parts:
        if p in _MOD_NAMES:
            modifiers.append(p)
        else:
            main = p
    if not main:
        main = modifiers[-1]
        modifiers = modifiers[:-1]
    seen = set()
    mods: list[str] = []
    for m in modifiers:
        if m not in seen:
            seen.add(m)
            mods.append(m)
    return ParsedKey(modifiers=tuple(mods), key=main)


# ============================================================
# 模拟发送
# ============================================================


class InputSimulator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        if _HAVE_PYNPUT:
            self._kb = KbController()
            self._mouse = MouseController()
        else:
            self._kb = None  # type: ignore
            self._mouse = None  # type: ignore

    def available(self) -> bool:
        return _HAVE_PYNPUT

    def send(self, key_spec: str, *, mode: str = "single", hold_ms: int = 80,
             repeat: int = 1, interval_ms: int = 50) -> None:
        if not _HAVE_PYNPUT:
            LOGGER.warning("pynput 未安装，跳过按键模拟: %s", key_spec)
            return
        parsed = parse_key(key_spec)
        if parsed.is_wheel:
            self._send_wheel(parsed)
            return
        if parsed.is_mouse:
            self._send_mouse(parsed, hold_ms=hold_ms, mode=mode,
                             repeat=repeat, interval_ms=interval_ms)
            return
        with self._lock:
            try:
                self._press_mods(parsed.modifiers)
                self._kb.press(self._to_pynput_key(parsed.key))
                if mode == "hold":
                    import time
                    time.sleep(max(0.005, hold_ms / 1000.0))
                self._kb.release(self._to_pynput_key(parsed.key))
                self._release_mods(parsed.modifiers)
                if repeat > 1 and mode != "hold":
                    import time
                    for _ in range(repeat - 1):
                        time.sleep(interval_ms / 1000.0)
                        self._press_mods(parsed.modifiers)
                        self._kb.press(self._to_pynput_key(parsed.key))
                        self._kb.release(self._to_pynput_key(parsed.key))
                        self._release_mods(parsed.modifiers)
            except Exception as exc:
                LOGGER.warning("按键 %s 模拟失败: %s", key_spec, exc)

    def _press_mods(self, mods) -> None:
        if not _HAVE_PYNPUT:
            return
        for m in mods:
            self._kb.press(self._to_pynput_key(m))

    def _release_mods(self, mods) -> None:
        if not _HAVE_PYNPUT:
            return
        for m in reversed(list(mods)):
            self._kb.release(self._to_pynput_key(m))

    def _send_mouse(self, parsed: ParsedKey, *, hold_ms: int, mode: str,
                    repeat: int, interval_ms: int) -> None:
        if not _HAVE_PYNPUT or self._mouse is None:
            return
        btn_map = {
            "left": MouseButton.left, "right": MouseButton.right,
            "middle": MouseButton.middle, "x1": MouseButton.x1, "x2": MouseButton.x2,
        }
        btn = btn_map.get(parsed.key)
        if btn is None:
            return
        import time
        for i in range(repeat):
            if i:
                time.sleep(interval_ms / 1000.0)
            self._mouse.press(btn)
            if mode == "hold":
                time.sleep(max(0.005, hold_ms / 1000.0))
            self._mouse.release(btn)

    def _send_wheel(self, parsed: ParsedKey) -> None:
        if not _HAVE_PYNPUT or self._mouse is None:
            return
        if parsed.key == "wheel":
            self._mouse.scroll(0, parsed.wheel_delta)
        else:
            self._mouse.scroll(parsed.wheel_delta, 0)

    def _to_pynput_key(self, name: str):
        if not _HAVE_PYNPUT:
            return None
        if not name:
            return None
        if len(name) == 1 and name.isalnum():
            return name
        norm = _PYNPUT_KEY_MAP.get(name.lower(), name.lower())
        if hasattr(KbKey, norm):
            return getattr(KbKey, norm)
        return name


# ============================================================
# 全局热键
# ============================================================


class GlobalHotkeyManager:
    """基于 `keyboard` 库注册全局热键."""

    def __init__(self) -> None:
        self._handles: list = []
        self._lock = threading.Lock()
        self._registered: list[tuple[str, Callable]] = []

    def register(self, spec: str, callback: Callable[[], None]) -> bool:
        if not _HAVE_KEYBOARD:
            LOGGER.warning("keyboard 库不可用，无法注册全局热键: %s", spec)
            return False
        if not spec:
            return False
        try:
            normalized = spec.lower().replace(" ", "")
            handle = _kb_lib.add_hotkey(normalized, callback, suppress=False)
            with self._lock:
                self._registered.append((spec, callback))
                self._handles.append(handle)
            LOGGER.info("注册全局热键: %s", spec)
            return True
        except Exception as exc:
            LOGGER.warning("注册热键 %s 失败: %s", spec, exc)
            return False

    def unregister_all(self) -> None:
        with self._lock:
            handles = list(self._handles)
            self._handles.clear()
            self._registered.clear()
        if not _HAVE_KEYBOARD:
            return
        for h in handles:
            try:
                _kb_lib.remove_hotkey(h)
            except Exception:
                pass

    def registered(self) -> list[tuple[str, Callable]]:
        with self._lock:
            return list(self._registered)
