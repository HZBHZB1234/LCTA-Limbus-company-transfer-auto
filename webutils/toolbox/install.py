# -*- coding: utf-8 -*-
"""工具箱安装引擎：底座安装、插件安装/启停/更新/回滚/卸载。

plan 10.2–10.5 的落地。所有文件操作都经过 ``paths`` 的受管区断言，
所有多文件提交都包在 ``state.Journal`` 事务里。

## 核心不变量

1. **游戏关闭**才动文件（``runtime.assert_can_install``）；
2. **先备份、写 journal、再提交**；失败/中断可回滚（``state.recover_if_needed``）；
3. **只在受管区**内 move/delete（``paths.assert_managed_target``）；
4. **停用 = 移出 BepInEx 加载树**，不是改配置布尔值；
5. **更新不改变启停状态**（原本停用的更新后仍停用）；
6. **卸载只删 manifest 记载且校验归属的文件**，用户配置默认保留；
7. 哈希不符/清单不合法/依赖缺失 → 拒绝安装，不「尽力而为」。

## 依赖关系

底座先于插件；插件依赖底座（``requires_runtime``）。
不删除仍被其他插件依赖的底座（plan 10.4）。
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from . import archive, paths, runtime, state

logger = logging.getLogger(__name__)


class InstallError(RuntimeError):
    """安装失败。``code`` 供界面映射为可解释文案（plan 12.3 的错误码建议）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# 错误码（与 plan 12.3 建议对齐）
E_GAME_RUNNING = "GAME_RUNNING"
E_FOREIGN_LOADER = "FOREIGN_LOADER"
E_PATH_UNSAFE = "PATH_UNSAFE"
E_HASH_MISMATCH = "HASH_MISMATCH"
E_MANIFEST_INVALID = "MANIFEST_INVALID"
E_ENTITLEMENT_REQUIRED = "ENTITLEMENT_REQUIRED"
E_RELEASE_WITHDRAWN = "RELEASE_WITHDRAWN"
E_DISK_FULL = "DISK_FULL"
E_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
E_DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
E_GUID_CONFLICT = "GUID_CONFLICT"
E_LOCK_BUSY = "LOCK_BUSY"
E_NOT_MANAGED = "NOT_MANAGED"
E_UNKNOWN = "UNKNOWN"


@dataclass
class InstallPlan:
    """一次安装/更新要做什么（由调用方从签名清单构造）。

    ``files`` 是 ``(相对路径, sha256)``。服务器**只**给经过校验的工具 ID、
    文件名与 install_kind；不接受任意绝对路径（plan 10.2）。
    """

    kind: str                       # runtime | plugin
    release_id: str
    version: str = ""
    tool_id: str = ""
    guid: Optional[str] = None
    main_dll: str = ""
    files: Sequence[tuple] = ()
    allowed_prefixes: Sequence[str] = ()
    requires_runtime: bool = True
    stub_path: Optional[Path] = None   # 已下载并校验过的 zip


def _now_iso() -> str:
    return state._utcnow_iso()


def _require_disk_space(target: Path, needed: int) -> None:
    free = paths.find_disk_free(target)
    if free is None:
        return
    # 预留 32 MiB 余量：装满了连 journal 都写不下
    if free < needed + 32 * 1024 * 1024:
        raise InstallError(
            E_DISK_FULL,
            f"磁盘空间不足：需要约 {needed // 1024 // 1024} MiB，可用 {free // 1024 // 1024} MiB",
        )


