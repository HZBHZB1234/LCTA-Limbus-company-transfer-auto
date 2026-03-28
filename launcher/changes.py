import jsonpatch
import shlex
import logging
from pathlib import Path
import json
import shutil
import os

logging.basicConfig(level=logging.INFO)

def apply_patch(mod_path, _path):
    game_path = shlex.split(_path)[0]
    lang_path = Path(game_path).parent / "LimbusCompany_Data/lang"
    for lang_patch in Path(mod_path).rglob("*.json"):
        with open(lang_patch, "r") as f:
            patch_data = json.load(f)
        # Apply the patch to the corresponding language file
        for _lang_file in patch_data.get('patchs', {}):
            lang_file = lang_path / _lang_file
            logging.info("Patching %s", lang_file)
            shutil.copyfile(lang_file, lang_file.with_suffix(".bak"))
            if lang_file.exists():
                with open(lang_file, "r") as f:
                    lang_data = json.load(f)
                patched_data = jsonpatch.apply_patch(lang_data, patch_data['patchs'][_lang_file])
                with open(lang_file, "w") as f:
                    json.dump(patched_data, f)

def cleanup_patch(_path):
    game_path = shlex.split(_path)[0]
    lang_path = Path(game_path).parent / "LimbusCompany_Data/lang"
    for lang_file in lang_path.rglob("*.bak"):
        original_file = lang_file.with_suffix('.json')
        if original_file.exists():
            os.replace(lang_file, original_file)