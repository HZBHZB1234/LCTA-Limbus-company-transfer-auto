import datetime
import glob
import hashlib
import io
import json
import xxhash
import lzma
import os.path
import shutil
from threading import Lock
from globalManagers.LogManager import LogManager
_log_manager = LogManager()
from pathlib import Path
from zipfile import ZipFile

_cleanup_lock = Lock()

from UnityPy.enums import ClassIDType
from UnityPy.files import SerializedFile, BundleFile, ObjectReader

from launcher.compress import compress_lunartique_mod

import UnityPy


def get_bundle_file(env: UnityPy.Environment) -> BundleFile:
    bundle = getattr(env, "file", None)
    if isinstance(bundle, BundleFile):
        return bundle
    for f in env.files.values():
        if isinstance(f, BundleFile):
            return f
    raise ValueError("No BundleFile found in environment")


def bundle_data_paths(appdata: str = os.getenv("APPDATA")):
    cache_path = os.path.join(appdata, "../LocalLow/Unity/ProjectMoon_LimbusCompany/*/*/")
    return map(os.path.normpath, glob.glob(cache_path))


def file_digest(file_path):
    with open(file_path, "rb") as ff:
        xxdigest = xxhash.xxh128()
        while chunk := ff.read(8192):
            xxdigest.update(chunk)

        return xxdigest.hexdigest()


def detect_lunartique_mods(mod_zips_root: str) -> None:
    """zip→carra2 转换（带内容缓存，转换后删除源 zip）。

    缓存键 = 源 zip 的 sha256：同包重复安装直接命中，跳过耗时的转换。
    转换产物复制回模组目录（<zip 名>.carra2）并删除源 zip，保持旧版数据布局
    （carra2 常驻模组目录，供 extract_assets 按目录扫描）。
    """
    from launcher.modcache import (carra2_convert_dir, enabled_mod_files,
                                   prune_lru, sha256_file)

    for mod_zip in enabled_mod_files(mod_zips_root, "*.zip"):
        _log_manager.log("Compressing lunartique format mod (might take a while!): %s", mod_zip)
        try:
            digest = sha256_file(mod_zip)
            cached = carra2_convert_dir() / (digest + ".carra2")
            if cached.is_file():
                _log_manager.log("* 转换缓存命中（跳过转换）: %s", mod_zip.name)
            else:
                tmp = carra2_convert_dir() / (digest + ".carra2.tmp")
                if tmp.exists():
                    tmp.unlink()
                compress_lunartique_mod(str(mod_zip), str(tmp))
                os.replace(tmp, cached)
                _log_manager.log("* Done")
            dest = mod_zip.with_suffix(".carra2")
            cached_hash = sha256_file(str(cached))
            if not dest.is_file() or sha256_file(str(dest)) != cached_hash:
                shutil.copyfile(cached, dest)
            os.remove(mod_zip)
        except Exception as e:
            _log_manager.log("* Error: %s", e)
    prune_lru(carra2_convert_dir(), 30)


def mod_file_size(file):
    try:
        return os.path.getsize(file)
    except:
        return 1 << 64


