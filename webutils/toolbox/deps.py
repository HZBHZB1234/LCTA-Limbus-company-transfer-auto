# -*- coding: utf-8 -*-
"""工具间依赖解析（2026-11-02）。

服务端已经在发布与季目录两层挡住"依赖不存在 / 版本不满足 / 依赖环"，
客户端这一步只做三件事：

1. **解析安装顺序**（被依赖者先装）——多工具一次安装/更新时顺序错了会崩；
2. **缺口分类**（没装 / 版本太低 / 被停用 / 没资格 / 不在目录），
   让界面能说清"还差什么"，而不是抛一句"安装失败"；
3. **写文件之前 fail-fast**：依赖不满足时一个字节都不落盘。

## 版本比较不用 semver

依赖条目里的 ``min_version_sort`` 是服务端算好的零填充序串，客户端只做
字符串比较。理由：两套 semver 实现必然漂移，而"谁更新"的答案必须唯一。
本地清单里没记录 ``version_sort`` 的老安装（升级前的记录）按"未知"处理，
会被判成 ``unknown_version`` —— 让用户更新一次即可写入新记录。

## 停用依赖算缺失

插件停用 = 移出 BepInEx 加载树（见 ``install.set_enabled``）。依赖方加载时
找不到它就会报错，所以"装着但停用"按**未满足**上报（``disabled``），由界面
提示用户启用，而不是静默放行。
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

from . import state

logger = logging.getLogger(__name__)

# 依赖相关的错误码（与站点错误码不同命名空间：这是客户端判定的结果）
E_DEPENDENCY_MISSING = "dependency_missing"
E_DEPENDENCY_OUTDATED = "dependency_outdated"
E_DEPENDENCY_DISABLED = "dependency_disabled"
E_DEPENDENCY_NO_ENTITLEMENT = "dependency_no_entitlement"
E_DEPENDENCY_CYCLE = "dependency_cycle"
E_DEPENDENCY_UNKNOWN_VERSION = "dependency_unknown_version"


class DependencyError(RuntimeError):
    """依赖不满足。``data`` 带结构化缺口，供界面逐条展示。"""

    def __init__(self, code: str, message: str, data: Optional[dict] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


def _as_tool_id(value) -> str:
    return str(value or "").strip()


def _sort_value(value) -> str:
    """归一化版本序串：缺失按最低处理（空串字典序最小）。"""
    return str(value or "")


def _satisfies(have_sort, min_sort) -> bool:
    if not min_sort:
        return True
    return _sort_value(have_sort) >= str(min_sort)


def installed_index(manifest: "state.Manifest") -> Dict[str, dict]:
    """本地已安装工具索引：``{tool_id: {kind, release_id, version, version_sort, enabled, dependencies}}``。"""
    out: Dict[str, dict] = {}
    for tool_id, entry in manifest.plugins.items():
        out[_as_tool_id(tool_id)] = {
            "kind": "plugin",
            "release_id": entry.release_id,
            "version": entry.version,
            "version_sort": getattr(entry, "version_sort", "") or "",
            "enabled": bool(entry.enabled),
            "dependencies": list(getattr(entry, "dependencies", []) or []),
        }
    for tool_id, entry in manifest.packages.items():
        out[_as_tool_id(tool_id)] = {
            "kind": "package",
            "release_id": entry.release_id,
            "version": entry.version,
            "version_sort": getattr(entry, "version_sort", "") or "",
            # 文件包没有"启停"概念，永远视为可用
            "enabled": True,
            "dependencies": list(getattr(entry, "dependencies", []) or []),
        }
    return out


def catalog_index(catalog_items: Iterable[dict]) -> Dict[str, dict]:
    """目录索引：同工具多版本时优先 ``is_latest``，否则取版本序最大者。

    旧站点没有 ``is_latest``（返回 false/缺字段），此时退化为"按 version_sort
    取最大"——好过旧客户端的 ``release_id`` 字符串比较。
    """
    out: Dict[str, dict] = {}
    for item in catalog_items or []:
        if not isinstance(item, dict):
            continue
        tool_id = _as_tool_id(item.get("tool_id"))
        if not tool_id:
            continue
        current = out.get(tool_id)
        if current is None:
            out[tool_id] = item
            continue
        if item.get("is_latest") and not current.get("is_latest"):
            out[tool_id] = item
            continue
        if bool(item.get("is_latest")) == bool(current.get("is_latest")):
            if _sort_value(item.get("version_sort")) > _sort_value(current.get("version_sort")):
                out[tool_id] = item
    return out


def _dependency_entries(item: dict) -> List[dict]:
    deps = item.get("dependencies") if isinstance(item, dict) else None
    return [d for d in (deps or []) if isinstance(d, dict)]


def _gap(
    *,
    tool_id: str,
    dep: dict,
    reason: str,
    installed: Optional[dict] = None,
) -> dict:
    return {
        "tool_id": tool_id,
        "tool_name": dep.get("tool_name") or "",
        "min_version": dep.get("min_version"),
        "min_version_sort": dep.get("min_version_sort"),
        "optional": bool(dep.get("optional", False)),
        "downloadable": bool(dep.get("downloadable", True)),
        "in_catalog": dep.get("in_catalog"),
        "reason": reason,
        "installed_version": (installed or {}).get("version", ""),
        "installed_version_sort": (installed or {}).get("version_sort", ""),
    }


def resolve(
    manifest: "state.Manifest",
    catalog_items: Iterable[dict],
    tool_id,
) -> dict:
    """解析某工具的依赖：安装顺序 + 缺口分类。

    返回值:

    - ``order``：拓扑序（被依赖者在前，目标工具在最后），只含"需要安装/更新"
      的工具 id；目标是最后一项；
    - ``missing`` / ``outdated`` / ``disabled`` / ``no_entitlement`` /
      ``unknown_version``：结构化缺口（硬依赖进这里即视为阻塞）；
    - ``optional_missing``：可选依赖缺口（不阻塞安装，界面提示即可）；
    - ``cycles``：防御性——服务端已拒绝环，这里兜住脏目录数据。
    """
    target = _as_tool_id(tool_id)
    installed = installed_index(manifest)
    catalog = catalog_index(catalog_items)

    result = {
        "tool_id": target,
        "order": [],
        "missing": [],
        "outdated": [],
        "disabled": [],
        "no_entitlement": [],
        "unknown_version": [],
        "optional_missing": [],
        "cycles": [],
        "ok": True,
    }

    def fail(code: str, gap: dict) -> None:
        bucket = {
            E_DEPENDENCY_MISSING: "missing",
            E_DEPENDENCY_OUTDATED: "outdated",
            E_DEPENDENCY_DISABLED: "disabled",
            E_DEPENDENCY_NO_ENTITLEMENT: "no_entitlement",
            E_DEPENDENCY_UNKNOWN_VERSION: "unknown_version",
        }[code]
        if gap["optional"]:
            result["optional_missing"].append(gap)
            return
        result.setdefault(bucket, []).append(gap)
        result["ok"] = False

    order: List[str] = []
    visiting: List[str] = []
    visited: set[str] = set()

    def walk(current_tool: str, from_item: Optional[dict]) -> None:
        if current_tool in visited:
            return
        if current_tool in visiting:
            cycle = visiting[visiting.index(current_tool):] + [current_tool]
            result["cycles"].append(cycle)
            result["ok"] = False
            logger.warning("依赖环（脏目录数据）：%s", " → ".join(cycle))
            return
        visiting.append(current_tool)
        item = from_item if from_item is not None else catalog.get(current_tool)
        for dep in _dependency_entries(item or {}):
            dep_tool = _as_tool_id(dep.get("tool_id"))
            if not dep_tool:
                # release 锁定依赖：按"是否已装该 release"判定，无法拓扑
                dep_release = str(dep.get("release_id") or "")
                if not dep_release:
                    continue
                installed_release = next(
                    (v["release_id"] for v in installed.values() if v["release_id"] == dep_release),
                    None,
                )
                if installed_release is None:
                    fail(E_DEPENDENCY_MISSING, _gap(
                        tool_id=dep_release, dep=dep, reason="release_not_installed",
                    ))
                continue
            have = installed.get(dep_tool)
            if not have:
                fail(E_DEPENDENCY_MISSING, _gap(
                    tool_id=dep_tool, dep=dep, reason="not_installed",
                ))
                # 目录里有、但当前请求者没资格下载：即便"能一起装"也装不了
                if not dep.get("downloadable", True):
                    fail(E_DEPENDENCY_NO_ENTITLEMENT, _gap(
                        tool_id=dep_tool, dep=dep, reason="no_entitlement",
                    ))
                # 目录里有就能一起装：继续往下走以解析它自己的依赖
                if dep_tool in catalog:
                    walk(dep_tool, catalog.get(dep_tool))
                continue
            if not have["enabled"]:
                fail(E_DEPENDENCY_DISABLED, _gap(
                    tool_id=dep_tool, dep=dep, reason="disabled", installed=have,
                ))
            min_sort = dep.get("min_version_sort")
            if min_sort:
                if not have["version_sort"]:
                    fail(E_DEPENDENCY_UNKNOWN_VERSION, _gap(
                        tool_id=dep_tool, dep=dep, reason="unknown_version", installed=have,
                    ))
                elif not _satisfies(have["version_sort"], min_sort):
                    fail(E_DEPENDENCY_OUTDATED, _gap(
                        tool_id=dep_tool, dep=dep, reason="outdated", installed=have,
                    ))
                    walk(dep_tool, catalog.get(dep_tool))
            elif not have["version_sort"]:
                # 没有版本号要求时，老安装记录也放行
                pass
        visiting.remove(current_tool)
        visited.add(current_tool)
        order.append(current_tool)

    walk(target, None)
    result["order"] = order
    return result


def assert_ready(
    manifest: "state.Manifest",
    catalog_items: Iterable[dict],
    tool_id,
) -> dict:
    """安装前门禁：依赖不满足直接抛 ``DependencyError``（不落任何文件）。

    返回解析结果（调用方可用来提示"将同时安装 N 个依赖"）。
    """
    info = resolve(manifest, catalog_items, tool_id)
    if info["ok"]:
        return info
    if info["cycles"]:
        raise DependencyError(
            E_DEPENDENCY_CYCLE,
            "依赖关系存在环（目录数据异常）：" + " → ".join(info["cycles"][0]),
            info,
        )
    for code, bucket, label in (
        (E_DEPENDENCY_NO_ENTITLEMENT, "no_entitlement", "缺少依赖的下载资格"),
        (E_DEPENDENCY_OUTDATED, "outdated", "依赖版本过低"),
        (E_DEPENDENCY_DISABLED, "disabled", "依赖被停用"),
        (E_DEPENDENCY_UNKNOWN_VERSION, "unknown_version", "依赖版本未知"),
        (E_DEPENDENCY_MISSING, "missing", "缺少依赖"),
    ):
        gaps = info.get(bucket) or []
        if not gaps:
            continue
        names = [
            "{name}({tid})".format(
                name=g.get("tool_name") or "未知工具", tid=g.get("tool_id")
            )
            for g in gaps
        ]
        raise DependencyError(code, f"{label}：{'、'.join(names)}", info)
    raise DependencyError(E_DEPENDENCY_MISSING, "依赖不满足", info)


def dependents_of(manifest: "state.Manifest", tool_id) -> List[str]:
    """反查：本地已安装工具里，哪些依赖 ``tool_id``（卸载/停用前提示用）。

    用户确认的行为是「只警告、不阻止」，所以这里只返回清单，不做判定。
    """
    target = _as_tool_id(tool_id)
    out: List[str] = []
    for owner_id, owner in installed_index(manifest).items():
        if owner_id == target:
            continue
        for dep in owner.get("dependencies") or []:
            if _as_tool_id(dep.get("tool_id")) == target:
                out.append(owner_id)
                break
    return sorted(set(out))


def uninstall_warnings(manifest: "state.Manifest", tool_id) -> List[str]:
    """卸载前给用户看的警告文案（只提示，不阻塞）。"""
    dependents = dependents_of(manifest, tool_id)
    if not dependents:
        return []
    return [
        "以下已安装工具依赖它，卸载后将无法加载：{}".format("、".join(dependents))
    ]


def plan_updates(
    manifest: "state.Manifest",
    catalog_items: Iterable[dict],
    *,
    client_protocol: int | None = None,
) -> Dict[str, list]:
    """算出"哪些已装工具有新版"（启动器自动更新的输入，纯函数）。

    判定顺序**就是安全边界**：

    1. 只考虑**已安装**工具（自动更新不负责装新工具，那是用户的决定）；
    2. 目录里没有该工具 / 没有 ``is_latest`` 行 → 跳过（老站点没有指针，
       不猜）；
    3. 已经是最新版（release_id 相同）→ 跳过；
    4. 目标版本不高于已装（``version_sort`` 比较）→ 跳过，**绝不自动降级**；
    5. 底座（``runtime_zip_root``）→ 跳过（由用户手动更新：doorstop 原生层
       更新失败 = 游戏起不来）；
    6. 当前请求者没资格下载 → 跳过并上报（界面给引导）；
    7. 目标版本要求更高的客户端协议 → 跳过并上报 ``client_outdated``
       （不该让"客户端太旧"被记成一次安装失败）。

    返回 ``{"updates": [...], "skipped": [...]}``，``updates`` 已按依赖拓扑序
    排好（被依赖者先）。
    """
    installed = installed_index(manifest)
    catalog = catalog_index(catalog_items)
    updates: List[dict] = []
    skipped: List[dict] = []

    def skip(tool_id: str, reason: str, detail: str = "") -> None:
        skipped.append({"tool_id": tool_id, "reason": reason, "detail": detail})

    for tool_id, have in installed.items():
        item = catalog.get(tool_id)
        if item is None:
            skip(tool_id, "not_in_catalog")
            continue
        if not item.get("is_latest"):
            skip(tool_id, "no_latest")
            continue
        target_release = str(item.get("release_id") or "")
        if not target_release or target_release == have["release_id"]:
            continue
        if item.get("install_kind") == "runtime_zip_root":
            skip(tool_id, "runtime_manual", "底座需手动更新")
            continue
        if not item.get("downloadable", True):
            skip(tool_id, "no_entitlement")
            continue
        if client_protocol is not None:
            try:
                required = int(item.get("min_client_protocol") or 1)
            except (TypeError, ValueError):
                required = 1
            if required > int(client_protocol):
                skip(tool_id, "client_outdated", f"需要协议 {required}")
                continue
        target_sort = _sort_value(item.get("version_sort"))
        current_sort = _sort_value(have["version_sort"])
        if current_sort and target_sort and target_sort <= current_sort:
            skip(tool_id, "not_newer", f"{have['version']} ≥ {item.get('version')}")
            continue
        updates.append({
            "tool_id": tool_id,
            "release_id": target_release,
            "from_version": have["version"],
            "to_version": str(item.get("version") or ""),
            "install_kind": item.get("install_kind"),
            "min_client_protocol": item.get("min_client_protocol") or 1,
            "kind": have["kind"],
        })

    ordered_ids = update_order([u["tool_id"] for u in updates], catalog_items)
    by_id = {u["tool_id"]: u for u in updates}
    ordered = [by_id[tid] for tid in ordered_ids if tid in by_id]
    # 排序丢条目是不可接受的（自动更新会漏装），兜底补回原顺序
    for update in updates:
        if update not in ordered:
            ordered.append(update)
    return {"updates": ordered, "skipped": skipped}


def missing_installed_dependencies(
    manifest: "state.Manifest",
    catalog_items: Iterable[dict],
) -> List[dict]:
    """已装工具的**硬依赖缺失**清单（启动器的"修复"输入）。

    自动更新不装新工具，但"已装的工具缺了依赖"属于修复而不是新增 ——
    否则用户那个工具会静默坏掉。返回需要补装的依赖（含 tool_id/release_id）。
    """
    catalog = catalog_index(catalog_items)
    installed = installed_index(manifest)
    out: List[dict] = []
    seen: set[str] = set()
    for tool_id, have in installed.items():
        item = catalog.get(tool_id)
        if item is None:
            continue
        for dep in _dependency_entries(item):
            if dep.get("optional"):
                continue
            dep_tool = _as_tool_id(dep.get("tool_id"))
            if not dep_tool or dep_tool in installed or dep_tool in seen:
                continue
            dep_item = catalog.get(dep_tool)
            if dep_item is None or not dep_item.get("is_latest"):
                continue
            if not dep_item.get("downloadable", True):
                continue
            seen.add(dep_tool)
            out.append({
                "tool_id": dep_tool,
                "release_id": dep_item.get("release_id"),
                "to_version": dep_item.get("version"),
                "install_kind": dep_item.get("install_kind"),
                "needed_by": tool_id,
            })
    return out


def update_order(tool_ids: Iterable[str], catalog_items: Iterable[dict]) -> List[str]:
    """给一批待更新工具排序：被依赖者先更新。

    依赖关系取**目录里最新版本**的声明（服务端已保证无环）。未知工具保持
    原有相对顺序（稳定排序），避免"某次目录缺条目"把顺序打乱。
    """
    wanted = [str(t) for t in tool_ids]
    catalog = catalog_index(catalog_items)
    edges: Dict[str, set] = {}
    for tool in wanted:
        item = catalog.get(tool) or {}
        edges[tool] = {
            _as_tool_id(d.get("tool_id"))
            for d in _dependency_entries(item)
            if _as_tool_id(d.get("tool_id")) in wanted
        }
    ordered: List[str] = []
    seen: set[str] = set()

    def visit(node: str, stack: List[str]) -> None:
        if node in seen:
            return
        if node in stack:  # 环：防御性截断，不让排序卡死
            logger.warning("更新排序遇到依赖环：%s", " → ".join(stack + [node]))
            return
        stack.append(node)
        for dep in sorted(edges.get(node, ())):
            visit(dep, stack)
        stack.pop()
        if node not in seen:
            seen.add(node)
            ordered.append(node)

    for tool in wanted:
        visit(tool, [])
    return ordered
