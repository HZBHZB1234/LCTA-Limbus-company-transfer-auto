import atexit
import os
import signal
import sys
import tempfile

import UnityPy.config
UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"

from globalManagers.LogManager import LogManager

_log_manager = LogManager()

_mod_initialized = False
_steam_argv = None


def _do_cleanup_assets():
    try:
        _log_manager.log("Cleaning up assets")
        import launcher.patch as patch
        import launcher.sound as sound
        import launcher.changes as changes
        patch.cleanup_assets()
        sound.restore_sound()
        if _steam_argv is not None:
            changes.cleanup_patch(_steam_argv)
    except Exception as e:
        _log_manager.log_error(e)


def prepare_mod(steam_argv: str) -> None:
    global _mod_initialized, _steam_argv
    _steam_argv = steam_argv

    from launcher.modfolder import get_mod_folder
    import launcher.patch as patch
    import launcher.sound as sound
    import launcher.changes as changes

    _log_manager.log("Limbus Mod Loader version: v1.8")

    get_mod_folder()
    mod_zips_root_path = os.environ['mod_path']
    os.makedirs(mod_zips_root_path, exist_ok=True)

    def kill_handler(*args) -> None:
        sys.exit(0)

    _log_manager.log("Limbus args: %s", sys.argv)
    _do_cleanup_assets()
    atexit.register(_do_cleanup_assets)
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
    sound.replace_sound(mod_zips_root_path, steam_argv)
    _log_manager.log("Mod preparation complete")
    _mod_initialized = True


def cleanup_mod_assets() -> None:
    global _mod_initialized, _steam_argv
    if not _mod_initialized:
        return
    _do_cleanup_assets()
    _mod_initialized = False
    _steam_argv = None


_speed_exit_event = None


def start_speed_hotkey() -> None:
    global _speed_exit_event
    from launcher.speed_hotkey import run_speed_hotkey_if_enabled
    _speed_exit_event = run_speed_hotkey_if_enabled()


def stop_speed_hotkey() -> None:
    global _speed_exit_event
    if _speed_exit_event is not None:
        _speed_exit_event.set()
        _speed_exit_event = None
