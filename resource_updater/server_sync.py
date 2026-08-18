# -*- coding: utf-8 -*-
"""官服 ⇄ lethe 私服 Addressables 资源切换。

背景（依据 LimbusDecompile 工作区 `docs/LETHE_BUNDLE_SYNC.md` 与
`tools/sync_server_bundles.py`）：
- lethe 私服通过 BepInEx 插件（Lethe.dll）把 CDN 重定向到
  `assets.lethelc.site`，官服使用 `download.limbuscompanycdn.org`；
  两者共享同一 Unity Caching 目录
  `%USERPROFILE%\\AppData\\LocalLow\\Unity\\ProjectMoon_LimbusCompany`。
- 两服 catalog 的绝大多数 bundle 名称（含内容 hash 尾段）完全一致，
  缓存键一致、天然共享；仅有少量 lethe 独有 / 官服独有 bundle（随版本变化）。
- 切换服务器时若全量清缓存会重下公共资源（~14 GB）；正确做法是只处理差异：
  目标服独有且缓存缺失的 bundle 从对应 CDN 补下载，另一服独有且缓存存在的
  条目移除，公共 bundle 不动。

本模块提供：
- `ServerSync`：目录校验、catalog 加载、差异分析、同步计划、执行（下载/删除）。
- `run_server_sync()`：Launcher 集成入口（开启官服前恢复官服资源）。
- `create_lethe_shortcut()`：生成「开启 lethe 私服」桌面快捷方式
  （先同步 lethe 资源，再启动 lethe 游戏 exe）。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager

from .core import (
    DownloadCancelled,
    GameInfo,
    ResourceUpdater,
    X_REQUESTED_WITH,
    _headers,
    default_unity_cache_dir,
    default_work_dir,
    http_get,
    parse_catalog,
)

_log_manager = LogManager()

# lethe 插件 Http.PreSendWebRequest 的 CDN 重定向目标
LETHE_CDN_HOST = "assets.lethelc.site"
OFFICIAL_CDN_HOST = "download.limbuscompanycdn.org"

S_TOKEN_RE = re.compile(r"download\.limbuscompanycdn\.org/(s\d{8}_[A-Za-z0-9_-]+)/")

ProgressCallback = Callable[[str, str, Optional[float]], None]


class ServerSyncError(Exception):
    pass


class ServerSyncCancelled(ServerSyncError):
    pass


# ---------------------------------------------------------------- 配置

def get_server_switch_config() -> Dict[str, Any]:
    """读取 launcher.server_switch.* 配置（无则返回默认值）。"""
    manager = ConfigManager()
    prefix = "launcher.server_switch"

    def as_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    return {
        "enabled": bool(manager.get("{}.enabled".format(prefix), False)),
        "server": manager.get("{}.server".format(prefix), "official"),
        "lethe_dir": manager.get("{}.lethe_dir".format(prefix), ""),
        "keep_other": bool(manager.get("{}.keep_other".format(prefix), False)),
        "jobs": max(1, min(as_int(manager.get("{}.jobs".format(prefix), 8), 8), 32)),
        "engine": manager.get("{}.engine".format(prefix), "auto"),
        "retry_max": max(0, as_int(manager.get("{}.retry_max".format(prefix), 2), 2)),
        "retry_delay": max(5, as_int(manager.get("{}.retry_delay".format(prefix), 30), 30)),
        "connection_limit": max(
            1, min(16, as_int(manager.get("{}.connection_limit".format(prefix), 8), 8))
        ),
    }


def save_server_switch_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """持久化 launcher.server_switch.* 配置。返回 (是否成功, 更新条数)。"""
    def as_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    server = options.get("server", "official")
    if server not in ("official", "lethe"):
        server = "official"
    engine = options.get("engine", "auto")
    if engine not in ("auto", "aria2", "builtin"):
        engine = "auto"
    updates = {
        "launcher.server_switch.enabled": bool(options.get("enabled", False)),
        "launcher.server_switch.server": server,
        "launcher.server_switch.lethe_dir": str(options.get("lethe_dir", "") or ""),
        "launcher.server_switch.keep_other": bool(options.get("keep_other", False)),
        "launcher.server_switch.jobs": max(1, min(as_int(options.get("jobs", 8), 8), 32)),
        "launcher.server_switch.engine": engine,
        "launcher.server_switch.retry_max": max(
            0, as_int(options.get("retry_max", 2), 2)
        ),
        "launcher.server_switch.retry_delay": max(
            5, as_int(options.get("retry_delay", 30), 30)
        ),
        "launcher.server_switch.connection_limit": max(
            1, min(16, as_int(options.get("connection_limit", 8), 8))
        ),
    }
    count = ConfigManager().set_batch(updates)
    return {"success": count == len(updates), "updated": count}


# ---------------------------------------------------------------- 目录探测

def _s_token_from_settings(settings_path: Path) -> Optional[str]:
    """从 settings.json 提取 s-token（与 GameInfo.extract_tokens 同源，但
    只解析 settings.json，不要求 resources.assets 等其它文件存在，便于
    校验 lethe 目录时宽松处理）。"""
    if not settings_path.is_file():
        return None
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None
    for location in data.get("m_CatalogLocations", []):
        match = S_TOKEN_RE.search(str(location.get("m_InternalId", "")))
        if match:
            return match.group(1)
    return None


def _catalog_path_of(game_dir: Path) -> Path:
    return (
        Path(game_dir)
        / "LimbusCompany_Data"
        / "StreamingAssets"
        / "aa"
        / "catalog.bin"
    )


def _settings_path_of(game_dir: Path) -> Path:
    return (
        Path(game_dir)
        / "LimbusCompany_Data"
        / "StreamingAssets"
        / "aa"
        / "settings.json"
    )


def _game_executable_of(game_dir: Path) -> Path:
    return Path(game_dir) / "LimbusCompany.exe"


def detect_lethe_dir_candidates() -> List[Path]:
    """探测常见 lethe 分发包位置，供前端路径输入预填。"""
    candidates = []
    work = default_work_dir().parent  # %LOCALAPPDATA%/LCTA
    for base in (
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path.home(),
        Path(os.getenv("path_", "")),
        work,
    ):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            if child.name.lower().startswith("lethe") or "lethe" in child.name.lower():
                if _catalog_path_of(child).is_file():
                    candidates.append(child)
    seen = set()
    unique = []
    for candidate in candidates:
        resolved = str(candidate)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(candidate)
    return unique


# ---------------------------------------------------------------- 核心

class ServerSync:
    """在两服之间同步 Unity bundle 缓存。

    用法：
        sync = ServerSync(lethe_dir, official_dir, ...)
        report = sync.analyze()          # 差异分析
        plan = sync.plan("lethe")        # 生成 ADD/REMOVE 计划
        result = sync.run("lethe")       # 执行同步（dry_run 时仅预览）
    """

    def __init__(
        self,
        lethe_dir: Path,
        official_dir: Path,
        cache_dir: Optional[Path] = None,
        jobs: int = 8,
        engine: str = "auto",
        keep_other: bool = False,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
        retry_max: int = 0,
        retry_delay: float = 30.0,
        connection_limit: int = 8,
    ):
        self.lethe_dir = Path(lethe_dir)
        self.official_dir = Path(official_dir)
        self.cache_dir = Path(cache_dir) if cache_dir else default_unity_cache_dir()
        self.jobs = max(1, min(int(jobs), 32))
        self.engine = engine
        self.keep_other = bool(keep_other)
        self.progress_callback = progress_callback
        self.cancel_event = cancel_event or threading.Event()
        self.retry_max = max(0, int(retry_max))
        self.retry_delay = max(0.0, float(retry_delay))
        self.connection_limit = max(1, min(16, int(connection_limit)))
        # 复用 ResourceUpdater 的下载引擎（aria2 / 内置）与重试/进度机制
        self._updater = ResourceUpdater(
            official_dir,
            jobs=self.jobs,
            engine=self.engine,
            progress_callback=progress_callback,
            cancel_event=self.cancel_event,
            retry_max=self.retry_max,
            retry_delay=self.retry_delay,
            connection_limit=self.connection_limit,
        )

    # ---- 报告与取消 ----

    def report(
        self, message: str, fraction: Optional[float] = None, level: int = 20
    ) -> None:
        _log_manager.log("[服务器切换] {}".format(message), level)
        if self.progress_callback:
            self.progress_callback("server_switch", message, fraction)

    def cancel(self) -> None:
        self.cancel_event.set()
        if self._updater.aria2:
            self._updater.aria2.remove_all()

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise ServerSyncCancelled("服务器切换已取消")

    # ---- 加载 ----

    def validate(self) -> None:
        missing = []
        for label, game_dir in (("lethe", self.lethe_dir), ("official", self.official_dir)):
            if not _catalog_path_of(game_dir).is_file():
                missing.append("{} 缺少 catalog.bin: {}".format(label, game_dir))
        if missing:
            raise ServerSyncError("；".join(missing))

    def _load_catalog(self, game_dir: Path) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
        return parse_catalog(_catalog_path_of(game_dir))

    def _token_of(self, game_dir: Path) -> Optional[str]:
        return _s_token_from_settings(_settings_path_of(game_dir))

    def _existing_inner_to_outer(self) -> Dict[str, str]:
        return self._updater._existing_bundle_mapping()

    # ---- 差异分析 ----

    def analyze(self) -> Dict[str, Any]:
        """加载两服 catalog 并计算差异。返回结构化报告。"""
        self.validate()
        self._check_cancel()
        self.report("正在读取两服资源清单", 0.05)
        l_names, l_meta = self._load_catalog(self.lethe_dir)
        o_names, o_meta = self._load_catalog(self.official_dir)
        l_token = self._token_of(self.lethe_dir)
        o_token = self._token_of(self.official_dir)

        def cacheable(meta: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
            return {
                name: item
                for name, item in meta.items()
                if item.get("inner") and item.get("outer")
            }

        l_c = cacheable(l_meta)
        o_c = cacheable(o_meta)

        # 差异分类基于完整名称集合（含内容 hash 尾段）：名称一致即内容一致
        full_l = set(l_names)
        full_o = set(o_names)
        only_lethe = sorted(full_l - full_o)
        only_official = sorted(full_o - full_l)
        common = sorted(full_l & full_o)

        report = {
            "lethe_dir": str(self.lethe_dir),
            "official_dir": str(self.official_dir),
            "cache_dir": str(self.cache_dir),
            "lethe_token": l_token,
            "official_token": o_token,
            "lethe_bundles": len(full_l),
            "official_bundles": len(full_o),
            "shared": common,
            "shared_count": len(common),
            "only_lethe": only_lethe,
            "only_official": only_official,
            "only_lethe_count": len(only_lethe),
            "only_official_count": len(only_official),
            "lethe_cacheable": len(l_c),
            "official_cacheable": len(o_c),
        }
        self.report(
            "差异分析完成：共享 {}，lethe 独有 {}，官服独有 {}".format(
                len(common), len(only_lethe), len(only_official)
            ),
            0.5,
        )
        return report

    # ---- 计划 ----

    def plan(self, server: str, analyze: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """生成同步计划。server: 'official' | 'lethe'。"""
        if server not in ("official", "lethe"):
            raise ServerSyncError("未知目标服务器: {}".format(server))
        analysis = analyze if analyze is not None else self.analyze()
        self._check_cancel()

        if server == "lethe":
            target_meta = self._load_catalog(self.lethe_dir)[1]
            other_meta = self._load_catalog(self.official_dir)[1]
            token = analysis.get("lethe_token")
            add_names = analysis["only_lethe"]
            remove_names = analysis["only_official"]
            base = "https://{}/{}".format(LETHE_CDN_HOST, token) if token else None
        else:
            target_meta = self._load_catalog(self.official_dir)[1]
            other_meta = self._load_catalog(self.lethe_dir)[1]
            token = analysis.get("official_token")
            add_names = analysis["only_official"]
            remove_names = analysis["only_lethe"]
            base = "https://{}/{}".format(OFFICIAL_CDN_HOST, token) if token else None

        if not token:
            raise ServerSyncError(
                "无法提取 {} 服务器的 s-token（settings.json 缺失或格式异常）".format(server)
            )

        def cacheable(meta: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
            return {
                name: item
                for name, item in meta.items()
                if item.get("inner") and item.get("outer")
            }

        target_c = cacheable(target_meta)
        other_c = cacheable(other_meta)

        # 以本机缓存 inner->outer 校准（catalog 解析可能受二进制定界影响）
        existing = self._existing_inner_to_outer()
        for name, item in target_c.items():
            inner = item.get("inner")
            if inner and inner in existing:
                item["outer"] = existing[inner]
        for name, item in other_c.items():
            inner = item.get("inner")
            if inner and inner in existing:
                item["outer"] = existing[inner]

        def entry_exists(outer: str, inner: str) -> bool:
            data_f = self.cache_dir / outer / inner / "__data"
            return data_f.is_file() and data_f.stat().st_size > 0

        plan_add = []
        for name in add_names:
            item = target_c.get(name)
            if not item:
                continue  # 无缓存键（Steam 托管本地文件），不参与缓存
            if not entry_exists(item["outer"], item["inner"]):
                plan_add.append({
                    "name": name,
                    "inner": item["inner"],
                    "outer": item["outer"],
                    "url": "{}/{}".format(base, name),
                })

        plan_remove = []
        if not self.keep_other:
            for name in remove_names:
                item = other_c.get(name)
                if not item:
                    continue
                if (self.cache_dir / item["outer"] / item["inner"]).exists():
                    plan_remove.append({
                        "name": name,
                        "inner": item["inner"],
                        "outer": item["outer"],
                    })

        plan_add.sort(key=lambda item: item["name"])
        plan_remove.sort(key=lambda item: item["name"])
        return {
            "server": server,
            "token": token,
            "base": base,
            "add": plan_add,
            "remove": plan_remove,
            "add_count": len(plan_add),
            "remove_count": len(plan_remove),
            "keep_other": self.keep_other,
        }

    # ---- 执行 ----

    def _remove_entry(self, outer: str, inner: str) -> bool:
        entry = self.cache_dir / outer / inner
        if not entry.exists():
            return False
        for path in entry.glob("*"):
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
        try:
            entry.rmdir()
        except OSError:
            pass
        return True

    def run(self, server: str, dry_run: bool = False) -> Dict[str, Any]:
        """执行同步。dry_run=True 时仅预览，不下载不删除。"""
        self.report("正在为 {} 服务器生成同步计划".format(server), 0.1)
        analysis = self.analyze()
        plan = self.plan(server, analysis)

        for item in plan["add"]:
            self.report(
                "计划下载: {} ({})".format(item["name"], item["inner"])
            )
        for item in plan["remove"]:
            self.report(
                "计划移除: {} ({})".format(item["name"], item["inner"])
            )
        self.report(
            "计划完成：下载 {} 个，移除 {} 个（公共资源 {} 个不动）".format(
                plan["add_count"], plan["remove_count"], analysis["shared_count"]
            ),
            0.25,
        )
        if dry_run:
            return {
                "dry_run": True,
                "server": server,
                "added": 0,
                "removed": 0,
                "failed": 0,
                "retried": 0,
                "failed_items": [],
                "plan": plan,
                "analysis": analysis,
            }

        added = removed = failed = retried = 0
        failed_items = []

        def record_failure(name: str, reason: str, url: str = "") -> None:
            nonlocal failed
            failed += 1
            item = {"name": name, "reason": reason}
            if url:
                item["url"] = url
            failed_items.append(item)
            self.report("失败: {} ({})".format(name, reason), level=30)

        # ---- ADD：下载目标服独有 bundle 到缓存 ----
        if plan["add"]:
            tasks = []
            for item in plan["add"]:
                destination = (
                    self.cache_dir / item["outer"] / item["inner"] / "__data"
                )
                tasks.append((
                    item["url"],
                    destination,
                    True,                       # include_xrw
                    True,                       # skip_not_found
                    self._updater._write_bundle_info,  # post_action
                    True,                       # cleanup_parent
                ))
            try:
                if self._updater._resolved_engine() == "aria2":
                    result = self._updater._download_many_aria2("server_switch", tasks)
                    added += result["completed"]
                    retried += result.get("retried", 0)
                    for item in result.get("failed_items", []):
                        failed += 1
                        failed_items.append(item)
                        self.report(
                            "失败: {} ({})".format(item.get("name"), item.get("reason")),
                            level=30,
                        )
                else:
                    for index, task in enumerate(tasks):
                        self._check_cancel()
                        try:
                            attempts = self._updater._download_with_retry_builtin(
                                "server_switch",
                                task[0],
                                task[1],
                                task[2],
                                index,
                                len(tasks),
                                cleanup_parent=True,
                            )
                            task[4](task[1])
                            added += 1
                            retried += max(0, attempts - 1)
                        except FileNotFoundError:
                            self._updater._cleanup_failed_download(task[1], True)
                            self.report(
                                "跳过: {}（目标 CDN 无此资源）".format(
                                    task[0].rsplit("/", 1)[-1]
                                ),
                                level=30,
                            )
                        except DownloadCancelled:
                            raise ServerSyncCancelled("服务器切换已取消")
                        except Exception as exc:
                            self._updater._cleanup_failed_download(task[1], True)
                            record_failure(
                                task[0].rsplit("/", 1)[-1], str(exc), task[0]
                            )
            except ServerSyncCancelled:
                raise
            except Exception as exc:
                self.report("下载阶段异常: {}".format(exc), level=40)
                raise ServerSyncError("下载阶段异常: {}".format(exc)) from exc

        # ---- REMOVE：移除另一服独有 bundle 的缓存条目 ----
        if plan["remove"]:
            self.report("正在移除 {} 个另一服独有缓存条目".format(len(plan["remove"])), 0.8)
            for item in plan["remove"]:
                self._check_cancel()
                try:
                    removed_flag = self._remove_entry(item["outer"], item["inner"])
                    if removed_flag:
                        removed += 1
                        self.report("已移除: {} ({})".format(item["name"], item["inner"]))
                except Exception as exc:
                    record_failure(item["name"], "移除失败: {}".format(exc))

        self.report(
            "切换完成：下载 {}，移除 {}，失败 {}".format(added, removed, failed),
            1.0,
        )
        return {
            "dry_run": False,
            "server": server,
            "added": added,
            "removed": removed,
            "failed": failed,
            "retried": retried,
            "failed_items": failed_items,
            "plan": plan,
            "analysis": analysis,
        }


# ---------------------------------------------------------------- Launcher 集成

def run_server_sync(
    server: str,
    lethe_dir: Optional[Path] = None,
    official_dir: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    cancel_event: Optional[threading.Event] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """按配置执行一次服务器资源同步。

    Launcher 在开启官服前调用 server='official' 恢复官服资源。
    配置缺失/目录无效/无差异时安全返回（不抛异常）。
    """
    if server not in ("official", "lethe"):
        return {"success": False, "message": "未知目标服务器: {}".format(server)}
    cfg = config if config is not None else get_server_switch_config()
    official = Path(official_dir or ConfigManager().get("game_path", ""))
    lethe = Path(lethe_dir or cfg.get("lethe_dir", ""))
    if not official.is_dir():
        return {"success": False, "message": "官服目录无效: {}".format(official)}
    if not lethe.is_dir():
        return {"success": False, "message": "lethe 目录无效: {}".format(lethe)}
    sync = ServerSync(
        lethe_dir=lethe,
        official_dir=official,
        jobs=cfg.get("jobs", 8),
        engine=cfg.get("engine", "auto"),
        keep_other=cfg.get("keep_other", False),
        progress_callback=progress_callback,
        cancel_event=cancel_event,
        retry_max=cfg.get("retry_max", 2),
        retry_delay=cfg.get("retry_delay", 30),
        connection_limit=cfg.get("connection_limit", 8),
    )
    try:
        result = sync.run(server, dry_run=dry_run)
        result["success"] = result.get("failed", 0) == 0
        return result
    except ServerSyncCancelled:
        return {"success": False, "message": "服务器切换已取消"}
    except ServerSyncError as exc:
        return {"success": False, "message": str(exc)}


# ---------------------------------------------------------------- 桌面快捷方式

def _desktop_path() -> Path:
    """获取桌面目录（含 OneDrive 重定向场景）。"""
    try:
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.SystemInformation]::UserProfilePath "
        )
        # 用注册表更可靠：HKCU\...\User Shell Folders\Desktop
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "Desktop")
        if value.startswith("%"):
            expanded = os.path.expandvars(value)
            return Path(expanded)
        return Path(value)
    except Exception:
        return Path.home() / "Desktop"


def _create_lnk(lnk_path: Path, target: Path, work_dir: Path, icon: Path, description: str) -> bool:
    """通过 PowerShell WScript.Shell 创建 .lnk 快捷方式。"""
    command = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$sc = $ws.CreateShortcut('{}'); "
        "$sc.TargetPath = '{}'; "
        "$sc.WorkingDirectory = '{}'; "
        "$sc.IconLocation = '{},0'; "
        "$sc.Description = '{}'; "
        "$sc.Save()"
    ).format(
        str(lnk_path).replace("'", "''"),
        str(target).replace("'", "''"),
        str(work_dir).replace("'", "''"),
        str(icon).replace("'", "''"),
        description.replace("'", "''"),
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            timeout=60,
        )
        if completed.returncode != 0:
            _log_manager.log(
                "[服务器切换] 创建快捷方式失败: {}".format(
                    completed.stderr.decode("utf-8", "replace")[:300]
                ),
                40,
            )
            return False
        return True
    except Exception as exc:
        _log_manager.log("[服务器切换] 创建快捷方式失败: {}".format(exc), 40)
        return False


def create_lethe_shortcut(
    lethe_dir: Path,
    config: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """创建「开启 lethe 私服」桌面快捷方式。

    快捷方式指向一个生成的 .cmd 启动脚本：先执行 lethe 资源同步
    （缺失的 lethe 独有 bundle 补下载、官服独有条目移除），再启动
    lethe 游戏的 LimbusCompany.exe。快捷方式图标取 lethe 游戏 exe。
    """
    lethe = Path(lethe_dir)
    exe = _game_executable_of(lethe)
    if not exe.is_file():
        return {"success": False, "message": "lethe 目录缺少 LimbusCompany.exe: {}".format(lethe)}

    cfg = config if config is not None else get_server_switch_config()
    official = Path(ConfigManager().get("game_path", ""))
    if not official.is_dir():
        return {"success": False, "message": "官服目录无效，请先在设置页配置游戏目录: {}".format(official)}

    # 生成启动脚本（内含同步 + 启动）
    script_dir = default_work_dir() / "server_switch"
    script_dir.mkdir(parents=True, exist_ok=True)
    cmd_path = script_dir / "launch_lethe.cmd"
    project_root = Path(os.getenv("path_", "")) or Path(__file__).resolve().parent.parent
    python = Path(sys.executable)

    script_lines = [
        "@echo off",
        "chcp 65001 >nul",
        "cd /d \"{}\"".format(str(project_root)),
        "set \"path_={}\"".format(str(project_root)),
        "echo === 正在同步 lethe 私服资源，请稍候... ===",
        "\"{}\" -m resource_updater.server_sync --server lethe --lethe-dir \"{}\" --official-dir \"{}\" --shortcut".format(
            str(python),
            str(lethe),
            str(official),
        ),
        "echo === 资源同步完成，正在启动 lethe 私服... ===",
        "start \"\" /d \"{}\" \"{}\"".format(str(lethe), str(exe)),
    ]
    cmd_path.write_text("\r\n".join(script_lines) + "\r\n", encoding="utf-8")

    desktop = _desktop_path()
    lnk_path = desktop / "开启 lethe 私服.lnk"
    ok = _create_lnk(lnk_path, cmd_path, script_dir, exe, "启动 LCTA 管理的 lethe 私服（先同步资源）")
    if not ok:
        return {"success": False, "message": "快捷方式创建失败（PowerShell 不可用或权限不足）"}
    return {
        "success": True,
        "message": "已创建桌面快捷方式",
        "lnk": str(lnk_path),
        "script": str(cmd_path),
        "target": str(exe),
    }


# ---------------------------------------------------------------- CLI

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="resource_updater.server_sync",
        description="在官服与 lethe 私服之间同步 Unity bundle 缓存",
    )
    parser.add_argument("--server", choices=["official", "lethe"], required=True)
    parser.add_argument("--lethe-dir", default=None)
    parser.add_argument("--official-dir", default=None)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--keep-other", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--engine", choices=["auto", "aria2", "builtin"], default=None)
    parser.add_argument("--shortcut", action="store_true",
                        help="快捷方式模式：失败不阻断游戏启动（由 .cmd 后续启动游戏）")
    args = parser.parse_args(argv)

    cfg = get_server_switch_config()
    lethe = Path(args.lethe_dir or cfg.get("lethe_dir", ""))
    official = Path(
        args.official_dir
        or (ConfigManager().get("game_path", ""))
    )
    if not lethe.is_dir():
        print("error: lethe 目录无效: {}".format(lethe))
        return 2
    if not official.is_dir():
        print("error: 官服目录无效: {}".format(official))
        return 2

    sync = ServerSync(
        lethe_dir=lethe,
        official_dir=official,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        jobs=args.jobs or cfg.get("jobs", 8),
        engine=args.engine or cfg.get("engine", "auto"),
        keep_other=args.keep_other or cfg.get("keep_other", False),
        retry_max=cfg.get("retry_max", 2),
        retry_delay=cfg.get("retry_delay", 30),
        connection_limit=cfg.get("connection_limit", 8),
    )
    try:
        result = sync.run(args.server, dry_run=args.dry_run)
        print("summary: added={} removed={} failed={}".format(
            result["added"], result["removed"], result["failed"]
        ))
        return 0 if result["failed"] == 0 else 1
    except ServerSyncCancelled:
        print("cancelled")
        return 130
    except ServerSyncError as exc:
        print("error: {}".format(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
