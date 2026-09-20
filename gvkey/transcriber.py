"""语音识别抽象层.

定义 Transcriber 接口：喂音频数据，吐「识别的文本 + 能量 + 状态」。
实现两个：
- EnergyTranscriber: 仅做能量检测 + 静音判断；不识别具体文字（兜底用）
- VoskTranscriber: 真实离线 ASR（用户首次启动引导下载模型，可选）

实际命中规则留到 engine.KeywordMatcher 处理。
"""
from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class TranscriptEvent:
    text: str             # 识别出的文本（可能为空字符串）
    is_final: bool        # 是否最终结果
    energy: float = 0.0   # 当前帧能量 0..1
    timestamp: float = field(default_factory=time.time)


@dataclass
class ActivityEvent:
    """语音活动事件（用于唤醒 / 防抖）."""

    state: str            # 'speech_start' / 'speech_end'
    energy: float = 0.0
    timestamp: float = field(default_factory=time.time)


class Transcriber:
    """抽象基类，子类实现 _feed(audio_bytes)."""

    def __init__(self) -> None:
        self.on_transcript: Optional[Callable[[TranscriptEvent], None]] = None
        self.on_activity: Optional[Callable[[ActivityEvent], None]] = None
        self.on_state: Optional[Callable[[str], None]] = None
        self._running = False

    def start(self) -> bool:
        self._running = True
        return True

    def stop(self) -> None:
        self._running = False

    def feed(self, audio_bytes: bytes, energy: float = 0.0) -> None:
        if not self._running:
            return
        self._feed(audio_bytes, energy)

    def _feed(self, audio_bytes: bytes, energy: float) -> None:
        raise NotImplementedError

    def emit_transcript(self, text: str, is_final: bool, energy: float = 0.0) -> None:
        cb = self.on_transcript
        if cb is not None:
            try:
                cb(TranscriptEvent(text=text, is_final=is_final,
                                   energy=energy, timestamp=time.time()))
            except Exception:
                pass

    def emit_activity(self, state: str, energy: float = 0.0) -> None:
        cb = self.on_activity
        if cb is not None:
            try:
                cb(ActivityEvent(state=state, energy=energy,
                                 timestamp=time.time()))
            except Exception:
                pass

    def emit_state(self, state: str) -> None:
        cb = self.on_state
        if cb is not None:
            try:
                cb(state)
            except Exception:
                pass


# ============================================================
# EnergyTranscriber（兜底）
# ============================================================


class EnergyTranscriber(Transcriber):
    """仅基于能量的语音活动检测。

    - 不识别具体文字
    - engine.KeywordMatcher 会根据它抛出的文本做软匹配（用 placeholder + 能量判断）
    当 vosk 不可用或用户只想「按住右键说话」时这个也能跑
    """

    def __init__(self, threshold: float = 0.05, silence_ms: int = 700,
                 speech_min_ms: int = 150, energy_scale: float = 4.0) -> None:
        super().__init__()
        self._threshold = threshold
        self._silence_ms = silence_ms
        self._speech_min_ms = speech_min_ms
        self._energy_scale = energy_scale
        self._lock = threading.Lock()
        self._speaking = False
        self._last_active_at = 0.0
        self._speech_started_at = 0.0

    def set_threshold(self, t: float) -> None:
        with self._lock:
            self._threshold = float(t)

    def _feed(self, audio_bytes: bytes, energy: float) -> None:
        now = time.time()
        scaled = min(1.0, energy * self._energy_scale)
        is_speech = scaled >= self._threshold
        with self._lock:
            if is_speech:
                self._last_active_at = now
                if not self._speaking:
                    self._speaking = True
                    self._speech_started_at = now
                    self.emit_activity("speech_start", energy=scaled)
            else:
                if self._speaking and (now - self._last_active_at) * 1000 >= self._silence_ms:
                    self._speaking = False
                    duration_ms = (now - self._speech_started_at) * 1000
                    self.emit_activity("speech_end", energy=scaled)
                    # 在 speech_end 时把整段「占位文本」抛出：
                    # engine 看到空文本会用最后一次尝试兜底
                    if duration_ms >= self._speech_min_ms:
                        self.emit_transcript("", is_final=True, energy=scaled)


