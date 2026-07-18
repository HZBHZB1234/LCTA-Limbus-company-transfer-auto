import sys
from pathlib import Path

# Needed for embedded python
import os

# DO NOT IMPORT ANY FILES BEFORE THESE TWO LINES
print('开始')
file_dir = Path(os.path.dirname(__file__)).parent
print(f'\n\n{file_dir}')
sys.path.insert(0, str(file_dir))

from webFunc import GithubDownload
from globalManagers.LogManager import LogManager
_log_manager = LogManager()
from globalManagers.ConfigManager import ConfigManager
from launcher.updates import create_update
from launcher.cdn import run_cdn_optimization
from launcher.game_launch import main_after_mod, main_after_game

def resolve_steam_argv() -> str:
    steam_argv = os.getenv('steam_argv', '')

    if steam_argv == '':
        _log_manager.log("unexpectedly missing steam_argv environment variable")
        _log_manager.log("use path in config instead")

        steam_argv = ConfigManager().get("game_path", "")+'LimbusCompany.exe'
    _log_manager.log(f"steam_argv: {steam_argv}")
    return steam_argv

def main_pre() -> str:
    # 初始化单例配置管理器（第一次调用完成加载）
    ConfigManager()

    steam_argv = resolve_steam_argv()

    try:
        GithubDownload.init_request(quiet=True)

        # 使用工厂模式创建更新对象并执行更新
        update_obj = create_update()
        update_obj.run()

        # CDN优选（在启动游戏前优化CDN连接）
        run_cdn_optimization(file_dir)
    except Exception as e:
        _log_manager.log_error(e)

    return steam_argv

def main():
    ConfigManager()

    gui_mode = ConfigManager().get("launcher.work.gui_mode", False)
    progress = None
    log_handler = None

    if gui_mode:
        try:
            from launcher.gui_progress import create_progress_window, ProgressLogHandler
            _log_manager.log("正在启动GUI进度窗口...")
            progress = create_progress_window()
            log_handler = ProgressLogHandler(progress)
            _log_manager._logger.addHandler(log_handler)
        except Exception as e:
            _log_manager.log(f"无法创建GUI进度窗口，回退到控制台模式: {e}")

    steam_argv = ''
    try:
        if progress:
            progress.update_status("正在准备启动...")
        steam_argv = main_pre()
    except Exception as e:
        _log_manager.log_error(e)

    try:
        if progress and progress.is_alive():
            progress.set_progress_marquee()
            progress.update_status("正在启动游戏...")
        if ConfigManager().get("launcher.work.mod", False):
            main_after_mod(steam_argv)
        else:
            main_after_game(steam_argv)
    except Exception as e:
        _log_manager.log_error(e)

    _log_manager.log('正常退出')

    if progress and log_handler:
        try:
            _log_manager._logger.removeHandler(log_handler)
        except Exception:
            pass

    if progress and progress.is_alive():
        try:
            progress.update_status("启动完成")
            import time
            time.sleep(1.0)
            progress.close()
        except Exception:
            pass

if __name__ == '__main__':
    main()
