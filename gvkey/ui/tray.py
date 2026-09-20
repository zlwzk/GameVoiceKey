"""系统托盘."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .. import __app_display_name__


class TrayIcon(QSystemTrayIcon):
    def __init__(self, *, parent, icon: QIcon, engine,
                 on_show: Callable, on_quit: Callable) -> None:
        super().__init__(icon, parent)
        self._engine = engine
        self._on_show = on_show
        self._on_quit = on_quit
        self.setToolTip(__app_display_name__)

        menu = QMenu()
        act_show = QAction("打开主界面", menu)
        act_show.triggered.connect(self._on_show)
        menu.addAction(act_show)
        menu.addSeparator()

        self.act_toggle_master = QAction("暂停语音控制", menu)
        self.act_toggle_master.triggered.connect(lambda: engine.toggle_master())
        menu.addAction(self.act_toggle_master)

        self.act_pause = QAction("暂停监听", menu)
        self.act_pause.triggered.connect(lambda: engine.pause())
        menu.addAction(self.act_pause)

        self.act_mute = QAction("静音麦克风", menu)
        self.act_mute.triggered.connect(lambda: engine.mute_mic())
        menu.addAction(self.act_mute)

        menu.addSeparator()
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self._on_quit)
        menu.addAction(act_quit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

        # engine state -> 更新菜单文字
        engine.bus.subscribe("engine.state", self._refresh_actions)

        self.show()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._on_show()

    def _refresh_actions(self, ev) -> None:
        s = ev.payload.get("state", "")
        try:
            self.act_pause.setText("恢复监听" if s == "paused" else "暂停监听")
            self.act_mute.setText("取消静音" if s == "muted" else "静音麦克风")
            self.act_toggle_master.setText("启用语音控制" if s in ("disabled", "stopped") else "禁用语音控制")
        except Exception:
            pass

    def show_notification(self, title: str, msg: str) -> None:
        if self.supportsMessages():
            self.showMessage(title, msg, QSystemTrayIcon.Information, 2500)
