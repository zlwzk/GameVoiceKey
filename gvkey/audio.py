"""音频采集.

- 用 sounddevice 在默认输入设备上以 16kHz 采样（Vosk 期望）
- 输出 audio chunk 给消费者（Transcriber）通过回调
- 同时把能量（绝对振幅 / RMS）报告给 UI 用于波形可视化
"""
from __future__ import annotations

import math
import queue
import threading
import time
from typing import Callable, Optional

import numpy as np

try:
    import sounddevice as sd  # type: ignore
    _HAVE_SD = True
except Exception:
    sd = None  # type: ignore
    _HAVE_SD = False

from .logs import get_logger

LOGGER = get_logger()


def list_input_devices() -> list[dict]:
    if not _HAVE_SD:
        return []
    out: list[dict] = []
    try:
        devices = sd.query_devices()
    except Exception:
        return []
    for idx, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            out.append({
                "id": idx,
                "name": d.get("name", ""),
                "channels": d.get("max_input_channels", 0),
                "host_api": d.get("hostapi", 0),
            })
    return out


def default_input_device_id() -> Optional[int]:
    if not _HAVE_SD:
        return None
    try:
        return int(sd.default.device[0])
    except Exception:
        try:
            return int(sd.query_devices(kind="input")["index"])
        except Exception:
            return None


def list_output_devices() -> list[dict]:
    """列出可用的播放设备（扬声器 / 耳机），供扬声器测试选择。"""

    if not _HAVE_SD:
        return []
    out: list[dict] = []
    try:
        devices = sd.query_devices()
    except Exception:
        return []
    for idx, d in enumerate(devices):
        if d.get("max_output_channels", 0) > 0:
            out.append({
                "id": idx,
                "name": d.get("name", ""),
                "channels": d.get("max_output_channels", 0),
                "host_api": d.get("hostapi", 0),
            })
    return out


def default_output_device_id() -> Optional[int]:
    if not _HAVE_SD:
        return None
    try:
        return int(sd.default.device[1])
    except Exception:
        try:
            return int(sd.query_devices(kind="output")["index"])
        except Exception:
            return None


def play_test_tone(*, device: Optional[int] = None, frequency: int = 660,
                   duration_ms: int = 600, channel: str = "both",
                   volume: float = 0.32) -> bool:
    """播放一段测试音（用于扬声器 / 声道测试）。

    channel: ``left`` / ``right`` / ``both`` —— 用来验证左右声道接反没接反。

    波形由 numpy 现场合成，不依赖任何音频素材文件。
    ``sd.play`` 是非阻塞的，调用方需要自己在合适时机 ``stop_test_tone()``。
    """

    if not _HAVE_SD:
        return False

    duration_ms = max(80, min(5000, int(duration_ms)))
    rate = 44100
    count = int(rate * duration_ms / 1000.0)
    if count <= 0:
        return False

    try:
        t = np.linspace(0.0, duration_ms / 1000.0, count, endpoint=False)
        wave = np.sin(2.0 * math.pi * float(frequency) * t) * float(volume)
        # 淡入淡出各 20ms，避免起止爆音
        fade = min(int(rate * 0.02), count // 4)
        if fade > 0:
            ramp = np.linspace(0.0, 1.0, fade)
            wave[:fade] = wave[:fade] * ramp
            wave[-fade:] = wave[-fade:] * ramp[::-1]

        stereo = np.zeros((count, 2), dtype="float32")
        if channel in ("left", "both"):
            stereo[:, 0] = wave
        if channel in ("right", "both"):
            stereo[:, 1] = wave

        sd.stop()
        sd.play(stereo, rate, device=device)
        return True
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("播放测试音失败: %s", exc)
        return False


def stop_test_tone() -> None:
    """立刻停止正在播放的测试音。"""

    if not _HAVE_SD:
        return
    try:
        sd.stop()
    except Exception:  # noqa: BLE001
        pass


class AudioCapture:
    """单声道 16kHz 音频流，回调给消费者。

    usage:
        cap = AudioCapture()
        cap.on_chunk(cb_on_chunk)
        cap.on_level(cb_on_level)
        cap.start()
        ...
        cap.stop()
    """

    SAMPLE_RATE = 16000
    BLOCK_SIZE = 4000  # ~250ms at 16kHz, 给 Vosk/Energy 都有缓冲
    DTYPE = "int16"

    def __init__(self, device_id: Optional[int] = None) -> None:
        self._device_id = device_id if device_id is not None else default_input_device_id()
        self._stream: Optional["sd.InputStream"] = None  # type: ignore
        self._chunks: list[np.ndarray] = []
        self._chunk_cb: Optional[Callable[[bytes], None]] = None
        self._level_cb: Optional[Callable[[float], None]] = None
        self._state_cb: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()
        self._last_level_ts = 0.0
        self._level = 0.0

    def on_chunk(self, cb: Callable[[bytes], None]) -> None:
        self._chunk_cb = cb

    def on_level(self, cb: Callable[[float], None]) -> None:
        self._level_cb = cb

    def on_state(self, cb: Callable[[str], None]) -> None:
        self._state_cb = cb

    def is_running(self) -> bool:
        return self._stream is not None

    def set_device(self, device_id: Optional[int]) -> None:
        self._device_id = device_id

    def start(self) -> bool:
        if not _HAVE_SD:
            self._emit_state("unavailable")
            LOGGER.warning("sounddevice 未安装，音频采集不可用")
            return False
        if self._stream is not None:
            return True
        try:
            self._stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_SIZE,
                dtype=self.DTYPE,
                channels=1,
                device=self._device_id,
                callback=self._on_audio,
            )
            self._stream.start()
            self._emit_state("running")
            LOGGER.info("音频采集已启动 (device=%s)", self._device_id)
            return True
        except Exception as exc:
            LOGGER.error("启动音频采集失败: %s", exc)
            self._emit_state("error")
            self._stream = None
            return False

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                LOGGER.warning("关闭音频流异常: %s", exc)
            self._stream = None
            self._emit_state("stopped")
            LOGGER.info("音频采集已停止")

    def _on_audio(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        if status:
            LOGGER.debug("sounddevice status: %s", status)
        try:
            audio_int16 = np.asarray(indata, dtype=np.int16).flatten()
            audio_bytes = audio_int16.tobytes()
            # 能量：RMS / 32768 → 0..1（粗略）
            rms = float(np.sqrt(np.mean(np.square(audio_int16.astype(np.float32) / 32768.0))))
            peak = float(np.max(np.abs(audio_int16.astype(np.float32) / 32768.0))
                         if audio_int16.size else 0.0)
            level = max(rms, peak * 0.7)  # 给 peak 一个相对权重
            now = time.time()
            if now - self._last_level_ts > 0.05 and self._level_cb is not None:
                self._last_level_ts = now
                try:
                    self._level_cb(min(1.0, max(0.0, level)))
                except Exception:
                    pass
            cb = self._chunk_cb
            if cb is not None:
                cb(audio_bytes)
        except Exception as exc:
            LOGGER.warning("音频回调异常: %s", exc)

    def _emit_state(self, state: str) -> None:
        cb = self._state_cb
        if cb is not None:
            try:
                cb(state)
            except Exception:
                pass
