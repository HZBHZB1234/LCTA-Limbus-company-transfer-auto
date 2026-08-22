import atexit
import os
import signal
import sys
import tempfile
import threading
from typing import Callable, Optional

import UnityPy.config
UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
from globalManagers.exceptions import CancelRunning

_log_manager = LogManager()

_mod_initialized = False
_steam_argv = None


def _do_cleanup_assets():
    try:
        _log_manager.log("Cleaning up assets")
        import launcher.patch as patch
        import launcher.sound as sound
        import launcher.changes as changes
        import launcher.staticmod as staticmod
        patch.cleanup_assets()
        sound.restore_sound()
        try:
            staticmod.restore_staticmods()
        except Exception as e:
            _log_manager.log_error(e)
        if _steam_argv is not None:
            changes.cleanup_patch(_steam_argv)
    except Exception as e:
        _log_manager.log_error(e)


def prepare_mod(
    steam_argv: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    global _mod_initialized, _steam_argv
    _steam_argv = steam_argv

    def report(percent: int, text: str) -> None:
        if progress_callback is not None:
            try:
                progress_callback(percent, text)
            except Exception:
                pass

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise CancelRunning("cancelled")

    from launcher.modfolder import get_mod_folder
    import launcher.patch as patch
    import launcher.sound as sound
    import launcher.changes as changes

    _log_manager.log("Limbus Mod Loader version: v1.8")

    report(5, "正在定位模组目录...")
    check_cancel()
    get_mod_folder()
    mod_zips_root_path = os.environ['mod_path']
    os.makedirs(mod_zips_root_path, exist_ok=True)

    def kill_handler(*args) -> None:
        sys.exit(0)

    _log_manager.log("Limbus args: %s", sys.argv)
    report(15, "正在清理上次启动残留资源...")
    check_cancel()
    _do_cleanup_assets()
    atexit.register(_do_cleanup_assets)
    signal.signal(signal.SIGINT, kill_handler)
    signal.signal(signal.SIGTERM, kill_handler)
    _log_manager.log("Detecting lunartique mods")
    report(28, "正在检测 Lunartique 模组...")
    check_cancel()
    patch.detect_lunartique_mods(mod_zips_root_path)
    _log_manager.log("Patching text data")
    report(42, "正在应用模组文本补丁...")
    check_cancel()
    changes.apply_patch(mod_zips_root_path, steam_argv)
    tmp_asset_root = tempfile.mkdtemp()
    _log_manager.log("Extracting mod assets to %s", tmp_asset_root)
    report(58, "正在解压模组资源...")
    check_cancel()
    patch.extract_assets(tmp_asset_root, mod_zips_root_path)
    _log_manager.log("Backing up data and patching assets....")
    report(74, "正在备份并写入游戏资源...")
    check_cancel()
    patch.patch_assets(tmp_asset_root)
    patch.shutil.rmtree(tmp_asset_root)
    report(82, "正在应用静态数据 Mod...")
    check_cancel()
    import launcher.staticmod as staticmod
    static_result = staticmod.apply_staticmods(mod_zips_root_path)
    if static_result.get("applied"):
        _log_manager.log("staticmod: 应用 %d 个 .staticmod", static_result["applied"])
    report(90, "正在处理模组音频...")
    check_cancel()
    sound.replace_sound(mod_zips_root_path, steam_argv)
    _log_manager.log("Mod preparation complete")
    report(100, "模组准备完成")
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


_input_bypass_exit_event = None
_input_bypass_timeout = 180  # 等待游戏进程的最长时间（秒）


def _inject_input_bypass_when_game_ready(exit_event: threading.Event) -> None:
    """后台等待 LimbusCompany.exe 出现后注入输入反检测 hook。

    Steam 启动模式中，PHASE_RUNNING 触发时 Steam 可能还在拉起游戏，
    因此轮询等待游戏 PID 出现（最多 _input_bypass_timeout 秒）。
    """
    import time
    from webutils.function_input_bypass import InputBypassManager

    deadline = time.time() + _input_bypass_timeout
    pid = None
    while not exit_event.is_set() and time.time() < deadline:
        pid = InputBypassManager.find_game_pid()
        if pid is not None:
            break
        time.sleep(2)

    if exit_event.is_set():
        return
    if pid is None:
        _log_manager.log("输入反检测: 等待游戏进程超时，本次启动不注入")
        return

    try:
        InputBypassManager.apply()
        InputBypassManager.inject(pid)
        _log_manager.log(f"输入反检测 hook 已注入 (PID: {pid})")
    except Exception as e:
        _log_manager.log_error(e)


def start_input_bypass() -> None:
    """PHASE_RUNNING 回调：若开启输入反检测，后台等待游戏进程并注入。"""
    global _input_bypass_exit_event
    if not ConfigManager().get("launcher.work.input_bypass", False):
        return
    if _input_bypass_exit_event is not None:
        return
    try:
        from webutils.function_input_bypass import InputBypassManager
        InputBypassManager.apply()
        _log_manager.log("输入反检测已启用，等待游戏进程...")
    except Exception as e:
        _log_manager.log_error(e)

    event = threading.Event()
    t = threading.Thread(
        target=_inject_input_bypass_when_game_ready,
        args=(event,),
        daemon=True,
    )
    t.start()
    _input_bypass_exit_event = event


def stop_input_bypass() -> None:
    """PHASE_EXIT 回调：停止注入线程并弹出 DLL。"""
    global _input_bypass_exit_event
    if _input_bypass_exit_event is not None:
        _input_bypass_exit_event.set()
        _input_bypass_exit_event = None
    from webutils.function_input_bypass import InputBypassManager
    try:
        InputBypassManager.close()
        _log_manager.log("输入反检测 hook 已清理")
    except Exception as e:
        _log_manager.log_error(e)


def start_cheat_plugins() -> None:
    """PHASE_RUNNING 回调：若已解锁且插件启用，分发给各插件 on_start。"""
    from webutils import cheat_core
    if not cheat_core.ensure_unlocked().get("success"):
        _log_manager.log("作弊工具箱未解锁，跳过 Launcher 自动注入")
        return
    from webutils import CheatPluginHost
    CheatPluginHost.run_launcher_phase("start")


def stop_cheat_plugins() -> None:
    """PHASE_EXIT 回调：分发给各插件 on_stop。"""
    from webutils import CheatPluginHost
    CheatPluginHost.run_launcher_phase("stop")
