"""首页 —— 选游戏、看状态、一键开关."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
                                QPushButton, QVBoxLayout, QWidget)

from ...engine import Engine, Event
from ...logs import trigger_stats
from ..page_base import ScrollPage, divider, make_card
from ..widgets.log_view import LogView
from ..widgets.wave import BigWave

# 状态对应的圆点颜色
_DOT = {
    "ok": "#7ddcb4",
    "warn": "#e6b660",
    "bad": "#e58387",
    "idle": "#7d8e87",
}


class StateChip(QFrame):
    """一枚小状态胶囊：圆点 + 文字。"""

    def __init__(self, text: str, kind: str = "idle",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("StateChip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 5, 11, 5)
        lay.setSpacing(7)
        self._dot = QLabel("●")
        self._label = QLabel(text)
        self._label.setObjectName("CardHint")
        lay.addWidget(self._dot)
        lay.addWidget(self._label)
        self.set_kind(kind)

    def set_text(self, text: str, kind: str = "idle") -> None:
        self._label.setText(text)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        color = _DOT.get(kind, _DOT["idle"])
        self._dot.setStyleSheet(f"color: {color}; font-size: 11px;")


class HomePage(ScrollPage):
    """首页：把「选游戏」做成一等公民，其余都是状态展示。"""

    def __init__(self, engine: Engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            "首页",
            "在下面选一个正在玩的游戏，就能进去配语音指令了 —— "
            "之后打开游戏会自动切到这配置，关掉游戏自动休眠。",
            parent,
        )
        self.engine = engine

        self.body.addWidget(self._build_pick_card())
        self.body.addWidget(self._build_switch_card())
        self.body.addWidget(self._build_monitor_card())
        self.body.addWidget(self._build_log_card())
        self.finish_body()

        # ---- 订阅引擎事件 ----
        engine.bus.subscribe("engine.state", self._on_engine_state)
        engine.bus.subscribe("audio.level", self._on_audio_level)
        engine.bus.subscribe("transcript", self._on_transcript)
        engine.bus.subscribe("trigger", self._on_trigger)
        engine.bus.subscribe("profile.switched", self._on_profile_switched)
        engine.bus.subscribe("profile.unmatched", self._on_profile_unmatched)

        self._stat_timer = QTimer(self)
        self._stat_timer.timeout.connect(self._refresh_stats)
        self._stat_timer.start(700)

        self._on_engine_state(Event(type="engine.state", payload={"state": engine.state}))
        self._refresh_stats()

    # ============================================================
    # 各卡片
    # ============================================================

    def _build_pick_card(self) -> QFrame:
        """最重要的一张卡：选游戏 → 进编辑页。"""

        card, box = make_card(accent=True)

        row = QHBoxLayout()
        row.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(4)
        cap = QLabel("当前游戏配置")
        cap.setObjectName("CardHint")
        left.addWidget(cap)

        self._profile_name = QLabel("还没选择游戏")
        self._profile_name.setObjectName("BigNumber")
        self._profile_name.setWordWrap(True)
        left.addWidget(self._profile_name)

        self._profile_sub = QLabel("点右边的按钮，从正在运行的程序里挑一个")
        self._profile_sub.setObjectName("CardHint")
        self._profile_sub.setWordWrap(True)
        left.addWidget(self._profile_sub)
        row.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.btn_pick = QPushButton("选择当前游玩的游戏")
        self.btn_pick.setObjectName("Primary")
        self.btn_pick.setMinimumSize(210, 46)
        self.btn_pick.setToolTip("列出当前开着窗口的程序，选一个即可开始配置")
        self.btn_pick.clicked.connect(self.pick_process)
        right.addWidget(self.btn_pick)

        self.btn_edit = QPushButton("编辑当前配置")
        self.btn_edit.setObjectName("Ghost")
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self._edit_current)
        right.addWidget(self.btn_edit)
        row.addLayout(right)
        box.addLayout(row)

        return card

    def _build_switch_card(self) -> QFrame:
        card, box = make_card("运行状态")

        chips = QHBoxLayout()
        chips.setSpacing(9)
        self.chip_listen = StateChip("监听：已启动", "ok")
        self.chip_game = StateChip("当前游戏：未选择", "idle")
        chips.addWidget(self.chip_listen)
        chips.addWidget(self.chip_game)
        chips.addStretch(1)
        box.addLayout(chips)

        box.addWidget(divider())

        btns = QHBoxLayout()
        btns.setSpacing(10)
        master_on = self.engine.settings.master_enabled
        self.btn_master = QPushButton("语音控制已开启" if master_on else "语音控制已关闭")
        self.btn_master.setObjectName("Primary")
        self.btn_master.setCheckable(True)
        self.btn_master.setChecked(master_on)
        self.btn_master.toggled.connect(self._on_master_toggled)
        btns.addWidget(self.btn_master)

        self.btn_pause = QPushButton("正常监听")
        self.btn_pause.setCheckable(True)
        self.btn_pause.toggled.connect(self._on_pause_toggled)
        btns.addWidget(self.btn_pause)

        self.btn_reload = QPushButton("重新加载配置")
        self.btn_reload.setObjectName("Ghost")
        self.btn_reload.clicked.connect(self.engine.reload)
        btns.addWidget(self.btn_reload)

        self.btn_rescan = QPushButton("重新扫描配置")
        self.btn_rescan.setObjectName("Ghost")
        self.btn_rescan.clicked.connect(self.engine.profile_store.reload)
        btns.addWidget(self.btn_rescan)
        btns.addStretch(1)
        box.addLayout(btns)

        # 让按钮文字与初始状态一致
        self.btn_master.setText("语音控制已开启" if master_on else "语音控制已关闭")
        return card

    def _build_monitor_card(self) -> QFrame:
        card, box = make_card("实时声音")

        self._wave = BigWave()
        self._wave.setMinimumHeight(96)
        box.addWidget(self._wave)

        nums = QHBoxLayout()
        nums.setSpacing(30)
        self._n_trigger, lbl1 = self._make_number("触发次数", "0")
        self._n_success, lbl2 = self._make_number("成功次数", "0")
        self._n_rate, lbl3 = self._make_number("成功率", "—")
        for num, lbl in ((self._n_trigger, lbl1), (self._n_success, lbl2), (self._n_rate, lbl3)):
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(num)
            col.addWidget(lbl)
            holder = QWidget()
            holder.setLayout(col)
            nums.addWidget(holder)
        nums.addStretch(1)
        box.addLayout(nums)

        self._transcript_lbl = QLabel("")
        self._transcript_lbl.setObjectName("CardHint")
        self._transcript_lbl.setWordWrap(True)
        box.addWidget(self._transcript_lbl)
        return card

    def _build_log_card(self) -> QFrame:
        card, box = make_card("最近触发")
        self._log = LogView(max_lines=120)
        self._log.setMinimumHeight(140)
        box.addWidget(self._log)
        return card

    @staticmethod
    def _make_number(label: str, init: str):
        num = QLabel(init)
        num.setObjectName("BigNumber")
        lbl = QLabel(label)
        lbl.setObjectName("BigNumberLabel")
        return num, lbl

    # ============================================================
    # 选游戏
    # ============================================================

    def pick_process(self) -> None:
        """打开进程选择框 → 接管选中进程 → 跳到编辑页。"""

        from ..pick_process import PickProcessDialog

        dialog = PickProcessDialog(self.engine, self)
        if dialog.exec() != QDialog.Accepted:
            return

        app = dialog.chosen()
        if app is None:
            return

        profile = self.engine.adopt_process(
            app.process,
            display_name=app.title or app.display,
            window_title=app.title,
        )
        if profile is None:
            QMessageBox.warning(self, "没选到进程", "没能识别这个进程，换一个再试试。")
            return

        self.set_profile_name(profile.name)
        self.chip_game.set_text(f"当前游戏：{profile.name}", "ok")
        self._open_editor(profile.id)

    def _open_editor(self, profile_id: str) -> None:
        """跳到「语音按键编辑」页（通过主窗口，不依赖控件层级）。"""

        window = self.window()
        if hasattr(window, "goto_editor_for"):
            window.goto_editor_for(profile_id)

    def _edit_current(self) -> None:
        profile = self.engine.current_profile()
        if profile is not None:
            self._open_editor(profile.id)

    # ============================================================
    # 状态刷新
    # ============================================================

    def set_profile_name(self, name: str) -> None:
        if name:
            self._profile_name.setText(name)
            self._profile_sub.setText("配置已生效，可点「编辑当前配置」调整语音指令")
            self.btn_edit.setEnabled(True)
        else:
            self._profile_name.setText("还没选择游戏")
            self._profile_sub.setText("点右边的按钮，从正在运行的程序里挑一个")
            self.btn_edit.setEnabled(False)

    def _on_engine_state(self, ev: Event) -> None:
        state = ev.payload.get("state", "stopped")
        mapping = {
            "active": ("监听：已启动", "ok"),
            "paused": ("监听：已暂停", "warn"),
            "muted": ("监听：麦克风已静音", "warn"),
            "disabled": ("监听：语音控制已关闭", "bad"),
            "idle": ("监听：待机中", "idle"),
            "stopped": ("监听：未启动", "idle"),
        }
        text, kind = mapping.get(state, (f"监听：{state}", "idle"))
        self.chip_listen.set_text(text, kind)

        enabled = state not in ("disabled", "stopped")
        self.btn_master.blockSignals(True)
        self.btn_master.setChecked(enabled)
        self.btn_master.setText("语音控制已开启" if enabled else "语音控制已关闭")
        self.btn_master.blockSignals(False)

        paused = state == "paused"
        self.btn_pause.blockSignals(True)
        self.btn_pause.setChecked(paused)
        self.btn_pause.setText("已暂停 · 点我恢复" if paused else "正常监听")
        self.btn_pause.blockSignals(False)

    def _on_audio_level(self, ev: Event) -> None:
        self._wave.feed(ev.payload.get("level", 0.0))

    def _on_transcript(self, ev: Event) -> None:
        """显示识别到的文字 —— 用户靠它判断「到底有没有在听」。"""

        text = (ev.payload.get("text") or "").strip()
        if not text:
            return
        if ev.payload.get("is_final"):
            self._transcript_lbl.setText(f"听到：「{text}」")
        else:
            self._transcript_lbl.setText(f"正在听…「{text}」")

    def _on_trigger(self, ev: Event) -> None:
        profile = ev.payload.get("profile", "-")
        phrase = ev.payload.get("phrase", "-")
        key = ev.payload.get("key", "-")
        ok = ev.payload.get("success")
        text = f"【{profile}】「{phrase}」→ {key}"
        self._log.append(("✓ " if ok else "✗ ") + text)
        self._transcript_lbl.setText(("已触发：" if ok else "触发失败：") + text)

    def _on_profile_switched(self, ev: Event) -> None:
        profile = ev.payload.get("profile")
        if profile:
            self.set_profile_name(profile.name)
            self.chip_game.set_text(f"当前游戏：{profile.name}", "ok")

    def _on_profile_unmatched(self, _ev: Event) -> None:
        self.set_profile_name("")
        self.chip_game.set_text("当前游戏：未选择", "idle")

    def _on_master_toggled(self, checked: bool) -> None:
        if checked != self.engine.settings.master_enabled:
            self.engine.toggle_master()

    def _on_pause_toggled(self, checked: bool) -> None:
        self.engine.pause(checked)

    def _refresh_stats(self) -> None:
        stats = trigger_stats()
        self._n_trigger.setText(str(stats["total"]))
        self._n_success.setText(str(stats["success"]))
        if stats["total"] > 0:
            rate = int(round(stats["success"] / stats["total"] * 100))
            self._n_rate.setText(f"{rate}%")
        else:
            self._n_rate.setText("—")

    # ============================================================

    def on_show(self) -> None:
        self._refresh_stats()
        profile = self.engine.current_profile()
        if profile is not None:
            self.set_profile_name(profile.name)
            self.chip_game.set_text(f"当前游戏：{profile.name}", "ok")
