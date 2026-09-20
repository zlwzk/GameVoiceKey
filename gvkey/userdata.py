"""用户数据隔离与「更新不丢数据」保障.

两条硬约束（对应两个真实事故场景）：

1. **多用户不共享**
   Windows 上每个登录账户有独立的 ``%APPDATA%``，数据天然隔离。
   但代码有可能被改坏（比如误用 ``%PROGRAMDATA%``、写死路径、
   或把数据放到 exe 同目录），所以这里显式做校验 —— 见
   :func:`ensure_safe_data_dir`。

2. **换新版本不丢数据**
   用户升级的常规做法是「下载新 exe → 覆盖旧的」。
   只要数据在 ``%APPDATA%``，覆盖 exe 不会碰到它。
   但为了防止 schema 升级 / 误操作把配置搞坏，这里额外做：
   - 每次检测到版本变化 → 自动快照到 ``backups/``
   - 快照保留最近 N 份，旧的自动清理
   - 提供列出 / 恢复入口，用户随时可回滚

命令行 / 环境变量：
- ``GVKEY_DATA_DIR``：覆盖数据根目录（便携版 / 测试用）。
  **指向程序目录内的路径会被拒绝**，避免「覆盖 exe 时连带删掉数据」。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

# 快照里这些目录**不进**（体积大 / 是运行时产物 / 会自嵌套）
SNAPSHOT_EXCLUDE_DIRS = frozenset({"logs", "backups", "models", "__pycache__"})
# 这些后缀不进快照
SNAPSHOT_EXCLUDE_SUFFIXES = (".tmp", ".pyc", ".pyo")
# 快照里这些前缀/模式不进快照
SNAPSHOT_EXCLUDE_GLOBS = ("*.corrupt-*", "*.tmp", "*~")
# 默认保留多少份快照
DEFAULT_KEEP_SNAPSHOTS = 8
# 记录「上次运行版本」的文件名
LAST_VERSION_FILE = ".last-version"
# 记录「上次运行时间」的文件名
LAST_RUN_FILE = ".last-run"


# ============================================================
# 路径
# ============================================================


def app_root_dir() -> Path:
    """程序自身所在目录（**不是**数据目录）。

    - PyInstaller 打包后：exe 所在目录（用户覆盖 exe 就是覆盖这里）
    - 源码运行：仓库根目录
    """

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resolve_data_dir() -> Path:
    """按优先级决定数据根目录（不创建、不校验）。"""

    env = (os.environ.get("GVKEY_DATA_DIR") or "").strip()
    if env:
        return Path(env).expanduser()
    base = os.environ.get("APPDATA")
    if not base:
        # 非 Windows / 剥离环境：退回 home，仍是每用户独立
        base = str(Path.home())
        return Path(base) / ".GameVoiceKey"
    return Path(base) / "GameVoiceKey"


def _is_inside(child: Path, parent: Path) -> bool:
    """child 是否位于 parent 之内（含相等）。大小写不敏感（Windows）。"""

    try:
        c = child.resolve()
        p = parent.resolve()
    except OSError:
        c, p = child.absolute(), parent.absolute()
    cs = str(c).rstrip("\\/").lower()
    ps = str(p).rstrip("\\/").lower()
    return cs == ps or cs.startswith(ps + os.sep) or cs.startswith(ps + "/")


@dataclass(frozen=True)
class DataDirStatus:
    """数据目录体检结果。"""

    path: Path
    changed: bool
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.warnings


def ensure_safe_data_dir(*, create: bool = True) -> DataDirStatus:
    """校验并（必要时）修正数据目录，保证「更新不丢数据」。

    规则：
    - 数据目录**不能**落在程序目录内 → 否则覆盖 exe 会连带删掉数据，
      此时回退到默认的 ``%APPDATA%/GameVoiceKey`` 并记一条 warning。
    - 数据目录**不能**是盘符根（``C:\\``）→ 明显是配置事故，回退默认。

    返回 :class:`DataDirStatus`；``changed=True`` 表示实际改写了
    ``GVKEY_DATA_DIR`` 环境变量，调用方可以在 UI 上提示用户。
    """

    warnings: list[str] = []
    chosen = _resolve_data_dir()
    root = app_root_dir()

    if _is_inside(chosen, root):
        warnings.append(
            f"数据目录 {chosen} 位于程序目录内，升级覆盖 exe 时会丢失数据，"
            f"已自动改用 %APPDATA%\\GameVoiceKey"
        )
        chosen = Path(os.environ.get("APPDATA") or Path.home()) / "GameVoiceKey"
    elif chosen.parent == chosen:
        warnings.append(f"数据目录 {chosen} 是盘符根目录，已自动改用 %APPDATA%\\GameVoiceKey")
        chosen = Path(os.environ.get("APPDATA") or Path.home()) / "GameVoiceKey"

    # 二次确认：回退后的路径依然不能落在程序内
    if _is_inside(chosen, root):
        warnings.append("回退后的数据目录仍与程序目录重叠，请手动设置 GVKEY_DATA_DIR")
        chosen = root / ".." / "GameVoiceKey"

    changed = str(chosen) != str(_resolve_data_dir())
    if changed:
        os.environ["GVKEY_DATA_DIR"] = str(chosen)

    if create:
        try:
            chosen.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    return DataDirStatus(path=chosen, changed=changed, warnings=tuple(warnings))


def is_data_dir_isolated() -> bool:
    """数据目录是否与程序目录分离（分离=升级安全）。"""

    return not _is_inside(_resolve_data_dir(), app_root_dir())


def data_dir_display() -> str:
    """脱敏显示数据目录：把 ``%APPDATA%`` 前缀换成占位符。

    隐私约定：日志 / UI / issue 里不出现 Windows 用户名和绝对路径。
    """

    p = _resolve_data_dir()
    appdata = os.environ.get("APPDATA")
    if appdata:
        try:
            rel = p.relative_to(Path(appdata))
            return "%APPDATA%\\" + str(rel).replace("/", "\\")
        except ValueError:
            pass
    home = Path.home()
    try:
        rel = p.relative_to(home)
        return "%USERPROFILE%\\" + str(rel).replace("/", "\\")
    except ValueError:
        pass
    return str(p)


# ============================================================
# 快照 / 备份
# ============================================================


def backups_dir() -> Path:
    p = _resolve_data_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _should_skip(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & SNAPSHOT_EXCLUDE_DIRS:
        return True
    if rel.suffix.lower() in SNAPSHOT_EXCLUDE_SUFFIXES:
        return True
    # 点文件是运行时标记（.last-version / .schema-version），不是用户数据
    if any(p.startswith(".") for p in rel.parts):
        return True
    name = rel.name.lower()
    if name.startswith(".corrupt-") or ".corrupt-" in name:
        return True
    if name.endswith("~"):
        return True
    return False


def _has_user_data(root: Path) -> bool:
    """数据目录里是否真的有值得备份的用户内容。"""

    if (root / "settings.json").exists():
        return True
    pd = root / "profiles"
    if pd.is_dir() and any(pd.glob("*.json")):
        return True
    return False


def _copy_tree_filtered(src: Path, dst: Path) -> int:
    """递归复制，跳过排除项。返回复制的文件数。"""

    count = 0
    for item in src.iterdir():
        rel = item.relative_to(src)
        if _should_skip(rel):
            continue
        try:
            if item.is_dir():
                count += _copy_tree_filtered(item, dst / item.name)
            else:
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst / item.name)
                count += 1
        except OSError:
            continue
    return count


@dataclass(frozen=True)
class BackupInfo:
    name: str
    path: Path
    created_at: datetime
    file_count: int
    size_bytes: int
    reason: str

    @property
    def label(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M:%S}  ·  {self.reason}"


def snapshot(reason: str = "manual", *, keep: int = DEFAULT_KEEP_SNAPSHOTS) -> Path | None:
    """把用户数据快照到 ``backups/<时间戳>-<原因>/``。

    - 排除 logs / models / backups 本身 / 临时文件
    - 复制完成后自动清理超出 ``keep`` 的旧快照
    - 数据目录为空（一片空白的新装）时不产生快照，返回 ``None``
    """

    src = _resolve_data_dir()
    if not src.exists() or not _has_user_data(src):
        return None

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in reason)[:48]
    base = f"{ts}-{safe_reason or 'snapshot'}"

    # 同一秒内多次备份时递增后缀，保证每次都独立成目录
    target = backups_dir() / base
    n = 1
    while target.exists():
        n += 1
        target = backups_dir() / f"{base}-{n}"

    target.mkdir(parents=True, exist_ok=True)
    _copy_tree_filtered(src, target)

    # 写一份自描述信息，便于用户手工翻看 / 未来恢复校验
    try:
        (target / "_backup-info.json").write_text(
            json.dumps(
                {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "reason": reason,
                    "app_version": _app_version(),
                    "data_dir": data_dir_display(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass

    prune_backups(keep=keep)
    return target


def _app_version() -> str:
    try:
        from . import __version__

        return __version__
    except Exception:  # noqa: BLE001
        return "unknown"


def _dir_size(p: Path) -> int:
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            continue
    return total


def _count_files(p: Path) -> int:
    n = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                n += 1
        except OSError:
            continue
    return n


def list_backups() -> list[BackupInfo]:
    """列出全部快照，新的在前。"""

    out: list[BackupInfo] = []
    root = backups_dir()
    for d in root.iterdir():
        if not d.is_dir():
            continue
        created = datetime.fromtimestamp(d.stat().st_mtime)
        reason = "snapshot"
        info = d / "_backup-info.json"
        if info.exists():
            try:
                meta = json.loads(info.read_text(encoding="utf-8"))
                reason = str(meta.get("reason") or reason)
                created = datetime.fromisoformat(str(meta.get("created_at")))
            except Exception:  # noqa: BLE001
                pass
        elif "-" in d.name:
            reason = d.name.split("-", 1)[1].replace("-", " ")
        out.append(
            BackupInfo(
                name=d.name,
                path=d,
                created_at=created,
                file_count=_count_files(d),
                size_bytes=_dir_size(d),
                reason=reason,
            )
        )
    # 名称里带时间戳后缀序号，同秒创建时用它兜底，保证顺序稳定
    out.sort(key=lambda b: (b.created_at, b.name), reverse=True)
    return out


def prune_backups(*, keep: int = DEFAULT_KEEP_SNAPSHOTS) -> list[str]:
    """只保留最近 ``keep`` 份快照，返回被删掉的名字。"""

    if keep < 1:
        keep = 1
    removed: list[str] = []
    for b in list_backups()[keep:]:
        try:
            shutil.rmtree(b.path)
            removed.append(b.name)
        except OSError:
            continue
    return removed


def restore_backup(name: str) -> tuple[bool, str]:
    """从快照恢复用户数据。

    恢复前会先给**当前**数据打一份 ``pre-restore`` 快照（防呆），
    再用快照内容覆盖 ``settings.json`` + ``profiles/``。

    返回 ``(ok, message)``。
    """

    data = _resolve_data_dir()
    src = backups_dir() / name
    if not src.is_dir():
        return False, f"找不到快照：{name}"

    snapshot("pre-restore")

    restored = 0
    try:
        for item in src.iterdir():
            if item.name == "_backup-info.json":
                continue
            dst = data / item.name
            if item.is_dir():
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(item, dst)
                restored += 1
            else:
                data.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)
                restored += 1
    except OSError as exc:
        return False, f"恢复失败：{exc}"

    # 清掉可能遗留的损坏文件备份，避免下次又被误读
    for bad in data.glob("*.corrupt-*"):
        try:
            bad.unlink()
        except OSError:
            pass

    return True, f"已从快照恢复 {restored} 项（当前数据已另存为 pre-restore 快照）"


def delete_backup(name: str) -> bool:
    p = backups_dir() / name
    if not p.is_dir():
        return False
    try:
        shutil.rmtree(p)
        return True
    except OSError:
        return False


# ============================================================
# 版本变化检测：升级自动快照
# ============================================================


def last_run_version() -> str:
    p = _resolve_data_dir() / LAST_VERSION_FILE
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def write_last_run_version(version: str | None = None) -> None:
    v = version or _app_version()
    d = _resolve_data_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / LAST_VERSION_FILE).write_text(v, encoding="utf-8")
        (d / LAST_RUN_FILE).write_text(
            datetime.now().isoformat(timespec="seconds"), encoding="utf-8"
        )
    except OSError:
        pass


def maybe_snapshot_on_upgrade(*, keep: int = DEFAULT_KEEP_SNAPSHOTS) -> Path | None:
    """检测到版本变化时自动快照一次。

    首次运行（没有 ``.last-version``）不产生快照，只记录版本；
    之后每次版本号变了 → ``backups/<ts>-upgrade-<旧>-to-<新>/``。
    """

    current = _app_version()
    previous = last_run_version()

    if previous and previous != current:
        target = snapshot(f"upgrade-{previous}-to-{current}", keep=keep)
        write_last_run_version(current)
        return target

    if not previous:
        write_last_run_version(current)
    return None


# ============================================================
# schema 迁移（预留 + 幂等）
# ============================================================


def migrate_if_needed() -> list[str]:
    """把用户数据升级到当前 ``SCHEMA_VERSION``。

    当前 schema = 1，没有历史包袱；框架先立起来，
    未来加字段时在这里按版本号逐级补。

    返回执行的迁移说明列表（空 = 无需迁移）。
    """

    from . import SCHEMA_VERSION
    from .logs import get_logger

    log = get_logger()
    data = _resolve_data_dir()
    applied: list[str] = []

    marker = data / ".schema-version"
    old = 0
    try:
        old = int(marker.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        old = 0

    if old == 0:
        # 老版本没写 marker，按 0 处理：只记当前版本，不做破坏性改动
        applied.append(f"初始化 schema marker -> {SCHEMA_VERSION}")
    elif old > SCHEMA_VERSION:
        log.warning("数据 schema 版本 %s 高于程序 %s（可能降级运行）", old, SCHEMA_VERSION)
        return applied

    if old != SCHEMA_VERSION:
        # 占位：未来的迁移步骤写这里，例如
        # if old < 2: _migrate_1_to_2()
        pass

    try:
        data.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(SCHEMA_VERSION), encoding="utf-8")
    except OSError:
        pass

    return applied


def data_health() -> dict[str, object]:
    """给 UI 用的一次性体检摘要。"""

    return {
        "data_dir": data_dir_display(),
        "isolated": is_data_dir_isolated(),
        "app_root": app_root_dir().name,
        "last_version": last_run_version() or "-",
        "backup_count": len(list_backups()),
        "frozen": bool(getattr(sys, "frozen", False)),
    }


def bootstrap() -> list[str]:
    """启动时调用：校验隔离 → 迁移 schema → 升级快照。

    返回需要向用户展示的提示（一般只有「数据目录被修正」这类告警）。
    """

    notices: list[str] = []
    status = ensure_safe_data_dir()
    notices.extend(status.warnings)

    migrate_if_needed()
    upgraded = maybe_snapshot_on_upgrade()
    if upgraded is not None:
        notices.append(f"检测到版本更新，已自动备份旧数据到 backups/{upgraded.name}")

    return notices


__all__ = [
    "BackupInfo",
    "DataDirStatus",
    "DEFAULT_KEEP_SNAPSHOTS",
    "app_root_dir",
    "backups_dir",
    "bootstrap",
    "data_dir_display",
    "data_health",
    "delete_backup",
    "ensure_safe_data_dir",
    "is_data_dir_isolated",
    "last_run_version",
    "list_backups",
    "maybe_snapshot_on_upgrade",
    "migrate_if_needed",
    "prune_backups",
    "restore_backup",
    "snapshot",
    "write_last_run_version",
]
