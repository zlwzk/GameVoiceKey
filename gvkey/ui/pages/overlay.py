"""悬浮窗设置页（含实时预览）."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                                QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                                QPushButton, QRadioButton, QSizePolicy, QSlider,
                                QSpinBox, QSplitter, QVBoxLayout, QWidget)

from ...config import Settings, save_settings
from ...engine import Engine


class OverlaySettingsPage(QWidget):
    def __init__(self, engine: Engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setObjectName("PageInner")
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        title = QLabel("悬浮窗设置")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        hint = QLabel("所有调整实时预览、即时生效；无需重启软件。")
        hint.setObjectName("PageHint")
        outer.addWidget(hint)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, 1)

        # === 左侧：设置项 ===
        left = QFrame(); left.setObjectName("Card")
        ll = QVBoxLayout(left); ll.setContentsMargins(20, 18, 20, 18); ll.setSpacing(12)

        gb0 = QGroupBox("总开关")
        l0 = QVBoxLayout(gb0)
        self.ck_enabled = QCheckBox("启用悬浮窗")
        l0.addWidget(self.ck_enabled)
        ll.addWidget(gb0)

        gb1 = QGroupBox("显示模式")
        l1 = QVBoxLayout(gb1)
        self.cmb_show = QComboBox()
        self.cmb_show.addItems(["始终显示", "仅触发时显示", "仅游戏内显示"])
        l1.addWidget(QLabel("显示策略"))
        l1.addWidget(self.cmb_show)
        ll.addWidget(gb1)

        gb2 = QGroupBox("尺寸 & 布局")
        l2 = QFormLayout(gb2)
        self.cmb_size = QComboBox()
        self.cmb_size.addItems(["紧凑（仅指示灯）", "标准（默认）", "完整（全部信息）"])
        l2.addRow("尺寸", self.cmb_size)
        ll.addWidget(gb2)

        gb3 = QGroupBox("外观")
        l3 = QFormLayout(gb3)
        self.sl_opacity = QDoubleSpinBox()
        self.sl_opacity.setRange(0.2, 1.0)
        self.sl_opacity.setSingleStep(0.05)
        self.sl_opacity.setDecimals(2)
        l3.addRow("透明度", self.sl_opacity)
        self.sl_radius = QSpinBox()
        self.sl_radius.setRange(0, 28)
        self.sl_radius.setSuffix(" px")
        l3.addRow("圆角", self.sl_radius)
        self.sl_blur = QSpinBox()
        self.sl_blur.setRange(0, 64)
        self.sl_blur.setSuffix(" px")
        l3.addRow("背景模糊", self.sl_blur)
        self.sl_font = QSpinBox()
        self.sl_font.setRange(9, 22)
        self.sl_font.setSuffix(" px")
        l3.addRow("文字大小", self.sl_font)
        ll.addWidget(gb3)

        gb4 = QGroupBox("位置预设")
        l4 = QGridLayout(gb4)
        for i, name in enumerate(["左上", "右上", "左下", "右下"]):
            r, c = divmod(i, 2)
            btn = QPushButton(name)
            btn.clicked.connect(lambda _=False, n=["topleft","topright","bottomleft","bottomright"][["左上","右上","左下","右下"].index(name)]: self._set_position(n))
            l4.addWidget(btn, r, c)
        ll.addWidget(gb4)

        gb5 = QGroupBox("触发反馈")
        l5 = QFormLayout(gb5)
        self.ck_show_key = QCheckBox("显示对应按键名")
        l5.addRow(self.ck_show_key)
        self.sp_flash = QDoubleSpinBox()
        self.sp_flash.setRange(0.5, 8.0)
        self.sp_flash.setSuffix(" s")
        l5.addRow("触发文字停留", self.sp_flash)
        ll.addWidget(gb5)

        gb6 = QGroupBox("行为")
        l6 = QVBoxLayout(gb6)
        self.ck_click_through = QCheckBox("开启鼠标点击穿透")
        l6.addWidget(self.ck_click_through)
        self.ck_auto_compact = QCheckBox("全屏时自动切紧凑模式")
        l6.addWidget(self.ck_auto_compact)
        ll.addWidget(gb6)

        ll.addStretch(1)

        apply_btn = QPushButton("应用并保存")
        apply_btn.setObjectName("Primary")
        apply_btn.clicked.connect(self._on_save)
        ll.addWidget(apply_btn)

        splitter.addWidget(left)

        # === 右侧：实时预览 ===
        right = QFrame(); right.setObjectName("CardMid")
        rl = QVBoxLayout(right); rl.setContentsMargins(20, 18, 20, 18); rl.setSpacing(10)
        rl.addWidget(QLabel("实时预览（带桌面色背景模拟）"))
        self._preview = PreviewOverlayWidget()
        self._preview.setMinimumHeight(300)
        self._preview.setStyleSheet("background-color: #1a3855; border-radius: 12px;")
        rl.addWidget(self._preview, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        # 拉取初值
        s: Settings = self.engine.settings
        self.ck_enabled.setChecked(s.overlay_enabled)
        idx_show = {"always": 0, "trigger-only": 1, "in-game-only": 2}.get(s.overlay_show_only_on_trigger and "trigger-only" or "always", 0)
        if s.overlay_show_only_on_trigger:
            self.cmb_show.setCurrentIndex(1)
        idx_size = {"compact": 0, "standard": 1, "full": 2}.get(s.overlay_mode, 1)
        self.cmb_size.setCurrentIndex(idx_size)
        self.sl_opacity.setValue(s.overlay_opacity)
        self.sl_radius.setValue(12)
        self.sl_blur.setValue(20)
        self.sl_font.setValue(12)
        self.ck_show_key.setChecked(s.overlay_show_key_on_trigger)
        self.sp_flash.setValue(s.overlay_flash_seconds)
        self.ck_click_through.setChecked(s.overlay_click_through)
        self.ck_auto_compact.setChecked(s.overlay_auto_compact_fullscreen)

        # 实时预览刷新
        for w in (self.sl_opacity, self.sl_radius, self.sl_blur, self.sl_font,
                  self.cmb_size, self.cmb_show, self.ck_enabled, self.ck_show_key,
                  self.sp_flash, self.ck_click_through, self.ck_auto_compact):
            try:
                w.valueChanged.connect(self._apply_preview)
            except Exception:
                try:
                    w.currentIndexChanged.connect(self._apply_preview)
                except Exception:
                    try:
                        w.toggled.connect(self._apply_preview)
                    except Exception:
                        pass
        self._apply_preview()

    def _set_position(self, name: str) -> None:
        from ..main_window import MainWindow
        win = self.parent().parent() if self.parent() else None
        if win is None:
            return
        for w in win.findChildren(QFrame):
            pass
        s = self.engine.settings
        s.overlay_position = name
        save_settings(s)

    def _apply_preview(self) -> None:
        s: Settings = self.engine.settings
        s.overlay_enabled = self.ck_enabled.isChecked()
        s.overlay_show_only_on_trigger = self.cmb_show.currentIndex() == 1
        sizes = ["compact", "standard", "full"]
        s.overlay_mode = sizes[self.cmb_size.currentIndex()]
        s.overlay_opacity = self.sl_opacity.value()
        s.overlay_show_key_on_trigger = self.ck_show_key.isChecked()
        s.overlay_flash_seconds = self.sp_flash.value()
        s.overlay_click_through = self.ck_click_through.isChecked()
        s.overlay_auto_compact_fullscreen = self.ck_auto_compact.isChecked()

        self._preview.set_params(
            mode=s.overlay_mode,
            opacity=s.overlay_opacity,
            show_key=s.overlay_show_key_on_trigger,
        )

    def _on_save(self) -> None:
        self._apply_preview()
        s: Settings = self.engine.settings
        save_settings(s)
        if hasattr(self.parent(), "parent") and callable(getattr(self.parent(), "parent", None)):
            win = self.parent().parent()
            overlay = getattr(win, "_overlay", None)
            if overlay:
                overlay.update_settings(s)


class PreviewOverlayWidget(QFrame):
    """模拟悬浮窗外观的预览组件."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mode = "standard"
        self._opacity = 0.8
        self._show_key = True
        lay = QHBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.addStretch(1)

        self._bar = QFrame()
        self._bar.setStyleSheet("background-color: rgba(20, 28, 34, 220); border-radius: 12px;")
        inner = QHBoxLayout(self._bar)
        inner.setContentsMargins(10, 6, 10, 6)
        inner.setSpacing(10)
        self._dot = QLabel()
        self._dot.setFixedSize(16, 16)
        self._dot.setStyleSheet("background-color: #7CCAB1; border-radius: 8px;")
        inner.addWidget(self._dot, 0, Qt.AlignVCenter)
        self._wave = QLabel("▌▍▎▏▎▍▌")
        self._wave.setStyleSheet("color: #b9efe0; font-size: 14px;")
        inner.addWidget(self._wave, 0, Qt.AlignVCenter)
        self._text = QLabel("GVK · 当前配置\n「开枪」 → LMB")
        self._text.setStyleSheet("color: #cfe1d5;")
        inner.addWidget(self._text)
        lay.addWidget(self._bar)
        lay.addStretch(1)

    def set_params(self, mode: str, opacity: float, show_key: bool) -> None:
        self._mode = mode
        self._opacity = opacity
        self._show_key = show_key
        if mode == "compact":
            self._wave.setVisible(False); self._text.setVisible(False)
            self._bar.setMinimumWidth(48)
        elif mode == "full":
            self._wave.setVisible(True); self._text.setVisible(True)
            self._bar.setMinimumWidth(280)
        else:
            self._wave.setVisible(True); self._text.setVisible(True)
            self._bar.setMinimumWidth(220)
        if show_key:
            self._text.setText("GVK · 当前配置\n「开枪」 → LMB")
        else:
            self._text.setText("GVK · 当前配置\n「开枪」")
        self.setWindowOpacity(opacity)
