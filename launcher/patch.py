import glob
import io
import xxhash
import lzma
import os.path
import shutil
from globalManagers.LogManager import LogManager
_log_manager = LogManager()
from pathlib import Path
from zipfile import ZipFile

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


def detect_lunartique_mods(mod_zips_root: str):
    for mod_zip in Path(mod_zips_root).rglob("*.zip"):
        _log_manager.log("Compressing lunartique format mod (might take a while!): %s", mod_zip)
        try:
            compress_lunartique_mod(mod_zip, mod_zip.with_suffix(".carra2"))
            os.remove(mod_zip)
            _log_manager.log("* Done")
        except Exception as e:
            _log_manager.log("* Error: %s", e)


def mod_file_size(file):
    try:
        return os.path.getsize(file)
    except:
        return 1 << 64


def extract_assets(mod_asset_root: str, mod_zips_root: str):
    for mod_zip in sorted(Path(mod_zips_root).rglob("*.carra*"), key=mod_file_size, reverse=True):
        mod_zip = os.path.normpath(mod_zip)
        try:
            with ZipFile(mod_zip) as z:
                _log_manager.log("Extracting %s", mod_zip)
                z.extractall(mod_asset_root)
        except Exception as e:
            _log_manager.log("Error processing %s: %s", mod_zip, e)

    for mod_carra in glob.glob(f"{mod_asset_root}/*/*/*"):
        mod_carra_path = Path(mod_carra)
        new_mod_carra = os.path.join(mod_carra_path.parent.parent, mod_carra_path.name)
        os.replace(mod_carra, new_mod_carra)


def cleanup_assets(bundle_data=bundle_data_paths):
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
                if type_id > 0 and type_id != obj.type_id:
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


def patch_assets(mod_asset_root: str, bundle_data=bundle_data_paths):
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
            _log_manager.log("Patching %s", bundle_path)
            env = UnityPy.load(new_path)
            patch_bundle_asset(env, mod_path)

            bundle = get_bundle_file(env)
            bundle.version_player = "limbus_modded"
            with open(bundle_path, "wb") as out:
                out.write(bundle.save(packer="original"))
            _log_manager.log("* Patching complete %s (%d) -> %s (%d)", file_digest(new_path), os.path.getsize(new_path),
                         file_digest(bundle_path), os.path.getsize(bundle_path))
        except Exception:
            _log_manager.log_error("Failed to patch %s", bundle_path)
            if os.path.isfile(new_path):
                if os.path.isfile(bundle_path):
                    os.remove(bundle_path)
                os.replace(new_path, bundle_path)
            raise
