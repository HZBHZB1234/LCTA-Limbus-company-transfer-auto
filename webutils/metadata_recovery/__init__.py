# -*- coding: utf-8 -*-
"""webutils.metadata_recovery - Limbus Company IL2CPP metadata 解密恢复工具。

移植自 HZBHZB1234/LimbusMetadataRecovery，流水线：

    locate（IDA 内）→ extract → verify → solve 31 段 → apply profile

- locate：`locator.py`，需在 IDA 内运行（插件或 MCP）；页面提供一键安装插件。
- extract/verify/solve/profile：纯 stdlib 离线流水线，由 `pipeline.py` 编排，
  页面「Metadata 恢复」直接调用 `run_recovery()`。

替换表 hex 的来源：定位器 dump、手工粘贴，或本包从 GameAssembly.dll
按反编译文本中的 VA 自动读取（`read_rva_data`）。

公共 API：
    run_recovery()           完整离线流水线（页面/CLI/测试入口）
    install_ida_plugin()     安装 IDA 定位器插件（自动探测 plugins 目录）
    find_ida_plugins_dir()   探测 IDA plugins 目录
    output_dir() / new_run_dir()  运行产物目录（<path_>/metadata_recovery/）
    各阶段纯函数：extract_from_text / verify_profile / solve / build_profile
"""

from __future__ import annotations

from .extractor import extract_from_text, build_report, RE_TABLE
from .verify import (
    classify_section,
    decrypt_bytes,
    next_xorshift64,
    parse_triplets,
    verify_profile,
)
from .solver import (
    STANDARD_NAMES,
    decrypt_header,
    parse_reference,
    rebuild_standard,
    solve,
)
from .profile import build_profile
from .report import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_PASS_WITH_REVIEW,
    Gate,
    Report,
    ReviewItem,
)
from .pipeline import (
    new_run_dir,
    output_dir,
    read_rva_data,
    resolve_table_hex,
    run_recovery,
)
from pathlib import Path
import json

# locator 需在 IDA 内运行；模块本身可安全导入（内部 try/except 守卫）
from .locator import INSIDE_IDA, analyze, run_background  # noqa: E402

__all__ = [
    "extract_from_text",
    "build_report",
    "RE_TABLE",
    "classify_section",
    "decrypt_bytes",
    "next_xorshift64",
    "parse_triplets",
    "verify_profile",
    "STANDARD_NAMES",
    "decrypt_header",
    "parse_reference",
    "rebuild_standard",
    "solve",
    "build_profile",
    "VERDICT_FAIL",
    "VERDICT_PASS",
    "VERDICT_PASS_WITH_REVIEW",
    "Gate",
    "Report",
    "ReviewItem",
    "new_run_dir",
    "output_dir",
    "read_rva_data",
    "resolve_table_hex",
    "run_recovery",
    "INSIDE_IDA",
    "analyze",
    "run_background",
    "find_ida_plugins_dir",
    "install_ida_plugin",
    "plugin_installed",
    "derive_game_files",
    "load_locator_export",
]

# ------------------------------------------------------------- IDA 插件安装

_PLUGIN_FILENAME = "metadata_locator_plugin.py"
_TOOLS_DIRNAME = "metadata_recovery_tools"

_PLUGIN_SOURCE = '''# -*- coding: utf-8 -*-
"""metadata_locator_plugin.py - 解密入口定位器 IDA 插件。

由 LCTA「Metadata 恢复」页面自动安装，请勿手动编辑。
热键：Ctrl-Alt-Shift-M（与旧插件的 Ctrl-Alt-M 不冲突）。
输出：<IDB 目录>/locator_out/locate_candidates.json + 报告。
"""

import os
import sys
from pathlib import Path

import idaapi
import ida_kernwin

_plugin_dir = Path(__file__).resolve().parent
if str(_plugin_dir) not in sys.path:
    sys.path.insert(0, str(_plugin_dir))
if str(_plugin_dir / "%(tools_dir)s") not in sys.path:
    sys.path.insert(0, str(_plugin_dir / "%(tools_dir)s"))

import locate_metadata_init  # noqa: E402


class LocateMetadataInitPlugin(idaapi.plugin_t):
    flags = idaapi.PLUGIN_KEEP
    comment = "Locate metadata decrypt init function via evidence scoring"
    help = "Scan xorshift patterns + decompile features, rank candidates"
    wanted_name = "Locate Metadata Init"
    wanted_hotkey = "Ctrl-Alt-Shift-M"

    def init(self):
        return idaapi.PLUGIN_OK

    def run(self, arg):
        out_dir = Path(idaapi.get_root_filename()).parent / "locator_out"
        env = os.environ.get("LIMBUS_LOCATOR_OUT")
        if env:
            out_dir = Path(env)
        try:
            locate_metadata_init.run_background(out_dir, top_k=20)
            ida_kernwin.info(f"定位器完成：{out_dir / 'locate_candidates.json'}")
        except Exception as exc:  # noqa: BLE001
            ida_kernwin.warning(f"定位器失败：{exc}")

    def term(self):
        pass


def PLUGIN_ENTRY():
    return LocateMetadataInitPlugin()
'''


