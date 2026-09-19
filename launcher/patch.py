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


def detect_lunartique_mods(mod_zips_root: str, threads: int = 1,
                           progress_cb=None) -> None:
    """zip→carra2 转换（带内容缓存，转换后删除源 zip，多线程）。

    缓存键 = 源 zip 的 sha256：同包重复安装直接命中，跳过耗时的转换。
    转换产物复制回模组目录（<zip 名>.carra2）并删除源 zip，保持旧版数据布局
    （carra2 常驻模组目录，供 extract_assets 按目录扫描）。

    非 Lunartique 格式的 zip（无 Uninstallation/Installation 结构）不再当作
    carra2 转换，而是把包内全部文件解压到模组目录根，由后续
    changes/extract_assets/sound 各阶段按类型自动加载；解压成功即删除源 zip，
    避免每次启动重复解压。

    threads > 1 且包数 > 1 时各 zip 在线程池中独立处理（互不相交的输出
    文件）；两个不同 zip 解压出同一路径的覆盖结果不再保证「排序靠后者胜出」，
    与旧串行语义仅在这种极端场景下存在差异。单包异常照旧记录后继续其余包。
    progress_cb(done, total) 在每处理完一个包后回调。
    """
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    from launcher.modcache import (carra2_convert_dir, enabled_mod_files,
                                   prune_lru, sha256_file)
    from launcher.compress import is_lunartique_zip
    import launcher.modstatus as modstatus

    zips = enabled_mod_files(mod_zips_root, "*.zip")
    convert_dir = carra2_convert_dir()
    total = len(zips)
    counter = [0]
    cb_lock = Lock()

    def _report_done():
        if progress_cb is None or total == 0:
            return
        with cb_lock:
            counter[0] += 1
            done = counter[0]
        try:
            progress_cb(min(done, total), total)
        except Exception:
            pass

    def _process(mod_zip) -> None:
        key = str(mod_zip)
        name = mod_zip.name
        modstatus.begin(key, name, "格式检测", "检测模组格式…")
        _log_manager.log("Detecting mod format: %s", mod_zip)
        try:
            if not is_lunartique_zip(str(mod_zip)):
                modstatus.update(key, stage="解压安装",
                                 description="非 Lunartique 格式，解压到模组目录")
                _log_manager.log("* 非 Lunartique 格式，解压到模组目录: %s", mod_zip)
                with ZipFile(mod_zip) as z:
                    z.extractall(mod_zips_root)
                os.remove(mod_zip)
                return
            _log_manager.log("Compressing lunartique format mod (might take a while!): %s", mod_zip)
            digest = sha256_file(mod_zip)
            cached = convert_dir / (digest + ".carra2")
            if cached.is_file():
                modstatus.update(key, stage="carra2 转换", description="转换缓存命中")
                _log_manager.log("* 转换缓存命中（跳过转换）: %s", name)
            else:
                modstatus.update(key, stage="carra2 转换", description="zip → carra2 转换中")
                tmp = convert_dir / (digest + ".carra2.tmp")
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
        finally:
            modstatus.finish(key)
            _report_done()

    if threads > 1 and total > 1:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = [pool.submit(_process, mod_zip) for mod_zip in zips]
            for future in futures:
                future.result()
    else:
        for mod_zip in zips:
            _process(mod_zip)
    prune_lru(convert_dir, 30)


def mod_file_size(file):
    try:
        return os.path.getsize(file)
    except:
        return 1 << 64


