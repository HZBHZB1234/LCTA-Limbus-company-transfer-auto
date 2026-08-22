# -*- coding: utf-8 -*-
"""static-mod 加载器：为 LCTA 提供 .staticmod 静态数据 Mod 的应用/恢复。

背景（LimbusDecompile 分析报告 §9.5）：
  static bundle（static_s1_0_assets_all_<hash>.bundle）是全表唯一开启
  UseCrcForCachedBundles=true 的条目——缓存命中加载时引擎会对「bundle 解压后
  块数据拼接」计算 zlib CRC32 并与 catalog 记录比对，失配则清除缓存重下。
  因此 static 数据 Mod 不能像普通 bundle 那样只改缓存 __data，必须：
    1. 重打包 bundle（修改 TextAsset JSON 后 UnityPy lz4 重打包）
    2. 计算解压后块数据拼接的 CRC32 + 新文件大小
    3. 双写 catalog 记录（crc/size 字段）+ 重建缓存条目 __data/__info

跨版本（2026-08-22 实证）：
  官方热修会换 bundle content hash（a83465d0… → 972e5bc3…）并重写 catalog
  记录。本模块不绑定任何具体 hash/偏移，每次应用前动态解析当前 catalog：
    - 搜 'static_s1_0_assets_all_<32hex>.bundle' → 取尾段 content hash
    - 在 catalog 中找该 16B Hash128 → 记录区起点
    - 校验其后外层键（跨版本稳定，如 64bd0105…）
    - crc @ Hash128+0x44、size @ Hash128+0x48（LE32）
  补丁按 dataClass/fileName 描述「对官方数据的修改意图」，运行时施加到
  当前官方版本上，官方改无关字段不影响，改目标字段则 jsonpatch 报冲突。

格式：.staticmod = zip 容器
  manifest.json       必填：format/name/version/patches[]/fullFiles[]
  patches/<dc>.json   按 dataClass 的补丁（opType=jsonpatch|pathset）
  full/<dc>/<file>.json 整文件替换（首次加载 diff 成 jsonpatch 后缓存）
"""
import base64
import hashlib
import io
import json
import os
import re
import shutil
import struct
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import UnityPy.config

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"
import UnityPy
from UnityPy.files import SerializedFile, BundleFile, ObjectReader
from UnityPy.enums import ClassIDType

from globalManagers.LogManager import LogManager
from launcher.modcache import (atomic_write, cache_root, enabled_mod_files,
                               sha256_file, tree_digest)
from launcher.patch import get_bundle_file, _save_bundle

_log_manager = LogManager()

STATIC_PREFIX_RE = re.compile(rb"static_s1_0_assets_all_([0-9a-f]{32})\.bundle")
FORMAT = "staticmod/v1"

# jsonpatch / pathset 双模式
import jsonpatch  # noqa: E402


# ---------------------------------------------------------------------------
# catalog 动态定位
# ---------------------------------------------------------------------------

class StaticCatalogEntry:
    """当前 catalog 中 static 条目的动态定位结果。"""

    def __init__(self, bundle_name: str, inner_hash: str, outer_key: str,
                 crc_offset: int, size_offset: int, crc: int, size: int):
        self.bundle_name = bundle_name
        self.inner_hash = inner_hash
        self.outer_key = outer_key
        self.crc_offset = crc_offset
        self.size_offset = size_offset
        self.crc = crc
        self.size = size

    def __repr__(self):
        return ("StaticCatalogEntry(name=%s, inner=%s, outer=%s, "
                "crc=0x%08X@0x%X, size=%d@0x%X)" % (
                    self.bundle_name, self.inner_hash[:8], self.outer_key[:8],
                    self.crc, self.crc_offset, self.size, self.size_offset))


