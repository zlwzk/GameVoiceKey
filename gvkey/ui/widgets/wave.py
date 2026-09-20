"""波形控件（首页/主页用的大块波形）."""
from __future__ import annotations

import time
from typing import List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class BigWave(QWidget):
    BARS = 36

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._levels: List[float] = [0.0] * self.BARS
        self._decay_timer = QTimer(self)
        self._decay_timer.timeout.connect(self._decay)
        self._decay_timer.start(60)
        self.setMinimumHeight(72)

    def feed(self, level: float) -> None:
        level = max(0.0, min(1.0, float(level)))
        self._levels = self._levels[1:]
        self._levels.append(level)
        self.update()

    def _decay(self) -> None:
        self._levels = [max(0.0, x * 0.85 - 0.015) for x in self._levels]
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        n = len(self._levels)
        bar_w = (w - (n - 1) * 4) / n
        for i, lv in enumerate(self._levels):
            bh = max(3, lv * (h - 8))
            x = i * (bar_w + 4)
            y = (h - bh) / 2
            r = 4
            color = QColor(120 + int(110 * lv), 220, 200, 230)
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(int(x), int(y), max(3, int(bar_w)), int(bh), r, r)