def extract_assets(mod_asset_root: str, mod_zips_root: str, threads: int = 1,
                   progress_cb=None):
    """解压 carra2 并展平到 mod_asset_root（带内容缓存，多线程）。

    按 mod_zips_root 下启用的 *.carra* 收集（detect_lunartique_mods 转换后
    carra2 常驻模组目录）。
    展平语义与现网一致：3 层条目 <account>/<bundle>/<path_id>.<type_id>
    上移一级丢弃 bundle 段。多线程只作用于「缓存未命中的解压+展平」
    （各包独立写入各自缓存目录）；拷贝到 mod_asset_root 仍按体积降序
    串行执行，保证同名目标路径的合并顺序与旧版一致。
    progress_cb(done, total) 在每包拷贝完成后回调。
    """
    from concurrent.futures import ThreadPoolExecutor

    from launcher.modcache import (carra2_extract_dir, enabled_mod_files,
                                   prune_lru, sha256_file)
    import launcher.modstatus as modstatus

    carra_files = [str(p) for p in enabled_mod_files(mod_zips_root, "*.carra*")]
    ordered = [os.path.normpath(p)
               for p in sorted(carra_files, key=mod_file_size, reverse=True)]
    extract_root = carra2_extract_dir()
    total = len(ordered)

    def _ensure_cache(mod_zip: str):
        """确保该包的解压缓存目录就绪；失败返回 None（跳过拷贝）。"""
        key = mod_zip
        name = os.path.basename(mod_zip)
        modstatus.begin(key, name, "解压展平", "计算内容摘要…")
        try:
            digest = sha256_file(mod_zip)
            cache_dir = extract_root / digest
            if cache_dir.is_dir():
                modstatus.update(key, description="解压缓存命中")
                _log_manager.log("* 解压缓存命中: %s", mod_zip)
                return cache_dir
            modstatus.update(key, description="解压 carra2 包…")
            tmp = extract_root / ("extract-" + digest + ".tmp")
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
            return cache_dir
        except Exception as e:
            _log_manager.log("Error processing %s: %s", mod_zip, e)
            return None
        finally:
            modstatus.finish(key)

    if threads > 1 and total > 1:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            cache_dirs = list(pool.map(_ensure_cache, ordered))
    else:
        cache_dirs = [_ensure_cache(mod_zip) for mod_zip in ordered]

    for done, (mod_zip, cache_dir) in enumerate(zip(ordered, cache_dirs), 1):
        if cache_dir is not None:
            try:
                for src in cache_dir.rglob("*"):
                    if src.is_file():
                        rel = src.relative_to(cache_dir)
                        dst = os.path.join(mod_asset_root, rel)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copyfile(src, dst)
            except Exception as e:
                # 与旧串行行为一致：单包拷贝失败仅记录，不中断其余包
                _log_manager.log("Error processing %s: %s", mod_zip, e)
        if progress_cb is not None and total:
            try:
                progress_cb(done, total)
            except Exception:
                pass
    prune_lru(extract_root, 30)


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


def make_mod_object_reader(assets_file: SerializedFile, path_id: int, type_id: int,
                           serialized_type, data: bytes) -> ObjectReader:
    """构造一个只存在于模组中（原版 bundle 没有）的 ObjectReader，不读流。

    UnityPy 1.10.x 的 `ObjectReader.__init__` 只接受 (assets_file, reader)，
    并没有新版的关键字构造签名；直接传 path_id/type_id/... 会抛
    `TypeError: __init__() got an unexpected keyword argument 'path_id'`，
    使所有「模组新增资产」的 bundle 打补丁失败（表现为 mod 装了但内容不生效）。

    这里统一走「跳过 __init__ + 逐字段赋值」，不依赖具体 UnityPy 版本的构造
    签名；字段集合取自 1.10.18 `ObjectReader` 读流时写入的属性，且 `write()`
    （序列化回 bundle 的唯一入口）在 `data` 非空时只用到 path_id / type_id /
    class_id / serialized_type / data / byte_size，因此足够。
    """
    obj = ObjectReader.__new__(ObjectReader)
    obj.assets_file = assets_file
    obj.reader = assets_file.reader
    obj.path_id = path_id
    obj.type_id = type_id
    obj.serialized_type = serialized_type
    obj.class_id = serialized_type.class_id
    obj.type = ClassIDType(serialized_type.class_id)
    obj.byte_start = 0
    obj.byte_size = len(data)
    obj.is_destroyed = None
    obj.is_stripped = None
    obj.stripped = False
    obj._read_until = 0
    obj.data = b""
    obj.set_raw_data(data)
    return obj


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
                obj = make_mod_object_reader(
                    f, path_id, type_id, serialized_type, data)
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


