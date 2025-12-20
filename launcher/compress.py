import logging
import lzma
from zipfile import ZipFile

import UnityPy
from xxhash import xxh128


def scan_lunartique_mod_root(zip_file: ZipFile) -> str:
    names = set()
    for name in zip_file.namelist():
        name_parts = name.split("/")
        while name_parts:
            name_part = "/".join(name_parts)
            names.add(name_part)
            name_parts.pop()

    for root in names:
        if f"{root}/Uninstallation" in names and f"{root}/Installation" in names:
            return root

    raise Exception("Root folder for installation folder and uninstallation folder not found")


def scan_lunartique_data(zip_path: ZipFile, data_folder: str):
    root = scan_lunartique_mod_root(zip_path)
    names = set()
    for name in zip_path.namelist():
        if name.startswith(f"{root}/{data_folder}/") and name.endswith("/__data"):
            names.add(name)
    return names


def compress_lunartique_mod(zip_path: str, output: str):
    with ZipFile(zip_path, "r") as root:
        vanilla_dict = {}
        vanilla_paths = scan_lunartique_data(root, "Uninstallation")
        if len(vanilla_paths) == 0:
            raise Exception("No asset files found")

        for vanilla_path in vanilla_paths:
            parts = vanilla_path.split("/")[-3:]
            with root.open(vanilla_path, "r") as f:
                env = UnityPy.load(f)

                for obj in env.objects:
                    data = obj.get_raw_data()
                    parts[2] = str(obj.path_id)
                    vanilla_dict["/".join(parts)] = xxh128(data).digest()

        with ZipFile(output, "w") as z:
            for modded_path in map(lambda s: s.replace("Uninstallation", "Installation"), vanilla_paths):
                parts = modded_path.split("/")[-3:]
                with root.open(modded_path, "r") as f:
                    env = UnityPy.load(f)

                    for obj in env.objects:
                        data = obj.get_raw_data()
                        parts[2] = str(obj.path_id)
                        key = "/".join(parts)
                        if vanilla_dict.get(key) == xxh128(data).digest():
                            continue
                        if key not in vanilla_dict:
                            logging.info("* New object found: %s","/".join(parts))
                        key += f".{obj.type_id}"
                        with z.open(key, "w") as z_f:
                            logging.info("* Writing %s", key)
                            z_f.write(lzma.compress(data, preset=9, format=lzma.FORMAT_XZ))