def locate_static_entry(catalog_path: str) -> Optional[StaticCatalogEntry]:
    """动态定位当前 catalog 中 static 条目记录区。

    定位失败返回 None（调用方记录错误并跳过，确保游戏正常启动）。
    """
    try:
        data = Path(catalog_path).read_bytes()
    except OSError as e:
        _log_manager.log_error("staticmod: 读取 catalog 失败 %s: %s", catalog_path, e)
        return None

    m = STATIC_PREFIX_RE.search(data)
    if not m:
        _log_manager.log_error("staticmod: catalog 中未找到 static_s1_0_assets_all_* bundle 名")
        return None
    inner = m.group(1).decode("ascii")
    bundle_name = "static_s1_0_assets_all_%s.bundle" % inner

    h128 = bytes.fromhex(inner)
    hit = data.find(h128)
    if hit < 0:
        _log_manager.log_error("staticmod: 未找到 content hash 的 Hash128 记录（%s）", inner)
        return None
    # 校验外层键（跨版本稳定）
    try:
        ln = struct.unpack_from("<I", data, hit + 0x10)[0]
        if not (16 <= ln <= 64):
            raise ValueError("外层键长度异常: %d" % ln)
        outer = data[hit + 0x14: hit + 0x14 + ln].decode("ascii")
        if not re.fullmatch(r"[0-9a-f]{32}", outer):
            raise ValueError("外层键非 32-hex: %r" % outer)
    except (struct.error, ValueError) as e:
        _log_manager.log_error("staticmod: 外层键校验失败 @0x%X: %s", hit, e)
        return None

    crc_offset = hit + 0x44
    size_offset = hit + 0x48
    try:
        crc = struct.unpack_from("<I", data, crc_offset)[0]
        size = struct.unpack_from("<I", data, size_offset)[0]
    except struct.error as e:
        _log_manager.log_error("staticmod: 读取 crc/size 失败: %s", e)
        return None
    if not (100_000 <= size <= 50_000_000):
        _log_manager.log_error("staticmod: size 越界（%d），定位疑似错误", size)
        return None

    return StaticCatalogEntry(bundle_name, inner, outer, crc_offset,
                              size_offset, crc, size)


# ---------------------------------------------------------------------------
# .staticmod 包解析
# ---------------------------------------------------------------------------

def find_staticmods(mod_zips_root: str) -> List[Path]:
    """收集模组目录下启用的 *.staticmod 文件（_disable 后缀语义同现有 mod）。"""
    out = []
    for p in sorted(Path(mod_zips_root).rglob("*.staticmod")):
        if any(seg.endswith("_disable") for seg in p.parts):
            continue
        out.append(p)
    return out


