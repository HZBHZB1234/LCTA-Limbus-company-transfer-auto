# -*- coding: utf-8 -*-
"""加载页 CG 缓存 bundle 扫描 / 预览 / 贴图替换（方案 A）。

缓存位置: %LOCALAPPDATA%\\..\\LocalLow\\Unity\\ProjectMoon_LimbusCompany\\<h1>\\<h2>\\__data
元数据抹除: bundle 内 unity_version="0.0.0"，UnityPy 会误报加密，须在导入后立即设置
FALLBACK_UNITY_VERSION="6000.3.12f1"（同 webutils/function_resource.py 的做法）。

CG ID = "Story_CG/<名>" / "Unit_CG/<名>"（上游已确认，BG/ 为历史失效格式）；
加载页 CG 复用剧情人格/立绘 CG，资源目录 Story/CG/Personality/ 与 Sprite/Unit/CG/，
ID 名字部分 = Sprite 名（= 资源文件名）。有效 ID 全集另可从本地
com.unity.addressables/catalog_S1.json 的 m_KeyDataString 正则提取（未缓存的可锁定不可预览/替换）。
替换流程: 定位 Sprite 引用的 Texture2D → 同规格重编码（保留原 format/mipmap）→
写回 bundle（version_player 标记 "limbus_modded"）。原对象字节保存到
cache_path/cg/originals/ 供「还原原图」使用。

扫描缓存（v3，按 bundle 路径键控）:
  前提：同路径 bundle 内容不可变（游戏更新以新 hash 路径重新下载，旧条目被驱逐）。
  因此「路径存在 + size 一致」即视为有效缓存，重扫时跳过（零 UnityPy 打开）；
  size 为廉价的 stat 兜底。cache_path/cg/cg_ids.json:
    {"version": 3, "scanned_at": t, "bundles": {"<path>": {"size": n, "hits": [...]}},
     "catalog": ["Story_CG/10101_normal", ...]}
  v1/v2 缓存含错误 ID 格式（BG/），直接作废重建；replace/restore 写回后同步 bundle size，
  避免贴图替换导致的 size 变化误触发重扫。modded 的唯一事实来源是 originals store。
"""
import base64
import hashlib
import io
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

import UnityPy.config

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"

import UnityPy  # noqa: E402  必须在设置 FALLBACK_UNITY_VERSION 之后导入
from PIL import Image  # noqa: E402
from UnityPy.enums import ClassIDType  # noqa: E402
from UnityPy.files.BundleFile import BundleFile  # noqa: E402

from globalManagers.ConfigManager import ConfigManager  # noqa: E402
from globalManagers.exceptions import CancelRunning  # noqa: E402
from .save import get_cache_root, lenient_cg_id, normalize_cg_id  # noqa: E402

CACHE_FILE = "cg_ids.json"
ORIGINALS_FILE = "originals.json"
# 加载页 CG 资源目录（上游已确认）：Story/CG/Personality/<名>.png、Sprite/Unit/CG/<名>.png
CG_CONTAINER_DIRS = ("story/cg/", "unit/cg/")
CATALOG_NAME = "catalog_S1.json"
SCAN_WORKERS = 8
MIN_BUNDLE_SIZE = 50_000


# ---------------- 工具 ----------------

def _cg_data_dir() -> Path:
    """扫描索引/还原数据的存放目录：cache_path/cg（同 fancy 技能色缓存模式）。"""
    cache_root = Path(ConfigManager().get("cache_path", "tmp")).expanduser()
    d = cache_root / "cg"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path() -> Path:
    return _cg_data_dir() / CACHE_FILE


def _originals_path() -> Path:
    return _cg_data_dir() / ORIGINALS_FILE


def _bundle_key(bundle_path: str) -> str:
    return hashlib.sha256(bundle_path.encode("utf-8")).hexdigest()[:16]


def _find_bundle_file(env) -> BundleFile:
    """从 UnityPy 环境取 BundleFile（env.file 或 env.files.values() 中的 BundleFile）。"""
    if isinstance(env.file, BundleFile):
        return env.file
    for f in env.files.values():
        if isinstance(f, BundleFile):
            return f
    raise RuntimeError("不是 BundleFile")


