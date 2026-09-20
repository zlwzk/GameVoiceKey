"""配置存档.

- 用户数据目录：%APPDATA%/GameVoiceKey/
    - settings.json    全局设置
    - profiles/<game_id>.json  每个游戏一份
    - models/          Vosk 模型目录
    - logs/            日志

数据契约：
- 每个 Profile = 一个游戏的所有信息（进程名、规则、参数、场景等）
- 每个 Scene = 该 Profile 下的一个场景组（替换 rules）
- 全局 Settings = 跨游戏的开关、快捷键、自启等
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .logs import get_logger, user_data_dir

LOGGER = get_logger()

# ============================================================
# 路径
# ============================================================


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def profiles_dir() -> Path:
    p = user_data_dir() / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_dir() -> Path:
    p = user_data_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def backups_dir() -> Path:
    """快照目录（实现见 gvkey.userdata，这里保留同名入口）。"""

    from .userdata import backups_dir as _bd

    return _bd()


# ============================================================
# 数据类
# ============================================================


@dataclass
class VoiceRule:
    """一条「语音 -> 按键」规则。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    phrase: str = ""
    phrases: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    mode: str = "single"
    hold_ms: int = 80
    repeat_count: int = 1
    interval_ms: int = 50
    delay_ms: int = 0
    enabled: bool = True
    cooldown_ms: int = 250
    note: str = ""


@dataclass
class Scene:
    """场景组：切换时替换当前激活 Profile 的 rules 列表。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "新场景"
    enabled: bool = True
    rules: list[VoiceRule] = field(default_factory=list)


@dataclass
class Profile:
    """一个游戏的完整配置。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "未命名游戏"
    processes: list[str] = field(default_factory=list)
    window_title_regex: str = ""
    window_class: str = ""
    pin: bool = False
    enabled: bool = True
    sensitivity: float = 0.5
    phrase_similarity: float = 0.7
    denoise: bool = True
    silence_lock_ms: int = 600
    debounce_ms: int = 120
    mouse_enabled: bool = True
    keyboard_enabled: bool = True
    push_to_talk: bool = False
    push_to_talk_key: str = ""
    blacklisted_phrases: list[str] = field(default_factory=list)
    rules: list[VoiceRule] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    last_modified: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    # 向前兼容：未知字段原样保留（同 Settings.extra）
    extra: dict[str, Any] = field(default_factory=dict)

    def all_phrases(self) -> list[tuple["VoiceRule", str]]:
        out: list[tuple["VoiceRule", str]] = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            if rule.phrase.strip():
                out.append((rule, rule.phrase.strip()))
            for p in rule.phrases:
                if p.strip():
                    out.append((rule, p.strip()))
        return out


@dataclass
class Settings:
    """全局设置。"""

    schema_version: int = SCHEMA_VERSION

    master_enabled: bool = True
    auto_switch_enabled: bool = True
    only_when_game_focused: bool = True
    default_profile_id: str = ""

    overlay_enabled: bool = True
    overlay_mode: str = "standard"
    overlay_opacity: float = 0.78
    overlay_show_only_on_trigger: bool = False
    overlay_position: str = "topright"
    overlay_custom_pos: list[int] = field(default_factory=lambda: [100, 100])
    overlay_click_through: bool = True
    overlay_auto_compact_fullscreen: bool = True
    overlay_flash_seconds: float = 1.6
    overlay_show_key_on_trigger: bool = True

    asr_engine: str = "energy"
    asr_model: str = ""
    asr_input_device: str = ""
    asr_output_device: str = ""
    asr_language: str = "zh-CN"

    # 启动向导（麦克风 / 扬声器测试）是否已走完。
    # 放在 settings 里 —— 用户升级软件后不会被重新弹一遍。
    setup_wizard_done: bool = False
    setup_wizard_version: str = ""  # 走完向导时的软件版本，便于将来需要时重测

    hotkey_master_toggle: str = "Ctrl+Alt+V"
    hotkey_pause: str = "Ctrl+Alt+P"
    hotkey_reload: str = "Ctrl+Alt+R"
    hotkey_mute_mic: str = "Ctrl+Alt+M"

    whitelist_processes: list[str] = field(default_factory=list)
    blacklist_processes: list[str] = field(default_factory=list)

    autostart_enabled: bool = False
    start_minimized: bool = True
    play_sound_on_trigger: bool = False

    scan_interval_ms: int = 1500
    foreground_poll_ms: int = 250

    # 向前兼容：如果读到「更高版本程序」写入的未知字段，原样保留，
    # 下次保存再写回去。避免「新版本 → 旧版本 → 新版本」把设置丢掉。
    extra: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Profile 文件 IO