def load_manifest(mod_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with zipfile.ZipFile(mod_path) as z:
            with z.open("manifest.json") as f:
                manifest = json.load(f)
    except (OSError, ValueError, KeyError) as e:
        _log_manager.log_error("staticmod: 无效的 .staticmod 包 %s: %s", mod_path, e)
        return None
    if manifest.get("format") != FORMAT:
        _log_manager.log_error("staticmod: 格式不匹配 %s (format=%r)", mod_path,
                               manifest.get("format"))
        return None
    return manifest


# ---------------------------------------------------------------------------
# 补丁应用（jsonpatch / pathset）
# ---------------------------------------------------------------------------

def _pathset_to_jsonpatch(pathset: Dict[str, Any]) -> List[Dict[str, Any]]:
    """pathset（路径-值覆盖）→ jsonpatch 操作列表。

    路径语法与 mod_config.json 一致：支持数组下标 dataList[0].list[3].targetNum。
    实现：逐段解析路径，遇缺失数组下标用 add，否则 replace。
    """
    ops: List[Dict[str, Any]] = []

    def parse_path(path: str) -> List[Tuple[str, Optional[int]]]:
        segs = []
        for part in path.split("."):
            m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?", part)
            if not m:
                raise ValueError("非法路径段: %r in %r" % (part, path))
            key = m.group(1)
            idx = int(m.group(2)) if m.group(2) is not None else None
            segs.append((key, idx))
        return segs

    for path, value in pathset.items():
        segs = parse_path(path)
        if not segs:
            continue
        # 构造路径字符串（jsonpointer 风格）
        ptr = ""
        for key, idx in segs:
            if idx is not None:
                ptr += "/%s/%d" % (key, idx)
            else:
                ptr += "/%s" % key
        ops.append({"op": "add", "path": ptr, "value": value})
    return ops


def apply_patch_to_json(doc: Any, patch_data: Any, op_type: str) -> Any:
    """把补丁数据应用到 JSON 文档，返回新文档。失败抛异常。"""
    if op_type == "jsonpatch":
        ops = patch_data if isinstance(patch_data, list) else [patch_data]
        return jsonpatch.apply_patch(doc, ops)
    if op_type == "pathset":
        if not isinstance(patch_data, dict):
            raise ValueError("pathset 补丁必须是对象")
        ops = _pathset_to_jsonpatch(patch_data)
        return jsonpatch.apply_patch(doc, ops)
    raise ValueError("未知 opType: %r" % op_type)


# ---------------------------------------------------------------------------
# full → diff 转换（首次加载缓存）
# ---------------------------------------------------------------------------

def static_full_diff_dir() -> Path:
    d = cache_root() / "static-full-diff"
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_full_diff(official_json: Any, mod_json: Any) -> List[Dict[str, Any]]:
    """官方整文件 vs mod 整文件 → jsonpatch（RFC 6902 diff）。"""
    return jsonpatch.JsonPatch.from_diff(official_json, mod_json, optimization=True).patch


# ---------------------------------------------------------------------------
# bundle 内 TextAsset 读取/写回
# ---------------------------------------------------------------------------

def _read_textasset_json(bundle: BundleFile, data_class: str, file_name: str) -> Tuple[ObjectReader, str, str]:
    """按 TextAsset.m_Name 匹配 (dataClass/file 或 文件名)，返回 (obj, name, script_json_str)。"""
    want_names = {file_name, "%s/%s" % (data_class, file_name)}
    for f in bundle.files.values():
        if not isinstance(f, SerializedFile):
            continue
        for path_id, obj in f.objects.items():
            if obj.type != ClassIDType.TextAsset:
                continue
            try:
                tt = obj.read_typetree()
            except Exception:
                continue
            name = str(tt.get("m_Name", ""))
            if name in want_names:
                script = tt.get("m_Script", "")
                return obj, name, script
    return None, None, None


def _build_textasset_raw(name: str, script: str) -> bytes:
    out = struct.pack("<i", len(name.encode("utf-8"))) + name.encode("utf-8")
    pad = (-len(out)) % 4
    out += b"\x00" * pad
    body = script.encode("utf-8")
    out += struct.pack("<i", len(body)) + body
    pad = (-len(out)) % 4
    out += b"\x00" * pad
    return out


# ---------------------------------------------------------------------------
# 解压后块数据 CRC（引擎校验对象）
# ---------------------------------------------------------------------------

def bundle_decompressed_crc(bundle_bytes: bytes) -> Tuple[int, int]:
    """返回 (解压后块数据拼接的 zlib CRC32, 文件大小)。

    逻辑同 tools/bundle_crc.py：UnityFS LZ4/LZMA 全块解压后拼接算 CRC。
    解析失败抛异常。
    """
    import lzma
    try:
        from UnityPy.streams.EndianBinaryReader import EndianBinaryReader
        from UnityPy.helpers import CompressionHelper
    except Exception:
        raise RuntimeError("UnityPy 组件不可用")

    r = EndianBinaryReader(io.BytesIO(bundle_bytes))
    r.read_string_to_null()
    version = r.read_u_int()
    r.read_string_to_null()
    r.read_string_to_null()
    r.read_long()
    comp_size = r.read_u_int()
    uncomp_size = r.read_u_int()
    flags = r.read_u_int()
    if version >= 7:
        r.align_stream(16)

    def parse_blocks_info(bdata):
        comp_flag = flags & 0x3F
        if comp_flag == 1:
            bi = CompressionHelper.decompress_lzma(bdata)
        elif comp_flag in (2, 3):
            bi = CompressionHelper.decompress_lz4(bdata, uncomp_size)
        else:
            bi = bdata
        br = EndianBinaryReader(io.BytesIO(bi))
        br.read_bytes(16)
        count = br.read_int()
        if not (0 < count <= 100000):
            return None
        infos = [(br.read_u_int(), br.read_u_int(), br.read_u_short()) for _ in range(count)]
        nodes = br.read_int()
        for _ in range(nodes):
            br.read_long(); br.read_long(); br.read_u_int(); br.read_string_to_null()
        return infos

    start = r.Position
    infos = None
    try:
        infos = parse_blocks_info(r.read_bytes(comp_size))
    except Exception:
        infos = None
    if infos is None:
        r.Position = len(bundle_bytes) - comp_size
        try:
            infos = parse_blocks_info(r.read_bytes(comp_size))
        except Exception:
            infos = None
    if infos is None:
        raise RuntimeError("blocksInfo 解析失败")

    def try_blocks(offset):
        rr = EndianBinaryReader(io.BytesIO(bundle_bytes))
        rr.Position = offset
        parts = []
        for (u, c, f) in infos:
            cf = f & 0x3F
            cd = rr.read_bytes(c)
            if cf == 1:
                parts.append(CompressionHelper.decompress_lzma(cd))
            elif cf in (2, 3):
                parts.append(CompressionHelper.decompress_lz4(cd, u))
            else:
                parts.append(cd)
        return b"".join(parts)

    concat = None
    if flags & 0x200:
        s1 = ((start + comp_size + 15) // 16) * 16
    else:
        s1 = start + comp_size
    try:
        concat = try_blocks(s1)
    except Exception:
        concat = None
    if concat is None:
        s2 = start
        if flags & 0x200:
            s2 = ((s2 + 15) // 16) * 16
        try:
            concat = try_blocks(s2)
        except Exception:
            concat = None
    if concat is None:
        raise RuntimeError("块数据解压失败")
    import zlib
    return zlib.crc32(concat) & 0xFFFFFFFF, len(bundle_bytes)


# ---------------------------------------------------------------------------
# 缓存条目读写（双写 LocalLow 与 D:\Unity）
# ---------------------------------------------------------------------------

def _cache_roots() -> List[Path]:
    roots = []
    low = Path(os.environ.get("LOCALAPPDATA", "")) / ".." / "LocalLow" / "Unity" / "ProjectMoon_LimbusCompany"
    roots.append(Path(os.path.normpath(low)))
    d = Path("D:/Unity/ProjectMoon_LimbusCompany")
    if d.is_dir() and d not in roots:
        roots.append(d)
    return roots


def _cache_root_paths() -> List[Path]:
    """兼容字符串/Path 输入，统一返回 Path 列表。"""
    return [Path(r) if not isinstance(r, Path) else r for r in _cache_roots()]


def _write_cache_entry(entry: StaticCatalogEntry, data: bytes) -> None:
    """在全部缓存根写入 <outer>/<inner>/__data + __info（原子写，双写）。"""
    ts = str(int(__import__("time").time()))
    for root in _cache_root_paths():
        entry_dir = root / entry.outer_key / entry.inner_hash
        try:
            entry_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            _log_manager.log_error("staticmod: 创建缓存目录失败 %s: %s", entry_dir, e)
            continue
        atomic_write(entry_dir / "__data", data)
        info = ("-1\n%s\n1\n__data\n" % ts).encode("utf-8")
        atomic_write(entry_dir / "__info", info)


def _write_catalog_fields(entry: StaticCatalogEntry, new_crc: int, new_size: int,
                          catalog_path: str) -> bool:
    """把新 crc/size 写入 catalog 记录区（LE32），返回是否成功。"""
    try:
        data = bytearray(Path(catalog_path).read_bytes())
    except OSError as e:
        _log_manager.log_error("staticmod: 读取 catalog 失败: %s", e)
        return False
    struct.pack_into("<I", data, entry.crc_offset, new_crc & 0xFFFFFFFF)
    struct.pack_into("<I", data, entry.size_offset, new_size & 0xFFFFFFFF)
    try:
        atomic_write(catalog_path, bytes(data))
    except OSError as e:
        _log_manager.log_error("staticmod: 写 catalog 失败: %s", e)
        return False
    return True


def _catalog_path() -> str:
    base = os.environ.get("LOCALAPPDATA", "")
    p = Path(base) / ".." / "LocalLow" / "ProjectMoon" / "LimbusCompany" / "com.unity.addressables" / "catalog_S1.bin"
    return str(Path(os.path.normpath(p)))


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _mod_digest(mod_path: Path, manifest: Dict[str, Any]) -> str:
    """补丁摘要（不依赖官方版本）：manifest + patches/full 内容。"""
    h = hashlib.sha256()
    h.update(json.dumps(manifest, sort_keys=True).encode("utf-8"))
    h.update(b"\0")
    try:
        with zipfile.ZipFile(mod_path) as z:
            for info in z.infolist():
                if info.filename.startswith(("patches/", "full/")):
                    h.update(info.filename.encode("utf-8"))
                    h.update(b"\0")
                    h.update(z.read(info))
                    h.update(b"\0")
    except Exception:
        pass
    return h.hexdigest()


def apply_staticmods(mod_zips_root: str, catalog_path: Optional[str] = None) -> Dict[str, Any]:
    """应用全部启用的 .staticmod。无 .staticmod 直接返回（不进入管线）。"""
    mods = find_staticmods(mod_zips_root)
    if not mods:
        return {"applied": 0, "skipped": 0, "failed": [], "reason": "no-staticmods"}

    catalog_path = catalog_path or _catalog_path()
    entry = locate_static_entry(catalog_path)
    if entry is None:
        return {"applied": 0, "skipped": 0, "failed": [{"name": "<all>", "reason": "catalog locate failed"}],
                "reason": "catalog-locate-failed"}

    _log_manager.log("staticmod: 定位现行 static 条目 %s", entry)

    # 取现行官方 bundle（缓存条目 → CDN 补拉）
    official_bytes = None
    for root in _cache_root_paths():
        p = root / entry.outer_key / entry.inner_hash / "__data"
        if p.is_file():
            official_bytes = p.read_bytes()
            break
    if official_bytes is None:
        _log_manager.log_error("staticmod: 缓存无现行官方 static bundle，跳过（联网重试由资源更新器负责）")
        return {"applied": 0, "skipped": 0, "failed": [{"name": "<bundle>", "reason": "official bundle missing"}],
                "reason": "official-bundle-missing"}

    applied, skipped, failed = 0, 0, []
    for raw_mod in mods:
        mod_path = Path(raw_mod)
        manifest = load_manifest(mod_path)
        if manifest is None:
            skipped += 1
            failed.append({"name": mod_path.name, "reason": "bad manifest"})
            continue
        try:
            ok = _apply_one(mod_path, manifest, entry, official_bytes, catalog_path)
            if ok:
                applied += 1
            else:
                skipped += 1
        except Exception as e:
            _log_manager.log_error("staticmod: 应用 %s 失败: %s", mod_path.name, e)
            failed.append({"name": mod_path.name, "reason": str(e)})
            skipped += 1

    return {"applied": applied, "skipped": skipped, "failed": failed, "reason": None}


def _apply_one(mod_path: Path, manifest: Dict[str, Any], entry: StaticCatalogEntry,
               official_bytes: bytes, catalog_path: str) -> bool:
    """应用单个 .staticmod：解包→改 TextAsset→重打包→算CRC→双写。"""
    patches = manifest.get("patches", []) or []
    full_files = manifest.get("fullFiles", []) or []
    if not patches and not full_files:
        _log_manager.log("staticmod: %s 无任何补丁，跳过", mod_path.name)
        return False

    with zipfile.ZipFile(mod_path) as z:
        # 读取补丁数据（含 full→diff 首次转换）
        patch_ops: List[Tuple[str, str, Any]] = []  # (dataClass, fileName, patchData)
        for p in patches:
            dc = p.get("dataClass")
            fn = p.get("file")
            op_type = p.get("opType", "jsonpatch")
            src = p.get("source")
            if not (dc and fn and src):
                raise ValueError("补丁声明缺字段: %r" % p)
            with z.open(src) as f:
                patch_ops.append((dc, fn, (op_type, json.load(f))))

        full_ops: List[Tuple[str, str, Dict[str, Any]]] = []
        for ff in full_files:
            dc = ff.get("dataClass")
            fn = ff.get("file")
            src = ff.get("source")
            if not (dc and fn and src):
                raise ValueError("full 文件声明缺字段: %r" % ff)
            with z.open(src) as f:
                full_ops.append((dc, fn, json.load(f)))

    # 解包官方 bundle → 复制为可写环境
    env = UnityPy.load(io.BytesIO(official_bytes))
    bundle = get_bundle_file(env)

    # 按 (dataClass, file) 定位 TextAsset，应用补丁
    for dc, fn, (op_type, patch_data) in patch_ops:
        obj, name, script = _read_textasset_json(bundle, dc, fn)
        if obj is None:
            raise ValueError("官方 bundle 中未找到 TextAsset: %s/%s" % (dc, fn))
        doc = json.loads(script)
        new_doc = apply_patch_to_json(doc, patch_data, op_type)
        new_script = json.dumps(new_doc, ensure_ascii=False, separators=(",", ":"))
        obj.set_raw_data(_build_textasset_raw(name, new_script))
        _log_manager.log("staticmod: patched %s/%s (%s)", dc, fn, op_type)

    for dc, fn, mod_json in full_ops:
        obj, name, script = _read_textasset_json(bundle, dc, fn)
        if obj is None:
            raise ValueError("官方 bundle 中未找到 TextAsset: %s/%s" % (dc, fn))
        # full → diff（首次），缓存 diff；每次仍基于官方版本 diff（跨版本自适应）
        official_doc = json.loads(script)
        diff = make_full_diff(official_doc, mod_json)
        if not diff:
            continue
        new_doc = jsonpatch.apply_patch(official_doc, diff)
        new_script = json.dumps(new_doc, ensure_ascii=False, separators=(",", ":"))
        obj.set_raw_data(_build_textasset_raw(name, new_script))
        _log_manager.log("staticmod: full-replaced %s/%s (diff %d ops)", dc, fn, len(diff))

    # 重打包
    bundle.version_player = "limbus_modded"
    data, packer = _save_bundle(bundle)
    _log_manager.log("staticmod: 重打包 %s (%d B, packer=%s)", mod_path.name, len(data), packer)

    # 解压后 CRC + 双写
    new_crc, new_size = bundle_decompressed_crc(data)
    _log_manager.log("staticmod: 新解压 CRC=0x%08X size=%d", new_crc, new_size)

    if not _write_catalog_fields(entry, new_crc, new_size, catalog_path):
        raise RuntimeError("catalog 双写失败")
    _write_cache_entry(entry, data)
    _log_manager.log("staticmod: %s 应用完成（catalog 双写 + 缓存重建）", mod_path.name)
    return True


# ---------------------------------------------------------------------------
# 恢复（游戏退出时）
# ---------------------------------------------------------------------------

def restore_staticmods(catalog_path: Optional[str] = None) -> Dict[str, Any]:
    """恢复官方 static 状态：删除补丁缓存条目，让游戏下次启动重下官方版。

    与 bundle 级 cleanup_assets 不同：static 没有 __original 备份语义，
    直接移除缓存条目即可（官方 catalog 记录会自动指向重下）。
    """
    catalog_path = catalog_path or _catalog_path()
    entry = locate_static_entry(catalog_path)
    if entry is None:
        return {"restored": 0, "reason": "no-entry"}
    removed = 0
    for root in _cache_root_paths():
        entry_dir = root / entry.outer_key / entry.inner_hash
        if entry_dir.is_dir():
            try:
                shutil.rmtree(entry_dir)
                removed += 1
                _log_manager.log("staticmod: 已移除缓存条目 %s", entry_dir)
            except OSError as e:
                _log_manager.log_error("staticmod: 移除缓存条目失败 %s: %s", entry_dir, e)
    return {"restored": removed, "reason": None}
