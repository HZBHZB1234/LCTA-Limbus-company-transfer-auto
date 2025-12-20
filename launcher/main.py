import atexit
import signal
import subprocess
import sys
import tempfile
from typing import List
from pathlib import Path
import json
from datetime import datetime, timedelta
import socket

# Needed for embedded python
import os

import logging

# DO NOT IMPORT ANY FILES BEFORE THESE TWO LINES
print('开始')
file_dir = Path(os.path.dirname(__file__)).parent
print(f'\n\n{file_dir}')
sys.path.insert(0, str(file_dir))

from web_function import *
from webutils.log_manage import LogManager
from webutils import *
import webutils.load as LoadUtils

config_whole = {}
logger = None

def check_network():
    try:
        socket.create_connection(("8.8.8.8", 53))
        return True
    except OSError:
        pass
    return False

def get_note_content():
    note_ = Note(address="062d22d6ecb233d1", pwd="AutoTranslate", read_only=True)
    note_.fetch_note_info()
    note_content = note_.note_content
    note_content = json.loads(note_content)
    return note_content

def update_config_last(name, version):
    global config_whole
    config_whole['launcher']['last_install'][name] = str(version)
    with open("config.json", 'w', encoding='utf-8') as f:
        json.dump(config_whole, f, indent=4, ensure_ascii=False)

def main_pre():
    global config_whole
    global logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(".\\logs\\launcher.log", encoding='utf-8'),
            logging.StreamHandler(stream=sys.stdout)
        ]
    )
    LoadUtils.set_logger(logger)
    logger = LogManager()
    logger.set_log_callback(logging.info)
    logger.set_error_callback(logging.exception)
    logger.set_ui_callback(lambda message,_: logging.info(message))
    logger.set_modal_callbacks(status_callback=lambda status, modal_id: logging.info(f"{modal_id}: 阶段 {status}"), 
                            log_callback=lambda message, modal_id: logging.info(f"{modal_id}: {message}"), 
                            progress_callback=lambda percent, text, modal_id: logging.info(f"{modal_id}: {text} {percent}%"),
                            check_running=lambda modal_id, log=True: (logging.info(f"{modal_id} 阶段正在运行")) if log else None)

    config_whole = LoadUtils.load_config()
    config = config_whole.get("launcher", {})
    if not check_network():
        logger.log("当前网络不可用，无法检查更新")
        return

    update = config.get("work", {}).get("update", "no")
    last = config.get("last_install", {})

    if update == "llc":
        logger.log("启用LLC更新")
        zero = config.get("zero", {})
        if zero.get("download_source", "github") == "github":
            latest_version = check_ver_github(zero.get("from_proxy", True))
        else:
            latest_version = str(get_note_content().get('llc_version', '0.0.0'))
        if latest_version == "0.0.0":
            logger.log("无法获取到最新版本，请检查网络连接")
            return
        if latest_version == last.get("llc", "0.0.0"):
            logger.log(f"当前已是最新版本 {latest_version}，无需更新")
            return
        zip_path = function_llc_main("llc_update", logger,
                        download_source=zero.get("download_source", "github"),
                        from_proxy=zero.get("from_proxy", True),
                        zip_type=zero.get("zip_type", "zip"),
                        use_cache=True)
        if not zip_path:
            logger.log(f"LLC更新包下载失败，路径: {zip_path}")
            return
        logger.log(f"LLC更新包下载成功，路径: {zip_path}")
        package_list = find_translation_packages('.')
        if not zip_path in package_list:
            logger.log(f"LLC更新包 {zip_path} 不在安装包列表中，请检查安装包")
            return
        logger.log(f"LLC更新包 {zip_path} 已在安装包列表中")
        install_translation_package(zip_path, config_whole.get("game_path", ""), logger, "llc_update_install")
        logger.log("LLC更新完成")
        update_config_last("llc", latest_version)
        return
    
    elif update == "ourplay":
        logger.log("启用ourplay更新")
        ourplay = config.get("ourplay", {})
        if ourplay.get("use_api", True):
            latest_version = str(get_note_content().get('ourplay_version', '0.0.0'))
        else:
            latest_version = str(check_ver_ourplay(logger))
        if latest_version == "0.0.0":
            logger.log("无法获取到最新版本，请检查网络连接")
            return
        if latest_version == last.get("ourplay", "0.0.0"):
            logger.log(f"当前已是最新版本 {latest_version}，无需更新")
            return
        if not ourplay.get("use_api", True):
            function_ourplay_main("llc_update", logger,
                        check_hash=ourplay.get("check_hash", True),
                        font_option=ourplay.get("font_option", "simplify")
                        )
        else:
            function_ourplay_api("llc_update", logger,
                        check_hash=ourplay.get("check_hash", True),
                        font_option=ourplay.get("font_option", "simplify")
                        )
        zip_path = "ourplay.zip"
        logger.log(f"ourplay更新包下载成功，路径: {zip_path}")
        package_list = find_translation_packages('.')
        if not zip_path in package_list:
            logger.log(f"ourplay更新包 {zip_path} 不在安装包列表中，请检查安装包")
            return
        logger.log(f"ourplay更新包 {zip_path} 已在安装包列表中")
        install_translation_package(zip_path, config_whole.get("game_path", ""), logger, "llc_update_install")
        logger.log("ourplay更新完成")
        update_config_last("ourplay", latest_version)
        return
    
    elif update == "all":
        logger.log("启用LLC和ourplay更新")
        note_content = get_note_content()
        try:
            ourplay_last_update = datetime.fromisoformat(note_content.get('ourplay_last_update_time', '1970-01-01T00:00:00'))
        except (ValueError, TypeError):
            ourplay_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
        try:
            llc_last_update = datetime.fromisoformat(note_content.get('llc_last_update_time', '1970-01-01T00:00:00'))
        except (ValueError, TypeError):
            llc_last_update = datetime.fromisoformat('1970-01-01T00:00:00')

        if llc_last_update < ourplay_last_update:
            logger.log("ourplay更新时间较新，执行ourplay更新")
            ourplay = config.get("ourplay", {})
            if str(note_content.get('ourplay_version', '0.0.0')) == last.get("ourplay", "0.0.0"):
                logger.log(f"当前已是最新版本 {note_content.get('ourplay_version', '0.0.0')}，无需更新")
                return
            if not ourplay.get("use_api", True):
                function_ourplay_main("llc_update", logger,
                            check_hash=ourplay.get("check_hash", True),
                            font_option=ourplay.get("font_option", "simplify")
                            )
            else:
                function_ourplay_api("llc_update", logger,
                            check_hash=ourplay.get("check_hash", True),
                            font_option=ourplay.get("font_option", "simplify")
                            )
            zip_path = "ourplay.zip"
            logger.log(f"ourplay更新包下载成功，路径: {zip_path}")
            package_list = find_translation_packages('.')
            if not zip_path in package_list:
                logger.log(f"ourplay更新包 {zip_path} 不在安装包列表中，请检查安装包")
                return
            logger.log(f"ourplay更新包 {zip_path} 已在安装包列表中")
            install_translation_package(zip_path, config_whole.get("game_path", ""), logger, "llc_update_install")
            logger.log("ourplay更新完成")
            update_config_last("ourplay", note_content.get('ourplay_version', '0.0.0'))
        else:
            logger.log("LLC更新时间较新，执行LLC更新")
            if str(note_content.get('llc_version', '0.0.0')) == last.get("llc", "0.0.0"):
                logger.log(f"当前已是最新版本 {last.get('llc', '0.0.0')}，无需更新")
                return
            zero = config.get("zero", {})
            zip_path = function_llc_main("llc_update", logger,
                            download_source=zero.get("download_source", "github"),
                            from_proxy=zero.get("from_proxy", True),
                            zip_type=zero.get("zip_type", "zip"),
                            use_cache=True)
            if not zip_path:
                logger.log(f"LLC更新包下载失败，路径: {zip_path}")
                return
            logger.log(f"LLC更新包下载成功，路径: {zip_path}")
            package_list = find_translation_packages('.')
            if not zip_path in package_list:
                logger.log(f"LLC更新包 {zip_path} 不在安装包列表中，请检查安装包")
                return
            logger.log(f"LLC更新包 {zip_path} 已在安装包列表中")
            install_translation_package(zip_path, config_whole.get("game_path", ""), logger, "llc_update_install")
            logger.log("LLC更新完成")
            update_config_last("llc", note_content.get('llc_version', '0.0.0'))
    else:
        logger.log("未启用任何更新选项，跳过更新检查")