def find_ida_plugins_dir() -> str | None:
    """探测 IDA plugins 目录：注册表优先，其次常见安装路径。"""
    import glob as _glob

    candidates = []
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\Hex-Rays\IDA",
                        r"SOFTWARE\WOW6432Node\Hex-Rays\IDA"):
                try:
                    with winreg.OpenKey(hive, sub) as key:
                        for value_name in ("InstallPath", "Path",
                                           "InstallationPath", "IDA_Path"):
                            try:
                                value, _ = winreg.QueryValueEx(key, value_name)
                                if value:
                                    candidates.append(str(value))
                            except OSError:
                                continue
                except OSError:
                    continue
    except ImportError:
        pass
    for root in (r"C:\Program Files", r"C:\Program Files (x86)", "C:\\", "D:\\",
                 "E:\\"):
        candidates.extend(_glob.glob(rf"{root}\IDA*\plugins"))
        candidates.extend(_glob.glob(rf"{root}\Hex-Rays\IDA*\plugins"))
    for path in candidates:
        if path and Path(path).is_dir():
            return path
    return None


def install_ida_plugin(plugins_dir: str = "") -> dict:
    """安装 IDA 定位器插件到 plugins 目录。

    写入：
    - <plugins>/metadata_locator_plugin.py（插件入口，热键 Ctrl-Alt-Shift-M）
    - <plugins>/metadata_recovery_tools/locate_metadata_init.py + report.py

    返回 {"success", "plugin_path", "tools_dir", "files": [...]}。
    """
    import shutil

    pkg_dir = Path(__file__).resolve().parent
    if plugins_dir:
        target = Path(plugins_dir)
    else:
        found = find_ida_plugins_dir()
        if not found:
            raise RuntimeError("未自动探测到 IDA plugins 目录，请手动选择")
        target = Path(found)
    if not target.is_dir():
        raise RuntimeError(f"plugins 目录不存在：{target}")

    tools_dir = target / _TOOLS_DIRNAME
    tools_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = target / _PLUGIN_FILENAME

    files = []
    plugin_path.write_text(
        _PLUGIN_SOURCE % {"tools_dir": _TOOLS_DIRNAME}, encoding="utf-8")
    files.append(str(plugin_path))
    for src_name, dst_name in (("locator.py", "locate_metadata_init.py"),
                               ("report.py", "report.py")):
        src = pkg_dir / src_name
        dst = tools_dir / dst_name
        shutil.copy2(src, dst)
        files.append(str(dst))
    return {"success": True, "plugin_path": str(plugin_path),
            "tools_dir": str(tools_dir), "files": files}


def plugin_installed(plugins_dir: str = "") -> bool:
    """检查插件是否已安装（未指定目录时自动探测）。"""
    if plugins_dir:
        target = Path(plugins_dir)
    else:
        found = find_ida_plugins_dir()
        if not found:
            return False
        target = Path(found)
    return (target / _PLUGIN_FILENAME).is_file()


