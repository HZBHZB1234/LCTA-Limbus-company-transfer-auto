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
7. 哈希不符/清单不合法/依赖缺失 → 拒绝安装，不「尽力而为」；
8. **解压型文件包（``game_relative_zip``）先检查后解压**：成员数/大小/压缩比/
   路径逃逸全在写字节之前判定，解压到暂存后再走与逐文件包**完全相同**的
   提交路径（``_apply_package``）—— 交付形态不同，落盘语义一字不差。

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
E_CANCELLED = "CANCELLED"
E_UNKNOWN = "UNKNOWN"


@dataclass
class InstallPlan:
    """一次安装/更新要做什么（由调用方从签名清单构造）。

    ``files`` 是 ``(相对路径, sha256)``。服务器**只**给经过校验的工具 ID、
    文件名与 install_kind；不接受任意绝对路径（plan 10.2）。
    """

    kind: str                       # runtime | plugin | package | package_zip
    release_id: str
    version: str = ""
    # 服务端下发的可比较版本序（v3 清单）；空 = 老站点/旧清单，按未知处理
    version_sort: str = ""
    # 该版本声明的工具间依赖（原样保存，供卸载/停用前反查）
    dependencies: Sequence[dict] = ()
    tool_id: str = ""
    guid: Optional[str] = None
    main_dll: str = ""
    files: Sequence[tuple] = ()
    allowed_prefixes: Sequence[str] = ()
    requires_runtime: bool = True
    stub_path: Optional[Path] = None   # 已下载并校验过的 zip（runtime/plugin/package_zip）
    # game_relative_files / game_relative_zip：签名清单声明的游戏内相对目录
    target_dir: str = ""
    # game_relative_files：[(清单相对路径, 已下载并校验的本地文件), ...]
    file_sources: Sequence[tuple[str, Path]] = ()
    # package_zip：包内成员允许的前缀（空 = 不限，仍受 package_root 约束）。
    # 语义与 runtime 的 allowed_prefixes 相同：清单若声明了包内布局就强制收窄。
    # ⚠️ 目前站点不下发该字段（清单无新增字段），保留给未来的收窄场景。
    archive_prefixes: Sequence[str] = ()


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

    ## LimiNex 遗留（2026-11-02）

    旧版把 BepInEx 挂载做在 cheat core 里（``BepInEx/lcta-liminex.json``
    标记 + 游戏根 ``il2cpp_mappings.txt`` / ``BepInEx/mapping-source.dat``）。
    该实现已被 Zylarnex 底座取代并移除，但存量用户的磁盘上还留着这些痕迹。
    这里只**识别并上报**（``liminex_legacy``），不删除任何东西 —— 接管由用户
    在订阅工具页显式确认（覆盖安装会 journal 备份原文件，不会丢）。
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
    # LimiNex 遗留痕迹：标记文件或它独有的两个 mapping 产物
    liminex_marker = (root / "BepInEx" / "lcta-liminex.json").exists()
    liminex_artifacts = (root / "il2cpp_mappings.txt").exists() or (
        root / "BepInEx" / "mapping-source.dat"
    ).exists()
    out["liminex_legacy"] = bool(liminex_marker or (liminex_artifacts and out["bepinex_dir"]))
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
                version_sort=plan.version_sort,
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

            # 旧版本有、新版本没有的文件：**只删哈希仍匹配的受管文件**（2026-11-02）
            #
            # 不清理会怎样：旧版 DLL 留在 BepInEx/plugins/LCTA/<tool> 里，BepInEx
            # 照样扫描加载 —— 轻则双版本共存（改的是旧 DLL），重则类型冲突直接崩。
            # 文件包安装早就有这段逻辑，插件一直没有。
            if existing:
                stale = _remove_stale_plugin_files(
                    root, journal, existing=existing, keep_rels=set(),
                    new_files=new_files,
                )
                if stale:
                    logger.info("插件 %s 更新后清理旧文件 %d 个", tool_id, len(stale))

            manifest.plugins[tool_id] = state.PluginEntry(
                tool_id=tool_id,
                release_id=plan.release_id,
                version=plan.version,
                version_sort=plan.version_sort,
                dependencies=list(plan.dependencies or []),
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


def _remove_stale_plugin_files(
    root: Path,
    journal: "state.Journal",
    *,
    existing: "state.PluginEntry",
    keep_rels: set,
    new_files: List["state.ManagedFile"],
) -> List[str]:
    """删除旧版本残留的插件文件（哈希仍匹配才删）。

    ``keep_rels`` 显式保留的相对路径集合（当前实现传空集：新清单里的文件
    已经在写入阶段覆盖过，旧条目若同名会被 ``new_files`` 覆盖，不需要保留）。
    用户改过的文件（哈希不符）保留并告警 —— 与文件包卸载同一口径。
    """
    keep = {str(r).casefold() for r in keep_rels}
    keep |= {f.relative_path.casefold() for f in new_files}
    removed: List[str] = []
    bases = (
        paths.plugin_dir(root, existing.tool_id),
        paths.disabled_dir(root, existing.tool_id, existing.release_id),
    )
    for old in existing.files:
        rel = str(old.relative_path or "")
        if not rel or rel.casefold() in keep:
            continue
        for base in bases:
            try:
                stale = paths.resolve_within(base, rel)
            except paths.UnsafePathError:
                continue
            if not stale.exists():
                continue
            if old.sha256 and paths.short_hash(stale) != old.sha256:
                logger.warning("插件 %s 的旧文件被用户修改，保留不删：%s", existing.tool_id, stale)
                continue
            try:
                paths.assert_managed_target(root, stale)
            except paths.UnsafePathError:
                continue
            backup_rel = (
                f"plugin/{existing.tool_id}/{existing.release_id}/removed__"
                f"{rel.replace('/', '__')}"
            )
            backup = state.backup_file(root, stale, backup_rel)
            journal.add_entry(stale, backup_rel=backup, existed=True)
            try:
                stale.unlink()
                removed.append(str(stale))
            except OSError:
                logger.warning("删除旧插件文件失败：%s", stale, exc_info=True)
    return removed


def install_package(
    game_root: os.PathLike | str,
    plan: InstallPlan,
    *,
    progress: Optional[Callable[[str, int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Dict[str, object]:
    """安装/更新一个 ``game_relative_files`` 文件包（清单逐文件交付）。

    ``plan.target_dir`` 来自**已验签的安装清单**；``plan.file_sources`` 是
    ``[(清单相对路径, 已下载并校验的本地文件), ...]``。所有写入都经过
    ``paths.package_dir`` / ``resolve_within`` 校验，并在 journal 中登记，
    失败或崩溃可回滚。

    与插件不同：包没有 BepInEx 加载树概念，因此不提供启用/停用；更新时
    会清理旧版本中不再存在的受管文件（只删除哈希仍匹配的文件）。

    ## 与 ``install_package_zip`` 的关系

    两者只差「文件从哪来」：这里每个文件由清单逐条声明、逐个下载；
    ``install_package_zip`` 只下一个 .zip 然后自己解压。**落盘语义完全共享**
    （同一个 ``_apply_package``）：target_dir 校验、重叠检测、备份、journal、
    旧文件清理、manifest 记录。
    """
    if not plan.file_sources:
        raise InstallError(E_MANIFEST_INVALID, "安装清单没有可写入的文件")
    return _apply_package(
        game_root, plan,
        sources=[(rel, Path(src)) for rel, src in plan.file_sources],
        progress=progress,
        should_cancel=should_cancel,
        label="文件包",
        kind="package",
    )


def install_package_zip(
    game_root: os.PathLike | str,
    plan: InstallPlan,
    *,
    progress: Optional[Callable[[str, int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Dict[str, object]:
    """安装/更新一个 ``game_relative_zip`` 文件包（**客户端解压**）。

    与 ``install_package`` 的差别只有交付形态：清单只声明**一个 .zip**，
    客户端下载并校验 sha256 后，由 ``archive.extract_zip_safe`` 解压到暂存
    目录，再走与逐文件包完全相同的提交路径。

    ## 安全边界（与底座安装同一套，不因「只是文件包」而放松）

    1. ``archive.inspect_archive`` 先检查后解压：成员数/单成员/总大小/压缩比/
       大小写冲突/CRC 全部在写任何字节之前判定（zip bomb 在这里被拒）；
    2. ``extract_zip_safe`` 逐成员净化名字并校验落点在**暂存目录**内
       （Zip Slip / UNC / ADS / 设备名 / 尾点空格一律中止）；
    3. ``plan.archive_prefixes`` 非空时强制包内布局白名单；
    4. 暂存目录在 ``.lcta-toolbox`` 内，解压失败只清理暂存，不留半成品；
    5. 真正落盘时**再**经过 ``paths.package_dir`` / ``resolve_within`` /
       ``journal`` —— 暂存通过不代表目标通过，两道门都在。

    ``target_dir`` 仍然只来自签名清单，敏感目录（``BepInEx/core`` 等）由
    ``paths.package_dir`` 独立拒绝。
    """
    root = paths.validate_game_root(game_root)
    _assert_runtime_present(root, plan)

    if not plan.target_dir:
        raise InstallError(E_MANIFEST_INVALID, "安装清单缺少 target_dir")
    if plan.stub_path is None or not Path(plan.stub_path).exists():
        raise InstallError(E_MANIFEST_INVALID, "安装包缺失，请重新下载")

    stub = _stage_and_verify(plan)
    # 解压后体积可达压缩包的数倍（zip 允许 200:1），按 4 倍预留
    _require_disk_space(root, stub.stat().st_size * 4)

    tool_id = paths._safe_id(plan.tool_id)
    staging = paths.staging_dir(root) / f"pz-{tool_id}-{plan.release_id}-{int(time.time())}"
    try:
        try:
            written = archive.extract_zip_safe(
                stub, staging,
                allowed_prefixes=list(plan.archive_prefixes) or None,
                progress=progress, should_cancel=should_cancel,
            )
        except archive.ArchiveError as exc:
            raise InstallError(E_MANIFEST_INVALID, f"解压失败：{exc}") from exc

        if not written:
            raise InstallError(E_MANIFEST_INVALID, "压缩包里没有可写入的文件")

        sources = [(path.relative_to(staging).as_posix(), path) for path in written]
        return _apply_package(
            game_root, plan, sources=sources,
            progress=None, should_cancel=should_cancel,
            label="解压包", kind="package_zip",
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _apply_package(
    game_root: os.PathLike | str,
    plan: InstallPlan,
    *,
    sources: Sequence[tuple[str, Path]],
    label: str,
    kind: str,
    progress: Optional[Callable[[str, int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Dict[str, object]:
    """文件包落盘提交（逐文件包与解压包的**唯一**共享实现）。

    ``sources`` 是 ``[(包内相对路径, 已校验的本地文件), ...]`` —— 无论这些
    文件是清单逐条下载的、还是从 .zip 解出来的，落盘规则一字不差：

    - ``target_dir`` 只来自签名清单，经 ``paths.package_dir`` 校验；
    - 与已安装的其它包目录重叠 → 拒绝（否则卸载 A 会删到 B）；
    - 逐文件「先备份 + journal 登记 + 再写」，任何失败整体回滚；
    - 更新时清理旧版本不再声明的文件（只删哈希仍匹配的）；
    - 写入 ``manifest.packages[tool_id]``，卸载/回滚/完整性检查全部复用。
    """
    root = paths.validate_game_root(game_root)
    _assert_runtime_present(root, plan)
    tool_id = paths._safe_id(plan.tool_id)
    package_root = paths.package_dir(root, plan.target_dir)

    needed = 0
    for _rel, src in sources:
        try:
            needed += Path(src).stat().st_size
        except OSError:
            raise InstallError(E_MANIFEST_INVALID, f"安装文件不可读：{src}") from None
    _require_disk_space(root, max(needed * 2, needed + 32 * 1024 * 1024))

    manifest = state.Manifest.load(root)
    existing = manifest.packages.get(tool_id)

    # 两个包不能写到重叠目录：否则卸载 A 可能删到 B 的文件。
    for other_id, other in manifest.packages.items():
        if other_id == tool_id:
            continue
        try:
            other_root = paths.package_dir(root, other.target_dir)
        except paths.UnsafePathError:
            continue
        if paths.is_within(package_root, other_root) or paths.is_within(other_root, package_root):
            raise InstallError(
                E_PATH_UNSAFE,
                f"目标目录与已安装的包 {other_id} 重叠：{plan.target_dir}",
            )

    journal = state.Journal(root)
    written: List[state.ManagedFile] = []
    seen: set[str] = set()
    total = max(needed, 1)
    done = 0

    with runtime.game_lock(root):
        runtime.assert_can_install(root)
        try:
            journal.begin(f"install_{kind}", tool_id)
            for rel, src in sources:
                if should_cancel and should_cancel():
                    raise InstallError(E_CANCELLED, "已取消")
                clean = paths.sanitize_member_name(rel)
                key = clean.casefold()
                if key in seen:
                    raise InstallError(E_MANIFEST_INVALID, f"安装清单存在重复路径：{clean}")
                seen.add(key)
                target = paths.resolve_within(package_root, clean)
                existed = target.exists()
                backup_rel = f"package/{tool_id}/{plan.release_id}/{clean.replace('/', '__')}"
                backup = state.backup_file(root, target, backup_rel) if existed else None
                journal.add_entry(
                    target, backup_rel=backup, existed=existed, allowed_root=package_root
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(target))
                written.append(
                    state.ManagedFile(
                        relative_path=clean,
                        sha256=paths.short_hash(target),
                        backup_path=backup,
                        existed_before=existed,
                    )
                )
                try:
                    done += Path(src).stat().st_size
                except OSError:
                    done = 0
                if progress:
                    progress(clean, min(done, total), total)

            # 旧版本有、新版本没有的文件：只清理哈希仍匹配的受管文件
            if existing:
                for old in existing.files:
                    if old.relative_path.casefold() in seen:
                        continue
                    try:
                        old_target = paths.resolve_within(package_root, old.relative_path)
                    except paths.UnsafePathError:
                        continue
                    if not old_target.exists():
                        continue
                    if old.sha256 and paths.short_hash(old_target) != old.sha256:
                        logger.warning("包 %s 的旧文件被用户修改，保留不删：%s", tool_id, old_target)
                        continue
                    backup_rel = (
                        f"package/{tool_id}/{plan.release_id}/removed__"
                        f"{old.relative_path.replace('/', '__')}"
                    )
                    backup = state.backup_file(root, old_target, backup_rel)
                    journal.add_entry(
                        old_target, backup_rel=backup, existed=True, allowed_root=package_root
                    )
                    old_target.unlink()

            manifest.packages[tool_id] = state.PackageEntry(
                tool_id=tool_id,
                release_id=plan.release_id,
                version=plan.version,
                version_sort=plan.version_sort,
                dependencies=list(plan.dependencies or ()),
                target_dir=plan.target_dir,
                files=written,
                installed_at=_now_iso(),
                requires_runtime=bool(plan.requires_runtime),
            )
            journal.set_state(state.STATE_COMMITTING)
            manifest.save()
            journal.set_state(state.STATE_DONE)
            journal.clear()
        except BaseException as exc:
            logger.exception("%s安装失败，回滚", label)
            result = state.restore_from_journal(root, journal)
            journal.clear()
            if isinstance(exc, InstallError):
                raise
            raise InstallError(
                E_UNKNOWN,
                f"{label}安装失败并已回滚（恢复 {len(result['restored'])} 个文件）：{exc}",
            ) from exc

    return {
        "ok": True,
        "kind": kind,
        "tool_id": tool_id,
        "release_id": plan.release_id,
        "target_dir": plan.target_dir,
        "files": len(written),
    }


def uninstall_runtime(
    game_root: os.PathLike | str,
    *,
    restore_originals: bool = True,
) -> Dict[str, object]:
    """卸载工具箱底座（Zylarnex）：**只动自己登记过的文件**。

    ## 为什么必须有这个函数（2026-11-02）

    底座是插件的前置（``requires_runtime``），历史上只有 ``install_runtime``
    没有卸载入口：一旦装上就再也回不到裸跑。旧版 LimiNex 挂载有 ``unmount``
    作对照，迁移到订阅工具底座后这个能力不能丢。

    ## 语义

    - 只处理 ``RuntimeEntry.files`` 登记过、且**哈希仍匹配**的文件；
      被用户改过的文件跳过并上报（不静默覆盖用户改动）；
    - ``restore_originals=True``（默认）：安装时被覆盖过的原始文件（
      ``existed_before`` + ``backup_path``）**还原回去**，其余删除 ——
      效果等于"回到装底座之前"；
    - ``BepInEx/plugins`` 下的用户插件**一律不动**（它们不在底座清单里，
      这与旧 LimiNex 整目录删除的做法不同）；
    - 全程 journal + 备份，失败可回滚。

    游戏运行中拒绝（文件被锁）。
    """
    root = paths.validate_game_root(game_root)
    manifest = state.Manifest.load(root)
    entry = manifest.runtime
    if entry is None:
        raise InstallError(E_NOT_MANAGED, "本机没有受管的工具箱底座")

    removed = 0
    restored = 0
    skipped: List[str] = []
    with runtime.game_lock(root):
        runtime.assert_can_install(root)

        journal = state.Journal(root)
        journal.begin("uninstall_runtime", "runtime")
        try:
            for f in entry.files:
                try:
                    target = paths.resolve_within(root, f.relative_path)
                except paths.UnsafePathError:
                    skipped.append(f.relative_path)
                    continue
                if not target.exists():
                    continue
                if f.sha256 and paths.short_hash(target) != f.sha256:
                    # 用户改过 → 不删不还原，交由用户决定
                    skipped.append(f.relative_path)
                    continue
                try:
                    paths.assert_runtime_target(root, target)
                except paths.UnsafePathError:
                    skipped.append(f.relative_path)
                    continue

                backup_rel = None
                if restore_originals and f.existed_before and f.backup_path:
                    backup = paths.resolve_within(paths.backups_dir(root), f.backup_path)
                    if backup.exists():
                        # 先登记、再改写：中断后 journal 能把它恢复成"删除前"
                        current = state.backup_file(
                            root, target,
                            f"runtime/{entry.release_id}/uninstall__"
                            f"{f.relative_path.replace('/', '__')}",
                        )
                        journal.add_entry(target, backup_rel=current, existed=True)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(backup), str(target))
                        restored += 1
                        continue
                current = state.backup_file(
                    root, target,
                    f"runtime/{entry.release_id}/uninstall__"
                    f"{f.relative_path.replace('/', '__')}",
                )
                journal.add_entry(target, backup_rel=current, existed=True)
                target.unlink()
                removed += 1

            _prune_empty_dirs(root / "BepInEx" / "core")
            _prune_empty_dirs(root / "dotnet")
            manifest.runtime = None
            manifest.save()
            journal.set_state(state.STATE_DONE)
            journal.clear()
        except BaseException:
            logger.exception("底座卸载失败，回滚")
            state.restore_from_journal(root, journal)
            journal.clear()
            raise

    return {
        "ok": True,
        "kind": "runtime",
        "release_id": entry.release_id,
        "removed": removed,
        "restored": restored,
        "skipped": skipped,
    }


def rollback_runtime(game_root: os.PathLike | str) -> Dict[str, object]:
    """把底座文件还原为安装前的内容（保留受管记录，由卸载负责清空）。

    与 ``rollback_plugin`` 同语义：只按 ``backup_path`` 还原，找不到备份的
    文件列入 ``missing_backup``。
    """
    root = paths.validate_game_root(game_root)
    manifest = state.Manifest.load(root)
    entry = manifest.runtime
    if entry is None:
        raise InstallError(E_NOT_MANAGED, "本机没有受管的工具箱底座")

    restored: List[str] = []
    missing: List[str] = []
    with runtime.game_lock(root):
        runtime.assert_can_install(root)
        for f in entry.files:
            if not f.backup_path:
                continue
            backup = paths.resolve_within(paths.backups_dir(root), f.backup_path)
            if not backup.exists():
                missing.append(f.relative_path)
                continue
            target = paths.resolve_within(root, f.relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(backup), str(target))
            restored.append(f.relative_path)

    return {
        "ok": bool(restored) or not missing,
        "kind": "runtime",
        "restored": restored,
        "missing_backup": missing,
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


def uninstall_package(game_root: os.PathLike | str, tool_id: str) -> Dict[str, object]:
    """卸载 ``game_relative_files`` 文件包（只删哈希仍匹配的受管文件）。"""
    root = paths.validate_game_root(game_root)
    tool_id = paths._safe_id(tool_id)
    manifest = state.Manifest.load(root)
    entry = manifest.packages.get(tool_id)
    if entry is None:
        raise InstallError(E_NOT_MANAGED, f"文件包 {tool_id} 不在 LCTA 受管清单内")

    package_root = paths.package_dir(root, entry.target_dir)
    removed = 0
    skipped: List[str] = []
    with runtime.game_lock(root):
        runtime.assert_can_install(root)
        journal = state.Journal(root)
        journal.begin("uninstall_package", tool_id)
        for f in entry.files:
            try:
                target = paths.resolve_within(package_root, f.relative_path)
            except paths.UnsafePathError:
                skipped.append(f.relative_path)
                continue
            if not target.exists():
                continue
            if f.sha256 and paths.short_hash(target) != f.sha256:
                skipped.append(str(target))
                continue
            try:
                paths.assert_managed_target(root, target, extra_roots=[package_root])
                backup_rel = f"package/{tool_id}/{entry.release_id}/uninstall__{f.relative_path.replace('/', '__')}"
                backup = state.backup_file(root, target, backup_rel)
                journal.add_entry(target, backup_rel=backup, existed=True, allowed_root=package_root)
                target.unlink()
                removed += 1
            except (OSError, paths.UnsafePathError):
                skipped.append(str(target))

        # 只清空包根下的空目录，保留用户自己放进去的内容
        _prune_empty_dirs(package_root)
        del manifest.packages[tool_id]
        manifest.save()
        journal.set_state(state.STATE_DONE)
        journal.clear()

    return {"ok": True, "tool_id": tool_id, "removed": removed, "skipped": skipped}


def _prune_empty_dirs(root: Path) -> None:
    """自底向上删除空目录（不删 root 本身之外的任何非空目录）。"""
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def verify_integrity_package(game_root: os.PathLike | str, tool_id: str) -> Dict[str, object]:
    """校验文件包的文件哈希与布局。"""
    root = paths.validate_game_root(game_root)
    tool_id = paths._safe_id(tool_id)
    manifest = state.Manifest.load(root)
    entry = manifest.packages.get(tool_id)
    if entry is None:
        raise InstallError(E_NOT_MANAGED, f"文件包 {tool_id} 不在受管清单内")

    package_root = paths.package_dir(root, entry.target_dir)
    missing: List[str] = []
    modified: List[str] = []
    for f in entry.files:
        target = paths.resolve_within(package_root, f.relative_path)
        if not target.exists():
            missing.append(f.relative_path)
            continue
        if f.sha256 and paths.short_hash(target) != f.sha256:
            modified.append(f.relative_path)

    return {
        "ok": not (missing or modified),
        "kind": "package",
        "tool_id": tool_id,
        "target_dir": entry.target_dir,
        "missing": missing,
        "modified": modified,
        "needs_repair": bool(missing or modified),
    }


def rollback_package(game_root: os.PathLike | str, tool_id: str) -> Dict[str, object]:
    """回滚文件包到本地备份（离线可用）。"""
    root = paths.validate_game_root(game_root)
    tool_id = paths._safe_id(tool_id)
    manifest = state.Manifest.load(root)
    entry = manifest.packages.get(tool_id)
    if entry is None:
        raise InstallError(E_NOT_MANAGED, f"文件包 {tool_id} 不在受管清单内")

    package_root = paths.package_dir(root, entry.target_dir)
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
            target = paths.resolve_within(package_root, f.relative_path)
            paths.assert_managed_target(root, target, extra_roots=[package_root])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(backup), str(target))
            restored.append(f.relative_path)

    return {
        "ok": bool(restored) or not missing,
        "kind": "package",
        "tool_id": tool_id,
        "restored": restored,
        "missing_backup": missing,
    }


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
            "version_sort": p.version_sort,
            "dependencies": list(p.dependencies or []),
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

    packages = [
        {
            "tool_id": p.tool_id,
            "release_id": p.release_id,
            "version": p.version,
            "version_sort": p.version_sort,
            "dependencies": list(p.dependencies or []),
            "target_dir": p.target_dir,
            "installed_at": p.installed_at,
            "requires_runtime": p.requires_runtime,
        }
        for p in manifest.packages.values()
    ]

    return {
        "game_root": str(root),
        "runtime": (
            {
                "release_id": manifest.runtime.release_id,
                "version": manifest.runtime.version,
                "version_sort": manifest.runtime.version_sort,
            }
            if manifest.runtime else None
        ),
        "plugins": plugins,
        "packages": packages,
        "unmanaged": unmanaged,
    }