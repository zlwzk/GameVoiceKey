"""语音按键自定义编辑页."""
from __future__ import annotations

import json
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                                QFrame, QGroupBox, QHBoxLayout, QHeaderView,
                                QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
                                QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                                QVBoxLayout, QWidget)

from ...config import Profile, VoiceRule, save_profile, load_profile
from ...engine import Engine


COL_ORDER = ["idx", "phrase", "keys", "mode", "hold_ms", "repeat_count",
             "interval_ms", "delay_ms", "cooldown_ms", "enabled", "note"]
COL_TITLES = ["#", "触发短语", "按键 / 组合键", "执行方式", "按住 ms",
              "连发次数", "间隔 ms", "延迟 ms", "冷却 ms", "启用", "备注"]


class EditorPage(QWidget):
    def __init__(self, engine: Engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setObjectName("PageInner")
        self._profile_id: Optional[str] = None
        self._build()

        engine.profile_store.subscribe(lambda _: self._refresh_profiles())

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        title = QLabel("语音按键自定义")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        hint = QLabel("为每个游戏配置独立的语音→按键规则，无需保存按钮，所有改动都会实时落盘。")
        hint.setObjectName("PageHint")
        outer.addWidget(hint)

        # === 顶部：选择 Profile ===
        head = QHBoxLayout()
        head.addWidget(QLabel("当前游戏："))
        self._cmb_profile = QComboBox()
        self._cmb_profile.currentIndexChanged.connect(self._on_profile_changed)
        head.addWidget(self._cmb_profile)
        head.addStretch(1)
        self._lbl_count = QLabel("规则数：0")
        head.addWidget(self._lbl_count)
        outer.addLayout(head)

        # === 表格 ===
        self._table = QTableWidget()
        self._table.setColumnCount(len(COL_TITLES))
        self._table.setHorizontalHeaderLabels(COL_TITLES)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self._table.horizontalHeader()
        for i in range(len(COL_TITLES)):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.itemChanged.connect(self._on_item_changed)
        outer.addWidget(self._table, 1)

        # === 底部按钮 ===
        btns = QHBoxLayout()
        self._btn_add = QPushButton("+ 新增规则")
        self._btn_add.setObjectName("Primary")
        self._btn_add.clicked.connect(self._on_add_rule)
        btns.addWidget(self._btn_add)

        self._btn_add_capture = QPushButton("捕获按键 → 新规则")
        self._btn_add_capture.clicked.connect(self._on_capture_then_add)
        btns.addWidget(self._btn_add_capture)

        self._btn_bulk = QPushButton("批量导入…")
        self._btn_bulk.clicked.connect(self._on_bulk_import)
        btns.addWidget(self._btn_bulk)

        self._btn_export = QPushButton("批量导出…")
        self._btn_export.setObjectName("Ghost")
        self._btn_export.clicked.connect(self._on_bulk_export)
        btns.addWidget(self._btn_export)

        self._btn_test = QPushButton("测试语音…")
        self._btn_test.setObjectName("Ghost")
        self._btn_test.clicked.connect(self._on_test)
        btns.addWidget(self._btn_test)

        self._btn_clear = QPushButton("清空所有")
        self._btn_clear.setObjectName("Danger")
        self._btn_clear.clicked.connect(self._on_clear)
        btns.addWidget(self._btn_clear)

        btns.addStretch(1)
        self._btn_delete = QPushButton("删除选中")
        self._btn_delete.clicked.connect(self._on_delete_selected)
        btns.addWidget(self._btn_delete)
        outer.addLayout(btns)

        self._refresh_profiles()

    # ----- 数据加载 -----

    def _refresh_profiles(self) -> None:
        profiles = self.engine.profile_store.all()
        self._cmb_profile.blockSignals(True)
        self._cmb_profile.clear()
        for p in profiles:
            self._cmb_profile.addItem(f"{p.name}  ({p.id[:4]})", p.id)
        if profiles:
            self._cmb_profile.setCurrentIndex(0)
        self._cmb_profile.blockSignals(False)
        self._reload_table()

    def _current_profile(self) -> Optional[Profile]:
        if self._cmb_profile.count() == 0:
            self._profile_id = None
            return None
        pid = self._cmb_profile.currentData()
        self._profile_id = pid
        p = self.engine.profile_store.get(pid)
        if p is None:
            p = load_profile(pid)
        return p

    def _on_profile_changed(self, _idx: int) -> None:
        self._reload_table()

    def _reload_table(self) -> None:
        p = self._current_profile()
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        if p is None:
            self._lbl_count.setText("规则数：0")
            self._table.blockSignals(False)
            return
        for i, rule in enumerate(p.rules):
            self._add_row(i, rule)
        self._lbl_count.setText(f"规则数：{len(p.rules)}")
        self._table.blockSignals(False)

    def _add_row(self, idx: int, rule: VoiceRule) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        # 序号
        item_idx = QTableWidgetItem(str(idx + 1))
        item_idx.setFlags(item_idx.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(r, 0, item_idx)
        # 短语
        self._table.setItem(r, 1, QTableWidgetItem(rule.phrase))
        # 按键
        self._table.setItem(r, 2, QTableWidgetItem(", ".join(rule.keys)))
        # 模式（下拉）
        cmb = QComboBox()
        cmb.addItems(["single", "hold", "repeat"])
        cmb.setCurrentText(rule.mode)
        cmb.currentTextChanged.connect(lambda v, row=r: self._on_combo_changed(row, "mode", v))
        self._table.setCellWidget(r, 3, cmb)
        # 数值
        for col, key in ((4, "hold_ms"), (5, "repeat_count"), (6, "interval_ms"),
                          (7, "delay_ms"), (8, "cooldown_ms")):
            sp = QSpinBox()
            sp.setRange(0, 60000)
            sp.setValue(int(getattr(rule, key)))
            sp.valueChanged.connect(lambda v, row=r, k=key: self._on_spin_changed(row, k, int(v)))
            self._table.setCellWidget(r, col, sp)
        # 启用 checkbox
        ck = QCheckBox()
        ck.setChecked(rule.enabled)
        ck.toggled.connect(lambda v, row=r: self._on_check_changed(row, "enabled", bool(v)))
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(ck)
        self._table.setCellWidget(r, 9, wrap)
        # 备注
        self._table.setItem(r, 10, QTableWidgetItem(rule.note))

    # ----- 表格编辑 -----

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        p = self._current_profile()
        if p is None or item.row() >= len(p.rules):
            return
        col = item.column()
        text = item.text()
        rule = p.rules[item.row()]
        if col == 1:
            rule.phrase = text.strip()
        elif col == 2:
            rule.keys = [x.strip() for x in text.split(",") if x.strip()]
        elif col == 10:
            rule.note = text.strip()
        else:
            return
        self.engine.profile_store.upsert(p)

    def _on_combo_changed(self, row: int, key: str, value: str) -> None:
        p = self._current_profile()
        if p is None or row >= len(p.rules):
            return
        setattr(p.rules[row], key, value)
        self.engine.profile_store.upsert(p)

    def _on_spin_changed(self, row: int, key: str, value: int) -> None:
        p = self._current_profile()
        if p is None or row >= len(p.rules):
            return
        setattr(p.rules[row], key, int(value))
        self.engine.profile_store.upsert(p)

    def _on_check_changed(self, row: int, key: str, value: bool) -> None:
        p = self._current_profile()
        if p is None or row >= len(p.rules):
            return
        setattr(p.rules[row], key, bool(value))
        self.engine.profile_store.upsert(p)

    # ----- 操作 -----

    def _on_add_rule(self) -> None:
        p = self._current_profile()
        if p is None:
            QMessageBox.information(self, "提示", "请先在游戏配置管理页创建一个游戏配置。")
            return
        new_rule = VoiceRule(phrase="新短语")
        p.rules.append(new_rule)
        save_profile(p)
        self.engine.profile_store.reload()
        self._reload_table()

    def _on_capture_then_add(self) -> None:
        from ...keyboard_sim import parse_key
        key_text, ok = QInputDialog.getText(self, "捕获按键", "按下要绑定的按键（中文描述，如 Ctrl+1）")
        if not ok or not key_text.strip():
            return
        parsed = parse_key(key_text.strip())
        if parsed.key == "" and not parsed.is_mouse and not parsed.is_wheel:
            QMessageBox.warning(self, "无法识别", "按键字符串格式不正确。")
            return
        p = self._current_profile()
        if p is None:
            return
        new_rule = VoiceRule(phrase="新短语", keys=[key_text.strip()], mode="single")
        p.rules.append(new_rule)
        save_profile(p)
        self.engine.profile_store.reload()
        self._reload_table()

    def _on_delete_selected(self) -> None:
        p = self._current_profile()
        if p is None:
            return
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for r in rows:
            if r < len(p.rules):
                p.rules.pop(r)
        save_profile(p)
        self.engine.profile_store.reload()
        self._reload_table()

    def _on_clear(self) -> None:
        p = self._current_profile()
        if p is None:
            return
        if QMessageBox.question(self, "确认", f"清空「{p.name}」的全部 {len(p.rules)} 条规则？") != QMessageBox.Yes:
            return
        p.rules.clear()
        save_profile(p)
        self.engine.profile_store.reload()
        self._reload_table()

    def _on_bulk_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "批量导入", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(open(path, "r", encoding="utf-8").read())
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        p = self._current_profile()
        if p is None:
            return
        added = 0
        if isinstance(data, list):
            for it in data:
                if isinstance(it, dict) and it.get("phrase") and it.get("keys"):
                    p.rules.append(VoiceRule(
                        phrase=str(it.get("phrase", "")),
                        keys=[str(k) for k in it.get("keys", [])],
                        mode=it.get("mode", "single"),
                        hold_ms=int(it.get("hold_ms", 80)),
                        repeat_count=int(it.get("repeat_count", 1)),
                        interval_ms=int(it.get("interval_ms", 50)),
                        delay_ms=int(it.get("delay_ms", 0)),
                        cooldown_ms=int(it.get("cooldown_ms", 250)),
                        enabled=bool(it.get("enabled", True)),
                        note=str(it.get("note", "")),
                    ))
                    added += 1
        elif isinstance(data, dict) and "rules" in data:
            for it in data.get("rules", []):
                if isinstance(it, dict) and it.get("phrase") and it.get("keys"):
                    p.rules.append(VoiceRule(
                        **{
                            k: it.get(k, getattr(VoiceRule(), k))
                            for k in ("phrase", "keys", "mode", "hold_ms",
                                       "repeat_count", "interval_ms", "delay_ms",
                                       "cooldown_ms", "enabled", "note")
                        }
                    ))
                    added += 1
        save_profile(p)
        self.engine.profile_store.reload()
        self._reload_table()
        QMessageBox.information(self, "导入完成", f"已新增 {added} 条规则。")

    def _on_bulk_export(self) -> None:
        p = self._current_profile()
        if p is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "批量导出", f"{p.name}-rules.json",
                                              "JSON (*.json)")
        if not path:
            return
        try:
            payload = [{
                "phrase": r.phrase,
                "phrases": r.phrases,
                "keys": r.keys,
                "mode": r.mode,
                "hold_ms": r.hold_ms,
                "repeat_count": r.repeat_count,
                "interval_ms": r.interval_ms,
                "delay_ms": r.delay_ms,
                "cooldown_ms": r.cooldown_ms,
                "enabled": r.enabled,
                "note": r.note,
            } for r in p.rules]
            open(path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=2))
            QMessageBox.information(self, "导出", f"已导出 {len(p.rules)} 条规则。")
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def _on_test(self) -> None:
        p = self._current_profile()
        if not p:
            return
        text, ok = QInputDialog.getText(self, "测试语音",
                                         "输入一句测试短语，会立即判断会触发哪条规则：",
                                         text=p.rules[0].phrase if p.rules else "")
        if not ok or not text.strip():
            return
        m = self.engine.matcher.find(text, p)
        if m:
            rule, phrase, score = m
            QMessageBox.information(
                self, "命中",
                f"会触发：\n  「{rule.phrase}」\n  按键：{', '.join(rule.keys)}\n  模式：{rule.mode}\n  相似度：{score:.2f}",
            )
        else:
            QMessageBox.information(self, "未命中", "没有匹配的规则。")

    def on_show(self) -> None:
        self._reload_table()
