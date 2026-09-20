"""深色磨砂玻璃主题.

色板（OKLCH 灵感）：
- 主色：青绿 #7CCAB1（accent）
- 背景层次：#0F1418 → #1A2128 → #232B33
- 文字：#E6F0E8 / #95A8A2
- 状态色：active=#7CCAB1, paused=#E6B660, disabled=#D86F73, idle=#7A8C84
"""

GLOBAL_QSS = """
* {
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 13px;
    color: #d7e2dc;
}
QMainWindow, QWidget {
    background-color: #12161a;
}
QWidget#Sidebar {
    background-color: #0d1116;
    border-right: 1px solid #1e252c;
}
QWidget#SidebarHeader {
    padding: 16px;
    border-bottom: 1px solid #1e252c;
}
QLabel#AppTitle {
    color: #e6f0e8;
    font-size: 18px;
    font-weight: 700;
}
QLabel#AppSubtitle {
    color: #7d8e87;
    font-size: 11px;
}
QListWidget#NavList {
    background: transparent;
    border: none;
    padding: 8px 6px;
    outline: 0;
}
QListWidget#NavList::item {
    color: #b9c4be;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 2px 4px;
}
QListWidget#NavList::item:hover {
    background-color: #1c232a;
}
QListWidget#NavList::item:selected {
    background-color: #243029;
    color: #b9efe0;
}
QStackedWidget#PageStack {
    background-color: #161b20;
}
QWidget#PageInner {
    background-color: transparent;
}
QLabel#PageTitle {
    color: #e6f0e8;
    font-size: 18px;
    font-weight: 600;
    padding-bottom: 4px;
}
QLabel#PageHint {
    color: #7d8e87;
    font-size: 11px;
    padding-bottom: 12px;
}
QFrame#Card {
    background-color: #1a2128;
    border: 1px solid #232c33;
    border-radius: 12px;
}
QFrame#CardMid {
    background-color: #1e252d;
    border: 1px solid #283138;
    border-radius: 12px;
}
QLabel#CardTitle {
    color: #cfe1d5;
    font-size: 13px;
    font-weight: 600;
}
QLabel#CardHint {
    color: #8b9c93;
    font-size: 11px;
}
QLabel#BigNumber {
    color: #9ce4cb;
    font-size: 30px;
    font-weight: 700;
}
QLabel#BigNumberLabel {
    color: #8b9c93;
    font-size: 11px;
}
QPushButton {
    background-color: #283138;
    color: #d7e2dc;
    border: 1px solid #354049;
    border-radius: 8px;
    padding: 6px 14px;
}
QPushButton:hover {
    background-color: #324047;
}
QPushButton:pressed {
    background-color: #283138;
}
QPushButton#Primary {
    background-color: #2f6e5b;
    color: #e6f1eb;
    border: 1px solid #3a8471;
}
QPushButton#Primary:hover {
    background-color: #398b71;
}
QPushButton#Danger {
    background-color: #6e3a3a;
    color: #f5e0e0;
    border: 1px solid #8a4a4a;
}
QPushButton#Danger:hover {
    background-color: #8a4a4a;
}
QPushButton#Ghost {
    background-color: transparent;
    border: 1px solid #2e3941;
    color: #b3c0bb;
}
QPushButton#Ghost:hover {
    background-color: #1d252b;
}
QPushButton#BigToggle {
    background-color: #1c3130;
    color: #b6e7d8;
    border: 1px solid #2f6e5b;
    border-radius: 14px;
    padding: 12px 24px;
    font-size: 16px;
    font-weight: 600;
}
QPushButton#BigToggle:checked {
    background-color: #2f6e5b;
    color: #ffffff;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #14191e;
    color: #d7e2dc;
    border: 1px solid #2a3239;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #355f50;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #4f8979;
}
QSpinBox, QDoubleSpinBox {
    padding-right: 18px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 14px;
    background: transparent;
    border: none;
}
QCheckBox {
    color: #bcc5bf;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3a4851;
    border-radius: 4px;
    background: #14191e;
}
QCheckBox::indicator:checked {
    background: #2f6e5b;
    border: 1px solid #7CCAB1;
}
QRadioButton {
    color: #bcc5bf;
    spacing: 6px;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #2a3239;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    background: #7CCAB1;
    border-radius: 7px;
    margin: -5px 0;
}
QScrollArea, QListView, QTreeView, QTableView {
    background: transparent;
    border: none;
}
QHeaderView::section {
    background-color: #1a2128;
    color: #cfe1d5;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid #2a3239;
}
QTableWidget {
    background-color: #161b20;
    alternate-background-color: #1a2128;
    gridline-color: #2a3239;
    border: 1px solid #232c33;
    border-radius: 8px;
}
QTableWidget::item {
    padding: 4px 6px;
}
QTableWidget::item:selected {
    background-color: #2c4038;
    color: #e6f1eb;
}
QGroupBox {
    border: 1px solid #232c33;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 8px;
    color: #cfe1d5;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}
QProgressBar {
    background-color: #1a2128;
    border: 1px solid #232c33;
    border-radius: 4px;
    height: 14px;
    text-align: center;
    color: #d7e2dc;
}
QProgressBar::chunk {
    background-color: #2f6e5b;
    border-radius: 4px;
}
QStatusBar {
    background-color: #0d1116;
    color: #8b9c93;
}
QToolTip {
    background-color: #1a2128;
    color: #d7e2dc;
    border: 1px solid #2f6e5b;
    border-radius: 4px;
    padding: 4px 8px;
}
QMenu {
    background-color: #1a2128;
    color: #d7e2dc;
    border: 1px solid #2a3239;
    padding: 4px 4px;
}
QMenu::item {
    padding: 6px 18px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #2c4038;
}
QMenu::separator {
    height: 1px;
    background: #2a3239;
    margin: 4px 8px;
}
QSplitter::handle {
    background-color: #1e252c;
}
QSplitter::handle:hover {
    background-color: #2a3239;
}
QTabWidget::pane {
    border: 1px solid #232c33;
    border-radius: 8px;
    background: #161b20;
}
QTabBar::tab {
    background: #1a2128;
    color: #bcc5bf;
    padding: 6px 12px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #232c33;
    border-bottom: none;
}
QTabBar::tab:selected {
    background: #243029;
    color: #b9efe0;
}
"""


def apply_theme(app) -> None:
    """把 GLOBAL_QSS 应用到 QApplication."""

    app.setStyleSheet(GLOBAL_QSS)
    app.setStyle("Fusion")