# ============================================================
# VoskTranscriber（真实离线识别，按需导入）
# ============================================================


class VoskTranscriber(Transcriber):
    """基于 Vosk 的离线 ASR."""

    def __init__(self, model_path: str, sample_rate: int = 16000,
                 energy_threshold: float = 0.04, silence_ms: int = 700) -> None:
        super().__init__()
        self._model_path = model_path
        self._sample_rate = sample_rate
        self._energy_threshold = energy_threshold
        self._silence_ms = silence_ms
        self._model = None
        self._recognizer = None
        self._lock = threading.Lock()
        self._speaking = False
        self._last_partial = ""

    def start(self) -> bool:
        try:
            from vosk import Model, KaldiRecognizer, SetLogLevel  # type: ignore
            try:
                SetLogLevel(-1)  # quiet
            except Exception:
                pass
            LOGGER.info("加载 Vosk 模型: %s", self._model_path)
            self._model = Model(self._model_path)
            self._recognizer = KaldiRecognizer(self._model, self._sample_rate)
            self._running = True
            self.emit_state("running")
            return True
        except Exception as exc:
            LOGGER.error("Vosk 模型加载失败: %s", exc)
            self.emit_state("error")
            return False

    def stop(self) -> None:
        super().stop()
        try:
            if self._recognizer is not None:
                # 拿一次 final 文本
                final_json = self._recognizer.FinalResult()
                try:
                    data = json.loads(final_json)
                    text = (data.get("text") or "").strip()
                except Exception:
                    text = ""
                if text:
                    self.emit_transcript(text, is_final=True)
        except Exception:
            pass
        self._recognizer = None
        self._model = None
        self.emit_state("stopped")

    def _feed(self, audio_bytes: bytes, energy: float) -> None:
        if self._recognizer is None:
            return
        if energy < self._energy_threshold and not self._speaking:
            return  # 节省 CPU
        with self._lock:
            try:
                if self._recognizer.AcceptWaveform(audio_bytes):
                    res = json.loads(self._recognizer.Result())
                    text = (res.get("text") or "").strip()
                    if text:
                        self._speaking = True
                        self.emit_transcript(text, is_final=True, energy=energy)
                        self._last_partial = ""
                else:
                    pres = json.loads(self._recognizer.PartialResult())
                    ptxt = (pres.get("partial") or "").strip()
                    if ptxt and ptxt != self._last_partial:
                        self._speaking = True
                        self.emit_transcript(ptxt, is_final=False, energy=energy)
                        self._last_partial = ptxt
            except Exception as exc:
                LOGGER.warning("Vosk feed 异常: %s", exc)


# ============================================================
# 工厂
# ============================================================


def make_transcriber(engine: str, model_path: str = "") -> Transcriber:
    e = (engine or "energy").lower()
    if e == "vosk" and model_path:
        try:
            t = VoskTranscriber(model_path=model_path)
            return t
        except Exception as exc:
            LOGGER.warning("Vosk transcriber 创建失败，回落到 energy: %s", exc)
    return EnergyTranscriber()


VOSK_MODEL_PRESETS = [
    {
        "id": "vosk-model-small-cn-0.22",
        "name": "Vosk 中文 small (≈42MB, 推荐)",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip",
        "size_mb": 42,
        "note": "中文识别，日常使用足够",
    },
    {
        "id": "vosk-model-cn-0.22",
        "name": "Vosk 中文 large (≈1.3GB)",
        "url": "https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip",
        "size_mb": 1300,
        "note": "高精度，需大磁盘",
    },
    {
        "id": "vosk-model-small-en-us-0.15",
        "name": "Vosk 英文 small (≈40MB)",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "size_mb": 40,
        "note": "备用英文识别",
    },
]
