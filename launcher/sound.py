import ctypes
import glob
from globalManagers.LogManager import LogManager
_log_manager = LogManager()
import os
import shutil
import time
import shlex
from pathlib import Path
from threading import Thread

from launcher.modfolder import get_mod_folder

# -- 快速 PID 存活检查（与 webutils/function_speed.py 相同的模式） --
_kernel32 = ctypes.windll.kernel32
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_game_pid = None


def _pid_alive(pid: int) -> bool:
    """用 OpenProcess 快速检查 PID 是否仍然存在。"""
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        _kernel32.CloseHandle(handle)
        return True
    return False


def is_game_running() -> bool:
    """检查 LimbusCompany.exe 是否在运行（PID 缓存 + 快速验证）。"""
    global _game_pid

    # 快速路径：验证缓存的 PID
    if _game_pid is not None and _pid_alive(_game_pid):
        return True

    # 慢速路径：通过 SpeedController 枚举进程（与 function_speed.py 复用同一方式）
    _game_pid = None
    try:
        from openspeedy import SpeedController
        with SpeedController() as sc:
            processes = sc.list_processes(fast=False)
        for p in processes:
            if p.name == "LimbusCompany.exe":
                _game_pid = p.pid
                return True
    except Exception:
        return False

    return False

_game_path = None
def sound_folder():
    return Path(_game_path).parent / "LimbusCompany_Data/StreamingAssets/Assets/Sound/FMODBuilds/Desktop"

def sound_data_paths():
    return map(os.path.normpath, glob.glob(str(sound_folder()) + "/*.bank"))

def smallest_sound_file():
    return min(sound_data_paths(), key=os.path.getsize)

def wait_for_validation():
    smallest = smallest_sound_file()
    os.remove(smallest)
    while not os.path.exists(smallest):
        time.sleep(0.1)

def sound_replace_thread(mod_folder: str):
    wait_for_validation()

    _log_manager.log("Validation complete, replacing sound files")
    target_folder = sound_folder()
    for sound_file in Path(mod_folder).rglob("*.bank"):
        _log_manager.log("Replacing %s", sound_file)
        target = os.path.join(target_folder, sound_file.name)

        if os.path.exists(target) and not os.path.exists(target + ".bak"):
            os.replace(target, target + ".bak")
        elif os.path.exists(target):
            os.remove(target)

        shutil.copyfile(sound_file, target)

    # Wait for game to start (up to 30 seconds)
    for _ in range(30):
        if is_game_running():
            break
        time.sleep(1)

    # Monitor the process and wait until game closes
    _log_manager.log("Game is running. Monitoring for exit to restore all assets...")
    while is_game_running():
        time.sleep(2)

    time.sleep(1)
    _log_manager.log("Game closed detected. Cleaning up both sound and __data assets...")

    # Restore the sound files
    restore_sound()

    # Restore __data
    try:
        import launcher.patch as patch
        patch.cleanup_assets()
        _log_manager.log("Main mod assets successfully restored.")
    except Exception as e:
        _log_manager.log_error(e)

def restore_sound():
    target_folder = sound_folder()
    backup_files = list(Path(target_folder).rglob("*.bank.bak"))
    if not backup_files:
        return

    for sound_file in backup_files:
        target = str(sound_file.with_suffix(""))  # remove .bak, keep .bank
        if os.path.exists(target):
            os.remove(target)
        os.replace(str(sound_file), target)
    _log_manager.log("Audio restoration complete.")

def replace_sound(mod_folder: str, game_path: str = None):
    mod_zips_root_path = get_mod_folder()
    if game_path is not None:
        global _game_path
        _game_path = shlex.split(game_path)[0]
    if any(file_name.endswith(".bank") for file_name in os.listdir(mod_zips_root_path)):
        Thread(target=sound_replace_thread, args=(mod_folder,)).start()
    else:
        _log_manager.log("No .bank found, skip sound replacing process.")