# dev分割线

def main_after_mod():
    from modfolder import get_mod_folder
    import patch
    import sound

    mod_zips_root_path = get_mod_folder()
    os.makedirs(mod_zips_root_path, exist_ok=True)



    logging.info("Limbus Mod Loader version: v1.8")


    def kill_handler(*args) -> None:
        sys.exit(0)


    def cleanup_assets():
        try:
            logging.info("Cleaning up assets")
            patch.cleanup_assets()
            sound.restore_sound()
        except Exception as e:
            logging.error("Error: %s", e)

    try:
        logging.info("Limbus args: %s", sys.argv)
        cleanup_assets()
        atexit.register(cleanup_assets)
        signal.signal(signal.SIGINT, kill_handler)
        signal.signal(signal.SIGTERM, kill_handler)

        logging.info("Detecting lunartique mods")
        patch.detect_lunartique_mods(mod_zips_root_path)
        tmp_asset_root = tempfile.mkdtemp()
        logging.info("Extracting mod assets to %s", tmp_asset_root)
        patch.extract_assets(tmp_asset_root, mod_zips_root_path)
        logging.info("Backing up data and patching assets....")
        patch.patch_assets(tmp_asset_root)
        patch.shutil.rmtree(tmp_asset_root)
        sound.replace_sound(mod_zips_root_path,config_whole.get("game_path", "")+'LimbusCompany.exe')
        logging.info("Starting game")
        subprocess.call(config_whole.get("game_path", "")+'LimbusCompany.exe')

    except Exception as e:
        logging.error("Error: %s", e)
        sys.exit(1)

def main_after_game():
    subprocess.call(config_whole.get("game_path", "")+'LimbusCompany.exe')

def main():
    try:
        main_pre()
    except Exception as e:
        logger.log_error(e)
    if config_whole.get("launcher", {}).get("work", {}).get("mod", False):
        main_after_mod()
    else:
        main_after_game()

if __name__ == '__main__':
    main()