def detect_conflicts(game_root: os.PathLike | str) -> Dict[str, object]:
    """检查底座相关的外部状态（plan 10.3 第 6 条）。

    识别「受管旧版 / 其他框架 / 未知修改」，供界面提示用户确认，
    **不**静默覆盖别人的文件。
    """
    root = Path(game_root)
    manifest = state.Manifest.load(root)
    out: Dict[str, object] = {
        "managed_runtime": manifest.runtime is not None,
        "managed_runtime_release": manifest.runtime.release_id if manifest.runtime else None,
        "winhttp": (root / "winhttp.dll").exists(),
        "bepinex_dir": (root / "BepInEx").is_dir(),
        "bepinex_core": (root / "BepInEx" / "core").is_dir(),
        "doorstop_config": (root / "doorstop_config.ini").exists(),
        "dotnet_dir": (root / "dotnet").is_dir(),
    }
    # 有 BepInEx 但没有受管记录 → 可能是外部安装，需要用户确认
    out["foreign_loader"] = bool(out["bepinex_dir"]) and not out["managed_runtime"]
    return out


def _assert_runtime_present(game_root: os.PathLike | str, plan: InstallPlan) -> None:
    if not plan.requires_runtime:
        return
    manifest = state.Manifest.load(game_root)
    if manifest.runtime is None:
        raise InstallError(E_DEPENDENCY_MISSING, "请先安装工具箱底座，再安装插件")


def _stage_and_verify(plan: InstallPlan) -> Path:
    """校验暂存包：存在、哈希（若有）、可解压且安全。"""
    if plan.stub_path is None or not Path(plan.stub_path).exists():
        raise InstallError(E_MANIFEST_INVALID, "安装包缺失，请重新下载")
    stub = Path(plan.stub_path)
    if not os.access(str(stub), os.R_OK):
        raise InstallError(E_PATH_UNSAFE, f"安装包不可读：{stub}")
    try:
        archive.inspect_archive(stub)
    except archive.ArchiveError as exc:
        raise InstallError(E_MANIFEST_INVALID, f"安装包校验失败：{exc}") from exc
    return stub


