import ctypes
import glob
from globalManagers.LogManager import LogManager
_log_manager = LogManager()
import os
import shutil
import time
from pathlib import Path
from threading import Thread, Lock

from launcher.modfolder import get_mod_folder
from launcher.changes import extract_exe_path

# -- 快速 PID 存活检查（与 webutils/function_speed.py 相同的模式） --
_kernel32 = ctypes.windll.kernel32
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_game_pid = None

_sound_restore_lock = Lock()

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

def wait_for_validation(timeout: float = 120.0):
    bank_files = list(sound_data_paths())
    if not bank_files:
        _log_manager.log("未找到 .bank 音频文件，跳过校验等待")
        return
    smallest = min(bank_files, key=os.path.getsize)
    with open(smallest, "rb") as f:
        backup = f.read()
    os.remove(smallest)

    deadline = time.time() + timeout
    while not os.path.exists(smallest):
        if time.time() > deadline:
            _log_manager.log(f"等待游戏校验超时（{int(timeout)} 秒），恢复备份的音频文件: {smallest}")
            try:
                with open(smallest, "wb") as f:
                    f.write(backup)
            except Exception as e:
                _log_manager.log_error(e)
            return
        time.sleep(0.1)

def sound_replace_thread(mod_folder: str):
    wait_for_validation()

    _log_manager.log("Validation complete, replacing sound files")
    from launcher.modcache import enabled_mod_files
    target_folder = sound_folder()
    for sound_file in enabled_mod_files(mod_folder, "*.bank"):
        _log_manager.log(f"Replacing {sound_file}")
        target = os.path.join(target_folder, sound_file.name)

        if os.path.exists(target) and not os.path.exists(target + ".bak"):
            os.replace(target, target + ".bak")
        elif os.path.exists(target):
            os.remove(target)

        shutil.copyfile(sound_file, target)

    # 应用 .rebank fsb 补丁模组（哈希缓存，命中免重编码）
    try:
        from launcher.bankmod import apply_rebanks
        result = apply_rebanks(mod_folder)
        _log_manager.log("Rebank mods applied: patched=%s cache_hit=%d cache_miss=%d"
                         % (result["patched"], result["cache_hit"], result["cache_miss"]))
    except Exception as e:
        _log_manager.log_error(e)

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
    with _sound_restore_lock:
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
        _game_path = extract_exe_path(game_path)
    from launcher.bankmod import rebank_files_in
    from launcher.modcache import enabled_mod_files
    has_bank = bool(enabled_mod_files(mod_zips_root_path, "*.bank"))
    has_rebank = bool(rebank_files_in(mod_zips_root_path))
    if has_bank or has_rebank:
        Thread(target=sound_replace_thread, args=(mod_folder,), daemon=True).start()
    else:
        _log_manager.log("No .bank/.rebank found, skip sound replacing process.")