"""启动向导：麦克风和扬声器测试.

在主窗口出现**之前**跑一遍设备检查，让用户在真正使用前就确认：

1. 麦克风收得到声音（看得见的实时电平条 —— 不需要懂什么技术）
2. 扬声器放得出声音，且左右声道没接反
3. 顺便把选好的设备写进 settings，主程序直接生效

任何一步都可以「跳过」，引导流程绝不阻塞用户。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
                                QProgressBar, QPushButton, QStackedWidget,
                                QVBoxLayout, QWidget)

from .. import __app_name__, __version__
from ..audio import (default_input_device_id, default_output_device_id,
                      list_input_devices, list_output_devices, play_test_tone,
                      stop_test_tone)
from ..config import Settings, save_settings
from ..logs import get_logger
from .theme import CARD_PADDING

LOGGER = get_logger()

# 电平超过这个值就认为「听到声音了」
_VOICE_THRESHOLD = 0.10
# 需要连续多少帧超过阈值才算通过（避免误判）
_VOICE_FRAMES = 3


class MicProbe(QObject):
    """轻量麦克风电平探针：只测音量，不做识别。

    向导独立于引擎运行（此时引擎还没启动），所以自己开一条音频流。
    """

    level = Signal(float)
    failed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._stream = None
        self._device: Optional[int] = None

    @property
    def running(self) -> bool:
        return self._stream is not None

    def start(self, device: Optional[int]) -> bool:
        self.stop()
        try:
            import sounddevice as sd
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"音频库不可用：{exc}")
            return False

        self._device = device
        try:
            def _callback(indata, frames, time_info, status) -> None:  # noqa: ARG001
                try:
                    import numpy as np

                    if len(indata) == 0:
                        return
                    rms = float(np.sqrt(np.mean(np.square(indata, dtype="float64"))))
                    # 放大到 0~1 便于显示；人声正常说话大约落在 0.1~0.5
                    self.level.emit(min(1.0, rms * 6.0))
                except Exception:  # noqa: BLE001
                    pass

            self._stream = sd.InputStream(
                device=device,
                channels=1,
                samplerate=16000,
                blocksize=1600,
                dtype="float32",
                callback=_callback,
            )
            self._stream.start()
            return True
        except Exception as exc:  # noqa: BLE001
            self._stream = None
            self.failed.emit(str(exc))
            LOGGER.warning("打开麦克风失败 (device=%s): %s", device, exc)
            return False

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass


class DeviceTestWizard(QDialog):
    """麦克风 / 扬声器测试向导。"""

    STEP_COUNT = 4

    def __init__(self, settings: Settings, *, first_run: bool = True,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.first_run = first_run
        self._step = 0
        self._voice_hits = 0
        self._mic_ok = False
        self._speaker_ok = False
        self._peak = 0.0
        self.skipped = False

        self.setWindowTitle(f"{__app_name__} 设备检测" if first_run else "设备检测")
        self.setModal(True)
        self.setMinimumSize(660, 480)

        self._probe = MicProbe(self)
        self._probe.level.connect(self._on_level)
        self._probe.failed.connect(self._on_probe_failed)

        self._decay = QTimer(self)
        self._decay.setInterval(60)
        self._decay.timeout.connect(self._decay_level)

        self._build()
        self._go(0)

    # ============================================================
    # 构建
    # ============================================================

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(14)

        self._lbl_step = QLabel("")
        self._lbl_step.setObjectName("CardHint")
        root.addWidget(self._lbl_step)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._page_welcome())
        self._stack.addWidget(self._page_mic())
        self._stack.addWidget(self._page_speaker())
        self._stack.addWidget(self._page_done())
        root.addWidget(self._stack, 1)

        line = QFrame()
        line.setObjectName("Divider")
        line.setFixedHeight(1)
        root.addWidget(line)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self._btn_skip = QPushButton("跳过这一步")
        self._btn_skip.setObjectName("Ghost")
        self._btn_skip.clicked.connect(self._on_skip)
        bar.addWidget(self._btn_skip)

        bar.addStretch(1)

        self._btn_back = QPushButton("上一步")
        self._btn_back.setObjectName("Ghost")
        self._btn_back.clicked.connect(lambda: self._go(self._step - 1))
        bar.addWidget(self._btn_back)

        self._btn_next = QPushButton("下一步")
        self._btn_next.setObjectName("Primary")
        self._btn_next.setMinimumWidth(120)
        self._btn_next.clicked.connect(self._on_next)
        bar.addWidget(self._btn_next)
        root.addLayout(bar)

    def _card(self, title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        box.setSpacing(10)
        lbl = QLabel(title)
        lbl.setObjectName("PageTitle")
        box.addWidget(lbl)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("PageHint")
            sub.setWordWrap(True)
            box.addWidget(sub)
        return card, box

    # ---------- 第 1 步：欢迎 ----------

    def _page_welcome(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        card, box = self._card(
            "先花 30 秒确认一下声音设备" if self.first_run else "重新检测声音设备",
            f"{__app_name__} 靠麦克风听你的指令、再模拟按键，所以麦克风能不能收到声音是"
            "最关键的一步。下面两张卡片会带你分别测试麦克风和扬声器。",
        )
        for text in (
            "① 麦克风：对着话筒说句话，能看见电平条跳动就算通过",
            "② 扬声器：点一下测试音，确认左右声道没接反",
            "③ 选好的设备会自动保存，之后不用再配",
        ):
            item = QLabel(text)
            item.setObjectName("Value")
            item.setWordWrap(True)
            box.addWidget(item)
        lay.addWidget(card)

        tip, tbox = self._card("小提示")
        for text in (
            "· 用笔记本内置麦克风也能玩，但外接耳机麦识别更准",
            "· 游戏里如果听不到队友声音，检查一下是否被独占模式占用了设备",
            "· 随时可以在「高级设置 → 声音设备」里重新检测",
        ):
            lbl = QLabel(text)
            lbl.setObjectName("CardHint")
            lbl.setWordWrap(True)
            tbox.addWidget(lbl)
        lay.addWidget(tip)
        lay.addStretch(1)
        return page

    # ---------- 第 2 步：麦克风 ----------

    def _page_mic(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        card, box = self._card(
            "麦克风测试",
            "请用平常说话的语调说一句，例如「放大招」——看下面的电平条会不会动。",
        )

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("输入设备"))
        self._cmb_mic = QComboBox()
        self._cmb_mic.currentIndexChanged.connect(self._on_mic_device_changed)
        row.addWidget(self._cmb_mic, 1)
        btn_rescan = QPushButton("重新扫描")
        btn_rescan.setObjectName("Ghost")
        btn_rescan.clicked.connect(self._reload_mic_devices)
        row.addWidget(btn_rescan)
        box.addLayout(row)

        self._bar_level = QProgressBar()
        self._bar_level.setRange(0, 100)
        self._bar_level.setValue(0)
        self._bar_level.setTextVisible(False)
        self._bar_level.setFixedHeight(18)
        box.addWidget(self._bar_level)

        self._lbl_mic_state = QLabel("等待声音…")
        self._lbl_mic_state.setObjectName("StatusWarn")
        box.addWidget(self._lbl_mic_state)

        self._lbl_mic_tip = QLabel("")
        self._lbl_mic_tip.setObjectName("CardHint")
        self._lbl_mic_tip.setWordWrap(True)
        box.addWidget(self._lbl_mic_tip)

        lay.addWidget(card)
        lay.addStretch(1)
        return page

    # ---------- 第 3 步：扬声器 ----------

    def _page_speaker(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        card, box = self._card(
            "扬声器测试",
            "依次点三个按钮。正常情况：点左声道只有左边响，点右声道只有右边响。",
        )

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("输出设备"))
        self._cmb_spk = QComboBox()
        self._cmb_spk.currentIndexChanged.connect(self._on_spk_device_changed)
        row.addWidget(self._cmb_spk, 1)
        btn_rescan = QPushButton("重新扫描")
        btn_rescan.setObjectName("Ghost")
        btn_rescan.clicked.connect(self._reload_spk_devices)
        row.addWidget(btn_rescan)
        box.addLayout(row)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        for text, channel in (("◀ 左声道", "left"), ("双声道", "both"), ("右声道 ▶", "right")):
            b = QPushButton(text)
            b.clicked.connect(lambda _checked=False, c=channel: self._play(c))
            btns.addWidget(b)
        box.addLayout(btns)

        self._lbl_spk_state = QLabel("点上面的按钮试试")
        self._lbl_spk_state.setObjectName("CardHint")
        self._lbl_spk_state.setWordWrap(True)
        box.addWidget(self._lbl_spk_state)

        ask = QLabel("听到声音了吗？")
        ask.setObjectName("Value")
        box.addWidget(ask)

        yn = QHBoxLayout()
        yn.setSpacing(10)
        btn_yes = QPushButton("听到了")
        btn_yes.setObjectName("Primary")
        btn_yes.clicked.connect(lambda: self._answer_speaker(True))
        yn.addWidget(btn_yes)
        btn_no = QPushButton("没听到")
        btn_no.setObjectName("Ghost")
        btn_no.clicked.connect(lambda: self._answer_speaker(False))
        yn.addWidget(btn_no)
        yn.addStretch(1)
        box.addLayout(yn)

        lay.addWidget(card)
        lay.addStretch(1)
        return page

    # ---------- 第 4 步：完成 ----------

    def _page_done(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        card, box = self._card("准备就绪", "设备检查完成，现在可以开始用了。")
        self._lbl_summary_mic = QLabel("")
        self._lbl_summary_mic.setObjectName("Value")
        self._lbl_summary_mic.setWordWrap(True)
        box.addWidget(self._lbl_summary_mic)
        self._lbl_summary_spk = QLabel("")
        self._lbl_summary_spk.setObjectName("Value")
        self._lbl_summary_spk.setWordWrap(True)
        box.addWidget(self._lbl_summary_spk)

        nxt = QLabel("下一步：在首页点「选择当前游玩的游戏」，挑中你正在玩的进程，"
                     "就能马上进去配语音指令了。")
        nxt.setObjectName("CardHint")
        nxt.setWordWrap(True)
        box.addWidget(nxt)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    # ============================================================
    # 步骤流转
    # ============================================================

    def _go(self, index: int) -> None:
        index = max(0, min(self.STEP_COUNT - 1, index))

        # 离开麦克风页就关掉音频流，别占着设备
        if self._step == 1 and index != 1:
            self._probe.stop()
            self._decay.stop()

        self._step = index
        self._stack.setCurrentIndex(index)
        self._lbl_step.setText(f"第 {index + 1} 步 / 共 {self.STEP_COUNT} 步")

        if index == 1:
            self._reload_mic_devices()
        elif index == 2:
            self._reload_spk_devices()
        elif index == 3:
            self._refresh_summary()

        self._btn_back.setEnabled(index > 0)
        self._btn_skip.setVisible(index in (1, 2))
        self._btn_next.setText("开始使用" if index == self.STEP_COUNT - 1 else "下一步")

    def _on_next(self) -> None:
        if self._step >= self.STEP_COUNT - 1:
            self._finish()
            return
        self._go(self._step + 1)

    def _on_skip(self) -> None:
        # 跳过当前测试步骤，但向导的其余部分照常走
        if self._step == 1:
            self._mic_ok = False
            self._probe.stop()
            self._decay.stop()
        elif self._step == 2:
            self._speaker_ok = False
            stop_test_tone()
        self._go(self._step + 1)

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        self._teardown()
        super().closeEvent(event)

    def _teardown(self) -> None:
        self._probe.stop()
        self._decay.stop()
        stop_test_tone()

    def _finish(self) -> None:
        self._teardown()
        self._save()
        self.accept()

    def _save(self) -> None:
        s = self.settings
        mic = self._cmb_mic.currentData() if hasattr(self, "_cmb_mic") else None
        spk = self._cmb_spk.currentData() if hasattr(self, "_cmb_spk") else None
        # 设置字段是 str，而控件 itemData 是 int —— 统一转成 str 存，读回时再比字符串
        if mic is not None and self._mic_ok:
            s.asr_input_device = str(mic)
        if spk is not None and self._speaker_ok:
            s.asr_output_device = str(spk)
        s.setup_wizard_done = True
        s.setup_wizard_version = __version__
        try:
            save_settings(s)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("保存设备设置失败: %s", exc)

    # ============================================================
    # 麦克风
    # ============================================================

    def _reload_mic_devices(self) -> None:
        self._cmb_mic.blockSignals(True)
        self._cmb_mic.clear()
        devices = list_input_devices()
        current = self.settings.asr_input_device
        for dev in devices:
            label = f"{dev['name']}（{dev['channels']} 通道）"
            self._cmb_mic.addItem(label, dev["id"])
        self._cmb_mic.blockSignals(False)

        if not devices:
            self._lbl_mic_state.setObjectName("StatusBad")
            self._lbl_mic_state.setText("✘ 没有找到任何麦克风设备")
            self._lbl_mic_tip.setText("请检查设备是否插好，或稍后在「高级设置 → 声音设备」里重试。")
            self._restyle(self._lbl_mic_state)
            return

        # 优先恢复用户上次选的设备
        picked = -1
        if current not in (None, ""):
            for i in range(self._cmb_mic.count()):
                if str(self._cmb_mic.itemData(i)) == str(current):
                    picked = i
                    break
        if picked < 0:
            default_id = default_input_device_id()
            for i in range(self._cmb_mic.count()):
                if self._cmb_mic.itemData(i) == default_id:
                    picked = i
                    break
        self._cmb_mic.setCurrentIndex(max(0, picked))
        self._start_probe()

    def _on_mic_device_changed(self) -> None:
        self._voice_hits = 0
        self._start_probe()

    def _start_probe(self) -> None:
        device = self._cmb_mic.currentData()
        self._lbl_mic_state.setObjectName("StatusWarn")
        if self._probe.start(device):
            self._lbl_mic_state.setText("等待声音…")
            self._lbl_mic_tip.setText("")
            self._decay.start()
        self._restyle(self._lbl_mic_state)

    def _on_probe_failed(self, message: str) -> None:
        self._lbl_mic_state.setObjectName("StatusBad")
        self._lbl_mic_state.setText("✘ 打不开这个麦克风")
        self._lbl_mic_tip.setText(f"换一个设备试试。系统返回：{message}")
        self._restyle(self._lbl_mic_state)

    def _on_level(self, level: float) -> None:
        self._peak = max(self._peak, level)
        self._bar_level.setValue(int(min(1.0, self._peak) * 100))
        if level >= _VOICE_THRESHOLD:
            self._voice_hits += 1
            if self._voice_hits >= _VOICE_FRAMES and not self._mic_ok:
                self._mic_ok = True
                self._lbl_mic_state.setObjectName("StatusOk")
                self._lbl_mic_state.setText("✔ 收到你的声音了，麦克风正常")
                self._lbl_mic_tip.setText("保持这个音量就行。点「下一步」继续。")
                self._restyle(self._lbl_mic_state)

    def _decay_level(self) -> None:
        """峰值缓慢回落，让进度条看起来像真实音量表。"""

        self._peak *= 0.82
        if self._peak < 0.005:
            self._peak = 0.0
        self._bar_level.setValue(int(self._peak * 100))

    # ============================================================
    # 扬声器
    # ============================================================

    def _reload_spk_devices(self) -> None:
        self._cmb_spk.blockSignals(True)
        self._cmb_spk.clear()
        devices = list_output_devices()
        current = self.settings.asr_output_device
        for dev in devices:
            label = f"{dev['name']}（{dev['channels']} 通道）"
            self._cmb_spk.addItem(label, dev["id"])
        self._cmb_spk.blockSignals(False)

        if not devices:
            self._lbl_spk_state.setObjectName("StatusBad")
            self._lbl_spk_state.setText("✘ 没有找到任何扬声器设备")
            self._restyle(self._lbl_spk_state)
            return

        picked = -1
        if current not in (None, ""):
            for i in range(self._cmb_spk.count()):
                if str(self._cmb_spk.itemData(i)) == str(current):
                    picked = i
                    break
        if picked < 0:
            default_id = default_output_device_id()
            for i in range(self._cmb_spk.count()):
                if self._cmb_spk.itemData(i) == default_id:
                    picked = i
                    break
        self._cmb_spk.setCurrentIndex(max(0, picked))

    def _on_spk_device_changed(self) -> None:
        self._speaker_ok = False
        self._lbl_spk_state.setObjectName("CardHint")
        self._lbl_spk_state.setText("点上面的按钮试试")
        self._restyle(self._lbl_spk_state)

    def _play(self, channel: str) -> None:
        device = self._cmb_spk.currentData()
        name = {"left": "左声道", "right": "右声道", "both": "双声道"}.get(channel, channel)
        ok = play_test_tone(device=device, channel=channel)
        self._lbl_spk_state.setObjectName("CardHint" if ok else "StatusBad")
        self._lbl_spk_state.setText(
            f"正在播放{name}测试音…" if ok else "✘ 播放失败，换一个输出设备试试"
        )
        self._restyle(self._lbl_spk_state)

    def _answer_speaker(self, heard: bool) -> None:
        self._speaker_ok = heard
        stop_test_tone()
        if heard:
            self._lbl_spk_state.setObjectName("StatusOk")
            self._lbl_spk_state.setText("✔ 扬声器正常，已记录这个输出设备")
        else:
            self._lbl_spk_state.setObjectName("StatusWarn")
            self._lbl_spk_state.setText(
                "没听到也没关系：检查一下系统音量和静音键，或者换一个输出设备再点一次。"
                "也可以直接跳过，不影响语音识别。"
            )
        self._restyle(self._lbl_spk_state)

    # ============================================================
    # 完成页
    # ============================================================

    def _refresh_summary(self) -> None:
        mic_name = self._cmb_mic.currentText() if self._cmb_mic.count() else "（无设备）"
        spk_name = self._cmb_spk.currentText() if self._cmb_spk.count() else "（无设备）"
        self._lbl_summary_mic.setText(
            f"麦克风：{'✔ 已确认 ' + mic_name if self._mic_ok else '— 未测试（稍后可在高级设置里测）'}"
        )
        self._lbl_summary_spk.setText(
            f"扬声器：{'✔ 已确认 ' + spk_name if self._speaker_ok else '— 未测试（不影响识别）'}"
        )

    # ============================================================

    @staticmethod
    def _restyle(widget: QLabel) -> None:
        """objectName 改了要手动重新应用样式表，否则颜色不刷新。"""

        widget.style().unpolish(widget)
        widget.style().polish(widget)


def run_wizard_if_needed(settings: Settings, *, parent: Optional[QWidget] = None) -> bool:
    """首次启动时弹向导；已走过就直接跳过。

    返回 True 表示这次真的弹了并走完了。
    """

    if settings.setup_wizard_done:
        return False
    wizard = DeviceTestWizard(settings, first_run=True, parent=parent)
    wizard.exec()
    return True
