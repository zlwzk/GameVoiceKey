"""日志与统计页."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                                QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from ...engine import Engine
from ...logs import export_triggers, trigger_history, trigger_stats


class LogsPage(QWidget):
    def __init__(self, engine: Engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setObjectName("PageInner")
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(800)
        self._refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        title = QLabel("日志与统计")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        hint = QLabel("实时记录所有语音触发 + 系统状态日志，可导出 jsonl。")
        hint.setObjectName("PageHint")
        outer.addWidget(hint)

        # ====== 统计卡片 ======
        stats_row = QGridLayout()
        stats_row.setSpacing(14)

        self._n_total = QLabel("0"); self._l_total = QLabel("触发总数")
        self._n_success = QLabel("0"); self._l_success = QLabel("成功数")
        self._n_fail = QLabel("0"); self._l_fail = QLabel("失败数")
        self._n_rate = QLabel("—"); self._l_rate = QLabel("成功率")
        for n, l, c in (
            (self._n_total, self._l_total, 0),
            (self._n_success, self._l_success, 1),
            (self._n_fail, self._l_fail, 2),
            (self._n_rate, self._l_rate, 3),
        ):
            card = QFrame(); card.setObjectName("Card")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(20, 16, 20, 16)
            n.setObjectName("BigNumber"); l.setObjectName("BigNumberLabel")
            lay.addWidget(n); lay.addWidget(l)
            stats_row.addWidget(card, 0, c)
        outer.addLayout(stats_row)

        # ====== 触发记录 ======
        btns = QHBoxLayout()
        btns.addWidget(QLabel("最近触发记录："))
        btns.addStretch(1)
        btn_export = QPushButton("导出触发记录…")
        btn_export.setObjectName("Ghost")
        btn_export.clicked.connect(self._on_export)
        btns.addWidget(btn_export)
        btn_open_dir = QPushButton("打开日志目录")
        btn_open_dir.setObjectName("Ghost")
        btn_open_dir.clicked.connect(self._on_open_log_dir)
        btns.addWidget(btn_open_dir)
        outer.addLayout(btns)

        self._trigger_view = QPlainTextEdit()
        self._trigger_view.setReadOnly(True)
        self._trigger_view.setMaximumBlockCount(2000)
        outer.addWidget(self._trigger_view, 1)

        # ====== 系统日志 ======
        outer.addWidget(QLabel("系统日志（最近 200 条）："))
        from ..widgets.log_view import LogView
        self._sys_view = LogView(max_lines=300)
        outer.addWidget(self._sys_view, 1)

    def _refresh(self) -> None:
        s = trigger_stats()
        self._n_total.setText(str(s["total"]))
        self._n_success.setText(str(s["success"]))
        self._n_fail.setText(str(s["fail"]))
        if s["total"]:
            rate = round(s["success"] / s["total"] * 100)
            self._n_rate.setText(f"{rate}%")
        else:
            self._n_rate.setText("—")

        # 触发记录
        lines = []
        for e in trigger_history(400):
            mark = "✓" if e.get("success") else "✗"
            ts = e.get("ts", "")
            lines.append(f"[{ts}] {mark} [{e.get('profile','-')}]  「{e.get('phrase','')}」 → {e.get('key','')}")
        self._trigger_view.setPlainText("\n".join(lines))

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出", "triggers.jsonl", "JSON Lines (*.jsonl)")
        if not path:
            return
        try:
            export_triggers(path)
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "导出", f"已导出到：{path}")

    def _on_open_log_dir(self) -> None:
        from ...logs import logs_dir
        os.startfile(str(logs_dir())) if hasattr(os, "startfile") else None

    def on_show(self) -> None:
        self._refresh()