def patch_assets(mod_asset_root: str, threads: int = 1, progress_cb=None,
                 bundle_data=bundle_data_paths):
    """备份并补丁全部有模组资源的 bundle（多线程，带重打包缓存）。

    每个 bundle_root 相互独立（备份 os.replace / UnityPy env / 写回文件
    互不相交），threads > 1 且任务数 > 1 时按 bundle 并行；单 bundle 失败
    照旧回滚该 bundle 后记录，全部任务结束后重抛第一个异常（与旧串行
    「失败即中断」等价的对外行为）。prune_lru 收尾串行执行。
    progress_cb(done, total) 在每处理完一个 bundle 后回调。
    """
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    from launcher.modcache import (atomic_write, bundle_patch_dir, prune_lru,
                                   tree_digest)
    import launcher.modstatus as modstatus

    tasks = []
    for bundle_root in bundle_data():
        mod_path = os.path.join(mod_asset_root, Path(bundle_root).parent.name)
        if not os.path.isdir(mod_path):
            continue
        tasks.append((bundle_root, mod_path))

    total = len(tasks)
    counter = [0]
    cb_lock = Lock()
    errors = []

    def _report_done():
        if progress_cb is None or total == 0:
            return
        with cb_lock:
            counter[0] += 1
            done = counter[0]
        try:
            progress_cb(min(done, total), total)
        except Exception:
            pass

    def _patch_one(bundle_root, mod_path) -> None:
        key = str(bundle_root)
        name = Path(bundle_root).parent.name
        bundle_path = os.path.join(bundle_root, "__data")
        new_path = os.path.join(bundle_root, "__original")
        modstatus.begin(key, name, "备份", "备份原版 bundle…")
        # Move the original data to a new location temporarily
        try:
            os.chmod(bundle_path, 0o777)
            _log_manager.log("Backing up %s", bundle_path)
            os.replace(bundle_path, new_path)

            modstatus.update(key, stage="补丁", description="加载并补丁资源…")
            orig_hash = file_digest(new_path)
            mod_hash = tree_digest(mod_path)
            digest = hashlib.sha256(f"{orig_hash}|{mod_hash}|lz4".encode("utf-8")).hexdigest()
            cache_root_dir = bundle_patch_dir() / digest
            cache_file = cache_root_dir / "__data"
            if cache_file.is_file():
                modstatus.update(key, stage="重打包", description="重打包缓存命中")
                _log_manager.log("* 重打包缓存命中 %s", digest)
                shutil.copyfile(cache_file, bundle_path)
                return
            _log_manager.log("Patching %s", bundle_path)
            env = UnityPy.load(new_path)
            patch_bundle_asset(env, mod_path)

            modstatus.update(key, stage="重打包", description="UnityFS LZ4 重打包中…")
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
        except Exception as e:
            _log_manager.log_error("Failed to patch %s", bundle_path)
            if os.path.isfile(new_path):
                if os.path.isfile(bundle_path):
                    os.remove(bundle_path)
                os.replace(new_path, bundle_path)
            errors.append(e)
        finally:
            modstatus.finish(key)
            _report_done()

    if threads > 1 and total > 1:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = [pool.submit(_patch_one, bundle_root, mod_path)
                       for bundle_root, mod_path in tasks]
            for future in futures:
                future.result()
    else:
        for bundle_root, mod_path in tasks:
            _patch_one(bundle_root, mod_path)
    prune_lru(bundle_patch_dir(), 30)
    if errors:
        raise errors[0]
