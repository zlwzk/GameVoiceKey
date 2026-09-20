"""GameVoiceKey 自检脚本.

跑 `python -m scripts.selftest`：
- 13 项核心模块 + 数据契约断言
- 不要求真实硬件，只验证逻辑可工作
- 退出码：0=全过，1=有失败
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable

# 把 APPDATA 重定向到临时目录，避免污染用户真实数据
_TEMP_APPDATA = Path(tempfile.mkdtemp(prefix="gvkey-selftest-"))
os.environ["APPDATA"] = str(_TEMP_APPDATA)


class TestRunner:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def run(self, name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
            self.results.append((name, True, ""))
            print(f"  [+] {name}")
        except AssertionError as exc:
            self.results.append((name, False, str(exc)))
            print(f"  [-] {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            self.results.append((name, False, f"{type(exc).__name__}: {exc}"))
            print(f"  [-] {name}: {type(exc).__name__}: {exc}")

    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.results)

    def summary(self) -> None:
        total = len(self.results)
        ok = sum(1 for _, x, _ in self.results if x)
        print(f"\n=== {ok}/{total} passed ===")
        if ok < total:
            print("\n失败项：")
            for n, x, msg in self.results:
                if not x:
                    print(f"  - {n}: {msg}")


def test_version() -> None:
    import gvkey
    assert gvkey.__version__ == "0.1.0", f"version 错: {gvkey.__version__}"
    assert gvkey.SCHEMA_VERSION >= 1


def test_logs_init() -> None:
    from gvkey.logs import setup_logging, get_logger, trigger_history, record_trigger
    setup_logging("INFO")
    log = get_logger()
    assert log.name == "gvkey"
    record_trigger(profile="p1", phrase="x", key="y", success=True)
    h = trigger_history(10)
    assert any(e["profile"] == "p1" for e in h)


def test_user_data_dir_isolation() -> None:
    from gvkey.logs import user_data_dir
    p = user_data_dir()
    assert p.exists()
    assert p.name == "GameVoiceKey"


def test_config_io() -> None:
    from gvkey.config import Settings, save_settings, load_settings
    s = Settings(asr_engine="vosk", scan_interval_ms=2200)
    save_settings(s)
    loaded = load_settings()
    assert loaded.asr_engine == "vosk"
    assert loaded.scan_interval_ms == 2200


def test_profile_roundtrip() -> None:
    from gvkey.config import Profile, VoiceRule, save_profile, load_profile, profiles_dir
    p = Profile(name="测试Profile",
                processes=["csgo", "hl2"],
                sensitivity=0.42,
                push_to_talk_key="Ctrl+Space")
    p.rules.append(VoiceRule(phrase="开枪", keys=["LMB"], mode="single"))
    p.rules.append(VoiceRule(phrase="开镜", keys=["RMB"], mode="hold", hold_ms=300))
    save_profile(p)
    loaded = load_profile(p.id)
    assert loaded is not None
    assert loaded.name == "测试Profile"
    assert loaded.processes == ["csgo", "hl2"]
    assert loaded.sensitivity == 0.42
    assert loaded.push_to_talk_key == "Ctrl+Space"
    assert len(loaded.rules) == 2
    assert loaded.rules[0].phrase == "开枪"
    assert loaded.rules[1].hold_ms == 300
    assert (profiles_dir() / f"{p.id}.json").exists()


def test_seed_if_empty() -> None:
    """清空 profiles 目录后再调 seed_if_empty，验证种子会全部写入."""

    from gvkey.config import seed_if_empty, profiles_dir
    import shutil
    pd = profiles_dir()
    if pd.exists():
        # 只清 profiles，logs/settings 留着（log handler 还开着日志文件）
        for f in pd.glob("*.json"):
            f.unlink()
        for f in pd.glob("*.bak"):
            f.unlink()
        for f in pd.glob("*.corrupt-*"):
            f.unlink()
    profiles = seed_if_empty()
    assert len(profiles) >= 2, f"expected >= 2 seed profiles, got {len(profiles)}"
    files = list(profiles_dir().glob("*.json"))
    assert len(files) >= 2


def test_export_import_profile() -> None:
    from gvkey.config import Profile, VoiceRule, export_profile, import_profile
    p = Profile(name="导出测试")
    p.rules.append(VoiceRule(phrase="跳跃", keys=["Space"], mode="single"))
    text = export_profile(p)
    payload = json.loads(text)
    assert payload["type"] == "gvprofile"
    assert payload["schema_version"] >= 1
    restored = import_profile(text)
    assert restored is not None
    assert restored.name == "导出测试"
    assert restored.id != p.id  # 导入应换新 id
    assert len(restored.rules) == 1
    assert restored.rules[0].phrase == "跳跃"


def test_parse_key() -> None:
    from gvkey.keyboard_sim import parse_key
    p = parse_key("Ctrl+1")
    assert "ctrl" in p.modifiers
    assert p.key == "1"
    assert not p.is_mouse and not p.is_wheel
    p = parse_key("LMB")
    assert p.is_mouse and p.key == "left"
    p = parse_key("RMB")
    assert p.is_mouse and p.key == "right"
    p = parse_key("WheelUp")
    assert p.is_wheel and p.wheel_delta == -1
    p = parse_key("F12")
    assert p.key == "f12"
    p = parse_key("Ctrl+Alt+Shift+F1")
    assert "ctrl" in p.modifiers and "alt" in p.modifiers and "shift" in p.modifiers
    p = parse_key("MMB")
    assert p.is_mouse and p.key == "middle"


def test_keyword_matcher_exact() -> None:
    from gvkey.config import Profile, VoiceRule
    from gvkey.engine import KeywordMatcher
    p = Profile(name="P")
    p.rules.append(VoiceRule(phrase="开枪", keys=["LMB"], mode="single"))
    m = KeywordMatcher()
    hit = m.find("开枪", p)
    assert hit is not None
    rule, phrase, score = hit
    assert rule.phrase == "开枪"
    assert score == 1.0


def test_keyword_matcher_similarity() -> None:
    from gvkey.config import Profile, VoiceRule
    from gvkey.engine import KeywordMatcher
    p = Profile(name="P", phrase_similarity=0.5)
    p.rules.append(VoiceRule(phrase="开枪", keys=["LMB"], mode="single"))
    m = KeywordMatcher()
    hit = m.find("开枪啊", p)
    assert hit is not None
    _, _, score = hit
    assert score >= 0.5


def test_keyword_blacklist_blocks() -> None:
    from gvkey.config import Profile, VoiceRule
    from gvkey.engine import KeywordMatcher
    p = Profile(name="P", blacklisted_phrases=["结束", "取消"])
    p.rules.append(VoiceRule(phrase="开枪", keys=["LMB"], mode="single"))
    p.rules.append(VoiceRule(phrase="结束", keys=["ESC"], mode="single"))
    m = KeywordMatcher()
    assert m.find("结束", p) is None
    assert m.find("开枪", p) is not None


def test_transcriber_energy() -> None:
    from gvkey.transcriber import EnergyTranscriber
    t = EnergyTranscriber(threshold=0.05, silence_ms=80, speech_min_ms=40)
    events: list = []
    t.on_activity = lambda ev: events.append(ev.state)
    t.on_transcript = lambda ev: events.append("transcript")
    t.start()
    t.feed(b"\x00\x00" * 800, energy=0.01)
    t.feed(b"\xff\x7f" * 4000, energy=0.5)
    assert "speech_start" in events, f"unexpected events: {events}"


def test_engine_smoke() -> None:
    from gvkey import config
    from gvkey.engine import Engine
    config.seed_if_empty()
    eng = Engine()
    eng.start()
    assert eng._running
    assert eng.state in {"active", "idle", "disabled", "paused", "muted", "stopped"}
    eng.stop()
    assert not eng._running


def test_corrupt_backup_on_read() -> None:
    from gvkey.config import settings_path
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{this is not valid json,", encoding="utf-8")
    backups_before = list(p.parent.glob("*.corrupt-*"))
    from gvkey.config import load_settings
    s = load_settings()
    assert s.schema_version >= 1
    backups_after = list(p.parent.glob("*.corrupt-*"))
    # 至少应该有一个新备份
    assert len(backups_after) > len(backups_before), (
        f"expected backup to be created, before={backups_before} after={backups_after}"
    )


def test_overlay_window_smoke() -> None:
    """OverlayWindow 实例化不应抛异常（需要先有 QApplication）."""
    from PySide6.QtWidgets import QApplication
    from gvkey.config import Settings
    from gvkey.overlay import OverlayWindow
    app = QApplication.instance() or QApplication(sys.argv)
    settings = Settings()
    w = OverlayWindow(settings)
    assert w._dot is not None
    assert w._wave is not None
    # 不强制 show，避免 CI 失败


def test_readme_version_match() -> None:
    """README.md 项目状态行必须包含当前 __version__。"""

    import gvkey
    readme = Path("README.md")
    if not readme.exists():
        return  # 没 README 不算失败（仓库 CI 自带可没有）
    text = readme.read_text(encoding="utf-8")
    # README 里有 "v0.1.0" 这一段（任意一处出现即可）
    assert gvkey.__version__ in text, (
        f"README.md does not contain version {gvkey.__version__}, "
        f"请在 README 项目状态行同步版本号。"
    )


def test_release_notes_contain_current_version() -> None:
    """RELEASE_NOTES.md 必须以当前版本的标题开头。"""

    import gvkey
    p = Path("RELEASE_NOTES.md")
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    # 至少包含 "## vX.Y.Z" 这样的标题
    import re
    header_re = re.compile(rf"^##\s*v?{re.escape(gvkey.__version__)}", re.MULTILINE)
    assert header_re.search(text), (
        f"RELEASE_NOTES.md 缺少当前版本 {gvkey.__version__} 的标题。"
        f"发版前请在最顶端新增 ## v{gvkey.__version__} - ... 章节。"
    )


# ============================================================
# 入口
# ============================================================


def main() -> int:
    print(f"[*] 使用临时 APPDATA: {_TEMP_APPDATA}")
    runner = TestRunner()
    tests = [
        test_version,
        test_logs_init,
        test_user_data_dir_isolation,
        test_config_io,
        test_profile_roundtrip,
        test_seed_if_empty,
        test_export_import_profile,
        test_parse_key,
        test_keyword_matcher_exact,
        test_keyword_matcher_similarity,
        test_keyword_blacklist_blocks,
        test_transcriber_energy,
        test_engine_smoke,
        test_corrupt_backup_on_read,
        test_overlay_window_smoke,
        test_readme_version_match,
        test_release_notes_contain_current_version,
    ]
    for t in tests:
        runner.run(t.__name__, t)
    runner.summary()
    return 0 if runner.passed() else 1


if __name__ == "__main__":
    sys.exit(main())
