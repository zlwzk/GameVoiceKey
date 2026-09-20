"""游戏内悬浮窗.

- 半透明 QWidget，置顶，无焦点，点击穿透（可选）
- 三种显示模式：compact / standard / full
- 指示灯颜色：green=active / yellow=paused / gray=idle / red=disabled
- 接收 engine 事件来更新内容

实现细节：
- 浮动在屏幕右上角（可拖拽粘边）
- 使用 WindowStaysOnTopHint + Tool（不在任务栏）+ Frameless
- WS_EX_TRANSPARENT 通过 gvkey.windows.apply_click_through 切换
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget)

from .config import Settings
from .windows import (apply_click_through, is_current_fullscreen,
                       set_window_pos_topmost)


class DotIndicator(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = QColor("#7be29a")
        self._border = QColor("#113322")
        self.setFixedSize(16, 16)

    def set_state(self, state: str) -> None:
        color_map = {
            "active": QColor("#7be29a"),
            "paused": QColor("#ffcb6b"),
            "muted": QColor("#c0c0c0"),
            "disabled": QColor("#e06c75"),
            "idle": QColor("#777777"),
            "stopped": QColor("#555555"),
            "running": QColor("#7be29a"),
            "energy-only": QColor("#a3c9b6"),
        }
        self._color = color_map.get(state, QColor("#7be29a"))
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = min(self.width(), self.height()) // 2 - 1
        cx, cy = self.width() // 2, self.height() // 2
        p.setPen(QPen(self._border, 1))
        p.setBrush(self._color)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 90))
        p.drawEllipse(cx - r // 2 - 1, cy - r // 2 - 1, r, r)


class WaveBar(QWidget):
    BARS = 14

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._levels = [0.0] * self.BARS
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._decay)
        self._timer.start(80)
        self.setMinimumWidth(80)
        self.setMaximumHeight(28)

    def feed(self, level: float) -> None:
        level = max(0.0, min(1.0, level))
        self._levels.pop(0)
        self._levels.append(level)
        self.update()

    def _decay(self) -> None:
        self._levels = [max(0.0, x * 0.7 - 0.02) for x in self._levels]
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        n = len(self._levels)
        w = self.width() / max(1, n)
        for i, lv in enumerate(self._levels):
            h = max(2, lv * self.height())
            x = i * w + 1
            y = (self.height() - h) / 2
            color = QColor(120 + int(100 * lv), 220, 200, 220)
            p.fillRect(int(x), int(y), max(2, int(w - 2)), int(h), color)


class OverlayWindow(QWidget):

    def __init__(self, settings: Settings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(self._settings.overlay_opacity)
        self._build_ui()
        self._last_trigger_at = 0.0
        self._saved_mode: Optional[str] = None

        self._poll_fs = QTimer(self)
        self._poll_fs.timeout.connect(self._check_fullscreen)
        self._poll_fs.start(800)

        self._dragging = False
        self._global_press: Optional[QPoint] = None
        self._press_pos: Optional[QPoint] = None

        self._snap_to(self._settings.overlay_position)
        self._refresh_mode()
        self._apply_click_through(self._settings.overlay_click_through)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6)
        root.setSpacing(10)

        self._dot = DotIndicator(self)
        root.addWidget(self._dot, 0, Qt.AlignVCenter)

        self._wave = WaveBar(self)
        root.addWidget(self._wave, 0, Qt.AlignVCenter)

        self._text_box = QFrame(self)
        self._text_box.setObjectName("TextBox")
        tb_lay = QVBoxLayout(self._text_box)
        tb_lay.setContentsMargins(0, 0, 0, 0)
        tb_lay.setSpacing(0)
        self._line1 = QLabel("GameVoiceKey")
        self._line1.setObjectName("Line1")
        self._line2 = QLabel("等待匹配游戏")
        self._line2.setObjectName("Line2")
        tb_lay.addWidget(self._line1)
        tb_lay.addWidget(self._line2)
        root.addWidget(self._text_box, 0, Qt.AlignVCenter)

        self.setStyleSheet(self._stylesheet())

    def _stylesheet(self) -> str:
        return (
            "#TextBox { background: transparent; }"
            "#Line1 { color: #cfead8; font-size: 12px; font-weight: 600; background: transparent; }"
            "#Line2 { color: #95c8b0; font-size: 11px; background: transparent; }"
        )

    # ----- 对外接口 -----

    def update_settings(self, settings: Settings) -> None:
        self._settings = settings
        self.setWindowOpacity(settings.overlay_opacity)
        self._apply_click_through(settings.overlay_click_through)
        self._refresh_mode()
        if settings.overlay_position != "custom":
            self._snap_to(settings.overlay_position)

    def feed_level(self, level: float) -> None:
        self._wave.feed(level)

    def set_state(self, state: str) -> None:
        self._dot.set_state(state)

    def set_profile(self, profile_name: str) -> None:
        self._line1.setText(f"GVK · {profile_name}")

    def set_trigger(self, phrase: str, key: str) -> None:
        if self._settings.overlay_show_key_on_trigger:
            self._line2.setText(f"「{phrase}」 -> {key}")
        else:
            self._line2.setText(f"「{phrase}」")
        self._last_trigger_at = time.time()
        QTimer.singleShot(int(self._settings.overlay_flash_seconds * 1000),
                          self._maybe_clear_trigger)

    def _maybe_clear_trigger(self) -> None:
        if self._settings.overlay_show_only_on_trigger:
            self.hide()
            return
        if time.time() - self._last_trigger_at >= self._settings.overlay_flash_seconds - 0.1:
            self._line2.setText("待机中…")

    def set_idle(self) -> None:
        self._line1.setText("GameVoiceKey")
        self._line2.setText("等待匹配游戏")

    # ----- 模式 -----

    def _refresh_mode(self) -> None:
        mode = self._settings.overlay_mode
        if mode == "compact":
            self._wave.setVisible(False)
            self._text_box.setVisible(False)
            self.setFixedSize(56, 36)
        elif mode == "full":
            self._wave.setVisible(True)
            self._text_box.setVisible(True)
            self.setMinimumWidth(260)
            self.setMaximumWidth(420)
            self.setMinimumHeight(48)
        else:
            self._wave.setVisible(True)
            self._text_box.setVisible(True)
            self.setFixedSize(220, 44)
            self.setMinimumWidth(180)

    def _check_fullscreen(self) -> None:
        if not self._settings.overlay_auto_compact_fullscreen:
            return
        try:
            fs = is_current_fullscreen()
        except Exception:
            fs = False
        if fs and self._settings.overlay_mode != "compact" and self._saved_mode is None:
            self._saved_mode = self._settings.overlay_mode
            self._settings.overlay_mode = "compact"
            self._refresh_mode()
        elif not fs and self._saved_mode is not None:
            self._settings.overlay_mode = self._saved_mode
            self._saved_mode = None
            self._refresh_mode()

    # ----- 位置 -----

    def _snap_to(self, pos_name: str) -> None:
        screen = self.screen().availableGeometry()
        size = self.sizeHint()
        if size.width() < 220:
            size.setWidth(220)
        if size.height() < 44:
            size.setHeight(44)
        margin = 24
        if pos_name == "topleft":
            target = QPoint(screen.x() + margin, screen.y() + margin)
        elif pos_name == "bottomleft":
            target = QPoint(screen.x() + margin,
                            screen.y() + screen.height() - size.height() - margin)
        elif pos_name == "bottomright":
            target = QPoint(screen.x() + screen.width() - size.width() - margin,
                            screen.y() + screen.height() - size.height() - margin)
        elif pos_name == "custom":
            # 用保存的自定义坐标
            cx, cy = self._settings.overlay_custom_pos or [100, 100]
            target = QPoint(int(cx), int(cy))
        else:
            target = QPoint(screen.x() + screen.width() - size.width() - margin,
                            screen.y() + margin)
        self.move(target)
        try:
            set_window_pos_topmost(int(self.winId()))
        except Exception:
            pass

    def _apply_click_through(self, enabled: bool) -> None:
        try:
            hwnd = int(self.winId())
            apply_click_through(hwnd, enabled)
        except Exception:
            pass

    # ----- 鼠标事件 -----

    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if ev.button() == Qt.LeftButton and not self._settings.overlay_click_through:
            self._dragging = True
            self._press_pos = ev.position().toPoint()
            self._global_press = ev.globalPosition().toPoint()
            ev.accept()
        else:
            ev.ignore()

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if self._dragging and self._global_press is not None:
            delta = ev.globalPosition().toPoint() - self._global_press
            self.move(self.pos() + delta)
            self._global_press = ev.globalPosition().toPoint()
            ev.accept()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if self._dragging:
            self._dragging = False
            self._snap_nearest_edge()
            self._settings.overlay_position = "custom"
            self._settings.overlay_custom_pos = [self.pos().x(), self.pos().y()]
            ev.accept()

    def _snap_nearest_edge(self) -> None:
        screen = self.screen().availableGeometry()
        rect = self.geometry()
        d_top = abs(rect.top() - screen.top())
        d_bot = abs((screen.top() + screen.height()) - rect.bottom())
        d_left = abs(rect.left() - screen.left())
        d_right = abs((screen.left() + screen.width()) - rect.right())
        mh, mv = min(d_left, d_right), min(d_top, d_bot)
        x, y = rect.x(), rect.y()
        if mh < 220:
            if d_left < d_right:
                x = screen.left() + 24
            else:
                x = screen.left() + screen.width() - rect.width() - 24
        if mv < 220:
            if d_top < d_bot:
                y = screen.top() + 24
            else:
                y = screen.top() + screen.height() - rect.height() - 24
        self.move(x, y)
