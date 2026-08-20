import jsonpatch
from globalManagers.LogManager import LogManager
_log_manager = LogManager()
from pathlib import Path
import json
import shutil
import os

def extract_exe_path(cmdline: str) -> str:
    """从 Windows 命令行中提取可执行文件路径。

    兼容引号包裹的空格路径（Steam 传入）与无引号路径（config 回退）。
    不做 POSIX 语义的 shlex 解析，避免反斜杠被当作转义符吞掉。
    """
    cmdline = cmdline.strip()
    if not cmdline:
        return ""
    if cmdline.startswith('"'):
        end = cmdline.find('"', 1)
        if end != -1:
            return cmdline[1:end]
    return cmdline.split(maxsplit=1)[0]

def apply_patch(mod_path, _path):
    from launcher.modcache import enabled_mod_files

    game_path = extract_exe_path(_path)
    lang_path = Path(game_path).parent / "LimbusCompany_Data/lang"
    for lang_patch in enabled_mod_files(mod_path, "*.json"):
        try:
            with open(lang_patch, "r") as f:
                patch_data = json.load(f)
        except (OSError, ValueError) as e:
            _log_manager.log("跳过无效 json 补丁 %s: %s", lang_patch, e)
            continue
        # Apply the patch to the corresponding language file
        for _lang_file in patch_data.get('patchs', {}):
            lang_file = lang_path / _lang_file
            _log_manager.log("Patching %s", lang_file)
            if not lang_file.exists():
                continue
            if not lang_file.with_suffix(".bak").exists():
                shutil.copyfile(lang_file, lang_file.with_suffix(".bak"))
            try:
                with open(lang_file, "r") as f:
                    lang_data = json.load(f)
                patched_data = jsonpatch.apply_patch(lang_data, patch_data['patchs'][_lang_file])
            except Exception as e:
                _log_manager.log("应用补丁失败 %s: %s", _lang_file, e)
                continue
            with open(lang_file, "w") as f:
                json.dump(patched_data, f)

def cleanup_patch(_path):
    game_path = extract_exe_path(_path)
    lang_path = Path(game_path).parent / "LimbusCompany_Data/lang"
    for lang_file in lang_path.rglob("*.bak"):
        original_file = lang_file.with_suffix('.json')
        if original_file.exists():
            os.replace(lang_file, original_file)