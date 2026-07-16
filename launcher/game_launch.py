"""游戏启动流程：mod 加载模式与普通模式（从 launcher/main.py 拆分而来）"""
import atexit
import os
import signal
import subprocess
import sys
import tempfile

import UnityPy.config
UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"

from globalManagers.LogManager import LogManager
from launcher.speed_hotkey import run_speed_hotkey_if_enabled

_log_manager = LogManager()

def main_after_mod(steam_argv: str) -> None:
    from launcher.modfolder import get_mod_folder
    import launcher.patch as patch
    import launcher.sound as sound
    import launcher.changes as changes

    get_mod_folder()
    mod_zips_root_path = os.environ['mod_path']
    os.makedirs(mod_zips_root_path, exist_ok=True)

    _log_manager.log("Limbus Mod Loader version: v1.8")

    def kill_handler(*args) -> None:
        sys.exit(0)

    def cleanup_assets():
        try:
            _log_manager.log("Cleaning up assets")
            patch.cleanup_assets()
            sound.restore_sound()
            changes.cleanup_patch(steam_argv)
        except Exception as e:
            _log_manager.log_error(e)

    try:
        _log_manager.log("Limbus args: %s", sys.argv)
        cleanup_assets()
        atexit.register(cleanup_assets)
        signal.signal(signal.SIGINT, kill_handler)
        signal.signal(signal.SIGTERM, kill_handler)
        _log_manager.log("Detecting lunartique mods")
        patch.detect_lunartique_mods(mod_zips_root_path)
        _log_manager.log("Patching text data")
        changes.apply_patch(mod_zips_root_path, steam_argv)
        tmp_asset_root = tempfile.mkdtemp()
        _log_manager.log("Extracting mod assets to %s", tmp_asset_root)
        patch.extract_assets(tmp_asset_root, mod_zips_root_path)
        _log_manager.log("Backing up data and patching assets....")
        patch.patch_assets(tmp_asset_root)
        patch.shutil.rmtree(tmp_asset_root)
        sound.replace_sound(mod_zips_root_path,steam_argv)
        _log_manager.log("Starting game")

        # 游戏加速热键
        speed_exit = run_speed_hotkey_if_enabled()

        subprocess.call(steam_argv)

        # 清理加速热键
        if speed_exit is not None:
            speed_exit.set()

        cleanup_assets()

    except Exception as e:
        _log_manager.log_error(e)
        sys.exit(1)

def main_after_game(steam_argv: str) -> None:

    # 游戏加速热键
    speed_exit = run_speed_hotkey_if_enabled()

    subprocess.call(steam_argv)

    # 清理加速热键
    if speed_exit is not None:
        speed_exit.set()