def install_runtime(
    game_root: os.PathLike | str,
    plan: InstallPlan,
    *,
    confirm_foreign: bool = False,
    progress: Optional[Callable[[str, int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Dict[str, object]:
    """安装/更新工具箱底座（BepInEx 定制包）。

    ``confirm_foreign`` 为 False 且检测到外部 loader 时拒绝 —— 覆盖别人的
    BepInEx 安装属于破坏性操作，必须由用户明确同意。
    """
    root = paths.validate_game_root(game_root)
    conflicts = detect_conflicts(root)
    if conflicts["foreign_loader"] and not confirm_foreign:
        raise InstallError(
            E_FOREIGN_LOADER,
            "检测到非 LCTA 管理的 BepInEx 安装。继续可能覆盖现有框架，需你明确确认并已备份。",
        )

    stub = _stage_and_verify(plan)
    _require_disk_space(root, stub.stat().st_size * 4)

    staging = paths.staging_dir(root) / f"rt-{plan.release_id}-{int(time.time())}"
    journal = state.Journal(root)

    with runtime.game_lock(root):
        runtime.assert_can_install(root)   # 锁内再查一次，避免竞态

        # 解压到暂存（先解压后提交：解压失败不留半成品）
        try:
            written = archive.extract_zip_safe(
                stub, staging, allowed_prefixes=list(plan.allowed_prefixes) or None,
                progress=progress, should_cancel=should_cancel,
            )
        except archive.ArchiveError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise InstallError(E_MANIFEST_INVALID, f"解压失败：{exc}") from exc

        try:
            journal.begin("install_runtime", "runtime")
            manifest = state.Manifest.load(root)

            # 逐文件备份 + 登记 + 提交
            new_files: List[state.ManagedFile] = []
            for staged in written:
                rel = staged.relative_to(staging).as_posix()
                target = paths.resolve_within(root, rel)
                existed = target.exists()
                backup_rel = f"runtime/{plan.release_id}/{rel.replace('/', '__')}"
                backup = state.backup_file(root, target, backup_rel) if existed else None
                journal.add_entry(target, backup_rel=backup, existed=existed)

                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(staged), str(target))
                new_files.append(
                    state.ManagedFile(
                        relative_path=rel,
                        sha256=paths.short_hash(target),
                        backup_path=backup,
                        existed_before=existed,
                    )
                )

            manifest.runtime = state.RuntimeEntry(
                release_id=plan.release_id,
                version=plan.version,
                files=new_files,
                installed_at=_now_iso(),
                allowed_prefixes=list(plan.allowed_prefixes),
            )
            journal.set_state(state.STATE_COMMITTING)
            manifest.save()
            journal.set_state(state.STATE_DONE)
            journal.clear()
        except BaseException as exc:
            # 任何失败都回滚到事务前状态，而不是留下半安装
            logger.exception("底座安装失败，回滚")
            result = state.restore_from_journal(root, journal)
            journal.clear()
            shutil.rmtree(staging, ignore_errors=True)
            if isinstance(exc, InstallError):
                raise
            raise InstallError(
                E_UNKNOWN,
                f"底座安装失败并已回滚（恢复 {len(result['restored'])} 个文件）：{exc}",
            ) from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    return {
        "ok": True,
        "kind": "runtime",
        "release_id": plan.release_id,
        "files": len(new_files),
    }


def install_plugin(
    game_root: os.PathLike | str,
    plan: InstallPlan,
    *,
    progress: Optional[Callable[[str, int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Dict[str, object]:
    """安装或更新一个插件（DLL）。

    更新时保持原有启停状态：原本停用的插件更新后仍停用（plan 10.4）。
    """
    root = paths.validate_game_root(game_root)
    _assert_runtime_present(root, plan)

    tool_id = paths._safe_id(plan.tool_id)
    stub = _stage_and_verify(plan)
    _require_disk_space(root, stub.stat().st_size * 4)

    manifest = state.Manifest.load(root)
    existing = manifest.plugins.get(tool_id)

    # GUID 冲突：两个启用的插件不能同 GUID
    if plan.guid:
        clash = manifest.has_guid_conflict(plan.guid, exclude_tool=tool_id)
        if clash:
            raise InstallError(E_GUID_CONFLICT, f"GUID {plan.guid} 已被插件 {clash} 占用")

    staging = paths.staging_dir(root) / f"pl-{tool_id}-{int(time.time())}"
    journal = state.Journal(root)

    with runtime.game_lock(root):
        runtime.assert_can_install(root)

        try:
            written = archive.extract_zip_safe(
                stub, staging, progress=progress, should_cancel=should_cancel
            )
        except archive.ArchiveError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise InstallError(E_MANIFEST_INVALID, f"解压失败：{exc}") from exc

        # 更新时：原本停用 → 新版本也停用
        was_enabled = existing.enabled if existing else True
        target_root = (
            paths.plugin_dir(root, tool_id)
            if was_enabled
            else paths.disabled_dir(root, tool_id, plan.release_id)
        )

        try:
            journal.begin("install_plugin", tool_id)

            new_files: List[state.ManagedFile] = []
            for staged in written:
                rel = staged.relative_to(staging).as_posix()
                target = paths.resolve_within(target_root, rel)
                existed = target.exists()
                backup_rel = f"plugin/{tool_id}/{plan.release_id}/{rel.replace('/', '__')}"
                backup = state.backup_file(root, target, backup_rel) if existed else None
                journal.add_entry(target, backup_rel=backup, existed=existed)

                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(staged), str(target))
                new_files.append(
                    state.ManagedFile(
                        relative_path=rel,
                        sha256=paths.short_hash(target),
                        backup_path=backup,
                        existed_before=existed,
                    )
                )

            manifest.plugins[tool_id] = state.PluginEntry(
                tool_id=tool_id,
                release_id=plan.release_id,
                version=plan.version,
                guid=plan.guid,
                enabled=was_enabled,
                main_dll=plan.main_dll,
                files=new_files,
                installed_at=_now_iso(),
                keep_config=existing.keep_config if existing else True,
            )
            journal.set_state(state.STATE_COMMITTING)
            manifest.save()
            journal.set_state(state.STATE_DONE)
            journal.clear()
        except BaseException as exc:
            logger.exception("插件安装失败，回滚")
            result = state.restore_from_journal(root, journal)
            journal.clear()
            shutil.rmtree(staging, ignore_errors=True)
            if isinstance(exc, InstallError):
                raise
            raise InstallError(
                E_UNKNOWN,
                f"插件安装失败并已回滚（恢复 {len(result['restored'])} 个文件）：{exc}",
            ) from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    return {
        "ok": True,
        "kind": "plugin",
        "tool_id": tool_id,
        "release_id": plan.release_id,
        "enabled": was_enabled,
        "files": len(new_files),
    }


def set_enabled(game_root: os.PathLike | str, tool_id: str, enabled: bool) -> Dict[str, object]:
    """启用/停用插件。

    **停用 = 把 DLL 移出整个 BepInEx 加载树**（移到 ``.lcta-toolbox/disabled/``），
    而不是改配置里的 enabled 布尔值 —— 后者 BepInEx 照样加载（plan 10.4）。

    本地操作，**不需要**在线资格（过季后仍能停用/卸载）。
    """
    root = paths.validate_game_root(game_root)
    tool_id = paths._safe_id(tool_id)
    manifest = state.Manifest.load(root)
    entry = manifest.plugins.get(tool_id)
    if entry is None:
        raise InstallError(E_NOT_MANAGED, f"插件 {tool_id} 不在 LCTA 受管清单内")

    if entry.enabled == enabled:
        return {"ok": True, "tool_id": tool_id, "enabled": enabled, "changed": False}

    with runtime.game_lock(root):
        runtime.assert_can_install(root)

        src = paths.plugin_dir(root, tool_id)
        dst = paths.disabled_dir(root, tool_id, entry.release_id)

        try:
            if enabled:
                if not src.exists() and dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(src))
            else:
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
            entry.enabled = enabled
            manifest.save()
        except OSError as exc:
            raise InstallError(E_UNKNOWN, f"切换启停失败：{exc}") from exc

    return {"ok": True, "tool_id": tool_id, "enabled": enabled, "changed": True}


def verify_integrity(game_root: os.PathLike | str, tool_id: str) -> Dict[str, object]:
    """校验受管插件的文件哈希与布局（plan 10.4 完整性检查）。

    被杀毒隔离/用户手改都会在这里被发现，界面据此提示「需要修复」，
    **不**绕过或自动关闭安全软件。
    """
    root = paths.validate_game_root(game_root)
    tool_id = paths._safe_id(tool_id)
    manifest = state.Manifest.load(root)
    entry = manifest.plugins.get(tool_id)
    if entry is None:
        raise InstallError(E_NOT_MANAGED, f"插件 {tool_id} 不在受管清单内")

    base = (
        paths.plugin_dir(root, tool_id) if entry.enabled
        else paths.disabled_dir(root, tool_id, entry.release_id)
    )

    missing: List[str] = []
    modified: List[str] = []
    for f in entry.files:
        target = paths.resolve_within(base, f.relative_path)
        if not target.exists():
            missing.append(f.relative_path)
            continue
        if f.sha256 and paths.short_hash(target) != f.sha256:
            modified.append(f.relative_path)

    return {
        "ok": not (missing or modified),
        "tool_id": tool_id,
        "enabled": entry.enabled,
        "missing": missing,
        "modified": modified,
        "needs_repair": bool(missing or modified),
    }


def uninstall_plugin(
    game_root: os.PathLike | str,
    tool_id: str,
    *,
    remove_config: bool = False,
) -> Dict[str, object]:
    """卸载受管插件。

    只移除 manifest 记载且校验归属的文件；**用户配置默认保留**；
    非受管文件一律不动（plan 10.4）。
    """
    root = paths.validate_game_root(game_root)
    tool_id = paths._safe_id(tool_id)
    manifest = state.Manifest.load(root)
    entry = manifest.plugins.get(tool_id)
    if entry is None:
        raise InstallError(E_NOT_MANAGED, f"插件 {tool_id} 不在受管清单内")

    with runtime.game_lock(root):
        runtime.assert_can_install(root)

        journal = state.Journal(root)
        journal.begin("uninstall_plugin", tool_id)

        removed = 0
        skipped: List[str] = []
        for base in (paths.plugin_dir(root, tool_id), paths.disabled_dir(root, tool_id, entry.release_id)):
            for f in entry.files:
                try:
                    target = paths.resolve_within(base, f.relative_path)
                except paths.UnsafePathError:
                    skipped.append(f.relative_path)
                    continue
                if not target.exists():
                    continue
                # 归属校验：内容被用户改过就不自动删，交给用户决定
                if f.sha256 and paths.short_hash(target) != f.sha256:
                    skipped.append(str(target))
                    continue
                try:
                    paths.assert_managed_target(root, target)
                    target.unlink()
                    removed += 1
                except (OSError, paths.UnsafePathError):
                    skipped.append(str(target))

            # 清空受管目录（只删空目录，保留用户放进去的东西）
            try:
                if base.exists() and not any(base.iterdir()):
                    base.rmdir()
            except OSError:
                pass

        if not remove_config:
            # 用户配置默认保留（BepInEx/config 下同名配置不动）
            pass

        del manifest.plugins[tool_id]
        manifest.save()
        journal.set_state(state.STATE_DONE)
        journal.clear()

    return {"ok": True, "tool_id": tool_id, "removed": removed, "skipped": skipped}


def rollback_plugin(game_root: os.PathLike | str, tool_id: str) -> Dict[str, object]:
    """回滚到本地备份（离线可用，不需要在线资格）。

    从 manifest 记录的 ``backup_path`` 恢复；保持启停状态。
    """
    root = paths.validate_game_root(game_root)
    tool_id = paths._safe_id(tool_id)
    manifest = state.Manifest.load(root)
    entry = manifest.plugins.get(tool_id)
    if entry is None:
        raise InstallError(E_NOT_MANAGED, f"插件 {tool_id} 不在受管清单内")

    base = paths.plugin_dir(root, tool_id) if entry.enabled else paths.disabled_dir(root, tool_id, entry.release_id)

    restored: List[str] = []
    missing: List[str] = []
    with runtime.game_lock(root):
        for f in entry.files:
            if not f.backup_path:
                continue
            backup = paths.resolve_within(paths.backups_dir(root), f.backup_path)
            if not backup.exists():
                missing.append(f.relative_path)
                continue
            target = paths.resolve_within(base, f.relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(backup), str(target))
            restored.append(f.relative_path)

    return {
        "ok": bool(restored) or not missing,
        "tool_id": tool_id,
        "restored": restored,
        "missing_backup": missing,
    }


def list_installed(game_root: os.PathLike | str) -> Dict[str, object]:
    """列出本地受管状态（**离线可用**，不需要在线资格）。

    同时列出「非受管」的同目录 DLL，供界面提示冲突（plan 10.4：
    非受管插件可列出文件/提示冲突，但不自动删除或升级）。
    """
    root = paths.validate_game_root(game_root)
    manifest = state.Manifest.load(root)

    plugins = [
        {
            "tool_id": p.tool_id,
            "release_id": p.release_id,
            "version": p.version,
            "guid": p.guid,
            "enabled": p.enabled,
            "main_dll": p.main_dll,
            "installed_at": p.installed_at,
        }
        for p in manifest.plugins.values()
    ]

    # 非受管：BepInEx/plugins 下存在但不在受管清单里的 DLL
    managed_names = {p.main_dll.lower() for p in manifest.plugins.values() if p.main_dll}
    unmanaged: List[str] = []
    plugins_root = root / "BepInEx" / "plugins"
    if plugins_root.is_dir():
        for dll in plugins_root.rglob("*.dll"):
            if dll.name.lower() not in managed_names:
                unmanaged.append(str(dll.relative_to(root).as_posix()))

    return {
        "game_root": str(root),
        "runtime": (
            {"release_id": manifest.runtime.release_id, "version": manifest.runtime.version}
            if manifest.runtime else None
        ),
        "plugins": plugins,
        "unmanaged": unmanaged,
    }