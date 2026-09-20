"""首页 - 智能自动适配主页."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                                QVBoxLayout, QWidget)

from ...engine import Engine, Event
from ...logs import trigger_stats
from ..widgets.log_view import LogView
from ..widgets.wave import BigWave


class StateChip(QFrame):
    """左侧小标签样式."""

    def __init__(self, text: str, accent: str = "#7CCAB1", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("StateChip")
        self._accent = accent
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {accent}; font-size: 12px;")
        self._label = QLabel(text)
        self._label.setStyleSheet("color: #cfe1d5; font-size: 12px;")
        lay.addWidget(self._dot)
        lay.addWidget(self._label)
        self.setStyleSheet(
            "QFrame#StateChip { background-color: #1a2128; border: 1px solid #2f6e5b; border-radius: 10px; }"
        )

    def set_text(self, text: str, accent: Optional[str] = None) -> None:
        self._label.setText(text)
        if accent:
            self._accent = accent
            self._dot.setStyleSheet(f"color: {accent}; font-size: 12px;")


class HomePage(QWidget):
    def __init__(self, engine: Engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setObjectName("PageInner")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(20)

        # ----- 顶部标题 -----
        title = QLabel("智能自动适配主页")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        hint = QLabel("打开任意已配置的游戏即可自动适配；关闭游戏后自动休眠。")
        hint.setObjectName("PageHint")
        outer.addWidget(hint)

        # ----- 状态芯片行 -----
        chips = QHBoxLayout()
        chips.setSpacing(10)
        self.chip_listen = StateChip("监听状态：已启动", "#7CCAB1")
        self.chip_game = StateChip("识别游戏：等待中", "#7d8e87")
        self.chip_proc = StateChip("进程状态：扫描中", "#7d8e87")
        chips.addWidget(self.chip_listen)
        chips.addWidget(self.chip_game)
        chips.addWidget(self.chip_proc)
        chips.addStretch(1)
        outer.addLayout(chips)

        # ----- 中央大卡片：当前 Profile + 波形 + 成功率 -----
        center = QFrame()
        center.setObjectName("Card")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(10)
        self._profile_lbl = QLabel("当前配置：未匹配游戏")
        self._profile_lbl.setStyleSheet("color: #cfe1d5; font-size: 14px;")
        cl.addWidget(self._profile_lbl)
        self._profile_name = QLabel("GameVoiceKey · 等待匹配游戏")
        self._profile_name.setObjectName("BigNumber")
        cl.addWidget(self._profile_name)
        # 波形
        self._wave = BigWave()
        cl.addWidget(self._wave, 1)
        # 成功率 / 触发数 / 失败数
        nums = QHBoxLayout()
        nums.setSpacing(28)
        self._n_trigger, self._lbl_trigger = self._make_number("触发次数", "0")
        self._n_success, self._lbl_success = self._make_number("成功数", "0")
        self._n_rate, self._lbl_rate = self._make_number("成功率", "—")
        for n, l in ((self._n_trigger, self._lbl_trigger),
                     (self._n_success, self._lbl_success),
                     (self._n_rate, self._lbl_rate)):
            box = QVBoxLayout()
            box.setSpacing(2)
            box.addWidget(n)
            box.addWidget(l)
            w = QWidget()
            w.setLayout(box)
            nums.addWidget(w)
        nums.addStretch(1)
        cl.addLayout(nums)
        outer.addWidget(center, 1)

        # ----- 快捷功能 -----
        quick = QHBoxLayout()
        quick.setSpacing(12)
        self.btn_master = QPushButton("总开关 · 语音控制")
        self.btn_master.setObjectName("BigToggle")
        self.btn_master.setCheckable(True)
        self.btn_master.setChecked(engine.settings.master_enabled)
        self.btn_master.toggled.connect(self._on_master_toggled)
        self.btn_reload = QPushButton("重新识别")
        self.btn_reload.clicked.connect(self._on_reload)
        self.btn_pause = QPushButton("暂停监听")
        self.btn_pause.setCheckable(True)
        self.btn_pause.toggled.connect(self._on_pause_toggled)
        self.btn_rescan = QPushButton("重新扫描进程")
        self.btn_rescan.clicked.connect(self.engine.profile_store.reload)
        quick.addWidget(self.btn_master)
        quick.addWidget(self.btn_reload)
        quick.addWidget(self.btn_pause)
        quick.addStretch(1)
        quick.addWidget(self.btn_rescan)
        outer.addLayout(quick)

        # ----- 底部最近触发日志极简滚动 -----
        outer.addWidget(QLabel("最近触发："))
        self._log = LogView(max_lines=120)
        outer.addWidget(self._log, 1)

        # ---- 订阅 events -----
        engine.bus.subscribe("engine.state", self._on_engine_state)
        engine.bus.subscribe("audio.level", self._on_audio_level)
        engine.bus.subscribe("trigger", self._on_trigger)
        engine.bus.subscribe("profile.switched", self._on_profile_switched)
        engine.bus.subscribe("profile.unmatched", self._on_profile_unmatched)

        # 定时拉一下统计
        self._stat_timer = QTimer(self)
        self._stat_timer.timeout.connect(self._refresh_stats)
        self._stat_timer.start(700)
        self._refresh_stats()

    def _make_number(self, label: str, init: str):
        n = QLabel(init)
        n.setObjectName("BigNumber")
        l = QLabel(label)
        l.setObjectName("BigNumberLabel")
        return n, l

    def set_profile_name(self, name: str) -> None:
        if not name:
            self._profile_name.setText("等待匹配游戏…")
        else:
            self._profile_name.setText(name)

    # ---- 事件 ----

    def _on_engine_state(self, ev: Event) -> None:
        s = ev.payload.get("state", "stopped")
        chip_map = {
            "active": ("监听状态：已启动", "#7CCAB1"),
            "paused": ("监听状态：已暂停", "#E6B660"),
            "muted": ("监听状态：麦克风静音", "#9fa8a3"),
            "disabled": ("监听状态：总开关关闭", "#D86F73"),
            "idle": ("监听状态：待机", "#7d8e87"),
            "stopped": ("监听状态：未启动", "#7d8e87"),
        }
        text, color = chip_map.get(s, (f"监听状态：{s}", "#7d8e87"))
        self.chip_listen.set_text(text, color)
        # master 按钮
        try:
            self.btn_master.blockSignals(True)
            self.btn_master.setChecked(s not in ("disabled", "stopped"))
            self.btn_master.setText("已启用 · 语音控制" if s not in ("disabled", "stopped") else "已禁用 · 点击启用")
            self.btn_master.blockSignals(False)
        except Exception:
            pass
        # pause 按钮
        try:
            self.btn_pause.blockSignals(True)
            self.btn_pause.setChecked(s == "paused")
            self.btn_pause.setText("已暂停 · 点击恢复" if s == "paused" else "正常监听")
            self.btn_pause.blockSignals(False)
        except Exception:
            pass

    def _on_audio_level(self, ev: Event) -> None:
        self._wave.feed(ev.payload.get("level", 0.0))

    def _on_trigger(self, ev: Event) -> None:
        msg = f"【{ev.payload.get('profile','-')}】 「{ev.payload.get('phrase','-')}」 → {ev.payload.get('key','-')}"
        self._log.append("✓ " + msg if ev.payload.get("success") else "✗ " + msg)

    def _on_profile_switched(self, ev: Event) -> None:
        prof = ev.payload.get("profile")
        if prof:
            self.set_profile_name(prof.name)
            self.chip_game.set_text(f"识别游戏：{prof.name}", "#7CCAB1")
            self.chip_proc.set_text(f"进程状态：已匹配（pin={prof.pin}）", "#7CCAB1")

    def _on_profile_unmatched(self, _ev: Event) -> None:
        self.set_profile_name("")
        self.chip_game.set_text("识别游戏：等待中", "#7d8e87")
        self.chip_proc.set_text("进程状态：扫描中", "#7d8e87")

    def _on_master_toggled(self, checked: bool) -> None:
        if checked != self.engine.settings.master_enabled:
            self.engine.toggle_master()

    def _on_pause_toggled(self, checked: bool) -> None:
        self.engine.pause(checked)

    def _on_reload(self) -> None:
        self.engine.reload()

    def _refresh_stats(self) -> None:
        stats = trigger_stats()
        self._n_trigger.setText(str(stats["total"]))
        self._n_success.setText(str(stats["success"]))
        if stats["total"] > 0:
            rate = int(round(stats["success"] / stats["total"] * 100))
            self._n_rate.setText(f"{rate}%")
        else:
            self._n_rate.setText("—")

    def on_show(self) -> None:
        self._refresh_stats()
