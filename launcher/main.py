import sys
import time
import subprocess
from pathlib import Path

import os

print('开始')
file_dir = Path(os.path.dirname(__file__)).parent
print(f'\n\n{file_dir}')
sys.path.insert(0, str(file_dir))

from webFunc import GithubDownload
from globalManagers.LogManager import LogManager
try:
    _log_manager = LogManager()
except Exception as e:
    import sys
    print(f"无法初始化日志系统: {e}", file=sys.stderr)
    class _FallbackLogManager:
        def log(self, msg, *args): print(msg % args if args else msg, file=sys.stderr)
        def log_error(self, e): print(f"ERROR: {e}", file=sys.stderr)
    _log_manager = _FallbackLogManager()
from globalManagers.ConfigManager import ConfigManager
from launcher.updates import create_update
from launcher.cdn import run_cdn_optimization

from launcher.pipeline import (
    LaunchPipeline,
    PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN,
    PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING, PHASE_EXIT,
)


def resolve_steam_argv() -> str:
    steam_argv = os.getenv('steam_argv', '')

    if steam_argv == '':
        _log_manager.log("unexpectedly missing steam_argv environment variable")
        _log_manager.log("use path in config instead")

        steam_argv = ConfigManager().get("game_path", "") + 'LimbusCompany.exe'
    _log_manager.log(f"steam_argv: {steam_argv}")
    return steam_argv


def _prepare_mod_handler(**kw):
    steam_argv = kw.get('steam_argv')
    if steam_argv is None:
        return
    if ConfigManager().get("launcher.work.mod", False):
        from launcher.game_launch import prepare_mod
        prepare_mod(steam_argv)


def _cleanup_mod_handler(**kw):
    try:
        from launcher.game_launch import cleanup_mod_assets
        cleanup_mod_assets()
    except Exception as e:
        _log_manager.log_error(e)


def _register_speed_hotkey_handler(**kw):
    try:
        from launcher.game_launch import start_speed_hotkey
        start_speed_hotkey()
    except Exception as e:
        _log_manager.log_error(e)


def _unregister_speed_hotkey_handler(**kw):
    try:
        from launcher.game_launch import stop_speed_hotkey
        stop_speed_hotkey()
    except Exception as e:
        _log_manager.log_error(e)


def _wait_for_game(process, cancel_event):
    while process.poll() is None:
        if cancel_event.is_set():
            _log_manager.log("收到取消信号，正在终止游戏进程...")
            process.terminate()
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                process.kill()
            return
        time.sleep(0.5)
    _log_manager.log(f"游戏进程已退出，退出码: {process.returncode}")


def _hide_launcher_console():
    import ctypes
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        user32.ShowWindow(hwnd, 0)


def main():
    ConfigManager()

    gui_mode = ConfigManager().get("launcher.work.gui_mode", False)
    mod_enabled = ConfigManager().get("launcher.work.mod", False)

    if gui_mode:
        _hide_launcher_console()

    pipeline = LaunchPipeline()

    if mod_enabled:
        pipeline.on(PHASE_PREPARE_MOD, _prepare_mod_handler)
    pipeline.on(PHASE_EXIT, _cleanup_mod_handler)
    pipeline.on(PHASE_RUNNING, _register_speed_hotkey_handler)
    pipeline.on(PHASE_EXIT, _unregister_speed_hotkey_handler)

    progress = None
    log_handler = None

    if gui_mode:
        try:
            from launcher.gui_progress import create_progress_window, ProgressLogHandler
            _log_manager.log("正在启动GUI进度窗口...")
            progress = create_progress_window()
            progress.register_to_pipeline(pipeline)
            log_handler = ProgressLogHandler(progress)
            _log_manager._logger.addHandler(log_handler)
        except Exception as e:
            _log_manager.log(f"无法创建GUI进度窗口，回退到控制台模式: {e}")

    def _launcher_check_running(modal_id=None, log=True):
        if pipeline.cancel_event.is_set():
            raise RuntimeError("cancelled")
    _log_manager.set_modal_callbacks(check_running=_launcher_check_running)

    pipeline.emit(PHASE_INIT)

    steam_argv = ''
    try:
        if not pipeline.cancel_event.is_set():
            if progress and progress.is_alive():
                progress.set_progress_marquee()
                progress.update_status("正在检查更新...")
            pipeline.emit(PHASE_CHECK_UPDATE)
            steam_argv = resolve_steam_argv()
            try:
                GithubDownload.init_request(quiet=True)
                update_obj = create_update()
                update_obj.run()
            except Exception as e:
                _log_manager.log_error(e)

        if not pipeline.cancel_event.is_set():
            if progress and progress.is_alive():
                progress.update_status("正在进行CDN优选...")
            pipeline.emit(PHASE_CDN)
            try:
                run_cdn_optimization(file_dir, cancel_event=pipeline.cancel_event)
            except Exception as e:
                _log_manager.log_error(e)

        if not pipeline.cancel_event.is_set():
            pipeline.context['steam_argv'] = steam_argv
            if progress and progress.is_alive():
                progress.update_status("正在准备模组...")
            pipeline.emit(PHASE_PREPARE_MOD, steam_argv=steam_argv)
    except Exception as e:
        _log_manager.log_error(e)

    game_process = None
    exit_code = -1

    if not pipeline.cancel_event.is_set():
        try:
            if progress and progress.is_alive():
                progress.update_status("正在启动游戏...")
            pipeline.emit(PHASE_LAUNCH)

            game_process = subprocess.Popen(steam_argv)
            pipeline.context['game_process'] = game_process
            pipeline.context['game_pid'] = game_process.pid
            _log_manager.log(f"游戏已启动 (PID: {game_process.pid})")

            pipeline.emit(PHASE_RUNNING)

            _wait_for_game(game_process, pipeline.cancel_event)

            exit_code = game_process.returncode if game_process.poll() is not None else -1
        except Exception as e:
            _log_manager.log_error(e)
            exit_code = -1

    try:
        pipeline.emit(PHASE_EXIT, exit_code=exit_code)
    except Exception:
        pass

    _log_manager.log('正常退出')

    _log_manager.set_modal_callbacks(check_running=None)

    if log_handler:
        try:
            _log_manager._logger.removeHandler(log_handler)
        except Exception:
            pass

    if progress and progress.is_alive():
        try:
            time.sleep(3.0)
            progress.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()
