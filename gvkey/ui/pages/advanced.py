"""高级设置页."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                                QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                                QListWidget, QListWidgetItem, QMessageBox,
                                QPushButton, QSpinBox, QToolButton, QVBoxLayout,
                                QWidget)

from ... import __app_name__, __version__
from ...config import Settings, save_settings
from ...engine import Engine
from ...transcriber import VOSK_MODEL_PRESETS
from ...windows import get_autostart, remove_autostart, set_autostart, current_exe_path


class AdvancedPage(QWidget):
    def __init__(self, engine: Engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setObjectName("PageInner")
        self._build()
        self.reload()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        title = QLabel("高级设置")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        hint = QLabel("设置会立即生效；自动保存到 settings.json。")
        hint.setObjectName("PageHint")
        outer.addWidget(hint)

        # ====== 进程自动识别 ======
        gb_proc = QGroupBox("进程自动识别")
        lay = QVBoxLayout(gb_proc)
        self.ck_auto = QCheckBox("启用自动进程切换")
        lay.addWidget(self.ck_auto)
        row_int = QHBoxLayout()
        row_int.addWidget(QLabel("扫描周期"))
        self.sp_scan = QSpinBox()
        self.sp_scan.setRange(300, 10_000)
        self.sp_scan.setSingleStep(100)
        self.sp_scan.setSuffix(" ms")
        row_int.addWidget(self.sp_scan)
        row_int.addStretch(1)
        lay.addLayout(row_int)
        lay.addWidget(QLabel("白名单进程（仅扫描列表内进程，留空表示不限）"))
        self._whitelist = QListWidget()
        self._whitelist.setMaximumHeight(90)
        lay.addWidget(self._whitelist)
        wl_btns = QHBoxLayout()
        self._ed_wl = QLineEdit()
        self._ed_wl.setPlaceholderText("添加进程名（不含 .exe）")
        wl_btns.addWidget(self._ed_wl, 1)
        btn_wl_add = QPushButton("添加")
        btn_wl_add.clicked.connect(lambda: self._add_to_list(self._whitelist, self._ed_wl))
        wl_btns.addWidget(btn_wl_add)
        btn_wl_del = QPushButton("删除选中")
        btn_wl_del.clicked.connect(lambda: self._del_from_list(self._whitelist))
        wl_btns.addWidget(btn_wl_del)
        lay.addLayout(wl_btns)

        lay.addWidget(QLabel("黑名单进程（强制忽略）"))
        self._blacklist = QListWidget()
        self._blacklist.setMaximumHeight(90)
        lay.addWidget(self._blacklist)
        bl_btns = QHBoxLayout()
        self._ed_bl = QLineEdit()
        self._ed_bl.setPlaceholderText("添加进程名（不含 .exe）")
        bl_btns.addWidget(self._ed_bl, 1)
        btn_bl_add = QPushButton("添加")
        btn_bl_add.clicked.connect(lambda: self._add_to_list(self._blacklist, self._ed_bl))
        bl_btns.addWidget(btn_bl_add)
        btn_bl_del = QPushButton("删除选中")
        btn_bl_del.clicked.connect(lambda: self._del_from_list(self._blacklist))
        bl_btns.addWidget(btn_bl_del)
        lay.addLayout(bl_btns)

        outer.addWidget(gb_proc)

        # ====== 语音识别 ======
        gb_asr = QGroupBox("语音识别引擎")
        asr_lay = QVBoxLayout(gb_asr)
        row_eng = QHBoxLayout()
        row_eng.addWidget(QLabel("识别引擎"))
        self.cmb_engine = QComboBox()
        self.cmb_engine.addItems(["energy (无模型, 仅能量检测)",
                                   "vosk (离线语音转文字)"])
        row_eng.addWidget(self.cmb_engine)
        row_eng.addStretch(1)
        asr_lay.addLayout(row_eng)
        row_model = QHBoxLayout()
        row_model.addWidget(QLabel("Vosk 模型路径（可选）"))
        self._ed_model = QLineEdit()
        self._ed_model.setPlaceholderText("例如 vosk-model-small-cn-0.22")
        row_model.addWidget(self._ed_model, 1)
        btn_pick = QPushButton("浏览…")
        btn_pick.clicked.connect(self._pick_model)
        row_model.addWidget(btn_pick)
        asr_lay.addLayout(row_model)

        self._lbl_model_status = QLabel("")
        self._lbl_model_status.setObjectName("CardHint")
        asr_lay.addWidget(self._lbl_model_status)

        # 一键下载模型
        self._model_btn_layout = QVBoxLayout()
        asr_lay.addLayout(self._model_btn_layout)
        for m in VOSK_MODEL_PRESETS:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{m['name']}  ·  {m['note']}"))
            row.addStretch(1)
            btn = QPushButton(f"下载 {m['size_mb']}MB")
            btn.setObjectName("Ghost")
            btn.clicked.connect(lambda _=False, url=m["url"], mid=m["id"]: self._download_model(url, mid))
            row.addWidget(btn)
            self._model_btn_layout.addLayout(row)
        outer.addWidget(gb_asr)

        # ====== 全局热键 ======
        gb_hot = QGroupBox("全局热键")
        hlay = QVBoxLayout(gb_hot)
        self._ed_hotk_master = QLineEdit(); hlay.addLayout(self._labeled("总开关", self._ed_hotk_master))
        self._ed_hotk_pause = QLineEdit(); hlay.addLayout(self._labeled("暂停监听", self._ed_hotk_pause))
        self._ed_hotk_reload = QLineEdit(); hlay.addLayout(self._labeled("重新加载配置", self._ed_hotk_reload))
        self._ed_hotk_mute = QLineEdit(); hlay.addLayout(self._labeled("静音麦克风", self._ed_hotk_mute))
        btn_save_hot = QPushButton("保存热键设置")
        btn_save_hot.clicked.connect(self._save_hotkeys)
        hlay.addWidget(btn_save_hot)
        outer.addWidget(gb_hot)

        # ====== 防误触 / 启动 ======
        gb_safe = QGroupBox("防误触 + 启动")
        slay = QVBoxLayout(gb_safe)
        self.ck_only_focused = QCheckBox("仅游戏窗口激活时生效（推荐）")
        slay.addWidget(self.ck_only_focused)
        self.ck_start_minimized = QCheckBox("启动时最小化到托盘")
        slay.addWidget(self.ck_start_minimized)
        self.ck_autostart = QCheckBox("开机自启")
        self.ck_autostart.toggled.connect(self._toggle_autostart)
        slay.addWidget(self.ck_autostart)
        outer.addWidget(gb_safe)

        # ====== 保存按钮 ======
        save_row = QHBoxLayout()
        btn_apply = QPushButton("保存全部")
        btn_apply.setObjectName("Primary")
        btn_apply.clicked.connect(self._save_all)
        save_row.addWidget(btn_apply)
        save_row.addStretch(1)
        btn_reset = QPushButton("恢复默认")
        btn_reset.setObjectName("Danger")
        btn_reset.clicked.connect(self._reset_defaults)
        save_row.addWidget(btn_reset)
        outer.addLayout(save_row)
        outer.addStretch(1)

    def _labeled(self, text: str, edit: QLineEdit):
        h = QHBoxLayout()
        h.addWidget(QLabel(text))
        h.addWidget(edit, 1)
        return h

    # ----- 数据 -----

    def reload(self) -> None:
        s: Settings = self.engine.settings
        self.ck_auto.setChecked(s.auto_switch_enabled)
        self.sp_scan.setValue(s.scan_interval_ms)
        self._whitelist.clear();
        for n in s.whitelist_processes: self._whitelist.addItem(QListWidgetItem(n))
        self._blacklist.clear();
        for n in s.blacklist_processes: self._blacklist.addItem(QListWidgetItem(n))
        self.cmb_engine.setCurrentIndex(1 if s.asr_engine.lower() == "vosk" else 0)
        self._ed_model.setText(s.asr_model)
        self._refresh_model_status()
        self._ed_hotk_master.setText(s.hotkey_master_toggle)
        self._ed_hotk_pause.setText(s.hotkey_pause)
        self._ed_hotk_reload.setText(s.hotkey_reload)
        self._ed_hotk_mute.setText(s.hotkey_mute_mic)
        self.ck_only_focused.setChecked(s.only_when_game_focused)
        self.ck_start_minimized.setChecked(s.start_minimized)
        self.ck_autostart.blockSignals(True)
        self.ck_autostart.setChecked(s.autostart_enabled)
        self.ck_autostart.blockSignals(False)

    def _refresh_model_status(self) -> None:
        from ...config import models_dir
        path = (self._ed_model.text() or "").strip()
        candidates = []
        if path:
            candidates.append(path)
        candidates.append(str(models_dir() / path))
        for c in candidates:
            if c and (models_dir() / c).exists():
                self._lbl_model_status.setText(f"已找到模型目录：{c}")
                return
            from pathlib import Path as _P
            if _P(c).exists():
                self._lbl_model_status.setText(f"已找到模型：{c}")
                return
        self._lbl_model_status.setText("尚未配置有效模型，首次切换到 vosk 引擎时将尝试自动加载。")

    # ----- actions -----

    def _save_all(self) -> None:
        s: Settings = self.engine.settings
        s.auto_switch_enabled = self.ck_auto.isChecked()
        s.scan_interval_ms = self.sp_scan.value()
        s.whitelist_processes = self._list_to_list(self._whitelist)
        s.blacklist_processes = self._list_to_list(self._blacklist)
        s.asr_engine = "vosk" if self.cmb_engine.currentIndex() == 1 else "energy"
        s.asr_model = self._ed_model.text().strip()
        s.only_when_game_focused = self.ck_only_focused.isChecked()
        s.start_minimized = self.ck_start_minimized.isChecked()
        s.autostart_enabled = self.ck_autostart.isChecked()
        save_settings(s)
        # 让 engine 重新加载部分
        self.engine.set_settings(
            scan_interval_ms=s.scan_interval_ms,
            whitelist_processes=s.whitelist_processes,
            blacklist_processes=s.blacklist_processes,
            asr_engine=s.asr_engine,
            asr_model=s.asr_model,
        )
        self._save_hotkeys(silent=True)
        self._save_autostart(silent=True)
        QMessageBox.information(self, "保存", "已保存。")

    def _save_hotkeys(self, silent: bool = False) -> None:
        s: Settings = self.engine.settings
        s.hotkey_master_toggle = self._ed_hotk_master.text().strip() or s.hotkey_master_toggle
        s.hotkey_pause = self._ed_hotk_pause.text().strip() or s.hotkey_pause
        s.hotkey_reload = self._ed_hotk_reload.text().strip() or s.hotkey_reload
        s.hotkey_mute_mic = self._ed_hotk_mute.text().strip() or s.hotkey_mute_mic
        save_settings(s)
        self.engine.set_settings(
            hotkey_master_toggle=s.hotkey_master_toggle,
            hotkey_pause=s.hotkey_pause,
            hotkey_reload=s.hotkey_reload,
            hotkey_mute_mic=s.hotkey_mute_mic,
        )
        if not silent:
            QMessageBox.information(self, "热键", "热键已保存并重新注册。")

    def _toggle_autostart(self, checked: bool) -> None:
        self._save_autostart()

    def _save_autostart(self, silent: bool = False) -> None:
        s: Settings = self.engine.settings
        if s.autostart_enabled:
            ok = set_autostart(__app_name__, current_exe_path().strip('"'),
                               args="--minimized" if s.start_minimized else "")
            if not ok:
                QMessageBox.warning(self, "开机自启", "写入注册表失败，请以管理员权限运行软件。")
        else:
            remove_autostart(__app_name__)
        save_settings(s)
        if not silent:
            pass

    def _reset_defaults(self) -> None:
        if QMessageBox.question(self, "确认", "恢复默认设置？所有自定义配置将被覆盖（但游戏配置不受影响）。") != QMessageBox.Yes:
            return
        from ...config import Settings
        save_settings(Settings())
        self.engine.reload()
        self.reload()
        QMessageBox.information(self, "已恢复", "已重置为默认设置。")

    def _add_to_list(self, lst: QListWidget, edit: QLineEdit) -> None:
        txt = edit.text().strip()
        if not txt:
            return
        items = [lst.item(i).text() for i in range(lst.count())]
        if txt.lower() in (x.lower() for x in items):
            edit.clear()
            return
        lst.addItem(QListWidgetItem(txt))
        edit.clear()

    def _del_from_list(self, lst: QListWidget) -> None:
        for item in lst.selectedItems():
            lst.takeItem(lst.row(item))

    def _list_to_list(self, lst: QListWidget) -> list[str]:
        return [lst.item(i).text() for i in range(lst.count())]

    def _pick_model(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择 Vosk 模型目录", "")
        if not d:
            return
        self._ed_model.setText(d)
        self._refresh_model_status()

    def _download_model(self, url: str, mid: str) -> None:
        from ...config import models_dir
        target = models_dir() / mid
        if (target).exists() and any(target.iterdir() if target.is_dir() else False):
            QMessageBox.information(self, "模型", f"已存在：{target}\n将直接使用。")
            self._ed_model.setText(str(target))
            self._refresh_model_status()
            return
        QMessageBox.information(
            self, "下载说明",
            f"即将打开下载链接，把压缩包解压到：\n{target}\n\n完成后回到这里选这个目录作为 Vosk 模型路径。",
        )
        import webbrowser
        webbrowser.open(url)
