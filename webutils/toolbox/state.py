# -*- coding: utf-8 -*-
"""本地受管清单（manifest）与事务 journal：崩溃可恢复的安装状态。

plan 10.5 的状态机：

    空闲 → 暂存下载/校验 → 等待游戏关闭/确认冲突
    → 备份 → 提交文件 → 写 manifest → 完成
                           └→ 失败/中断 → 回滚/待修复

## 为什么必须有 journal

多文件写入**不是**天然原子事务。若在「已覆盖 3 个文件、还剩 2 个」时进程被
杀掉，磁盘上就是半新半旧的混合状态 —— 而 manifest 还没写，界面会显示
「未安装」，用户再装一次又叠加一层。

所以提交前先把「我要改哪些文件、原内容备份在哪」写进 journal 并落盘，
启动时若发现未完成的 journal 就回滚。

## 写入原子性

manifest/journal 一律「临时文件 + ``os.replace``」原子替换：
直接覆写会在断电/崩溃时留下截断的 JSON，之后连读都读不了。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import paths

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# 事务状态
STATE_IDLE = "idle"
STATE_STAGING = "staging"
STATE_AWAITING_CONFIRM = "awaiting_confirm"
STATE_BACKING_UP = "backing_up"
STATE_COMMITTING = "committing"
STATE_DONE = "done"
STATE_ROLLED_BACK = "rolled_back"
STATE_REPAIR_REQUIRED = "repair_required"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """原子写 JSON：同目录临时文件 → ``os.replace``。

    必须同目录（``os.replace`` 不跨卷），也必须 ``fsync`` 后再替换 ——
    否则断电时可能替换了一个内容还在页缓存里的文件。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_json(path: Path, default: Any = None) -> Any:
    """读 JSON；损坏/缺失返回 ``default``（不抛，调用方按「无状态」处理）。"""
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError):
        logger.warning("读取 %s 失败（按无状态处理）", path, exc_info=True)
        return default


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


@dataclass
class ManagedFile:
    """一个受管文件：相对路径 + 内容哈希 + 备份位置。"""

    relative_path: str
    sha256: str = ""
    backup_path: Optional[str] = None   # 相对 backups/ 的路径
    original_sha256: Optional[str] = None
    existed_before: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "backup_path": self.backup_path,
            "original_sha256": self.original_sha256,
            "existed_before": self.existed_before,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ManagedFile":
        return cls(
            relative_path=str(d.get("relative_path", "")),
            sha256=str(d.get("sha256", "")),
            backup_path=d.get("backup_path"),
            original_sha256=d.get("original_sha256"),
            existed_before=bool(d.get("existed_before", True)),
        )


@dataclass
class PluginEntry:
    """一个受管插件。``enabled`` 由**文件位置**决定，不只是配置布尔值。"""

    tool_id: str
    release_id: str
    version: str = ""
    guid: Optional[str] = None
    enabled: bool = True
    main_dll: str = ""
    files: List[ManagedFile] = field(default_factory=list)
    installed_at: str = ""
    keep_config: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "release_id": self.release_id,
            "version": self.version,
            "guid": self.guid,
            "enabled": self.enabled,
            "main_dll": self.main_dll,
            "files": [f.to_dict() for f in self.files],
            "installed_at": self.installed_at,
            "keep_config": self.keep_config,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PluginEntry":
        return cls(
            tool_id=str(d.get("tool_id", "")),
            release_id=str(d.get("release_id", "")),
            version=str(d.get("version", "")),
            guid=d.get("guid"),
            enabled=bool(d.get("enabled", True)),
            main_dll=str(d.get("main_dll", "")),
            files=[ManagedFile.from_dict(x) for x in (d.get("files") or [])],
            installed_at=str(d.get("installed_at", "")),
            keep_config=bool(d.get("keep_config", True)),
        )