def _serialized_file(bundle: BundleFile):
    if not bundle.files:
        raise RuntimeError("bundle 内无 SerializedFile")
    return list(bundle.files.values())[0]


# ---------------- 缓存读写（v3：按 bundle 路径键控 + catalog ID 清单） ----------------

CACHE_VERSION = 3


def _empty_cache() -> dict:
    return {"version": CACHE_VERSION, "scanned_at": 0, "bundles": {}, "catalog": []}


def _load_cache() -> dict:
    """加载 v3 缓存；旧版本（v1/v2，含错误 BG/ 格式 ID）直接作废重建。"""
    p = _index_path()
    if not p.is_file():
        return _empty_cache()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_cache()
    if data.get("version") != CACHE_VERSION:
        return _empty_cache()
    data.setdefault("bundles", {})
    data.setdefault("catalog", [])
    return data


def _save_cache(cache: dict) -> None:
    _index_path().write_text(
        json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _build_items(cache: dict) -> dict:
    """从 bundle 缓存派生 CG ID 视图（按 bundle size 降序去重，最大 bundle 优先），
    再并入 catalog 中未缓存的 ID（可锁定，不可预览/替换）。

    同名合并：Unit_CG/<名> 与 Story_CG/<名> 是同一 CG（Unit_ 仅为 InvalidKey 兜底 label），
    展示名优先 Story_，贴图条目取先命中的 bundle（size 降序）。
    """
    by_name = {}
    for path, rec in sorted(
            cache.get("bundles", {}).items(),
            key=lambda kv: (-(kv[1].get("size") or 0), kv[0])):
        for hit in rec.get("hits", []):
            cg_id = hit.get("cg_id")
            if not cg_id or not hit.get("tex_pid"):
                continue
            name = cg_id.split("/", 1)[-1]
            if name not in by_name:
                by_name[name] = {
                    "bundle": path,
                    "sprite_pid": hit.get("sprite_pid"),
                    "tex_pid": hit.get("tex_pid"),
                    "size": rec.get("size", 0),
                    "has_story": cg_id.startswith("Story_CG/"),
                }
            elif cg_id.startswith("Story_CG/"):
                by_name[name]["has_story"] = True

    items = {}
    for name, e in by_name.items():
        key = "Story_CG/" + name if e["has_story"] else "Unit_CG/" + name
        items[key] = {
            "bundle": e["bundle"],
            "sprite_pid": e["sprite_pid"],
            "tex_pid": e["tex_pid"],
            "size": e["size"],
            "cached": True,
        }
    for cid in cache.get("catalog", []):
        if cid in items:
            continue
        name = cid.split("/", 1)[-1]
        if cid.startswith("Unit_CG/") and ("Story_CG/" + name) in items:
            continue
        items[cid] = {
            "bundle": "",
            "sprite_pid": None,
            "tex_pid": None,
            "size": 0,
            "cached": False,
        }
    # 最终合并：存在同名 Story_ 条目时剔除 Unit_（同一 CG，Unit_ 仅为兜底 label）
    for key in [k for k in items if k.startswith("Unit_CG/")]:
        if ("Story_CG/" + key.split("/", 1)[-1]) in items:
            del items[key]
    return items


def load_index() -> dict:
    """返回 CG ID 视图（预览/替换查询用）。"""
    cache = _load_cache()
    items = _build_items(cache)
    return {"scanned_at": cache.get("scanned_at", 0), "count": len(items), "items": items}


def _update_bundle_size(bundle_path: str) -> None:
    """替换/还原写回后同步缓存中的 bundle size，避免下次扫描误判为变动。"""
    cache = _load_cache()
    rec = cache.get("bundles", {}).get(bundle_path)
    if rec is None:
        return
    try:
        rec["size"] = Path(bundle_path).stat().st_size
    except OSError:
        return
    _save_cache(cache)


def _cleanup_evicted(bundle_path: str, on_log: Optional[Callable] = None) -> None:
    """清理已从磁盘消失（游戏更新驱逐）的 bundle 上的还原数据。"""
    store = _original_store()
    removed = [cid for cid, rec in store.items() if rec.get("bundle") == bundle_path]
    if not removed:
        return
    for cid in removed:
        raw = Path(store[cid].get("raw", ""))
        raw.unlink(missing_ok=True)
        del store[cid]
    _save_original_store(store)
    if on_log:
        on_log(f"缓存条目已被游戏更新移除，已清理其还原数据：{', '.join(removed)}")


def _catalog_path() -> Path:
    """本地 Addressable catalog：%LOCALAPPDATA%\\..\\LocalLow\\ProjectMoon\\LimbusCompany\\com.unity.addressables\\catalog_S1.json"""
    base = os.environ.get("LOCALAPPDATA", "")
    return (Path(base) / ".." / "LocalLow" / "ProjectMoon" / "LimbusCompany"
            / "com.unity.addressables" / CATALOG_NAME).resolve()


def _catalog_cg_ids() -> set:
    """从 catalog m_KeyDataString 正则提取全部有效 CG ID（Story_CG/Unit_CG，去 .png）。

    二进制布局难以精确解析，字符串为连续 ASCII，正则 [\\x20-\\x7e]{4,} 可完整覆盖（上游验证）。
    文件缺失/损坏时返回空集。
    """
    p = _catalog_path()
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        raw = base64.b64decode(data.get("m_KeyDataString", ""))
    except Exception:
        return set()
    ids = set()
    for m in re.findall(rb"[\x20-\x7e]{4,}", raw):
        s = m.decode()
        if re.match(r"^(Story_CG|Unit_CG)/.+\.png$", s):
            ids.add(s[:-4])
    return ids


# ---------------- 扫描 ----------------

def _glob_data_files(cache_root: Path) -> list:
    """递归收集缓存目录下的 __data 文件（覆盖 1-3 层子目录，与扫描/状态统计共用）。"""
    files = []
    for pat in ("*", "*/*", "*/*/*"):
        files.extend(cache_root.glob(pat + "/__data"))
    return files


def _scan_one(path: str, is_cancelled: Optional[Callable]) -> list:
    """打开单个缓存 bundle，返回其中的加载页 CG 资源描述列表。"""
    if is_cancelled and is_cancelled():
        raise CancelRunning()
    hits = []
    try:
        env = UnityPy.load(path)
    except Exception:
        return hits
    try:
        serialized = _serialized_file(_find_bundle_file(env))
    except Exception:
        return hits
    seen = 0
    for obj in serialized.objects.values():
        seen += 1
        if seen % 50 == 0 and is_cancelled and is_cancelled():
            raise CancelRunning()
        try:
            container = obj.container or ""
        except Exception:
            continue
        cname = str(container).lower()
        # 加载页 CG 资源目录（上游已确认）：Story/CG/ 与 Unit/CG/，前缀决定分类
        if CG_CONTAINER_DIRS[0] in cname:
            prefix = "Story_CG/"
        elif CG_CONTAINER_DIRS[1] in cname:
            prefix = "Unit_CG/"
        else:
            continue
        if obj.type != ClassIDType.Sprite:
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        name = str((tree.get("m_Name") or "").strip())
        if not name:
            continue
        tex_pid = None
        # Unity 6 (6000.x)：贴图引用在 m_RD.texture（m_RenderDataKey 为哈希，无 PPtr）
        rd = tree.get("m_RD")
        if isinstance(rd, dict):
            tex = rd.get("texture")
            if isinstance(tex, dict) and tex.get("m_FileID") == 0:
                tex_pid = tex.get("m_PathID")
        if not tex_pid:
            # 旧版兜底：m_RenderDataKey.texture
            rdk = tree.get("m_RenderDataKey")
            if isinstance(rdk, dict):
                tex = rdk.get("texture")
                if isinstance(tex, dict) and tex.get("m_FileID") == 0:
                    tex_pid = tex.get("m_PathID")
        hits.append({
            "cg_id": prefix + name,
            "sprite_pid": obj.path_id,
            "tex_pid": tex_pid,
            "bundle": path,
            "container": str(container),
        })
    return hits


def scan_cg_ids(
    on_log: Optional[Callable] = None,
    cancel_check: Optional[Callable] = None,
    is_cancelled: Optional[Callable] = None,
    force: bool = False,
) -> dict:
    """增量扫描缓存目录，建立并更新 per-bundle 缓存（v3），返回 CG ID 视图。

    前提：同路径 bundle 内容不可变（游戏更新以新路径下载）。缓存命中（路径存在且
    size 一致）的 bundle 直接跳过，仅扫描新路径 / size 变化路径；force=True 时全量重扫。
    失效条目（磁盘已不存在）自动驱逐并清理其还原数据。
    扫描后并入本地 catalog 中全部有效 CG ID（未缓存的标记 cached=False，可锁定）。

    on_log: 进度日志回调；cancel_check: 每个 bundle 处理前检查（抛 CancelRunning 即中止）；
    is_cancelled: 工作线程内的取消探测（返回 True 时中止）；force: 忽略缓存全量重扫。
    """
    cache_root = get_cache_root()
    files = []
    if cache_root.is_dir():
        files = _glob_data_files(cache_root)
    files = [f for f in files if f.stat().st_size >= MIN_BUNDLE_SIZE]
    files.sort(key=lambda p: p.stat().st_size, reverse=True)

    total = len(files)
    cache = _load_cache()
    known = cache.setdefault("bundles", {})

    if not force:
        # 1) 失效驱逐：缓存中但磁盘已不存在的路径（游戏更新驱逐）
        live = {str(f) for f in files}
        stale = [p for p in known if p not in live]
        for p in stale:
            _cleanup_evicted(p, on_log)
            del known[p]
        if stale and on_log:
            on_log(f"已驱逐 {len(stale)} 个被游戏更新移除的缓存条目")

        # 2) 待扫 = 新路径 ∪ size 变化路径
        to_scan = []
        for f in files:
            rec = known.get(str(f))
            if rec is None or rec.get("size") != f.stat().st_size:
                to_scan.append(f)
        hit = total - len(to_scan)
        if on_log:
            on_log(f"扫描缓存 bundle：共 {total} 个，缓存命中 {hit} 个，需扫描 {len(to_scan)} 个"
                   f"（≥{MIN_BUNDLE_SIZE} 字节，目录 {CG_CONTAINER_DIRS}）")
    else:
        to_scan = list(files)
        if on_log:
            on_log(f"强制全量重扫：共 {total} 个（≥{MIN_BUNDLE_SIZE} 字节，忽略缓存）")

    if on_log:
        on_log(f"扫描线程数：{SCAN_WORKERS}（可中途取消）")

    def worker(path: Path) -> list:
        return _scan_one(str(path), is_cancelled)

    done = 0
    try:
        with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
            futures = [ex.submit(worker, f) for f in to_scan]
            for fut in futures:
                if cancel_check:
                    cancel_check()
                try:
                    hits = fut.result()
                except CancelRunning:
                    raise
                except Exception:
                    hits = []
                done += 1
                # 无论有无命中都缓存该 bundle（空 hits 表示「此 bundle 无 CG」，
                # 基于同路径不可变前提，下次扫描直接跳过）
                p = str(to_scan[done - 1])
                known[p] = {"size": Path(p).stat().st_size, "hits": hits}
                if on_log and done % 200 == 0:
                    on_log(f"已扫描 {done}/{len(to_scan)}")
    except Exception:
        # 取消/异常时先把已完成的扫描结果落盘，下次增量扫描直接跳过这些 bundle
        if known and on_log:
            on_log(f"扫描中止，已保留 {len(known)} 个 bundle 的部分扫描结果")
        _save_cache(cache)
        raise

    cache["scanned_at"] = time.time()
    # 并入 catalog 全部有效 ID（未缓存的可锁定；扫描后刷新，避免 catalog 文件变化后过期）
    catalog_ids = _catalog_cg_ids()
    if catalog_ids:
        cache["catalog"] = sorted(catalog_ids)
    else:
        cache.setdefault("catalog", [])
    _save_cache(cache)

    items = _build_items(cache)
    index = {"scanned_at": cache["scanned_at"], "count": len(items), "items": items}
    cached_count = sum(1 for v in items.values() if v.get("cached"))
    if on_log:
        on_log(f"扫描完成：发现 {index['count']} 个加载页 CG（缓存 {cached_count} 个，"
               f"catalog 未缓存 {index['count'] - cached_count} 个），"
               f"缓存 {len(cache['bundles'])} 个 bundle（{_index_path()}）")
    return index


# ---------------- 预览 ----------------

def _resolve_entry_key(cg_id: str, items: dict) -> str:
    """解析索引键：兼容存档形式（CG/<名>）与键形式（Story_CG/<名>/Unit_CG/<名>）。

    CG/<名> 优先映射 Story_CG/<名>（主 label），仅当不存在时回退 Unit_CG/<名>；
    BG/ 等非 CG/ 形式原样返回。
    """
    if cg_id.startswith("CG/"):
        story = "Story_CG/" + cg_id[3:]
        if story in items:
            return story
        return "Unit_CG/" + cg_id[3:]
    return cg_id


def _get_texture_entry(cg_id: str):
    """按 ID（存档或键形式）解析索引条目。返回 (entry, 解析后的索引键)。"""
    index = load_index()
    items = index.get("items", {})
    key = _resolve_entry_key(cg_id, items)
    entry = items.get(key)
    if not entry:
        raise LookupError(f"索引中未找到 {cg_id}（请先扫描缓存 bundle）")
    if not entry.get("tex_pid"):
        raise LookupError(f"{cg_id} 未在本地缓存中下载（catalog 有效 ID，仅可锁定，无法预览/替换）")
    bundle_path = Path(entry["bundle"])
    if not bundle_path.is_file():
        raise LookupError(f"缓存 bundle 已不存在（游戏可能已更新缓存）：{bundle_path}")
    return entry, key


def _read_texture(entry: dict):
    """打开 bundle 并返回 (serialized, ObjectReader)。"""
    env = UnityPy.load(entry["bundle"])
    serialized = _serialized_file(_find_bundle_file(env))
    obj = serialized.objects.get(entry["tex_pid"])
    if obj is None:
        raise LookupError("bundle 内贴图对象缺失（缓存版本可能已变化，请重新扫描）")
    return env, serialized, obj


def preview_cg(cg_id: str) -> str:
    """导出指定 CG 的 PNG（Base64 data URI），失败抛异常。"""
    cg_id = normalize_cg_id(cg_id)
    entry, _ = _get_texture_entry(cg_id)
    _, _, obj = _read_texture(entry)
    tex = obj.read()
    img = tex.image
    if img is None:
        raise RuntimeError(f"{cg_id} 贴图解码失败（格式不支持预览）")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------- 贴图替换 / 还原（方案 A） ----------------

def _original_store() -> dict:
    p = _originals_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save_original_store(store: dict) -> None:
    _originals_path().write_text(
        json.dumps(store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _write_bundle(env, bundle_path: str) -> None:
    """以原始压缩方式写回 bundle 文件（原子替换）。"""
    bundle = _find_bundle_file(env)
    data = bundle.save(packer="original")
    tmp = bundle_path + ".cgtmp"
    Path(tmp).write_bytes(data)
    os.replace(tmp, bundle_path)


def replace_cg_texture(cg_id: str, image_path: str, on_log: Optional[Callable] = None) -> dict:
    """方案 A：用用户图片替换缓存 bundle 中目标 Texture2D 贴图。

    保持原 format / mipmap / 尺寸（自动缩放），标记 version_player="limbus_modded"；
    原贴图字节保存到 cache_path/cg/originals/ 供还原。
    """
    cg_id = normalize_cg_id(cg_id)
    entry, store_key = _get_texture_entry(cg_id)
    img_path = Path(image_path)
    if not img_path.is_file():
        raise FileNotFoundError(f"图片不存在：{img_path}")

    if on_log:
        on_log(f"替换 {cg_id}（{entry['bundle']}）...")
    env, serialized, obj = _read_texture(entry)
    tex = obj.read()

    original_raw = obj.get_raw_data()
    original_player = _find_bundle_file(env).version_player

    try:
        img = Image.open(img_path).convert("RGBA")
    except Exception as e:
        raise ValueError(f"无法读取图片：{e}")

    w, h = tex.m_Width, tex.m_Height
    if img.size != (w, h):
        if on_log:
            on_log(f"图片尺寸 {img.size} 与目标 {w}x{h} 不一致，自动缩放")
        img = img.resize((w, h), Image.LANCZOS)

    fmt = tex.m_TextureFormat
    mips = tex.m_MipCount
    try:
        tex.set_image(img, target_format=fmt, mipmap_count=mips)
    except NotImplementedError:
        raise RuntimeError(
            f"该 CG 贴图为 {fmt.name} 压缩格式，当前编码器不支持重编码，仅可锁定不可替换")
    except Exception as e:
        raise RuntimeError(f"贴图重编码失败（格式 {fmt.name}）：{e}")

    tex.save()

    bundle = _find_bundle_file(env)
    bundle.version_player = "limbus_modded"
    _write_bundle(env, entry["bundle"])
    if on_log:
        on_log(f"bundle 写回完成（标记 limbus_modded），原图数据已留存供还原")

    # 保存原贴图字节与索引状态
    key = _bundle_key(entry["bundle"])
    originals_dir = _cg_data_dir() / "originals"
    originals_dir.mkdir(parents=True, exist_ok=True)
    raw_file = originals_dir / f"{key}_{entry['tex_pid']}.bin"
    raw_file.write_bytes(original_raw)

    store = _original_store()
    # originals store 以解析后的索引键（键形式）为规范键，保证 restore/状态一致
    store[store_key] = {
        "raw": str(raw_file),
        "bundle": entry["bundle"],
        "tex_pid": entry["tex_pid"],
        "version_player": original_player or "",
    }
    _save_original_store(store)

    # 写回改变了 bundle 文件大小：同步缓存 size，避免下次扫描误判为变动
    _update_bundle_size(entry["bundle"])
    return {"success": True, "key": store_key,
            "message": f"{cg_id} 贴图替换完成（游戏更新缓存后需重新替换）"}


def restore_cg_texture(cg_id: str, on_log: Optional[Callable] = None) -> dict:
    """从留存的原贴图字节还原 bundle（还原后清除标记）。

    用宽松 key + 键形式解析查找 originals store，兼容存档形式/键形式与历史 BG/ 键。
    """
    cg_id = lenient_cg_id(cg_id)
    store = _original_store()
    store_key = _resolve_entry_key(cg_id, store)
    rec = store.get(store_key)
    if not rec:
        raise LookupError(f"{cg_id} 没有可还原的原始贴图数据")

    raw_file = Path(rec["raw"])
    if not raw_file.is_file():
        raise LookupError(f"原始贴图数据缺失：{raw_file}")
    bundle_path = rec.get("bundle", "")
    if not Path(bundle_path).is_file():
        raise LookupError(f"缓存 bundle 已不存在：{bundle_path}")

    if on_log:
        on_log(f"还原 {cg_id} 原始贴图...")
    env = UnityPy.load(bundle_path)
    serialized = _serialized_file(_find_bundle_file(env))
    obj = serialized.objects.get(rec["tex_pid"])
    if obj is None:
        raise LookupError("bundle 内贴图对象缺失（缓存版本可能已变化）")
    obj.set_raw_data(raw_file.read_bytes())
    bundle = _find_bundle_file(env)
    bundle.version_player = rec.get("version_player") or bundle.version_player
    _write_bundle(env, bundle_path)
    if on_log:
        on_log("bundle 已还原")

    raw_file.unlink(missing_ok=True)
    del store[store_key]
    _save_original_store(store)

    _update_bundle_size(bundle_path)
    return {"success": True, "key": store_key, "message": f"{cg_id} 已还原为原始贴图"}


# ---------------- 状态 ----------------

def cg_bundle_status() -> dict:
    """返回索引/还原数据状态（供页面初始化展示）。"""
    cache = _load_cache()
    store = _original_store()
    modded = [cid for cid, rec in store.items() if Path(rec.get("raw", "")).is_file()]
    cache_root = get_cache_root()
    cache_count = 0
    if cache_root.is_dir():
        try:
            cache_count = len(_glob_data_files(cache_root))
        except OSError:
            pass
    items = _build_items(cache)
    return {
        "cache_root": str(cache_root),
        "cache_count": cache_count,
        "cached_bundles": len(cache.get("bundles", {})),
        "index_count": len(items) if cache.get("scanned_at") else 0,
        "index_time": cache.get("scanned_at", 0),
        "modded": modded,
    }
