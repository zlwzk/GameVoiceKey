"""语音按键自定义编辑页."""
from __future__ import annotations

import json
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                                QFileDialog, QHBoxLayout, QHeaderView,
                                QKeySequenceEdit, QLabel, QMessageBox, QPushButton,
                                QSpinBox, QTableWidget, QTableWidgetItem,
                                QVBoxLayout, QWidget)

from ...config import Profile, VoiceRule, load_profile, save_profile
from ...engine import Engine
from ..page_base import divider, hint, make_card

COL_ORDER = ["idx", "phrase", "keys", "mode", "hold_ms", "repeat_count",
             "interval_ms", "delay_ms", "cooldown_ms", "enabled", "note"]
COL_TITLES = ["#", "触发短语", "按键 / 组合键", "执行方式", "按住 ms",
              "连发次数", "间隔 ms", "延迟 ms", "冷却 ms", "启用", "备注"]

# 数值列统一固定宽度，避免 ResizeToContents 在编辑时来回抖动
_NUM_COL_WIDTH = 66


class EditorPage(QWidget):
    """规则表格页。

    这里刻意**不用** ScrollPage：表格需要占满剩余高度，套进滚动区反而会
    被压成一条。改为「固定标题 + 工具条 + 可伸缩表格」的骨架。
    """

    def __init__(self, engine: Engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setObjectName("PageInner")
        self._profile_id: Optional[str] = None
        # 编辑单元格时不触发「仓库变化 → 重建表格」，否则打字光标会被抢走
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

        title = QLabel("语音按键编辑")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        sub = hint("为每个游戏配置独立的语音 → 按键规则。没有保存按钮，改动实时写入配置文件。")
        outer.addWidget(sub)

        # ---- 当前游戏选择 ----
        card, box = make_card()
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(QLabel("当前游戏"))
        self._cmb_profile = QComboBox()
        self._cmb_profile.setMinimumWidth(260)
        self._cmb_profile.currentIndexChanged.connect(self._on_profile_changed)
        head.addWidget(self._cmb_profile, 1)
        self._lbl_count = QLabel("规则数：0")
        self._lbl_count.setObjectName("CardHint")
        head.addWidget(self._lbl_count)
        box.addLayout(head)
        outer.addWidget(card)

        # ---- 表格 ----
        self._table = QTableWidget()
        self._table.setColumnCount(len(COL_TITLES))
        self._table.setHorizontalHeaderLabels(COL_TITLES)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed
                                    | QTableWidget.SelectedClicked)
        self._table.setShowGrid(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 38)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self._table.setColumnWidth(3, 92)
        for col in (4, 5, 6, 7, 8):
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self._table.setColumnWidth(col, _NUM_COL_WIDTH)
        header.setSectionResizeMode(9, QHeaderView.Fixed)
        self._table.setColumnWidth(9, 52)
        header.setSectionResizeMode(10, QHeaderView.Stretch)
        header.setMinimumSectionSize(36)
        self._table.itemChanged.connect(self._on_item_changed)
        outer.addWidget(self._table, 1)

        # ---- 工具条 ----
        outer.addWidget(divider())

        bar = QHBoxLayout()
        bar.setSpacing(9)
        self._btn_add = QPushButton("+ 新增规则")
        self._btn_add.setObjectName("Primary")
        self._btn_add.clicked.connect(self._on_add_rule)
        bar.addWidget(self._btn_add)

        self._btn_capture = QPushButton("捕获按键…")
        self._btn_capture.setToolTip("按下键盘就能绑定，不用手打键名")
        self._btn_capture.clicked.connect(self._on_capture_then_add)
        bar.addWidget(self._btn_capture)

        self._btn_import = QPushButton("批量导入…")
        self._btn_import.setObjectName("Ghost")
        self._btn_import.clicked.connect(self._on_bulk_import)
        bar.addWidget(self._btn_import)

        self._btn_export = QPushButton("批量导出…")
        self._btn_export.setObjectName("Ghost")
        self._btn_export.clicked.connect(self._on_bulk_export)
        bar.addWidget(self._btn_export)

        self._btn_test = QPushButton("测试语音…")
        self._btn_test.setObjectName("Ghost")
        self._btn_test.clicked.connect(self._on_test)
        bar.addWidget(self._btn_test)

        bar.addStretch(1)

        self._btn_delete = QPushButton("删除选中")
        self._btn_delete.setObjectName("Ghost")
        self._btn_delete.clicked.connect(self._on_delete_selected)
        bar.addWidget(self._btn_delete)

        self._btn_clear = QPushButton("清空所有")
        self._btn_clear.setObjectName("Danger")
        self._btn_clear.clicked.connect(self._on_clear)
        bar.addWidget(self._btn_clear)
        outer.addLayout(bar)

        self._refresh_profiles()

    # ============================================================
    # 数据加载
    # ============================================================

    def load_profile(self, profile_id: str) -> None:
        """外部调用（首页选完游戏）：切到这个配置。"""

        self._refresh_profiles(select=profile_id)

    def _on_store_changed(self, _profiles) -> None:
        if self._suspend_store_refresh:
            return
        self._refresh_profiles()

    def _refresh_profiles(self, select: Optional[str] = None) -> None:
        """重建下拉框，尽量保留当前选中的配置。"""

        target = select or self._profile_id
        profiles = self.engine.profile_store.all()

        self._cmb_profile.blockSignals(True)
        self._cmb_profile.clear()
        for p in profiles:
            self._cmb_profile.addItem(f"{p.name}   ({p.id[:4]})", p.id)

        index = -1
        if target:
            for i in range(self._cmb_profile.count()):
                if self._cmb_profile.itemData(i) == target:
                    index = i
                    break
        if index < 0 and profiles:
            index = 0
        self._cmb_profile.setCurrentIndex(index)
        self._cmb_profile.blockSignals(False)

        self._profile_id = self._cmb_profile.currentData() if index >= 0 else None
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
            if p is not None:
                self.engine.profile_store.reload()
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

        item_idx = QTableWidgetItem(str(idx + 1))
        item_idx.setFlags(item_idx.flags() & ~Qt.ItemIsEditable)
        item_idx.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(r, 0, item_idx)

        self._table.setItem(r, 1, QTableWidgetItem(rule.phrase))
        self._table.setItem(r, 2, QTableWidgetItem(", ".join(rule.keys)))

        cmb = QComboBox()
        cmb.addItems(["single", "hold", "repeat"])
        cmb.setCurrentText(rule.mode)
        cmb.currentTextChanged.connect(
            lambda v, row=r: self._on_widget_changed(row, "mode", v)
        )
        self._table.setCellWidget(r, 3, cmb)

        for col, key in ((4, "hold_ms"), (5, "repeat_count"), (6, "interval_ms"),
                          (7, "delay_ms"), (8, "cooldown_ms")):
            sp = QSpinBox()
            sp.setRange(0, 60000)
            sp.setValue(int(getattr(rule, key)))
            # 单位在表头，框内只有数字
            sp.valueChanged.connect(
                lambda v, row=r, k=key: self._on_widget_changed(row, k, int(v))
            )
            self._table.setCellWidget(r, col, sp)

        ck = QCheckBox()
        ck.setChecked(rule.enabled)
        ck.toggled.connect(
            lambda v, row=r: self._on_widget_changed(row, "enabled", bool(v))
        )
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(ck)
        self._table.setCellWidget(r, 9, wrap)

        self._table.setItem(r, 10, QTableWidgetItem(rule.note))

    # ============================================================
    # 表格编辑（实时落盘，但不重建表格）
    # ============================================================

    def _persist(self, profile: Profile) -> None:
        """落盘但**不**通知仓库，避免「改动 → 重建表格 → 光标丢失」死循环。"""

        self._suspend_store_refresh = True
        try:
            save_profile(profile)
        finally:
            self._suspend_store_refresh = False

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
        self._persist(p)

    def _on_widget_changed(self, row: int, key: str, value) -> None:
        p = self._current_profile()
        if p is None or row >= len(p.rules):
            return
        current = getattr(p.rules[row], key)
        if current == value:
            return
        setattr(p.rules[row], key, value)
        self._persist(p)

    # ============================================================
    # 操作
    # ============================================================

    def _require_profile(self) -> Optional[Profile]:
        p = self._current_profile()
        if p is None:
            QMessageBox.information(
                self, "还没有配置",
                "请先到「首页 → 选择当前游玩的游戏」，或到「游戏配置」页新建一个配置。",
            )
        return p

    def _after_rules_changed(self, profile: Profile) -> None:
        save_profile(profile)
        self.engine.profile_store.reload()
        self._reload_table()

    def _on_add_rule(self) -> None:
        p = self._require_profile()
        if p is None:
            return
        p.rules.append(VoiceRule(phrase="新短语"))
        self._after_rules_changed(p)
        self._table.setCurrentCell(self._table.rowCount() - 1, 1)
        self._table.editItem(self._table.item(self._table.rowCount() - 1, 1))

    def _on_capture_then_add(self) -> None:
        """用 QKeySequenceEdit 真按键捕获，不让用户手打键名。"""

        from ...keyboard_sim import parse_key

        p = self._require_profile()
        if p is None:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("捕获按键")
        dialog.setMinimumWidth(360)
        lay = QVBoxLayout(dialog)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("按下要绑定的按键（支持 Ctrl / Alt / Shift 组合）"))
        edit = QKeySequenceEdit()
        edit.setClearButtonEnabled(True)
        lay.addWidget(edit)
        tip = hint("例：按下 R 就是 R；按住 Ctrl 再按 1 就是 Ctrl+1。")
        lay.addWidget(tip)

        row = QHBoxLayout()
        row.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("Ghost")
        btn_cancel.clicked.connect(dialog.reject)
        row.addWidget(btn_cancel)
        btn_ok = QPushButton("确定")
        btn_ok.setObjectName("Primary")
        btn_ok.clicked.connect(dialog.accept)
        row.addWidget(btn_ok)
        lay.addLayout(row)

        if dialog.exec() != QDialog.Accepted:
            return

        seq: QKeySequence = edit.keySequence()
        text = seq.toString()
        if not text:
            return
        parsed = parse_key(text)
        if parsed.key == "" and not parsed.is_mouse and not parsed.is_wheel:
            QMessageBox.warning(self, "无法识别", f"「{text}」这个按键暂时不支持。")
            return

        p.rules.append(VoiceRule(phrase="新短语", keys=[text], mode="single"))
        self._after_rules_changed(p)

    def _on_delete_selected(self) -> None:
        p = self._require_profile()
        if p is None:
            return
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "删除", "请先在表格里选中要删除的行。")
            return
        for r in rows:
            if r < len(p.rules):
                p.rules.pop(r)
        self._after_rules_changed(p)

    def _on_clear(self) -> None:
        p = self._require_profile()
        if p is None:
            return
        if not p.rules:
            return
        if QMessageBox.question(self, "确认", f"清空「{p.name}」的全部 {len(p.rules)} 条规则？") != QMessageBox.Yes:
            return
        p.rules.clear()
        self._after_rules_changed(p)

    def _on_bulk_import(self) -> None:
        p = self._require_profile()
        if p is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "批量导入", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.loads(fh.read())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "导入失败", str(exc))
            return

        added = 0
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("rules", [])
        else:
            items = []
        for it in items:
            if not isinstance(it, dict) or not it.get("phrase") or not it.get("keys"):
                continue
            fields = {
                k: it.get(k, getattr(VoiceRule(), k))
                for k in ("phrase", "keys", "mode", "hold_ms", "repeat_count",
                          "interval_ms", "delay_ms", "cooldown_ms", "enabled", "note")
            }
            try:
                p.rules.append(VoiceRule(**fields))
            except Exception:  # noqa: BLE001
                continue
            added += 1

        self._after_rules_changed(p)
        QMessageBox.information(self, "导入完成", f"已新增 {added} 条规则。")

    def _on_bulk_export(self) -> None:
        p = self._require_profile()
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
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False, indent=2))
            QMessageBox.information(self, "导出", f"已导出 {len(p.rules)} 条规则。")
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def _on_test(self) -> None:
        p = self._require_profile()
        if not p:
            return
        if not p.rules:
            QMessageBox.information(self, "测试语音", "这个配置还没有规则，先加一条。")
            return
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(self, "测试语音",
                                        "输入一句测试短语，会立即判断会触发哪条规则：",
                                        text=p.rules[0].phrase)
        if not ok or not text.strip():
            return
        m = self.engine.matcher.find(text, p)
        if m:
            rule, _phrase, score = m
            QMessageBox.information(
                self, "命中",
                f"会触发：\n  「{rule.phrase}」\n  按键：{', '.join(rule.keys)}\n"
                f"  模式：{rule.mode}\n  相似度：{score:.2f}",
            )
        else:
            QMessageBox.information(self, "未命中", "没有匹配的规则。")

    # ============================================================

    def on_show(self) -> None:
        self._reload_table()
