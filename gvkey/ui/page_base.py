"""统一的页面骨架与小组件工厂.

所有页面统一继承 :class:`ScrollPage`：

- 标题 / 副标题固定在顶部（不随内容滚动，切换页面时位置稳定）
- 内容统一放进 ``QScrollArea`` —— 窗口再小也只是出现滚动条，
  **不会**把控件挤压重叠（这是之前界面「完全混乱」的直接原因之一）
- 页面边距 / 间距 / 卡片样式集中在这里，各页不再各写一套数字

页面只需在 ``self.body`` 上添加内容即可。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGroupBox, QHBoxLayout, QLabel, QScrollArea,
                                QSizePolicy, QVBoxLayout, QWidget)

from .theme import CARD_PADDING, PAGE_MARGIN_H, PAGE_MARGIN_V, PAGE_SPACING


class ScrollPage(QWidget):
    """页面骨架：固定标题区 + 可滚动内容区。

    子类用法::

        class MyPage(ScrollPage):
            def __init__(self, engine, parent=None):
                super().__init__("标题", "一句话说明", parent)
                self.engine = engine
                card, box = make_card("分组名")
                box.addWidget(QLabel("内容"))
                self.body.addWidget(card)
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PageInner")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- 固定标题区 ----------
        head = QWidget()
        head.setObjectName("PageInner")
        head_lay = QVBoxLayout(head)
        head_lay.setContentsMargins(PAGE_MARGIN_H, PAGE_MARGIN_V, PAGE_MARGIN_H, 10)
        head_lay.setSpacing(3)

        self._title = QLabel(title)
        self._title.setObjectName("PageTitle")
        head_lay.addWidget(self._title)

        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("PageHint")
        self._subtitle.setWordWrap(True)
        self._subtitle.setVisible(bool(subtitle))
        head_lay.addWidget(self._subtitle)

        root.addWidget(head)

        # ---------- 可滚动内容区 ----------
        self.scroll = QScrollArea()
        self.scroll.setObjectName("PageScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # viewport 自己填背景会盖住主题色，显式关掉
        self.scroll.viewport().setAutoFillBackground(False)

        host = QWidget()
        host.setObjectName("ScrollHost")
        host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.body = QVBoxLayout(host)
        self.body.setContentsMargins(PAGE_MARGIN_H, 4, PAGE_MARGIN_H, PAGE_MARGIN_V)
        self.body.setSpacing(PAGE_SPACING)

        self.scroll.setWidget(host)
        root.addWidget(self.scroll, 1)

    # ------------------------------------------------------------------

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))

    def finish_body(self) -> None:
        """内容加完后调用：末尾留一个弹性空白，让内容顶部对齐。"""

        self.body.addStretch(1)

    def on_show(self) -> None:  # pragma: no cover - 由 MainWindow 调用
        """页面被切换到前台时的钩子，子类按需覆盖。"""


# ============================================================
# 小组件工厂
# ============================================================


def make_card(title: str = "", hint: str = "", accent: bool = False):
    """返回 ``(card, box)``；``box`` 是垂直布局，往里 addWidget 即可。"""

    card = QFrame()
    card.setObjectName("CardAccent" if accent else "Card")
    box = QVBoxLayout(card)
    box.setContentsMargins(CARD_PADDING, CARD_PADDING - 4, CARD_PADDING, CARD_PADDING - 4)
    box.setSpacing(9)

    if title:
        lbl = QLabel(title)
        lbl.setObjectName("CardTitle")
        box.addWidget(lbl)
    if hint:
        h = QLabel(hint)
        h.setObjectName("CardHint")
        h.setWordWrap(True)
        box.addWidget(h)
    return card, box


def make_group(title: str):
    """返回 ``(group_box, vbox)``。"""

    gb = QGroupBox(title)
    lay = QVBoxLayout(gb)
    lay.setContentsMargins(14, 8, 14, 14)
    lay.setSpacing(9)
    return gb, lay


def make_form_group(title: str):
    """返回 ``(group_box, form_layout)``，用于「标签 + 控件」成对的行。"""

    from PySide6.QtWidgets import QFormLayout

    gb = QGroupBox(title)
    form = QFormLayout(gb)
    form.setContentsMargins(14, 8, 14, 14)
    form.setSpacing(9)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    return gb, form


def card_title_row(text: str) -> QHBoxLayout:
    """卡片内的小标题行（左标题、右侧可继续 addStretch + 按钮）。"""

    row = QHBoxLayout()
    row.setSpacing(8)
    lbl = QLabel(text)
    lbl.setObjectName("CardTitle")
    row.addWidget(lbl)
    row.addStretch(1)
    return row


def kv_row(label: str, widget: QWidget, label_width: int = 84) -> QHBoxLayout:
    """一行「定宽标签 + 控件」，用于替代 QFormLayout 在深色主题下的对齐问题。"""

    row = QHBoxLayout()
    row.setSpacing(10)
    lbl = QLabel(label)
    lbl.setObjectName("Value")
    lbl.setFixedWidth(label_width)
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    return row


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("CardHint")
    lbl.setWordWrap(True)
    return lbl


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    return line


def status_label(text: str, kind: str = "ok") -> QLabel:
    """kind: ok / warn / bad"""

    lbl = QLabel(text)
    lbl.setObjectName({"ok": "StatusOk", "warn": "StatusWarn", "bad": "StatusBad"}.get(kind, "StatusOk"))
    lbl.setWordWrap(True)
    return lbl