def extract_assets(mod_asset_root: str, mod_zips_root: str):
    """解压 carra2 并展平到 mod_asset_root（带内容缓存）。

    按 mod_zips_root 下启用的 *.carra* 收集（detect_lunartique_mods 转换后
    carra2 常驻模组目录）。
    展平语义与现网一致：3 层条目 <account>/<bundle>/<path_id>.<type_id>
    上移一级丢弃 bundle 段（逐包执行，合并顺序与原先按体积降序一致）。
    """
    from launcher.modcache import (carra2_extract_dir, enabled_mod_files,
                                   prune_lru, sha256_file)

    carra_files = [str(p) for p in enabled_mod_files(mod_zips_root, "*.carra*")]
    for mod_zip in sorted(carra_files, key=mod_file_size, reverse=True):
        mod_zip = os.path.normpath(mod_zip)
        try:
            digest = sha256_file(mod_zip)
            cache_dir = carra2_extract_dir() / digest
            if cache_dir.is_dir():
                _log_manager.log("* 解压缓存命中: %s", mod_zip)
            else:
                tmp = carra2_extract_dir() / ("extract-" + digest + ".tmp")
                if tmp.exists():
                    shutil.rmtree(tmp)
                tmp.mkdir(parents=True)
                with ZipFile(mod_zip) as z:
                    _log_manager.log("Extracting %s", mod_zip)
                    z.extractall(tmp)
                for mod_carra in glob.glob(f"{tmp}/*/*/*"):
                    mod_carra_path = Path(mod_carra)
                    new_mod_carra = os.path.join(mod_carra_path.parent.parent, mod_carra_path.name)
                    os.replace(mod_carra, new_mod_carra)
                os.replace(tmp, cache_dir)
            for src in cache_dir.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(cache_dir)
                    dst = os.path.join(mod_asset_root, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(src, dst)
        except Exception as e:
            _log_manager.log("Error processing %s: %s", mod_zip, e)
    prune_lru(carra2_extract_dir(), 30)


def cleanup_assets(bundle_data=bundle_data_paths):
    with _cleanup_lock:
        _log_manager.log("Restoring data")
        for bundle_root in bundle_data():
            bundle_path = os.path.join(bundle_root, "__data")
            new_path = os.path.join(bundle_root, "__original")
            if not os.path.isfile(new_path):
                continue

            try:
                with open(bundle_path, "rb") as fp:
                    env = UnityPy.load(io.BytesIO(fp.read()))
                bundle = get_bundle_file(env)
                if bundle.version_player != "limbus_modded":
                    os.remove(new_path)
                    continue
            except Exception as e:
                _log_manager.log("Corrupted file detected %s: %s", bundle_path, e)

            _log_manager.log("Restoring %s", bundle_path)
            os.replace(new_path, bundle_path)


def patch_bundle_asset(env: UnityPy.Environment, mod_path: str):
    bundle = get_bundle_file(env)
    for f in bundle.files.values():
        if not isinstance(f, SerializedFile):
            _log_manager.log("Expected serialized file but got a %s instead?? Skipped", type(f))
            return

        objects = f.objects
        for modded_asset in os.listdir(mod_path):
            try:
                name = modded_asset.split(".")
                path_id = int(name[0])
                type_id = -1
                if len(name) > 1:
                    type_id = int(name[1])
            except ValueError:
                continue

            mod_part_path = os.path.join(mod_path, modded_asset)
            if not os.path.isfile(mod_part_path):
                continue
            if obj := objects.get(path_id):
                if not isinstance(obj, ObjectReader):
                    _log_manager.log_error("- Object is not ObjectReader, wtf?")
                    continue
                _log_manager.log("- Loading %s", mod_part_path)
                if type_id >= 0 and type_id != obj.type_id:
                    _log_manager.log("- Mismatching asset type, vanilla: %d, modded: %d, skipped", obj.type_id, type_id)
                    continue
                with open(mod_part_path, "rb") as mf:
                    obj.set_raw_data(lzma.decompress(mf.read(), format=lzma.FORMAT_XZ))
            elif type_id >= 0:
                if type_id >= len(f.types):
                    _log_manager.log("- Unknown type index %d for %s, skipped", type_id, mod_part_path)
                    continue
                serialized_type = f.types[type_id]
                _log_manager.log("- Adding unused mod asset of type %d: %s", type_id, mod_part_path)
                with open(mod_part_path, "rb") as mf:
                    data = lzma.decompress(mf.read(), format=lzma.FORMAT_XZ)
                obj = ObjectReader(
                    assets_file=f,
                    reader=f.reader,
                    path_id=path_id,
                    type_id=type_id,
                    serialized_type=serialized_type,
                    class_id=serialized_type.class_id,
                    type=ClassIDType(serialized_type.class_id),
                    byte_start=0,
                    byte_size=len(data),
                    is_destroyed=None,
                    is_stripped=None,
                )
                obj.set_raw_data(data)
                objects[path_id] = obj


def _save_bundle(bundle: BundleFile) -> tuple:
    """以游戏标准格式（UnityFS LZ4）重打包；异常时回退 original 标志。

    返回 (bytes, packer)，packer 供缓存 meta 记录实际产物格式。
    """
    try:
        return bundle.save(packer="lz4"), "lz4"
    except Exception as e:
        _log_manager.log_error("LZ4 重打包失败（%s），回退 original 标志", e)
        return bundle.save(packer="original"), "original"


def patch_assets(mod_asset_root: str, bundle_data=bundle_data_paths):
    from launcher.modcache import (atomic_write, bundle_patch_dir, prune_lru,
                                   tree_digest)

    for bundle_root in bundle_data():
        # Move the original data to a new location temporarily
        bundle_root_path = Path(bundle_root)
        mod_path = os.path.join(mod_asset_root, bundle_root_path.parent.name)
        if not os.path.isdir(mod_path):
            continue

        bundle_path = os.path.join(bundle_root, "__data")
        new_path = os.path.join(bundle_root, "__original")
        os.chmod(bundle_path, 0o777)
        _log_manager.log("Backing up %s", bundle_path)
        os.replace(bundle_path, new_path)

        try:
            orig_hash = file_digest(new_path)
            mod_hash = tree_digest(mod_path)
            digest = hashlib.sha256(f"{orig_hash}|{mod_hash}|lz4".encode("utf-8")).hexdigest()
            cache_root_dir = bundle_patch_dir() / digest
            cache_file = cache_root_dir / "__data"
            if cache_file.is_file():
                _log_manager.log("* 重打包缓存命中 %s", digest)
                shutil.copyfile(cache_file, bundle_path)
                continue
            _log_manager.log("Patching %s", bundle_path)
            env = UnityPy.load(new_path)
            patch_bundle_asset(env, mod_path)

            bundle = get_bundle_file(env)
            bundle.version_player = "limbus_modded"
            data, packer = _save_bundle(bundle)
            atomic_write(bundle_path, data)
            meta = {"orig_hash": orig_hash, "mod_hash": mod_hash,
                    "packer": packer, "size": len(data),
                    "created": datetime.datetime.now().isoformat(timespec="seconds")}
            atomic_write(cache_root_dir / "meta.json",
                         json.dumps(meta).encode("utf-8"))
            atomic_write(cache_file, data)
            _log_manager.log("* Patching complete %s (%d) -> %s (%d)", file_digest(new_path), os.path.getsize(new_path),
                         file_digest(bundle_path), os.path.getsize(bundle_path))
        except Exception:
            _log_manager.log_error("Failed to patch %s", bundle_path)
            if os.path.isfile(new_path):
                if os.path.isfile(bundle_path):
                    os.remove(bundle_path)
                os.replace(new_path, bundle_path)
            raise
    prune_lru(bundle_patch_dir(), 30)
