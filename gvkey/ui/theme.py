"""深色磨砂玻璃主题（松石绿）.

色板（OKLCH 灵感，hue ≈ 165 松石绿）：
- 主色 accent : #6ECFAD
- 背景三层    : #0f1418（窗口）→ #141a20（页面）→ #1a222a（卡片）
- 文字        : #dce8e2（主）/ #9fb2ab（次）/ #7c8f88（弱）
- 状态色      : active #6ECFAD, paused #E6B660, disabled #D86F73, idle #7A8C84

================================================================
【重要】关于样式表的两条铁律（血的教训）
================================================================
1. **绝不使用裸 `QWidget` 选择器设置 background-color。**
   Qt 的 `QWidget` 选择器会命中「所有」QWidget 派生类（QLabel、
   QGroupBox、QScrollArea 的 viewport…）。一旦给它上背景色，卡片里
   的每个标签都会变成实心色块，把圆角卡片切成碎片，界面直接乱掉。
   → 需要背景的容器一律用 objectName 精确指定（#Sidebar / #PageStack…）。
   → 文字类控件统一显式 `background: transparent`。

2. **`QApplication.setStyle("Fusion")` 必须在 `setStyleSheet` 之前调用**，
   否则样式表可能被重新 polish 掉。
"""
from __future__ import annotations

# ============================================================
# 尺寸常量（各页面统一取用，避免各处写死不同数字）
# ============================================================

PAGE_MARGIN_H = 26
PAGE_MARGIN_V = 22
PAGE_SPACING = 16
CARD_PADDING = 18
CARD_RADIUS = 12


