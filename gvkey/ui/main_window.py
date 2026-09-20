"""主窗口."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                                QMainWindow, QStackedWidget, QStatusBar, QVBoxLayout,
                                QWidget)

from .. import __app_display_name__, __version__
from ..engine import Engine, Event
from ..logs import get_logger
from ..overlay import OverlayWindow
from .pages.advanced import AdvancedPage
from .pages.editor import EditorPage
from .pages.home import HomePage
from .pages.logs import LogsPage
from .pages.overlay import OverlaySettingsPage
from .pages.profiles import ProfilesPage
from .tray import TrayIcon

LOGGER = get_logger()

NAV = [
    ("首页", "选择当前游玩的游戏"),
    ("游戏配置", "管理多游戏配置"),
    ("语音按键编辑", "自定义短语 + 按键映射"),
    ("高级设置", "声音设备 / 进程 / 热键 / 备份"),
    ("日志与统计", "触发记录 / 成功率"),
    ("悬浮窗", "外观与位置"),
]

PAGE_INDEX = {name: i for i, (name, _) in enumerate(NAV)}


class MainWindow(QMainWindow):

    status_busy = Signal(bool)

    def __init__(self, engine: Engine, icon: QIcon) -> None:
        super().__init__()
        self.engine = engine
        self._icon = icon
        self.setWindowTitle(f"{__app_display_name__} · v{__version__}")
        self.setWindowIcon(icon)
        self.resize(1080, 720)
        self.setMinimumSize(960, 620)

        # 侧栏 + stack
        root = QWidget(self)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(root)

        # ===== Sidebar =====
        sidebar = QWidget(root)
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        header = QWidget(sidebar)
        header.setObjectName("SidebarHeader")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(16, 16, 16, 12)
        hl.setSpacing(4)
        title = QLabel(__app_display_name__)
        title.setObjectName("AppTitle")
        hl.addWidget(title)
        sub = QLabel(f"v{__version__} · 自动游戏语音按键")
        sub.setObjectName("AppSubtitle")
        hl.addWidget(sub)
        sl.addWidget(header)

        self._nav = QListWidget(sidebar)
        self._nav.setObjectName("NavList")
        for name, hint in NAV:
            item = QListWidgetItem(name)
            item.setToolTip(hint)
            self._nav.addItem(item)
        self._nav.setCurrentRow(0)
        sl.addWidget(self._nav, 1)

        footer = QLabel(
            f"v{__version__}\n配置存于 %APPDATA%\\GameVoiceKey\n升级覆盖 exe 不会丢配置"
        )
        footer.setObjectName("SidebarFooter")
        footer.setWordWrap(True)
        sl.addWidget(footer)

        layout.addWidget(sidebar)

        # ===== Stack =====
        self._stack = QStackedWidget(root)
        self._stack.setObjectName("PageStack")
        self.home_page = HomePage(self.engine, self)
        self.profiles_page = ProfilesPage(self.engine, self)
        self.editor_page = EditorPage(self.engine, self)
        self.advanced_page = AdvancedPage(self.engine, self)
        self.logs_page = LogsPage(self.engine, self)
        self.overlay_page = OverlaySettingsPage(self.engine, self)
        for p in (self.home_page, self.profiles_page, self.editor_page,
                  self.advanced_page, self.logs_page, self.overlay_page):
            self._stack.addWidget(p)
        layout.addWidget(self._stack, 1)

        # ===== Statusbar =====
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status = QLabel("就绪")
        sb.addPermanentWidget(self._status)
        sb.showMessage(f"{__app_display_name__} · v{__version__} · 数据存于 %APPDATA%\\GameVoiceKey")

        # ===== 信号 =====
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        self.engine.bus.subscribe("engine.state", self._on_engine_state)
        self.engine.bus.subscribe("profile.switched", self._on_profile_switched)
        self.engine.bus.subscribe("profile.unmatched", self._on_profile_unmatched)

    # ----- 跟 nav 联动 -----
    def _on_nav_changed(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        # 切到对应页面时让它刷新
        page = self._stack.currentWidget()
        if hasattr(page, "on_show"):
            try:
                page.on_show()
            except Exception:
                pass

    def goto(self, page: str) -> None:
        idx = PAGE_INDEX.get(page, 0)
        self._nav.setCurrentRow(idx)

    def goto_editor_for(self, profile_id: str) -> None:
        """跳到「语音按键编辑」页并载入指定配置.

        首页「选择当前游玩的游戏」选完就走这里 —— 选完立刻能配键，
        不用用户自己去另一个页面再找一遍。
        """

        try:
            self.editor_page.load_profile(profile_id)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("载入配置失败: %s", exc)
        self.goto("语音按键编辑")
        # 让用户一眼看到「现在配的是哪个游戏」
        self.statusBar().showMessage(f"正在配置「{self._profile_label(profile_id)}」", 4000)

    def _profile_label(self, profile_id: str) -> str:
        try:
            profile = self.engine.profile_store.get(profile_id)
        except Exception:  # noqa: BLE001
            profile = None
        return profile.name if profile else profile_id

    # ----- overlay 联动 -----
    def bind_overlay(self, overlay: OverlayWindow) -> None:
        self._overlay = overlay
        if self.engine.settings.overlay_enabled:
            overlay.show()

    def wire_engine_to_overlay(self, engine: Engine, overlay: OverlayWindow) -> None:
        """把 Engine 事件接到 Overlay."""

        def _state(ev: Event):
            overlay.set_state(ev.payload.get("state", "idle"))

        def _level(ev: Event):
            overlay.feed_level(ev.payload.get("level", 0.0))

        def _profile(ev: Event):
            prof = ev.payload.get("profile")
            if prof:
                overlay.set_profile(prof.name)

        def _profile_off(_ev: Event):
            overlay.set_idle()

        def _trigger(ev: Event):
            overlay.set_trigger(ev.payload.get("phrase", ""), ev.payload.get("key", ""))

        engine.bus.subscribe("engine.state", _state)
        engine.bus.subscribe("audio.level", _level)
        engine.bus.subscribe("profile.switched", _profile)
        engine.bus.subscribe("profile.unmatched", _profile_off)
        engine.bus.subscribe("trigger", _trigger)

    def bind_tray(self, tray: TrayIcon) -> None:
        self._tray = tray

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    # ----- engine 状态回调 -----
    def _on_engine_state(self, ev: Event) -> None:
        s = ev.payload.get("state", "stopped")
        text_map = {
            "active": "已启动 · 正在监听",
            "paused": "已暂停",
            "muted": "麦克风静音",
            "disabled": "总开关关闭",
            "idle": "待机 · 等待匹配游戏",
            "stopped": "已停止",
        }
        self._status.setText(text_map.get(s, s))

    def _on_profile_switched(self, ev: Event) -> None:
        prof = ev.payload.get("profile")
        if prof:
            self.home_page.set_profile_name(prof.name)
            self.profiles_page.refresh()

    def _on_profile_unmatched(self, _ev: Event) -> None:
        self.home_page.set_profile_name("")
        self.profiles_page.refresh()

    # ----- 关闭事件 -----
    def closeEvent(self, ev) -> None:  # noqa: N802
        # 不退出，最小化到托盘
        if getattr(self, "_tray", None) and self._tray.isVisible():
            ev.ignore()
            self.hide()
            self._tray.show_notification("仍在后台运行", "GameVoiceKey 已在系统托盘驻留")
        else:
            ev.accept()
