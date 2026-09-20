"""「选择当前游玩的游戏」对话框.

设计取向：**只列用户眼前看得见的东西**。

底层枚举的是「有可见窗口的进程」，所以服务、驱动、后台更新器都不会出现，
剩下的基本就是用户正在用的程序。列表里再用「是否已有配置」标注状态，
用户点一下就能进配置页，不需要理解进程名是什么。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QHBoxLayout,
                                QHeaderView, QInputDialog, QLabel, QLineEdit,
                                QPushButton, QTableWidget, QTableWidgetItem,
                                QVBoxLayout, QWidget)

from ..logs import get_logger
from ..process_monitor import (RunningApp, is_probably_game, list_running_apps,
                               normalize_process_name)

LOGGER = get_logger()

_ROLE_APP = Qt.UserRole + 1


class PickProcessDialog(QDialog):
    """列出运行中的程序，让用户挑「当前在玩的这个」。"""

    def __init__(self, engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self._apps: list[RunningApp] = []
        self._chosen: Optional[RunningApp] = None
        self._manual_name: str = ""

        self.setWindowTitle("选择当前游玩的游戏")
        self.setModal(True)
        self.setMinimumSize(720, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        title = QLabel("当前在玩哪个游戏？")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        hint = QLabel(
            "下面列出的是此刻有窗口开着的程序。找到你的游戏点中它 —— "
            "如果还没配过语音指令，会自动为你建一份新配置并跳到编辑页。"
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        tools = QHBoxLayout()
        tools.setSpacing(10)
        self._ed_search = QLineEdit()
        self._ed_search.setPlaceholderText("搜索进程名或窗口标题…")
        self._ed_search.textChanged.connect(self._apply_filter)
        tools.addWidget(self._ed_search, 1)

        self._ck_all = QCheckBox("显示系统组件")
        self._ck_all.toggled.connect(lambda _v: self.reload())
        tools.addWidget(self._ck_all)

        btn_reload = QPushButton("重新扫描")
        btn_reload.setObjectName("Ghost")
        btn_reload.clicked.connect(self.reload)
        tools.addWidget(btn_reload)

        btn_manual = QPushButton("手动输入…")
        btn_manual.setObjectName("Ghost")
        btn_manual.setToolTip("游戏的窗口标题可能是空的，这时可以手动填进程名")
        btn_manual.clicked.connect(self._manual_input)
        tools.addWidget(btn_manual)
        root.addLayout(tools)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["游戏 / 程序", "窗口标题", "配置状态"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.itemSelectionChanged.connect(self._on_selection)
        self._table.itemDoubleClicked.connect(lambda _i: self._accept_if_ready())
        root.addWidget(self._table, 1)

        self._lbl_count = QLabel("")
        self._lbl_count.setObjectName("CardHint")
        root.addWidget(self._lbl_count)

        bar = QHBoxLayout()
        bar.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("Ghost")
        btn_cancel.clicked.connect(self.reject)
        bar.addWidget(btn_cancel)

        self._btn_ok = QPushButton("就玩这个，开始配置")
        self._btn_ok.setObjectName("Primary")
        self._btn_ok.setMinimumWidth(170)
        self._btn_ok.setEnabled(False)
        self._btn_ok.clicked.connect(self._accept_if_ready)
        bar.addWidget(self._btn_ok)
        root.addLayout(bar)

        self.reload()

    # ============================================================

    def reload(self) -> None:
        try:
            self._apps = list_running_apps(include_system=self._ck_all.isChecked())
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("枚举进程失败: %s", exc)
            self._apps = []

        # 游戏排前面，其次按名字
        self._apps.sort(key=lambda a: (not is_probably_game(a), a.display.lower()))
        self._apply_filter()

    def _configured_profile_name(self, app: RunningApp) -> str:
        try:
            for profile in self.engine.profile_store.all():
                if any(normalize_process_name(p) == app.process for p in profile.processes):
                    return profile.name
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _apply_filter(self) -> None:
        keyword = self._ed_search.text().strip().lower()
        self._table.setRowCount(0)

        shown = 0
        for app in self._apps:
            if keyword and keyword not in app.process and keyword not in app.title.lower():
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(app.display)
            name_item.setData(_ROLE_APP, app.process)
            if is_probably_game(app):
                name_item.setToolTip("看起来是游戏（安装在常见游戏目录下）")
            else:
                name_item.setToolTip(app.path or app.display)
            self._table.setItem(row, 0, name_item)

            self._table.setItem(row, 1, QTableWidgetItem(app.title or "—"))

            existing = self._configured_profile_name(app)
            status = QTableWidgetItem(f"已有配置「{existing}」" if existing else "新建配置")
            status.setForeground(QColor("#7ddcb4") if existing else QColor("#85988f"))
            self._table.setItem(row, 2, status)
            shown += 1

        self._lbl_count.setText(
            f"共 {shown} 个可选项"
            + ("　（列表为空？先启动游戏再点「重新扫描」）" if shown == 0 else "")
        )
        self._on_selection()

    def _current_app(self) -> Optional[RunningApp]:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        proc = item.data(_ROLE_APP)
        for app in self._apps:
            if app.process == proc:
                return app
        return None

    def _on_selection(self) -> None:
        app = self._current_app()
        self._btn_ok.setEnabled(app is not None)
        if app is None:
            return
        existing = self._configured_profile_name(app)
        if existing:
            self._btn_ok.setText(f"打开配置「{existing}」")
        else:
            self._btn_ok.setText("就玩这个，开始配置")

    def _accept_if_ready(self) -> None:
        if self._current_app() is not None:
            self.accept()

    def _manual_input(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "手动输入进程名",
            "输入游戏的可执行文件名（不用写 .exe）\n例如 eldenring、cs2、dota2:",
        )
        if not ok or not text.strip():
            return
        name = text.strip()
        key = normalize_process_name(name)
        if not key:
            return
        self._manual_name = name
        self._chosen = RunningApp(pid=0, process=key, display=name, title="", path="")
        self.accept()

    # ============================================================

    def chosen(self) -> Optional[RunningApp]:
        if self._chosen is not None:
            return self._chosen
        return self._current_app()