GLOBAL_QSS = """
/* ================= 基础 ================= */
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 13px;
    color: #dce8e2;
}

/* 只有真正的窗口容器才有底色 */
QMainWindow, QDialog, QMessageBox {
    background-color: #0f1418;
}
QStackedWidget#PageStack {
    background-color: #141a20;
}
QWidget#PageInner, QWidget#ScrollHost {
    background: transparent;
}

/* 文字 / 勾选类控件一律透明，否则会盖住卡片背景 */
QLabel, QAbstractButton, QCheckBox, QRadioButton, QGroupBox, QToolButton {
    background: transparent;
}

/* ================= 侧栏 ================= */
QWidget#Sidebar {
    background-color: #0b1014;
    border-right: 1px solid #1b242b;
}
QWidget#SidebarHeader {
    background: transparent;
    border-bottom: 1px solid #1b242b;
}
QLabel#AppTitle {
    color: #eaf6f0;
    font-size: 17px;
    font-weight: 700;
}
QLabel#AppSubtitle {
    color: #7c8f88;
    font-size: 11px;
}
QLabel#SidebarFooter {
    color: #5f7069;
    font-size: 10px;
    padding: 10px 16px 14px 16px;
}

QListWidget#NavList {
    background: transparent;
    border: none;
    outline: 0;
    padding: 8px 8px 4px 8px;
}
QListWidget#NavList::item {
    color: #b3c2bc;
    padding: 9px 12px;
    border-radius: 8px;
    margin: 2px 0;
}
QListWidget#NavList::item:hover {
    background-color: #172029;
    color: #dce8e2;
}
QListWidget#NavList::item:selected {
    background-color: #1d3a33;
    color: #9fe8cd;
    border-left: 3px solid #6ECFAD;
    padding-left: 9px;
}

/* ================= 页面骨架 ================= */
QLabel#PageTitle {
    color: #eaf6f0;
    font-size: 19px;
    font-weight: 700;
}
QLabel#PageHint {
    color: #7c8f88;
    font-size: 11px;
}
QLabel#SectionTitle {
    color: #cfe1d8;
    font-size: 13px;
    font-weight: 600;
}
QLabel#CardTitle {
    color: #cfe1d8;
    font-size: 13px;
    font-weight: 600;
}
QLabel#CardHint {
    color: #85988f;
    font-size: 11px;
}
QLabel#BigNumber {
    color: #9fe8cd;
    font-size: 25px;
    font-weight: 700;
}
QLabel#BigNumberLabel {
    color: #85988f;
    font-size: 11px;
}
QLabel#Value {
    color: #dce8e2;
    font-size: 13px;
}
QLabel#StatusOk { color: #7ddcb4; font-size: 11px; }
QLabel#StatusWarn { color: #e6b660; font-size: 11px; }
QLabel#StatusBad { color: #e58387; font-size: 11px; }

/* ================= 卡片 ================= */
QFrame#Card {
    background-color: #1a222a;
    border: 1px solid #222c34;
    border-radius: 12px;
}
QFrame#CardMid {
    background-color: #1d262e;
    border: 1px solid #27323b;
    border-radius: 12px;
}
QFrame#CardAccent {
    background-color: #1a2b28;
    border: 1px solid #2c5a4d;
    border-radius: 12px;
}
QFrame#Divider {
    background-color: #222c34;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QFrame#StateChip {
    background-color: #182128;
    border: 1px solid #2a3a36;
    border-radius: 11px;
}

/* ================= 按钮 ================= */
QPushButton {
    background-color: #263139;
    color: #dce8e2;
    border: 1px solid #33414a;
    border-radius: 8px;
    padding: 7px 14px;
    min-height: 17px;
}
QPushButton:hover {
    background-color: #2f3d46;
    border-color: #40505b;
}
QPushButton:pressed {
    background-color: #222c34;
}
QPushButton:disabled {
    color: #62736c;
    background-color: #1b2329;
    border-color: #253038;
}
QPushButton#Primary {
    background-color: #2f6e5b;
    color: #eaf6f0;
    border: 1px solid #3d8a73;
    font-weight: 600;
}
QPushButton#Primary:hover {
    background-color: #38896f;
    border-color: #55a98d;
}
QPushButton#Primary:disabled {
    background-color: #24443b;
    color: #7d968d;
}
QPushButton#Danger {
    background-color: #5f3235;
    color: #f7e3e4;
    border: 1px solid #804447;
}
QPushButton#Danger:hover {
    background-color: #7a4044;
}
QPushButton#Ghost {
    background: transparent;
    border: 1px solid #2d3942;
    color: #b3c2bc;
}
QPushButton#Ghost:hover {
    background-color: #1b242b;
    border-color: #3c4c56;
    color: #dce8e2;
}
QPushButton#BigToggle {
    background-color: #14251f;
    color: #9fd8c4;
    border: 1px solid #2f6e5b;
    border-radius: 12px;
    padding: 14px 26px;
    font-size: 15px;
    font-weight: 700;
}
QPushButton#BigToggle:hover {
    background-color: #1a332a;
}
QPushButton#BigToggle:checked {
    background-color: #2f6e5b;
    color: #ffffff;
    border-color: #6ECFAD;
}
QPushButton#NavCard {
    background-color: #1a222a;
    border: 1px solid #222c34;
    border-radius: 12px;
    padding: 14px 16px;
    text-align: left;
    font-size: 13px;
}
QPushButton#NavCard:hover {
    background-color: #202a33;
    border-color: #33544a;
}

/* ================= 输入控件 ================= */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background-color: #111820;
    color: #dce8e2;
    border: 1px solid #2c3841;
    border-radius: 7px;
    padding: 6px 9px;
    selection-background-color: #2f6e5b;
    min-height: 17px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #4f9c83;
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: #62736c;
    background-color: #161d23;
}
QLineEdit#ReadOnly {
    background-color: #131a20;
    color: #9fb2ab;
}

/* 数值控件：单位走 setSuffix / 外部标签，框内只放数字 */
QSpinBox, QDoubleSpinBox {
    padding-right: 20px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    width: 17px;
    background: transparent;
    border: none;
}
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-position: top right; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-position: bottom right; }
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #24303a;
    border-radius: 3px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-bottom: 4px solid #8fa8a0;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid #8fa8a0;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border: none;
    background: transparent;
}
QComboBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8fa8a0;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #1a222a;
    border: 1px solid #2c3841;
    border-radius: 8px;
    padding: 4px;
    outline: 0;
    selection-background-color: #2c4038;
    selection-color: #eaf6f0;
}

/* ================= 勾选 ================= */
QCheckBox, QRadioButton {
    color: #c3d0cb;
    spacing: 7px;
    padding: 2px 0;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #3b4a54;
    border-radius: 4px;
    background-color: #111820;
}
QRadioButton::indicator {
    border-radius: 8px;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #5f8f7f;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #4ea88a;
    border: 1px solid #6ECFAD;
}

/* ================= 滑块 ================= */
QSlider::groove:horizontal {
    height: 4px;
    background: #2a3239;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #3d8a73;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    background: #6ECFAD;
    border-radius: 7px;
    margin: -5px 0;
}
QSlider::handle:horizontal:hover {
    background: #8fe3c6;
}

/* ================= 列表 / 表格 ================= */
QListWidget, QListView, QTreeView {
    background-color: #161e24;
    border: 1px solid #232d35;
    border-radius: 8px;
    outline: 0;
    padding: 3px;
}
QListWidget::item, QListView::item {
    padding: 6px 8px;
    border-radius: 6px;
    color: #c3d0cb;
}
QListWidget::item:hover, QListView::item:hover {
    background-color: #1e2830;
}
QListWidget::item:selected, QListView::item:selected {
    background-color: #2c4038;
    color: #eaf6f0;
}

QTableWidget, QTableView {
    background-color: #161e24;
    alternate-background-color: #1a232a;
    gridline-color: #222c34;
    border: 1px solid #232d35;
    border-radius: 8px;
    outline: 0;
}
QTableWidget::item, QTableView::item {
    padding: 4px 6px;
}
QTableWidget::item:selected, QTableView::item:selected {
    background-color: #2c4038;
    color: #eaf6f0;
}
QHeaderView::section {
    background-color: #1a222a;
    color: #cfe1d8;
    padding: 7px 8px;
    border: none;
    border-right: 1px solid #222c34;
    border-bottom: 1px solid #222c34;
    font-weight: 600;
}
QHeaderView::section:last {
    border-right: none;
}
QTableCornerButton::section {
    background-color: #1a222a;
    border: none;
}

/* ================= 滚动区 + 滚动条 ================= */
QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px 2px 2px 0;
}
QScrollBar::handle:vertical {
    background: #2f3d46;
    border-radius: 4px;
    min-height: 36px;
}
QScrollBar::handle:vertical:hover {
    background: #3f5260;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0 2px 2px 2px;
}
QScrollBar::handle:horizontal {
    background: #2f3d46;
    border-radius: 4px;
    min-width: 36px;
}
QScrollBar::handle:horizontal:hover {
    background: #3f5260;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
    background: none;
    border: none;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QScrollBar::corner {
    background: transparent;
}

/* ================= 分组框 ================= */
QGroupBox {
    border: 1px solid #222c34;
    border-radius: 10px;
    margin-top: 20px;
    padding: 16px 14px 14px 14px;
    font-weight: 600;
    color: #cfe1d8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #9fd8c4;
    font-weight: 600;
}

/* ================= 其他 ================= */
QProgressBar {
    background-color: #1a222a;
    border: 1px solid #232d35;
    border-radius: 6px;
    height: 14px;
    text-align: center;
    color: #dce8e2;
    font-size: 11px;
}
QProgressBar::chunk {
    background-color: #3d8a73;
    border-radius: 5px;
}

QStatusBar {
    background-color: #0b1014;
    color: #7c8f88;
    border-top: 1px solid #1b242b;
}
QStatusBar::item {
    border: none;
}

QSplitter::handle {
    background-color: transparent;
}
QSplitter::handle:hover {
    background-color: #2f3d46;
}
QSplitter::handle:horizontal {
    width: 8px;
}

QTabWidget::pane {
    border: 1px solid #232d35;
    border-radius: 8px;
    background: #161e24;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #9fb2ab;
    padding: 7px 14px;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover {
    color: #dce8e2;
}
QTabBar::tab:selected {
    color: #9fe8cd;
    border-bottom: 2px solid #6ECFAD;
}

QToolTip {
    background-color: #1a222a;
    color: #dce8e2;
    border: 1px solid #3d8a73;
    border-radius: 6px;
    padding: 5px 8px;
}

QMenu {
    background-color: #1a222a;
    color: #dce8e2;
    border: 1px solid #2c3841;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item {
    padding: 7px 20px;
    border-radius: 6px;
}
QMenu::item:selected {
    background-color: #2c4038;
}
QMenu::separator {
    height: 1px;
    background: #2c3841;
    margin: 5px 8px;
}
"""


def apply_theme(app) -> None:
    """把主题应用到 QApplication.

    顺序很重要：先 setStyle("Fusion")，再 setStyleSheet。
    反过来的话样式表会在重新 polish 时丢掉一部分。
    """

    app.setStyle("Fusion")
    app.setStyleSheet(GLOBAL_QSS)