@dataclass
class RuntimeEntry:
    """受管底座（BepInEx 定制包）。"""

    release_id: str
    version: str = ""
    files: List[ManagedFile] = field(default_factory=list)
    installed_at: str = ""
    allowed_prefixes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "release_id": self.release_id,
            "version": self.version,
            "files": [f.to_dict() for f in self.files],
            "installed_at": self.installed_at,
            "allowed_prefixes": list(self.allowed_prefixes),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RuntimeEntry":
        return cls(
            release_id=str(d.get("release_id", "")),
            version=str(d.get("version", "")),
            files=[ManagedFile.from_dict(x) for x in (d.get("files") or [])],
            installed_at=str(d.get("installed_at", "")),
            allowed_prefixes=list(d.get("allowed_prefixes") or []),
        )


class Manifest:
    """某个游戏目录的受管清单。

    ⚠️ 刻意**不含**任何凭据（邮箱验证码、会话 token、签名私钥、票据）——
    manifest 是本地明文文件，写进去等于泄露（plan 10.5）。
    """

    def __init__(self, game_root: os.PathLike | str, data: Optional[Dict[str, Any]] = None):
        self.game_root = Path(game_root)
        self.schema_version = SCHEMA_VERSION
        self.normalized_root = str(self.game_root.resolve())
        self.runtime: Optional[RuntimeEntry] = None
        self.plugins: Dict[str, PluginEntry] = {}
        self.updated_at = _utcnow_iso()

        if data:
            self._load(data)

    def _load(self, data: Dict[str, Any]) -> None:
        self.schema_version = int(data.get("schema_version", SCHEMA_VERSION))
        # 游戏目录被移动过：旧 manifest 不能套用到新路径（plan 10.5）
        stored_root = str(data.get("normalized_root", ""))
        self.normalized_root = str(self.game_root.resolve())
        if stored_root and os.path.normcase(stored_root) != os.path.normcase(self.normalized_root):
            logger.warning("manifest 的 game_root 与当前目录不一致（%s → %s），按未接管处理",
                           stored_root, self.normalized_root)
            self.runtime = None
            self.plugins = {}
            return

        rt = data.get("runtime")
        self.runtime = RuntimeEntry.from_dict(rt) if rt else None
        self.plugins = {
            str(k): PluginEntry.from_dict(v) for k, v in (data.get("plugins") or {}).items()
        }
        self.updated_at = str(data.get("updated_at", _utcnow_iso()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "normalized_root": self.normalized_root,
            "updated_at": _utcnow_iso(),
            "runtime": self.runtime.to_dict() if self.runtime else None,
            "plugins": {k: v.to_dict() for k, v in self.plugins.items()},
        }

    # -- 持久化 --------------------------------------------------------------

    @classmethod
    def load(cls, game_root: os.PathLike | str) -> "Manifest":
        data = read_json(paths.manifest_path(game_root), default=None)
        return cls(game_root, data if isinstance(data, dict) else None)

    def save(self) -> None:
        self.updated_at = _utcnow_iso()
        atomic_write_json(paths.manifest_path(self.game_root), self.to_dict())

    # -- 查询 ----------------------------------------------------------------

    def is_managed(self, tool_id: str) -> bool:
        return tool_id in self.plugins

    def enabled_plugins(self) -> List[PluginEntry]:
        return [p for p in self.plugins.values() if p.enabled]

    def has_guid_conflict(self, guid: str, *, exclude_tool: Optional[str] = None) -> Optional[str]:
        """检测 GUID 冲突：两个启用的插件不能有同一 GUID（plan 10.4）。"""
        if not guid:
            return None
        for tid, p in self.plugins.items():
            if tid == exclude_tool or not p.enabled:
                continue
            if p.guid and p.guid == guid:
                return tid
        return None


# ---------------------------------------------------------------------------
# Journal（事务日志）
# ---------------------------------------------------------------------------


class Journal:
    """一次安装/更新/卸载事务的可重放日志。

    记录「每个被改动的文件：备份在哪、原本是否存在」。中断后据此回滚。
    """

    def __init__(self, game_root: os.PathLike | str, data: Optional[Dict[str, Any]] = None):
        self.game_root = Path(game_root)
        self.operation = ""
        self.tool_id = ""
        self.state = STATE_IDLE
        self.started_at = _utcnow_iso()
        self.entries: List[Dict[str, Any]] = []
        if data:
            self._load(data)

    def _load(self, data: Dict[str, Any]) -> None:
        self.operation = str(data.get("operation", ""))
        self.tool_id = str(data.get("tool_id", ""))
        self.state = str(data.get("state", STATE_IDLE))
        self.started_at = str(data.get("started_at", _utcnow_iso()))
        self.entries = list(data.get("entries") or [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "operation": self.operation,
            "tool_id": self.tool_id,
            "state": self.state,
            "started_at": self.started_at,
            "entries": self.entries,
        }

    @classmethod
    def load(cls, game_root: os.PathLike | str) -> Optional["Journal"]:
        data = read_json(paths.journal_path(game_root), default=None)
        if not isinstance(data, dict):
            return None
        return cls(game_root, data)

    def save(self) -> None:
        atomic_write_json(paths.journal_path(self.game_root), self.to_dict())

    def clear(self) -> None:
        try:
            os.unlink(str(paths.journal_path(self.game_root)))
        except FileNotFoundError:
            pass

    def begin(self, operation: str, tool_id: str = "") -> None:
        self.operation = operation
        self.tool_id = tool_id
        self.state = STATE_BACKING_UP
        self.started_at = _utcnow_iso()
        self.entries = []
        self.save()

    def add_entry(self, target: Path, *, backup_rel: Optional[str], existed: bool) -> None:
        """登记一个将要被改动的文件（**写之前**登记）。"""
        self.entries.append(
            {
                "target": str(target),
                "backup_rel": backup_rel,
                "existed_before": bool(existed),
            }
        )
        self.save()

    def set_state(self, state: str) -> None:
        self.state = state
        self.save()

    def is_incomplete(self) -> bool:
        """是否为「未完成」事务（需要恢复）。"""
        return self.state in (STATE_BACKING_UP, STATE_COMMITTING, STATE_STAGING)


def backup_file(game_root: os.PathLike | str, target: Path, backup_rel: str) -> Optional[str]:
    """把文件备份到 ``backups/<backup_rel>``，返回备份的相对路径。

    文件不存在时返回 None（表示「原本没有这个文件」，回滚时应删除它）。
    """
    if not target.exists():
        return None
    dest = paths.resolve_within(paths.backups_dir(game_root), backup_rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(target), str(dest))
    return backup_rel


def restore_from_journal(game_root: os.PathLike | str, journal: Journal) -> Dict[str, Any]:
    """按 journal 回滚到事务开始前的状态。

    逆序恢复：后写入的先回滚，避免同一路径被多次改动时顺序错乱。
    返回 ``{restored, deleted, missing_backup}`` 供界面提示。
    """
    restored: List[str] = []
    deleted: List[str] = []
    missing: List[str] = []

    for entry in reversed(journal.entries):
        target = Path(str(entry.get("target", "")))
        backup_rel = entry.get("backup_rel")
        existed = bool(entry.get("existed_before", False))

        try:
            if not existed:
                # 原本没有 → 删除新写入的
                if target.exists():
                    paths.assert_managed_target(game_root, target)
                    target.unlink()
                    deleted.append(str(target))
                continue
            if not backup_rel:
                missing.append(str(target))
                continue
            backup = paths.resolve_within(paths.backups_dir(game_root), str(backup_rel))
            if not backup.exists():
                missing.append(str(target))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(backup), str(target))
            restored.append(str(target))
        except (OSError, paths.UnsafePathError):
            logger.exception("回滚 %s 失败", target)
            missing.append(str(target))

    return {"restored": restored, "deleted": deleted, "missing_backup": missing}


def recover_if_needed(game_root: os.PathLike | str) -> Optional[Dict[str, Any]]:
    """启动时调用：若存在未完成事务则回滚。

    返回恢复结果（无未完成事务时返回 None）。这是「模拟崩溃可恢复」
    （plan 16.4）的实际实现点。
    """
    journal = Journal.load(game_root)
    if journal is None or not journal.is_incomplete():
        return None
    logger.warning("检测到未完成的事务（%s/%s），开始回滚", journal.operation, journal.state)
    result = restore_from_journal(game_root, journal)
    journal.state = STATE_ROLLED_BACK
    journal.save()
    journal.clear()
    return result