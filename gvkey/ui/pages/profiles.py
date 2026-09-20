"""游戏配置管理页.

结构：左侧游戏列表 + 右侧参数详情。

右侧参数区套在 ``QScrollArea`` 里 —— 之前直接塞进固定高度的卡片，
窗口一小所有分组就互相压在一起（界面「乱」的主要原因之一）。
"""
from __future__ import annotations

import uuid
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout,
                                QInputDialog, QLabel, QLineEdit, QListWidget,
                                QListWidgetItem, QMenu, QMessageBox, QPushButton,
                                QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget)

from ...config import Profile, VoiceRule, export_profile, import_profile, save_profile
from ...engine import Engine
from ..page_base import divider, hint, kv_row


class ProfilesPage(QWidget):
    def __init__(self, engine: Engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setObjectName("PageInner")
        self._selected_pid: Optional[str] = None
        self._suspend_store_refresh = False
        self._build()

        engine.profile_store.subscribe(self._on_store_changed)

    # ============================================================
    # 构建
    # ============================================================

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 20)
        outer.setSpacing(13)

        title = QLabel("游戏配置管理")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        outer.addWidget(hint("左边是已配置的游戏，右边调这个游戏的识别参数。"
                             "想改语音指令，点右下角「进入规则编辑页」."))

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter, 1)

        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([280, 700])

        self.refresh()

    def _build_left(self) -> QFrame:
        left = QFrame()
        left.setObjectName("Card")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 14, 14, 14)
        ll.setSpacing(9)

        head = QHBoxLayout()
        head.setSpacing(8)
        h_title = QLabel("游戏列表")
        h_title.setObjectName("CardTitle")
        head.addWidget(h_title)
        head.addStretch(1)
        btn_new = QPushButton("+ 新建")
        btn_new.setObjectName("Primary")
        btn_new.clicked.connect(self._on_new)
        head.addWidget(btn_new)
        btn_imp = QPushButton("导入…")
        btn_imp.setObjectName("Ghost")
        btn_imp.clicked.connect(self._on_import)
        head.addWidget(btn_imp)
        ll.addLayout(head)

        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        ll.addWidget(self._list, 1)

        tip = hint("右键可以重命名 / 复制 / 置顶 / 删除")
        ll.addWidget(tip)
        return left

    def _build_right(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.viewport().setAutoFillBackground(False)

        host = QWidget()
        host.setObjectName("ScrollHost")
        rl = QVBoxLayout(host)
        rl.setContentsMargins(0, 0, 4, 0)
        rl.setSpacing(13)

        self._lbl_name = QLabel("未选中游戏")
        self._lbl_name.setObjectName("PageTitle")
        rl.addWidget(self._lbl_name)

        rl.addWidget(self._build_base_group())
        rl.addWidget(self._build_switch_group())
        rl.addWidget(self._build_param_group())
        rl.addLayout(self._build_actions())
        rl.addStretch(1)

        scroll.setWidget(host)
        return scroll

    def _build_base_group(self) -> QGroupBox:
        box = QGroupBox("基础信息")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 8, 14, 14)
        lay.setSpacing(9)

        self._ed_name = QLineEdit()
        self._ed_name.editingFinished.connect(self._save_field)
        lay.addLayout(kv_row("游戏名称", self._ed_name, 96))

        self._ed_proc = QLineEdit()
        self._ed_proc.setPlaceholderText("例如 csgo, hl2")
        self._ed_proc.editingFinished.connect(self._save_field)
        lay.addLayout(kv_row("进程名", self._ed_proc, 96))
        lay.addWidget(hint("多个进程名用英文逗号分隔；不含 .exe。"))

        self._ed_title = QLineEdit()
        self._ed_title.setPlaceholderText("可选，例如 Counter-Strike")
        self._ed_title.editingFinished.connect(self._save_field)
        lay.addLayout(kv_row("标题正则", self._ed_title, 96))

        self._ed_cls = QLineEdit()
        self._ed_cls.setPlaceholderText("可选，窗口类名")
        self._ed_cls.editingFinished.connect(self._save_field)
        lay.addLayout(kv_row("窗口类名", self._ed_cls, 96))
        return box

    def _build_switch_group(self) -> QGroupBox:
        box = QGroupBox("该游戏开关")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 8, 14, 14)
        lay.setSpacing(7)

        self._ck_enabled = QCheckBox("启用此游戏的语音控制")
        self._ck_enabled.stateChanged.connect(self._save_checkbox)
        lay.addWidget(self._ck_enabled)

        self._ck_pin = QCheckBox("置顶（同进程多开时优先用这个配置）")
        self._ck_pin.stateChanged.connect(self._save_checkbox)
        lay.addWidget(self._ck_pin)

        self._ck_ptt = QCheckBox("按住说话模式（不按住不响应）")
        self._ck_ptt.stateChanged.connect(self._save_checkbox)
        lay.addWidget(self._ck_ptt)

        self._ed_ptt = QLineEdit()
        self._ed_ptt.setPlaceholderText("例如 Ctrl+Space")
        self._ed_ptt.editingFinished.connect(self._save_field)
        lay.addLayout(kv_row("按住说话键", self._ed_ptt, 96))
        return box

    def _build_param_group(self) -> QGroupBox:
        box = QGroupBox("识别参数")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 8, 14, 14)
        lay.setSpacing(9)

        # 百分比一律用 QSpinBox 0~100 + 后缀，框内只有数字
        self._sp_sens = QSpinBox()
        self._sp_sens.setRange(1, 100)
        self._sp_sens.setSingleStep(5)
        self._sp_sens.setSuffix(" %")
        self._sp_sens.valueChanged.connect(
            lambda v: self._save_numeric("sensitivity", int(v) / 100.0)
        )
        sens_row = QHBoxLayout()
        sens_row.setSpacing(10)
        sens_row.addWidget(self._sp_sens)
        sens_row.addWidget(hint("越高越灵敏，容易误触发"))
        sens_row.addStretch(1)
        lay.addLayout(kv_row("麦克风灵敏度", self._wrap(sens_row), 96))

        self._sp_sim = QSpinBox()
        self._sp_sim.setRange(1, 100)
        self._sp_sim.setSingleStep(5)
        self._sp_sim.setSuffix(" %")
        self._sp_sim.valueChanged.connect(
            lambda v: self._save_numeric("phrase_similarity", int(v) / 100.0)
        )
        sim_row = QHBoxLayout()
        sim_row.setSpacing(10)
        sim_row.addWidget(self._sp_sim)
        sim_row.addWidget(hint("发音像到什么程度才算同一个词"))
        sim_row.addStretch(1)
        lay.addLayout(kv_row("词相似度阈值", self._wrap(sim_row), 96))

        lay.addWidget(divider())

        self._ck_denoise = QCheckBox("启用降噪（键盘声等会被压掉）")
        self._ck_denoise.stateChanged.connect(self._save_checkbox)
        lay.addWidget(self._ck_denoise)

        self._ck_mouse = QCheckBox("允许映射到鼠标按键 / 滚轮")
        self._ck_mouse.stateChanged.connect(self._save_checkbox)
        lay.addWidget(self._ck_mouse)

        self._ck_kbd = QCheckBox("允许映射到键盘按键")
        self._ck_kbd.stateChanged.connect(self._save_checkbox)
        lay.addWidget(self._ck_kbd)
        return box

    @staticmethod
    def _wrap(layout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        return holder

    def _build_actions(self) -> QHBoxLayout:
        btns = QHBoxLayout()
        btns.setSpacing(9)

        self._btn_apply = QPushButton("应用改动")
        self._btn_apply.setObjectName("Primary")
        self._btn_apply.clicked.connect(self._save_explicit)
        btns.addWidget(self._btn_apply)

        self._btn_export = QPushButton("导出这个配置…")
        self._btn_export.setObjectName("Ghost")
        self._btn_export.clicked.connect(self._on_export)
        btns.addWidget(self._btn_export)

        btns.addStretch(1)

        self._btn_rules = QPushButton("进入规则编辑页 →")
        self._btn_rules.clicked.connect(self._goto_rules)
        btns.addWidget(self._btn_rules)
        return btns

    # ============================================================
    # 数据交互
    # ============================================================

    def _on_store_changed(self, _profiles) -> None:
        if self._suspend_store_refresh:
            return
        self.refresh()

    def _persist(self, profile: Profile) -> None:
        """落盘但不触发仓库回调 —— 否则每改一个值都会重填表单、打断输入。"""

        self._suspend_store_refresh = True
        try:
            save_profile(profile)
        finally:
            self._suspend_store_refresh = False

    def refresh(self) -> None:
        profiles = self.engine.profile_store.all()
        self._list.blockSignals(True)
        self._list.clear()
        for p in profiles:
            text = ("📌 " if p.pin else "🎮 ") + f"{p.name}  ({', '.join(p.processes[:3])})"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, p.id)
            self._list.addItem(item)
        self._list.blockSignals(False)

        if not profiles:
            self._selected_pid = None
            self._show_empty()
            return

        target = 0
        if self._selected_pid:
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.UserRole) == self._selected_pid:
                    target = i
                    break
        self._list.setCurrentRow(target)

    def _show_empty(self) -> None:
        self._lbl_name.setText("还没有任何游戏配置")
        for w in (self._ed_name, self._ed_proc, self._ed_title, self._ed_cls, self._ed_ptt):
            w.blockSignals(True)
            w.setText("")
            w.blockSignals(False)
        for ck in (self._ck_enabled, self._ck_pin, self._ck_ptt,
                   self._ck_denoise, self._ck_mouse, self._ck_kbd):
            ck.blockSignals(True)
            ck.setChecked(False)
            ck.blockSignals(False)
        self._sp_sens.blockSignals(True)
        self._sp_sens.setValue(50)
        self._sp_sens.blockSignals(False)
        self._sp_sim.blockSignals(True)
        self._sp_sim.setValue(70)
        self._sp_sim.blockSignals(False)
        for btn in (self._btn_apply, self._btn_export, self._btn_rules):
            btn.setEnabled(False)

    def _on_selection_changed(self) -> None:
        item = self._list.currentItem()
        if not item:
            self._selected_pid = None
            return
        self._selected_pid = item.data(Qt.UserRole)
        p = self.engine.profile_store.get(self._selected_pid)
        if not p:
            return

        self._lbl_name.setText(p.name)
        for btn in (self._btn_apply, self._btn_export, self._btn_rules):
            btn.setEnabled(True)

        def _set_text(widget: QLineEdit, value: str) -> None:
            widget.blockSignals(True)
            widget.setText(value)
            widget.blockSignals(False)

        def _set_check(widget: QCheckBox, value: bool) -> None:
            widget.blockSignals(True)
            widget.setChecked(bool(value))
            widget.blockSignals(False)

        def _set_spin(widget: QSpinBox, value: float) -> None:
            widget.blockSignals(True)
            widget.setValue(int(round(float(value) * 100)))
            widget.blockSignals(False)

        _set_text(self._ed_name, p.name)
        _set_text(self._ed_proc, ", ".join(p.processes))
        _set_text(self._ed_title, p.window_title_regex)
        _set_text(self._ed_cls, p.window_class)
        _set_text(self._ed_ptt, p.push_to_talk_key)
        _set_check(self._ck_enabled, p.enabled)
        _set_check(self._ck_pin, p.pin)
        _set_check(self._ck_ptt, p.push_to_talk)
        _set_check(self._ck_denoise, p.denoise)
        _set_check(self._ck_mouse, p.mouse_enabled)
        _set_check(self._ck_kbd, p.keyboard_enabled)
        _set_spin(self._sp_sens, p.sensitivity)
        _set_spin(self._sp_sim, p.phrase_similarity)

    def _save_field(self) -> None:
        p = self._current_profile()
        if not p:
            return
        p.name = self._ed_name.text().strip() or "未命名游戏"
        p.processes = [x.strip() for x in self._ed_proc.text().split(",") if x.strip()]
        p.window_title_regex = self._ed_title.text().strip()
        p.window_class = self._ed_cls.text().strip()
        p.push_to_talk_key = self._ed_ptt.text().strip()
        self._persist(p)
        self._refresh_current_item_text(p)

    def _refresh_current_item_text(self, profile: Profile) -> None:
        """只更新当前这一行的文字，不重建整个列表。"""

        item = self._list.currentItem()
        if item is None:
            return
        prefix = "📌 " if profile.pin else "🎮 "
        item.setText(prefix + f"{profile.name}  ({', '.join(profile.processes[:3])})")
        self._lbl_name.setText(profile.name)

    def _save_numeric(self, key: str, value) -> None:
        p = self._current_profile()
        if not p:
            return
        if getattr(p, key) == value:
            return
        setattr(p, key, value)
        self._persist(p)

    def _save_checkbox(self) -> None:
        p = self._current_profile()
        if not p:
            return
        p.enabled = self._ck_enabled.isChecked()
        p.pin = self._ck_pin.isChecked()
        p.push_to_talk = self._ck_ptt.isChecked()
        p.denoise = self._ck_denoise.isChecked()
        p.mouse_enabled = self._ck_mouse.isChecked()
        p.keyboard_enabled = self._ck_kbd.isChecked()
        self._persist(p)

    def _save_explicit(self) -> None:
        self._save_field()

    def _current_profile(self) -> Optional[Profile]:
        if not self._selected_pid:
            return None
        return self.engine.profile_store.get(self._selected_pid)

    def _goto_rules(self) -> None:
        """进规则编辑页 —— 通过主窗口，不依赖控件父子层级。"""

        if not self._selected_pid:
            return
        window = self.window()
        if hasattr(window, "goto_editor_for"):
            window.goto_editor_for(self._selected_pid)
        elif hasattr(window, "goto"):
            window.goto("语音按键编辑")

    # ============================================================
    # 操作
    # ============================================================

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(self, "新建配置", "游戏名称")
        if not ok or not name.strip():
            return
        proc, ok = QInputDialog.getText(self, "新建配置", "进程名（不含 .exe，多个用逗号）")
        if not ok:
            proc = ""
        profile = Profile(name=name.strip(),
                          processes=[x.strip() for x in proc.split(",") if x.strip()])
        save_profile(profile)
        self._suspend_store_refresh = True
        try:
            self.engine.profile_store.reload()
        finally:
            self._suspend_store_refresh = False
        self._selected_pid = profile.id
        self.refresh()

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入游戏配置", "",
                                              "JSON (*.json);;所有文件 (*.*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            QMessageBox.warning(self, "导入失败", f"读取文件失败：{exc}")
            return
        profile = import_profile(text)
        if not profile:
            QMessageBox.warning(self, "导入失败", "文件格式不正确或内容不完整。")
            return
        save_profile(profile)
        self._suspend_store_refresh = True
        try:
            self.engine.profile_store.reload()
        finally:
            self._suspend_store_refresh = False
        self._selected_pid = profile.id
        self.refresh()
        QMessageBox.information(self, "导入成功", f"已新增配置：{profile.name}")

    def _on_export(self) -> None:
        p = self._current_profile()
        if not p:
            QMessageBox.information(self, "导出", "请先在左侧选中一个游戏。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出", f"{p.name}.gvprofile.json",
                                              "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(export_profile(p))
            QMessageBox.information(self, "导出", f"已导出到 {path}")
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        pid = item.data(Qt.UserRole)
        menu = QMenu(self)
        a_edit = QAction("重命名", self)
        a_edit.triggered.connect(lambda: self._rename_profile(pid))
        menu.addAction(a_edit)
        a_dup = QAction("复制配置", self)
        a_dup.triggered.connect(lambda: self._duplicate_profile(pid))
        menu.addAction(a_dup)
        a_pin = QAction("置顶 / 取消置顶", self)
        a_pin.triggered.connect(lambda: self._toggle_pin(pid))
        menu.addAction(a_pin)
        menu.addSeparator()
        a_del = QAction("删除", self)
        a_del.triggered.connect(lambda: self._delete_profile(pid))
        menu.addAction(a_del)
        menu.exec(self._list.mapToGlobal(pos))

    def _rename_profile(self, pid: str) -> None:
        p = self.engine.profile_store.get(pid)
        if not p:
            return
        name, ok = QInputDialog.getText(self, "重命名", "新名称", text=p.name)
        if not ok or not name.strip():
            return
        p.name = name.strip()
        self._persist(p)
        if pid == self._selected_pid:
            self._refresh_current_item_text(p)

    def _duplicate_profile(self, pid: str) -> None:
        p = self.engine.profile_store.get(pid)
        if not p:
            return
        new_p = Profile(
            id=uuid.uuid4().hex[:8],
            name=p.name + " 副本",
            processes=list(p.processes),
            window_title_regex=p.window_title_regex,
            window_class=p.window_class,
            pin=False,
            enabled=p.enabled,
            sensitivity=p.sensitivity,
            phrase_similarity=p.phrase_similarity,
            denoise=p.denoise,
            silence_lock_ms=p.silence_lock_ms,
            debounce_ms=p.debounce_ms,
            mouse_enabled=p.mouse_enabled,
            keyboard_enabled=p.keyboard_enabled,
            push_to_talk=p.push_to_talk,
            push_to_talk_key=p.push_to_talk_key,
            blacklisted_phrases=list(p.blacklisted_phrases),
            rules=[VoiceRule(**vars(r)) for r in p.rules],
        )
        save_profile(new_p)
        self._suspend_store_refresh = True
        try:
            self.engine.profile_store.reload()
        finally:
            self._suspend_store_refresh = False
        self._selected_pid = new_p.id
        self.refresh()

    def _toggle_pin(self, pid: str) -> None:
        p = self.engine.profile_store.get(pid)
        if not p:
            return
        p.pin = not p.pin
        self._persist(p)
        self.refresh()

    def _delete_profile(self, pid: str) -> None:
        p = self.engine.profile_store.get(pid)
        if not p:
            return
        ans = QMessageBox.question(self, "删除配置", f"确定删除「{p.name}」吗？此操作不可恢复。")
        if ans != QMessageBox.Yes:
            return
        if self._selected_pid == pid:
            self._selected_pid = None
        self.engine.profile_store.remove(pid)

    def on_show(self) -> None:
        self.refresh()