# ============================================================


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """原子写：先把旧内容滚成 ``.bak``，再临时文件 + replace。

    这样任何一次写入之后都同时存在「新文件」和「上一版良好副本」，
    即使新内容被人为改坏也能回退。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        except OSError:
            pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    with path.open("r", encoding="utf-8") as fh:
        got = json.load(fh)
    return got if isinstance(got, dict) else None


def _safe_read(path: Path) -> dict[str, Any] | None:
    """读 json：损坏时留证据（``.corrupt-*``）并尝试从 ``.bak`` 恢复。"""

    try:
        return _read_json(path)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        LOGGER.warning("无法解析 %s: %s", path, exc)
        if path.exists():
            try:
                bak = path.with_name(f"{path.name}.corrupt-{datetime.now():%Y%m%d-%H%M%S}")
                shutil.copy2(path, bak)
            except Exception:  # noqa: BLE001
                pass

        # 尝试从上次的良好副本恢复（这是「不丢数据」的最后一道闸）
        sibling = path.with_suffix(path.suffix + ".bak")
        if sibling.exists():
            try:
                recovered = _read_json(sibling)
            except Exception:  # noqa: BLE001
                recovered = None
            if recovered is not None:
                LOGGER.warning("已从 %s 恢复上次的良好配置", sibling.name)
                try:
                    _atomic_write(path, recovered)
                except OSError:
                    pass
                return recovered
        return None


def _known_fields(cls: type) -> set[str]:
    return set(getattr(cls, "__dataclass_fields__", {}).keys())


def _narrow(cls: type, raw: dict[str, Any], *, drop: tuple[str, ...] = ()) -> dict[str, Any]:
    """只取 ``cls`` 认识的字段，避免高版本写的未知字段把构造打崩。"""

    known = _known_fields(cls)
    skip = set(drop)
    return {k: v for k, v in raw.items() if k in known and k not in skip}


def _collect_unknown(
    cls: type, raw: dict[str, Any], *, drop: tuple[str, ...] = ()
) -> dict[str, Any]:
    """收集 ``cls`` 不认识的字段（含显式 drop 的），原样留待写回。"""

    known = _known_fields(cls) | set(drop)
    return {k: v for k, v in raw.items() if k not in known}


def _make_rule(raw: dict[str, Any]) -> VoiceRule:
    return VoiceRule(**_narrow(VoiceRule, raw))  # type: ignore[arg-type]


def _make_scene(raw: dict[str, Any]) -> Scene:
    s_rules = [_make_rule(r) for r in raw.get("rules", []) if isinstance(r, dict)]
    s = Scene(**_narrow(Scene, raw, drop=("rules",)))  # type: ignore[arg-type]
    s.rules = s_rules
    return s


def _profile_to_dict(p: Profile) -> dict[str, Any]:
    d = asdict(p)
    extra = d.pop("extra", {}) or {}
    d.update(extra)  # 未知字段平铺回顶层
    d["type"] = "profile"
    d["schema_version"] = SCHEMA_VERSION
    return d


def _dict_to_profile(d: dict[str, Any]) -> Profile:
    rules = [_make_rule(r) for r in d.get("rules", []) if isinstance(r, dict)]
    scenes = [_make_scene(s) for s in d.get("scenes", []) if isinstance(s, dict)]
    p = Profile(**_narrow(Profile, d, drop=("rules", "scenes", "extra")))  # type: ignore[arg-type]
    p.rules = rules
    p.scenes = scenes
    p.extra = _collect_unknown(Profile, d, drop=("type", "schema_version"))
    return p


def list_profiles() -> list[Profile]:
    out: list[Profile] = []
    for p in sorted(profiles_dir().glob("*.json")):
        d = _safe_read(p)
        if d and d.get("type") == "profile":
            try:
                out.append(_dict_to_profile(d))
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("profile 解析失败 %s: %s", p, exc)
    return out


def save_profile(profile: Profile) -> None:
    profile.last_modified = datetime.now().isoformat(timespec="seconds")
    _atomic_write(profiles_dir() / f"{profile.id}.json", _profile_to_dict(profile))


def load_profile(profile_id: str) -> Profile | None:
    p = profiles_dir() / f"{profile_id}.json"
    d = _safe_read(p)
    return _dict_to_profile(d) if d else None


def delete_profile(profile_id: str) -> None:
    p = profiles_dir() / f"{profile_id}.json"
    if p.exists():
        p.unlink()


def find_profile_by_process(proc_name: str) -> Profile | None:
    """根据进程名（不含 .exe，大小写不敏感）找匹配 Profile。"""

    from .process_monitor import normalize_process_name

    target = normalize_process_name(proc_name)
    for profile in list_profiles():
        for proc in profile.processes:
            if normalize_process_name(proc) == target:
                return profile
    return None


# ============================================================
# Settings IO
# ============================================================


def _settings_to_dict(s: Settings) -> dict[str, Any]:
    d = asdict(s)
    extra = d.pop("extra", {}) or {}
    d.update(extra)  # 未知字段平铺回顶层
    d["type"] = "settings"
    d["schema_version"] = SCHEMA_VERSION  # 写的时候总是升到当前
    return d


def _dict_to_settings(d: dict[str, Any]) -> Settings:
    s = Settings(**_narrow(Settings, d, drop=("extra",)))  # type: ignore[arg-type]
    s.extra = _collect_unknown(Settings, d, drop=("type",))
    return s


def load_settings() -> Settings:
    p = settings_path()
    d = _safe_read(p)
    if d is None:
        s = Settings()
        save_settings(s)
        return s
    s = _dict_to_settings(d)
    file_schema = int(d.get("schema_version", SCHEMA_VERSION) or SCHEMA_VERSION)
    if file_schema != SCHEMA_VERSION:
        LOGGER.info("settings.json schema %s -> %s（已自动迁移）", file_schema, SCHEMA_VERSION)
        save_settings(s)  # 立刻把迁移结果落盘，避免下次再算
    return s


def save_settings(s: Settings) -> None:
    _atomic_write(settings_path(), _settings_to_dict(s))


# ============================================================
# 导入 / 导出
# ============================================================


def export_profile(profile: Profile) -> str:
    payload = {
        "type": "gvprofile",
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "profile": _profile_to_dict(profile),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def import_profile(text: str) -> Profile | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        LOGGER.warning("导入失败：JSON 解析 - %s", exc)
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("type") == "gvprofile":
        data = payload.get("profile", {})
    elif "rules" in payload:
        data = payload
    else:
        return None
    try:
        # 导入要生成新 id，避免覆盖
        data = dict(data)
        data.pop("id", None)
        p = _dict_to_profile(data)
        return p
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("导入失败：结构错误 - %s", exc)
        return None


# ============================================================
# 内置示例
# ============================================================


_SEED_PROFILES: list[dict[str, Any]] = [
    {
        "name": "示例 - FPS",
        "processes": ["csgo", "valorant", "cs2"],
        "rules": [
            {"phrase": "开枪", "keys": ["LMB"], "mode": "single", "phrases": [], "hold_ms": 80, "repeat_count": 1, "interval_ms": 50, "delay_ms": 0, "enabled": True, "cooldown_ms": 250, "note": ""},
            {"phrase": "跳跃", "keys": ["Space"], "mode": "single", "phrases": [], "hold_ms": 80, "repeat_count": 1, "interval_ms": 50, "delay_ms": 0, "enabled": True, "cooldown_ms": 200, "note": ""},
            {"phrase": "换弹", "keys": ["R"], "mode": "hold", "phrases": [], "hold_ms": 150, "repeat_count": 1, "interval_ms": 50, "delay_ms": 0, "enabled": True, "cooldown_ms": 1000, "note": ""},
            {"phrase": "开镜", "keys": ["RMB"], "mode": "hold", "phrases": ["瞄准", "拉枪"], "hold_ms": 300, "repeat_count": 1, "interval_ms": 50, "delay_ms": 0, "enabled": True, "cooldown_ms": 200, "note": ""},
            {"phrase": "蹲下", "keys": ["Ctrl"], "mode": "hold", "phrases": [], "hold_ms": 200, "repeat_count": 1, "interval_ms": 50, "delay_ms": 0, "enabled": True, "cooldown_ms": 200, "note": ""},
        ],
    },
    {
        "name": "示例 - MOBA",
        "processes": ["league", "leagueclientux"],
        "rules": [
            {"phrase": "发起进攻", "keys": ["G"], "mode": "single", "phrases": [], "hold_ms": 80, "repeat_count": 1, "interval_ms": 50, "delay_ms": 0, "enabled": True, "cooldown_ms": 500, "note": ""},
            {"phrase": "撤退", "keys": ["V"], "mode": "single", "phrases": [], "hold_ms": 80, "repeat_count": 1, "interval_ms": 50, "delay_ms": 0, "enabled": True, "cooldown_ms": 500, "note": ""},
            {"phrase": "看地图", "keys": ["Y"], "mode": "single", "phrases": [], "hold_ms": 80, "repeat_count": 1, "interval_ms": 50, "delay_ms": 0, "enabled": True, "cooldown_ms": 300, "note": ""},
        ],
    },
]


def seed_if_empty() -> list[Profile]:
    existing = list_profiles()
    if existing:
        return existing
    profiles: list[Profile] = []
    for seed in _SEED_PROFILES:
        rules = [VoiceRule(**r) for r in seed.get("rules", [])]
        p = Profile(
            name=seed["name"],
            processes=seed.get("processes", []),
            enabled=seed.get("enabled", True),
            rules=rules,
        )
        save_profile(p)
        profiles.append(p)
    LOGGER.info("已写入 %d 份示例 profile", len(profiles))
    return profiles


# ============================================================
# ProfileStore（内存索引 + 订阅）
# ============================================================


class ProfileStore:
    """带内存缓存的 Profile 仓库，供 Engine 与 UI 共享。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, Profile] = {}
        self._listeners: list[Any] = []

    def reload(self) -> list[Profile]:
        with self._lock:
            profiles = list_profiles()
            self._cache = {p.id: p for p in profiles}
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(list(profiles))
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("ProfileStore listener failed: %s", exc)
        return profiles

    def all(self) -> list[Profile]:
        with self._lock:
            if not self._cache:
                return self.reload()
            return sorted(
                self._cache.values(),
                key=lambda p: (not p.pin, -datetime.fromisoformat(p.last_modified).timestamp(), p.name),
            )

    def get(self, pid: str) -> Profile | None:
        with self._lock:
            return self._cache.get(pid)

    def upsert(self, profile: Profile) -> None:
        save_profile(profile)
        self.reload()

    def remove(self, pid: str) -> None:
        delete_profile(pid)
        self.reload()

    def subscribe(self, cb: Any) -> None:
        with self._lock:
            self._listeners.append(cb)

    def unsubscribe(self, cb: Any) -> None:
        with self._lock:
            if cb in self._listeners:
                self._listeners.remove(cb)
