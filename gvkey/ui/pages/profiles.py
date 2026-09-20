"""游戏配置管理页."""
from __future__ import annotations

import uuid
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout,
                                QInputDialog, QLabel, QLineEdit, QListWidget,
                                QListWidgetItem, QMenu, QMessageBox, QPushButton,
                                QSplitter, QToolButton, QVBoxLayout, QWidget)

from ...config import Profile, VoiceRule, import_profile, export_profile, save_profile
from ...engine import Engine


class ProfilesPage(QWidget):
    def __init__(self, engine: Engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setObjectName("PageInner")
        self._selected_pid: Optional[str] = None
        self._build()

        # 监听 profile store
        engine.profile_store.subscribe(lambda _: self.refresh())

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        title = QLabel("游戏配置管理")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        hint = QLabel("左侧是已配置的游戏；右侧是该游戏的详细参数。")
        hint.setObjectName("PageHint")
        outer.addWidget(hint)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, 1)

        # === 左：游戏列表 ===
        left = QFrame()
        left.setObjectName("Card")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 14, 14, 14)
        ll.setSpacing(8)

        head = QHBoxLayout()
        h_title = QLabel("游戏列表")
        h_title.setObjectName("CardTitle")
        head.addWidget(h_title)
        head.addStretch(1)
        btn_new = QPushButton("+ 新建配置")
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

        splitter.addWidget(left)

        # === 右：详情面板 ===
        right = QFrame()
        right.setObjectName("CardMid")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(20, 18, 20, 18)
        rl.setSpacing(12)

        self._lbl_name = QLabel("未选中游戏")
        self._lbl_name.setObjectName("CardTitle")
        rl.addWidget(self._lbl_name)

        # 基础信息
        base_box = QGroupBox("基础信息")
        bl = QVBoxLayout(base_box)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("游戏名称"))
        self._ed_name = QLineEdit()
        self._ed_name.editingFinished.connect(self._save_field)
        row1.addWidget(self._ed_name, 1)
        bl.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("进程名（逗号分隔）"))
        self._ed_proc = QLineEdit()
        self._ed_proc.setPlaceholderText("例如 csgo, hl2")
        self._ed_proc.editingFinished.connect(self._save_field)
        row2.addWidget(self._ed_proc, 1)
        bl.addLayout(row2)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("窗口标题正则"))
        self._ed_title = QLineEdit()
        self._ed_title.setPlaceholderText("可选，例如 Counter-Strike")
        self._ed_title.editingFinished.connect(self._save_field)
        row3.addWidget(self._ed_title, 1)
        bl.addLayout(row3)
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("窗口类名"))
        self._ed_cls = QLineEdit()
        self._ed_cls.editingFinished.connect(self._save_field)
        row4.addWidget(self._ed_cls, 1)
        bl.addLayout(row4)
        rl.addWidget(base_box)

        # 全局开关
        gb_box = QGroupBox("该游戏开关")
        gl = QVBoxLayout(gb_box)
        self._ck_enabled = QCheckBox("启用此游戏的语音控制")
        self._ck_enabled.stateChanged.connect(self._save_checkbox)
        gl.addWidget(self._ck_enabled)
        self._ck_pin = QCheckBox("置顶（多开时优先）")
        self._ck_pin.stateChanged.connect(self._save_checkbox)
        gl.addWidget(self._ck_pin)
        self._ck_ptt = QCheckBox("按住说话模式")
        self._ck_ptt.stateChanged.connect(self._save_checkbox)
        gl.addWidget(self._ck_ptt)
        ptt_row = QHBoxLayout()
        ptt_row.addWidget(QLabel("按住说话键"))
        self._ed_ptt = QLineEdit()
        self._ed_ptt.setPlaceholderText("例如 Ctrl+Space")
        self._ed_ptt.editingFinished.connect(self._save_field)
        ptt_row.addWidget(self._ed_ptt, 1)
        gl.addLayout(ptt_row)
        rl.addWidget(gb_box)

        # 识别参数
        ip_box = QGroupBox("识别参数")
        il = QVBoxLayout(ip_box)
        row_sens = QHBoxLayout()
        row_sens.addWidget(QLabel("灵敏度"))
        from PySide6.QtWidgets import QDoubleSpinBox
        self._sp_sens = QDoubleSpinBox()
        self._sp_sens.setRange(0.0, 1.0)
        self._sp_sens.setSingleStep(0.05)
        self._sp_sens.setDecimals(2)
        self._sp_sens.valueChanged.connect(lambda v: self._save_numeric("sensitivity", float(v)))
        row_sens.addWidget(self._sp_sens)
        row_sens.addStretch(1)
        il.addLayout(row_sens)
        row_sim = QHBoxLayout()
        row_sim.addWidget(QLabel("词相似度阈值"))
        self._sp_sim = QDoubleSpinBox()
        self._sp_sim.setRange(0.0, 1.0)
        self._sp_sim.setSingleStep(0.05)
        self._sp_sim.setDecimals(2)
        self._sp_sim.valueChanged.connect(lambda v: self._save_numeric("phrase_similarity", float(v)))
        row_sim.addWidget(self._sp_sim)
        row_sim.addStretch(1)
        il.addLayout(row_sim)
        self._ck_denoise = QCheckBox("降噪")
        self._ck_denoise.stateChanged.connect(self._save_checkbox)
        il.addWidget(self._ck_denoise)
        self._ck_mouse = QCheckBox("启用鼠标映射")
        self._ck_mouse.stateChanged.connect(self._save_checkbox)
        il.addWidget(self._ck_mouse)
        self._ck_kbd = QCheckBox("启用键盘映射")
        self._ck_kbd.stateChanged.connect(self._save_checkbox)
        il.addWidget(self._ck_kbd)
        rl.addWidget(ip_box)

        # 操作按钮
        btns = QHBoxLayout()
        self._btn_save = QPushButton("应用")
        self._btn_save.setObjectName("Primary")
        self._btn_save.clicked.connect(self._save_explicit)
        btns.addWidget(self._btn_save)
        btns.addStretch(1)
        self._btn_export = QPushButton("导出当前…")
        self._btn_export.setObjectName("Ghost")
        self._btn_export.clicked.connect(self._on_export)
        btns.addWidget(self._btn_export)
        self._btn_rules = QPushButton("进入规则编辑页 →")
        self._btn_rules.clicked.connect(lambda: self.parent().parent().goto("语音按键编辑"))
        btns.addWidget(self._btn_rules)
        rl.addLayout(btns)

        rl.addStretch(1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        self.refresh()

    # ----- 数据交互 -----

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
        if self._selected_pid and self.engine.profile_store.get(self._selected_pid):
            # 重选
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.UserRole) == self._selected_pid:
                    self._list.setCurrentRow(i)
                    break
        elif self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._show_empty()

    def _show_empty(self) -> None:
        self._lbl_name.setText("未选中游戏")
        for w in (self._ed_name, self._ed_proc, self._ed_title, self._ed_cls, self._ed_ptt):
            w.blockSignals(True)
            w.setText("")
            w.blockSignals(False)
        self._ck_enabled.setChecked(False)
        self._ck_pin.setChecked(False)
        self._ck_ptt.setChecked(False)
        self._sp_sens.setValue(0.5)
        self._sp_sim.setValue(0.7)

    def _on_selection_changed(self) -> None:
        item = self._list.currentItem()
        if not item:
            self._selected_pid = None
            return
        self._selected_pid = item.data(Qt.UserRole)
        p = self.engine.profile_store.get(self._selected_pid)
        if not p:
            return
        self._lbl_name.setText(f"配置 - {p.name}")
        # 填充
        self._ed_name.blockSignals(True); self._ed_name.setText(p.name); self._ed_name.blockSignals(False)
        self._ed_proc.blockSignals(True); self._ed_proc.setText(", ".join(p.processes)); self._ed_proc.blockSignals(False)
        self._ed_title.blockSignals(True); self._ed_title.setText(p.window_title_regex); self._ed_title.blockSignals(False)
        self._ed_cls.blockSignals(True); self._ed_cls.setText(p.window_class); self._ed_cls.blockSignals(False)
        self._ed_ptt.blockSignals(True); self._ed_ptt.setText(p.push_to_talk_key); self._ed_ptt.blockSignals(False)
        self._ck_enabled.blockSignals(True); self._ck_enabled.setChecked(p.enabled); self._ck_enabled.blockSignals(False)
        self._ck_pin.blockSignals(True); self._ck_pin.setChecked(p.pin); self._ck_pin.blockSignals(False)
        self._ck_ptt.blockSignals(True); self._ck_ptt.setChecked(p.push_to_talk); self._ck_ptt.blockSignals(False)
        self._ck_denoise.blockSignals(True); self._ck_denoise.setChecked(p.denoise); self._ck_denoise.blockSignals(False)
        self._ck_mouse.blockSignals(True); self._ck_mouse.setChecked(p.mouse_enabled); self._ck_mouse.blockSignals(False)
        self._ck_kbd.blockSignals(True); self._ck_kbd.setChecked(p.keyboard_enabled); self._ck_kbd.blockSignals(False)
        self._sp_sens.blockSignals(True); self._sp_sens.setValue(p.sensitivity); self._sp_sens.blockSignals(False)
        self._sp_sim.blockSignals(True); self._sp_sim.setValue(p.phrase_similarity); self._sp_sim.blockSignals(False)

    def _save_field(self) -> None:
        p = self._current_profile()
        if not p:
            return
        p.name = self._ed_name.text().strip() or "未命名"
        p.processes = [x.strip() for x in self._ed_proc.text().split(",") if x.strip()]
        p.window_title_regex = self._ed_title.text().strip()
        p.window_class = self._ed_cls.text().strip()
        p.push_to_talk_key = self._ed_ptt.text().strip()
        self.engine.profile_store.upsert(p)
        self.refresh()

    def _save_numeric(self, key: str, value) -> None:
        p = self._current_profile()
        if not p:
            return
        setattr(p, key, value)
        self.engine.profile_store.upsert(p)

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
        self.engine.profile_store.upsert(p)

    def _save_explicit(self) -> None:
        self._save_field()

    def _current_profile(self) -> Optional[Profile]:
        if not self._selected_pid:
            return None
        return self.engine.profile_store.get(self._selected_pid)

    # ----- 操作 -----

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(self, "新建配置", "游戏名称")
        if not ok or not name.strip():
            return
        proc, ok = QInputDialog.getText(self, "新建配置", "进程名（不含 .exe，多个用逗号）")
        if not ok:
            proc = ""
        p = Profile(name=name.strip(),
                     processes=[x.strip() for x in proc.split(",") if x.strip()])
        save_profile(p)
        self.engine.profile_store.reload()

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入游戏配置", "", "JSON (*.json);;所有文件 (*.*)")
        if not path:
            return
        try:
            text = open(path, "r", encoding="utf-8").read()
        except OSError as exc:
            QMessageBox.warning(self, "导入失败", f"读取文件失败：{exc}")
            return
        p = import_profile(text)
        if not p:
            QMessageBox.warning(self, "导入失败", "文件格式不正确或内容不完整。")
            return
        save_profile(p)
        self.engine.profile_store.reload()
        QMessageBox.information(self, "导入成功", f"已新增配置：{p.name}")

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
            open(path, "w", encoding="utf-8").write(export_profile(p))
            QMessageBox.information(self, "导出", f"已导出到 {path}")
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        a_edit = QAction("编辑配置名", self)
        a_edit.triggered.connect(lambda: self._rename_profile(item.data(Qt.UserRole)))
        menu.addAction(a_edit)
        a_dup = QAction("复制配置", self)
        a_dup.triggered.connect(lambda: self._duplicate_profile(item.data(Qt.UserRole)))
        menu.addAction(a_dup)
        a_pin = QAction("置顶/取消置顶", self)
        a_pin.triggered.connect(lambda: self._toggle_pin(item.data(Qt.UserRole)))
        menu.addAction(a_pin)
        a_del = QAction("删除", self)
        a_del.triggered.connect(lambda: self._delete_profile(item.data(Qt.UserRole)))
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
        self.engine.profile_store.upsert(p)

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
        self.engine.profile_store.reload()

    def _toggle_pin(self, pid: str) -> None:
        p = self.engine.profile_store.get(pid)
        if not p:
            return
        p.pin = not p.pin
        self.engine.profile_store.upsert(p)

    def _delete_profile(self, pid: str) -> None:
        p = self.engine.profile_store.get(pid)
        if not p:
            return
        ans = QMessageBox.question(self, "删除配置", f"确定删除「{p.name}」吗？此操作不可恢复。")
        if ans != QMessageBox.Yes:
            return
        self.engine.profile_store.remove(pid)

    def on_show(self) -> None:
        self.refresh()
