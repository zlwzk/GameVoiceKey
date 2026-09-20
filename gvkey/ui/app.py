"""QApplication 入口."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from .. import __app_display_name__, __app_name__, __version__
from ..config import seed_if_empty
from ..engine import get_engine
from ..logs import get_logger, setup_logging
from ..userdata import bootstrap as bootstrap_userdata
from .main_window import MainWindow
from .theme import apply_theme
from .tray import TrayIcon


def _make_default_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QBrush(QColor("#2f6e5b")))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setBrush(QBrush(QColor("#b9efe0")))
    p.setPen(Qt.NoPen)
    p.drawEllipse(16, 18, 10, 10)
    p.drawEllipse(38, 18, 10, 10)
    p.setBrush(QBrush(QColor("#0d1116")))
    p.drawEllipse(19, 21, 4, 4)
    p.drawEllipse(41, 21, 4, 4)
    p.setBrush(QBrush(QColor("#b9efe0")))
    p.drawRoundedRect(20, 36, 24, 6, 3, 3)
    p.end()
    return QIcon(pix)


def run() -> int:
    setup_logging("INFO")

    # 数据隔离体检 + schema 迁移 + 升级自动快照。
    # 必须在任何读写用户数据之前执行。
    for notice in bootstrap_userdata():
        get_logger().warning("%s", notice)

    seed_if_empty()

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(__app_display_name__)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    icon = _make_default_icon()
    app.setWindowIcon(icon)

    apply_theme(app)

    # 设备检测向导：在引擎启动前跑，避免麦克风被采集流占着测不出电平。
    # 只在首次启动弹（走完会写进 settings.setup_wizard_done）。
    from ..config import load_settings
    from .first_run import run_wizard_if_needed

    settings = load_settings()
    try:
        run_wizard_if_needed(settings)
    except Exception as exc:  # noqa: BLE001 - 向导失败绝不能拦住主程序
        get_logger().warning("设备检测向导异常: %s", exc)

    engine = get_engine()
    engine.start()

    main_window = MainWindow(engine=engine, icon=icon)
    tray = TrayIcon(parent=main_window, icon=icon, engine=engine,
                    on_show=lambda: main_window.show_and_raise(),
                    on_quit=lambda: _shutdown(app, engine))
    main_window.bind_tray(tray)
    main_window.show()

    from ..overlay import OverlayWindow
    overlay = OverlayWindow(engine.settings)
    main_window.bind_overlay(overlay)
    main_window.wire_engine_to_overlay(engine, overlay)

    return app.exec()


def _shutdown(app: QApplication, engine) -> None:
    try:
        engine.stop()
    except Exception:
        pass
    app.quit()


if __name__ == "__main__":
    sys.exit(run())