def derive_game_files(game_path: str = "") -> dict:
    """从游戏根目录推导加密 metadata 与 GameAssembly.dll 的路径。

    标准布局（Steam 版）：
    - <game>/LimbusCompany_Data/il2cpp_data/Metadata/global-metadata.dat
    - <game>/GameAssembly.dll

    返回 dict 含 exists 标记（路径即使不存在也返回，便于 UI 提示位置）。
    """
    if not game_path:
        return {"game_path": "", "derived": False,
                "metadata_path": "", "metadata_exists": False,
                "dll_path": "", "dll_exists": False}
    root = Path(game_path)
    metadata = root / "LimbusCompany_Data" / "il2cpp_data" / "Metadata" / "global-metadata.dat"
    dll = root / "GameAssembly.dll"
    return {
        "game_path": str(root),
        "derived": True,
        "metadata_path": str(metadata),
        "metadata_exists": metadata.is_file(),
        "dll_path": str(dll),
        "dll_exists": dll.is_file(),
    }


_DECOMPILE_GLOB_PREFIX = "decompile_rank"


def load_locator_export(export_path: str, rank: int = 1) -> dict:
    """载入 IDA 定位器插件的导出（结构化流程步骤 3）。

    入参兼容导出目录（自动找 locate_candidates.json）或文件本身。
    解析 locate_candidates.json 的 verdict + 全量候选（每候选探测
    decompile_rank{n}_{name}.c 是否存在），按 rank 取替换表 hex 与
    反编译文本（仅导出目录中存在对应文件时才有）。

    返回 dict：{success, verdict, candidates[], table_hex, decompile_text,
    decompile_file, errors[]}。JSON 损坏/目录无效时 success=False 并带明确错误。
    """
    errors: list[str] = []
    path = Path(export_path)
    if not path.exists():
        return {"success": False, "errors": [f"路径不存在：{path}"]}
    if path.is_dir():
        json_path = path / "locate_candidates.json"
    else:
        json_path = path
    if not json_path.is_file():
        return {"success": False,
                "errors": [f"未找到 locate_candidates.json：{json_path}"]}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return {"success": False,
                "errors": [f"locate_candidates.json 解析失败：{exc}"]}
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(candidates, list) or not candidates:
        return {"success": False,
                "errors": ["locate_candidates.json 中无 candidates 列表"]}

    export_dir = json_path.parent
    normalized = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        c_rank = c.get("rank", 0)
        name = c.get("name", "")
        decompile = export_dir / f"{_DECOMPILE_GLOB_PREFIX}{c_rank}_{name}.c"
        normalized.append({
            "rank": c_rank,
            "name": name,
            "score": c.get("score"),
            "table_ref": c.get("table_ref"),
            "has_decompile": decompile.is_file(),
        })
    if not normalized:
        return {"success": False, "errors": ["候选列表为空或格式无效"]}

    chosen = None
    for c in normalized:
        if c["rank"] == rank:
            chosen = c
            break
    if chosen is None:
        return {"success": False, "errors": [f"rank={rank} 不在候选列表（可用 {len(normalized)} 个）"]}

    result = {
        "success": True,
        "verdict": data.get("verdict", ""),
        "candidates": normalized,
        "rank": chosen["rank"],
        "candidate_name": chosen["name"],
        "score": chosen["score"],
        "has_decompile": chosen["has_decompile"],
        "table_hex": "",
        "decompile_text": "",
        "decompile_file": "",
        "errors": [],
    }
    top = next((c for c in candidates if isinstance(c, dict) and c.get("rank") == rank), {})
    table_hex = top.get("table_hex", "")
    if table_hex:
        try:
            if len(bytes.fromhex(table_hex)) == 256:
                result["table_hex"] = table_hex
            else:
                errors.append(f"候选 {chosen['name']} 的 table_hex 长度不为 256 字节")
        except ValueError:
            errors.append(f"候选 {chosen['name']} 的 table_hex 不是合法 hex")
    if chosen["has_decompile"]:
        decompile = export_dir / f"{_DECOMPILE_GLOB_PREFIX}{rank}_{chosen['name']}.c"
        try:
            result["decompile_text"] = decompile.read_text(encoding="utf-8", errors="replace")
            result["decompile_file"] = str(decompile)
        except OSError as exc:
            errors.append(f"反编译文本读取失败：{exc}")
    else:
        errors.append(
            f"候选 {chosen['name']}（rank {rank}）无反编译文本（decompile_rank{rank}_*.c 不存在），"
            "table_hex 已载入，反编译文本需手动提供（如 IDA 伪代码粘贴）")
    result["errors"] = errors
    return result
