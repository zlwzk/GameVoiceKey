"""简易滚动日志视图."""
from __future__ import annotations

import time
from collections import deque
from typing import Deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


class LogView(QPlainTextEdit):
    """只读、彩色、自动滚到底."""

    def __init__(self, max_lines: int = 500, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_lines)
        self.setFont(QFont("Consolas, Microsoft YaHei", 10))
        self.setStyleSheet("background: transparent; border: none;")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(200)

    def append(self, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        color = "#7CCAB1" if text.startswith("✓") else "#E6B660" if text.startswith("✗") else "#a3b3ac"
        html = (
            f"<span style='color:#7d8e87'>{ts}</span> "
            f"<span style='color:{color}'>{text}</span>"
        )
        self.appendHtml(html)
        cur = self.textCursor()
        cur.movePosition(QTextCursor.End)
        self.setTextCursor(cur)

    def _poll(self) -> None:
        pass
