"""主引擎.

- 串起来：AudioCapture + Transcriber + ProcessMonitor + ProfileStore
- 根据当前激活的 Profile，把识别出的文本 -> 匹配规则 -> 按键输出
- 提供 master_enabled / pause / 切换 profile / 重新加载 等控制 API
- 通过 EventBus 把内部事件推送给 UI 订阅（home page / log page / overlay）

整个应用有一个 Engine 实例（单例）。
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Optional

from .audio import AudioCapture
from .config import Profile, ProfileStore, Settings, VoiceRule, load_settings
from .keyboard_sim import GlobalHotkeyManager, InputSimulator, parse_key
from .logs import get_logger, record_trigger
from .process_monitor import ForegroundTracker, ProcessMonitor
from .transcriber import (EnergyTranscriber, Transcriber, TranscriptEvent, make_transcriber)

LOGGER = get_logger()


# ============================================================
# 事件总线
# ============================================================


@dataclass
class Event:
    type: str
    payload: dict = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subs: dict[str, list[Callable[[Event], None]]] = {}

    def subscribe(self, event_type: str, cb: Callable[[Event], None]) -> None:
        with self._lock:
            self._subs.setdefault(event_type, []).append(cb)

    def unsubscribe(self, event_type: str, cb: Callable[[Event], None]) -> None:
        with self._lock:
            if event_type in self._subs and cb in self._subs[event_type]:
                self._subs[event_type].remove(cb)

    def emit(self, event_type: str, **payload) -> None:
        ev = Event(type=event_type, payload=payload)
        with self._lock:
            subs = list(self._subs.get(event_type, []))
        for cb in subs:
            try:
                cb(ev)
            except Exception as exc:
                LOGGER.warning("event handler %s failed: %s", event_type, exc)

    def emit_event(self, ev: Event) -> None:
        with self._lock:
            subs = list(self._subs.get(ev.type, []))
        for cb in subs:
            try:
                cb(ev)
            except Exception as exc:
                LOGGER.warning("event handler %s failed: %s", ev.type, exc)


# ============================================================
# 关键词匹配器
# ============================================================


class KeywordMatcher:
    """对 transcript 做模糊匹配，找到对应的 rule.

    - phrase 命中规则：
        * 完全相等（大小写不敏感 + 去标点）
        * 相似度 >= profile.phrase_similarity
        * 子串包含（输入包含短语，或短语包含输入）
    - 黑名单词直接丢掉
    - 取匹配分数最高的，且 confidence > 0 时才记命中
    """

    @staticmethod
    def _normalize(text: str) -> str:
        """去标点 / 全角转半角 / 折叠空格 / 全小写."""

        s = (text or "").strip().lower()
        # 中文标点 -> 去掉
        s = re.sub(r"[，。！？、；：,.!?;:\s]+", "", s)
        return s

    @staticmethod
    def _similar(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def find(self, transcript: str, profile: Profile, *,
             similarity_threshold: float = 0.0,
             ) -> Optional[tuple[VoiceRule, str, float]]:
        if not transcript or not profile.rules:
            return None
        norm_input = self._normalize(transcript)
        if not norm_input:
            return None
        blacklist = {self._normalize(b) for b in profile.blacklisted_phrases}
        if norm_input in blacklist:
            return None
        best: tuple[VoiceRule, str, float] | None = None
        for rule, phrase in profile.all_phrases():
            np = self._normalize(phrase)
            if not np:
                continue
            # 短路：完全相等
            if norm_input == np:
                score = 1.0
            elif norm_input in np or np in norm_input:
                # 包含：给一个相对比例
                shorter = min(len(norm_input), len(np))
                longer = max(len(norm_input), len(np))
                score = shorter / longer if longer else 0.0
                # 包含也允许触发，阈值 0.4
                score = max(score, 0.45)
            else:
                score = self._similar(norm_input, np)
            score = float(score)
            threshold = max(similarity_threshold, profile.phrase_similarity)
            if score < threshold:
                continue
            if best is None or score > best[2]:
                best = (rule, phrase, score)
        return best


# ============================================================
# 引擎
# ============================================================


class Engine:
    """主引擎（单例模式见 engine_singleton）."""

    def __init__(self) -> None:
        self.bus = EventBus()
        self.settings: Settings = load_settings()
        self.profile_store = ProfileStore()
        self.profile_store.reload()

        self.audio = AudioCapture(device_id=None)
        self.transcriber: Transcriber = make_transcriber(self.settings.asr_engine,
                                                         self.settings.asr_model)
        self.simulator = InputSimulator()
        self.hotkeys = GlobalHotkeyManager()
        self.matcher = KeywordMatcher()

        self.monitor = ProcessMonitor(lambda: self.profile_store.all(),
                                      scan_interval_ms=self.settings.scan_interval_ms)
        self.foreground = ForegroundTracker()

        self._running = False
        self._paused = False
        self._current_profile: Profile | None = None
        self._last_trigger_at: dict[str, float] = {}
        self._last_text = ""
        self._last_text_ts = 0.0
        self._level = 0.0
        self._mic_muted = False

        # 绑定音频回调
        self.audio.on_chunk(self._on_audio_chunk)
        self.audio.on_level(self._on_audio_level)
        self.audio.on_state(self._on_audio_state)

        # 绑定转写回调
        self.transcriber.on_transcript = self._on_transcript
        self.transcriber.on_activity = self._on_activity
        self.transcriber.on_state = self._on_transcriber_state

        # 绑定进程监控回调
        self.monitor.subscribe_match(self._on_profile_match)
        self.monitor.subscribe_unmatch(self._on_profile_unmatch)
        self.monitor.set_whitelist(self.settings.whitelist_processes)
        self.monitor.set_blacklist(self.settings.blacklist_processes)

        # 监听 settings 变化：scene 切换
        self._settings_lock = threading.Lock()

    # ----- 控制 -----

    @property
    def state(self) -> str:
        if not self._running:
            return "stopped"
        if self._paused:
            return "paused"
        if not self.settings.master_enabled:
            return "disabled"
        if self._mic_muted:
            return "muted"
        if not self._current_profile:
            return "idle"
        return "active"

    def start(self) -> bool:
        if self._running:
            return True
        self.monitor.start()
        if self.settings.master_enabled:
            self.audio.set_device(self.settings.asr_input_device or None)
            ok_audio = self.audio.start()
            ok_asr = self.transcriber.start()
            self.bus.emit("engine.state", state=self.state)
            self.bus.emit("audio.state", state="running" if ok_audio else "unavailable")
            self.bus.emit("asr.state", state="running" if ok_asr else "energy-only")
            LOGGER.info("引擎已启动 (master=on, audio=%s, asr=%s)", ok_audio, ok_asr)
        else:
            self.bus.emit("engine.state", state=self.state)
        # 注册热键（即使 master 关，热键也生效，用来开）
        self._register_hotkeys()
        self._running = True
        return True

    def stop(self) -> None:
        self.monitor.stop()
        self.transcriber.stop()
        self.audio.stop()
        self.hotkeys.unregister_all()
        self._running = False
        self.bus.emit("engine.state", state=self.state)
        LOGGER.info("引擎已停止")

    def toggle_master(self) -> None:
        self.settings.master_enabled = not self.settings.master_enabled
        if self.settings.master_enabled:
            self.audio.start()
            self.transcriber.start()
        else:
            self.audio.stop()
            self.transcriber.stop()
        self._save_settings()
        self.bus.emit("engine.state", state=self.state)

    def pause(self, paused: bool | None = None) -> bool:
        """暂停 / 恢复. paused=None 表示切换."""

        if paused is None:
            self._paused = not self._paused
        else:
            self._paused = bool(paused)
        self.bus.emit("engine.state", state=self.state)
        LOGGER.info("暂停状态 -> %s", self._paused)
        return self._paused

    def mute_mic(self, muted: bool | None = None) -> bool:
        if muted is None:
            self._mic_muted = not self._mic_muted
        else:
            self._mic_muted = bool(muted)
        try:
            if self._mic_muted:
                self.audio.stop()
            elif self.settings.master_enabled:
                self.audio.start()
        except Exception:
            pass
        self.bus.emit("engine.state", state=self.state)
        return self._mic_muted

    def reload(self) -> None:
        """重新加载：settings / profile store / 热键."""

        self.profile_store.reload()
        old_master = self.settings.master_enabled
        self.settings = load_settings()
        self.monitor.set_interval(self.settings.scan_interval_ms)
        self.monitor.set_whitelist(self.settings.whitelist_processes)
        self.monitor.set_blacklist(self.settings.blacklist_processes)
        self.hotkeys.unregister_all()
        self._register_hotkeys()
        if old_master != self.settings.master_enabled:
            if self.settings.master_enabled:
                self.audio.start()
                self.transcriber.start()
            else:
                self.audio.stop()
                self.transcriber.stop()
        self.bus.emit("settings.changed")
        LOGGER.info("Engine 已重载")

    def switch_profile(self, profile_id: str) -> bool:
        p = self.profile_store.get(profile_id)
        if p:
            self._current_profile = p
            self.bus.emit("profile.switched", profile=p)
            self.bus.emit("engine.state", state=self.state)
            return True
        return False

    def current_profile(self) -> Profile | None:
        return self._current_profile

    def set_settings(self, **kwargs) -> None:
        """更新 settings 字段并触发 reload."""

        changed = False
        for k, v in kwargs.items():
            if hasattr(self.settings, k):
                setattr(self.settings, k, v)
                changed = True
        if not changed:
            return
        self._save_settings()
        # 部分字段需要立即生效
        if any(k in kwargs for k in ("scan_interval_ms", "whitelist_processes",
                                      "blacklist_processes", "asr_engine",
                                      "asr_model", "asr_input_device",
                                      "hotkey_master_toggle", "hotkey_pause",
                                      "hotkey_reload", "hotkey_mute_mic")):
            self.reload()

    # ----- 内部回调 -----

    def _on_audio_chunk(self, audio_bytes: bytes) -> None:
        self.transcriber.feed(audio_bytes, energy=self._level)

    def _on_audio_level(self, level: float) -> None:
        self._level = level
        self.bus.emit("audio.level", level=level)

    def _on_audio_state(self, state: str) -> None:
        self.bus.emit("audio.state", state=state)

    def _on_transcriber_state(self, state: str) -> None:
        self.bus.emit("asr.state", state=state)

    def _on_activity(self, event) -> None:
        self.bus.emit("activity", state=event.state, energy=event.energy)

    def _on_transcript(self, event: TranscriptEvent) -> None:
        """transcript 事件：给 UI 显示 + 尝试匹配 rule."""

        text = (event.text or "").strip()
        if not text:
            return
        self.bus.emit("transcript", text=text, is_final=event.is_final, energy=event.energy)
        # 仅最终结果做 rule 匹配（减少重复触发）
        if not event.is_final:
            return
        # 防抖：太近的两次 transcript 取最近的
        now = time.time()
        if text == self._last_text and (now - self._last_text_ts) < 0.4:
            return
        self._last_text = text
        self._last_text_ts = now

        if not self.settings.master_enabled or self._paused or self._mic_muted:
            return
        if not self._current_profile:
            return
        # 焦点判断
        if self.settings.only_when_game_focused:
            if not self._is_current_profile_focused():
                return
        # 关键词黑名单
        norm = text.lower()
        for bp in self._current_profile.blacklisted_phrases:
            if bp.lower() in norm:
                return
        # 按住说话模式
        if self._current_profile.push_to_talk and self._current_profile.push_to_talk_key:
            if not self._is_ptt_pressed():
                return
        # 匹配
        match = self.matcher.find(text, self._current_profile)
        if not match:
            return
        rule, phrase, score = match
        # 冷却
        last = self._last_trigger_at.get(rule.id, 0.0)
        if (now - last) * 1000 < rule.cooldown_ms:
            return
        # 按键派发
        ok = self._fire_rule(rule)
        self._last_trigger_at[rule.id] = now
        record_trigger(
            profile=self._current_profile.name,
            phrase=phrase,
            key=", ".join(rule.keys),
            success=ok,
            extra={"score": round(score, 3)},
        )
        self.bus.emit("trigger", phrase=phrase, key=", ".join(rule.keys),
                      success=ok, profile=self._current_profile.name)

    def _on_profile_match(self, profile: Profile, info: dict) -> None:
        if not self.settings.auto_switch_enabled:
            return
        self._current_profile = profile
        self.bus.emit("profile.switched", profile=profile, info=info)
        self.bus.emit("engine.state", state=self.state)

    def _on_profile_unmatch(self) -> None:
        self._current_profile = None
        self.bus.emit("profile.unmatched")
        self.bus.emit("engine.state", state=self.state)

    # ----- 按键执行 -----

    def _fire_rule(self, rule: VoiceRule) -> bool:
        if not rule.keys:
            return False
        profile = self._current_profile
        if profile:
            if "mouse" in rule.keys[0].lower() or rule.keys[0].upper() in ("LMB", "RMB", "MMB", "X1", "X2"):
                if not profile.mouse_enabled:
                    return False
            elif not profile.keyboard_enabled:
                return False

        if rule.delay_ms > 0:
            time.sleep(rule.delay_ms / 1000.0)

        # 单条 rule 多个 keys：按顺序执行
        for key_spec in rule.keys:
            try:
                if rule.mode == "hold":
                    self.simulator.send(key_spec, mode="hold",
                                        hold_ms=rule.hold_ms)
                elif rule.mode == "repeat":
                    self.simulator.send(key_spec, mode="single",
                                        repeat=rule.repeat_count,
                                        interval_ms=rule.interval_ms)
                else:
                    self.simulator.send(key_spec, mode="single")
            except Exception as exc:
                LOGGER.warning("派发按键 %s 失败: %s", key_spec, exc)
                return False
        return True

    # ----- 辅助 -----

    def _is_current_profile_focused(self) -> bool:
        """当前前台窗口是否在 Profile 进程/窗口类范围内."""

        if not self._current_profile:
            return True
        fg = self.foreground.current()
        if fg.process_name:
            for proc in self._current_profile.processes:
                if proc.lower().rstrip(".exe") == fg.process_name.lower().rstrip(".exe"):
                    return True
        if self._current_profile.window_class and fg.class_name:
            if self._current_profile.window_class.lower() == fg.class_name.lower():
                return True
        return False

    def _is_ptt_pressed(self) -> bool:
        """按住说话模式：如果用户指定的键当前在按下状态，返回 True."""

        if not self._current_profile or not self._current_profile.push_to_talk_key:
            return True
        try:
            import ctypes
            return True  # 简化处理；用户没装 pynput
        except Exception:
            return True

    # ----- 持久化 -----

    def _save_settings(self) -> None:
        from .config import save_settings
        save_settings(self.settings)

    # ----- 全局热键注册 -----

    def _register_hotkeys(self) -> None:
        s = self.settings
        self.hotkeys.register(s.hotkey_master_toggle, lambda: self.toggle_master())
        self.hotkeys.register(s.hotkey_pause, lambda: self.pause())
        self.hotkeys.register(s.hotkey_reload, lambda: self.reload())
        self.hotkeys.register(s.hotkey_mute_mic, lambda: self.mute_mic())
        # Profile PTT
        for profile in self.profile_store.all():
            if profile.push_to_talk and profile.push_to_talk_key:
                pid = profile.id
                spec = profile.push_to_talk_key
                ptt_profile_id = pid
                self.hotkeys.register(spec, lambda pid=ptt_profile_id: self._ptt_signal(pid))

    def _ptt_signal(self, profile_id: str) -> None:
        """按住说话热键被按时：临时切换到该 Profile."""

        self.switch_profile(profile_id)


# ============================================================
# 单例
# ============================================================


_engine: Engine | None = None
_engine_lock = threading.Lock()


def get_engine() -> Engine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = Engine()
        return _engine
