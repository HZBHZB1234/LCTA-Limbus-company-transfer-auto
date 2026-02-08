import subprocess
import sys
import tempfile
from typing import List, Dict, Optional, Any
from pathlib import Path
import json
from datetime import datetime, timedelta
import socket
from abc import ABC, abstractmethod

# Needed for embedded python
import os

import logging
# 导入 RotatingFileHandler 用于日志文件轮换
from logging.handlers import RotatingFileHandler

# DO NOT IMPORT ANY FILES BEFORE THESE TWO LINES
print('开始')
file_dir = Path(os.path.dirname(__file__)).parent
print(f'\n\n{file_dir}')
sys.path.insert(0, str(file_dir))

from webFunc import *
from webFunc import GithubDownload
from webutils.log_manage import LogManager
from webutils import *
import webutils.load as LoadUtils
import webutils.functions as func_utils

config_whole = {}
logger = None
steam_argv = ''

def check_network():
    try:
        socket.create_connection(("8.8.8.8", 53))
        return True
    except OSError:
        pass
    return False

class CustomNote(Note):
    _cache_instance = {}
    @classmethod
    def create(cls, address, pwd, read_only) -> Note:
        argu = (address, pwd, read_only)
        if argu in cls._cache_instance:
            return cls._cache_instance[argu]
        else:
            note = cls(address, pwd, read_only)
            note.fetch_note_info()
            cls._cache_instance[argu] = note
            return note

def get_note_content():
    note_ = CustomNote.create(address="1df3ff8fe2ff2e4c", pwd="AutoTranslate", read_only=True)
    note_content = note_.note_content
    note_content = json.loads(note_content)
    return note_content

def update_config_last(name, version):
    global config_whole
    config_whole['launcher']['last_install'][name] = str(version)
    with open("config.json", 'w', encoding='utf-8') as f:
        json.dump(config_whole, f, indent=4, ensure_ascii=False)

class UpdateBase(ABC):
    """更新基类，定义更新操作的通用接口"""
    
    def __init__(self, logger: LogManager):
        self.logger = logger
        self.config_whole = config_whole
        self.launcher_config: dict = config_whole.get('launcher', {})
        self.cache_path = func_utils.get_cache_font(config_whole)
    
    def check_network_available(self) -> bool:
        """检查网络是否可用"""
        return check_network()
    
    def get_last_installed_version(self, name) -> str:
        """获取最后安装的版本"""
        last_config = self.config_whole.get("launcher", {}).get("last_install", {})
        return last_config.get(name, "0.0.0")
    
    def download_and_install(self, zip_path: str) -> bool:
        """下载并安装更新包"""
        package_list = find_translation_packages('.')
        if zip_path not in package_list:
            self.logger.log(f"更新包 {zip_path} 不在安装包列表中，请检查安装包")
            return False
            
        self.logger.log(f"更新包 {zip_path} 已在安装包列表中")
        install_translation_package(zip_path, self.config_whole.get("game_path", ""), 
                                   self.logger, f"update_install")
        return True
    
    @abstractmethod
    def check_update(self) -> bool:
        pass
    
    @abstractmethod
    def perform_update(self) -> Optional[str]:
        """执行更新操作，返回更新包路径"""
        pass
    
    @abstractmethod
    def update_config(self) -> bool:
        """更新配置文件"""
        pass
    
    def run(self) -> bool:
        """执行完整的更新流程"""
        if not self.check_network_available():
            self.logger.log("当前网络不可用，无法检查更新")
            return False
            
        if not self.check_update():
            self.logger.log("当前版本已经是最新版本")
            return False
            
        zip_path = self.perform_update()
        
        if not zip_path:
            self.logger.log(f"更新包下载失败")
            return False
            
        self.logger.log(f"更新包下载成功，路径: {zip_path}")
        
        if not self.download_and_install(zip_path):
            return False
            
        self.update_config()
        self.logger.log(f"汉化包更新完成")
        return True

class NoUpdate(UpdateBase):
    """不执行任何更新"""
    def check_update(self) -> bool:
        self.logger.log("未启用任何更新选项，跳过更新检查")
        return False
    
    def perform_update(self) -> Optional[str]:
        self.logger.log("你是怎么触发这条日志的？")
        return None
    
    def update_config(self):
        pass
    
class MachineUpdate(UpdateBase):
    """LCTA-AU更新类"""
    
    def __init__(self, logger: LogManager):
        super().__init__(logger)
        self.config: dict = self.launcher_config.get("machine", {})
    
    def get_latest_version(self) -> str:
        """获取LCTA-AU最新版本号"""
        download_source = self.config.get("download_source", "github")
        
        if download_source == "github":
            return check_ver_github_M(self.config.get("use_proxy", True))
        else:
            note_content = get_note_content()
            return str(note_content.get('machine_version', '0.0.0'))
        
    def check_update(self) -> bool:
        last_version = self.get_last_installed_version('machine')
        self.latest_version = self.get_latest_version()
        return last_version != self.latest_version
        
    def perform_update(self) -> Optional[str]:
        """执行LCTA-AU更新"""
        return function_llc_main(
            "LCTA-AU_update", 
            self.logger,
            download_source=self.config.get("download_source", "github"),
            from_proxy=self.config.get("use_proxy", True)
        )
        
    def update_config(self) -> bool:
        update_config_last('machine', self.latest_version)

class LLCUpdate(UpdateBase):
    """LLC更新类"""
    
    def __init__(self, logger: LogManager):
        super().__init__(logger)
        self.config: dict = self.launcher_config.get("zero", {})
    
    def get_latest_version(self) -> str:
        """获取LLC最新版本号"""
        download_source = self.config.get("download_source", "github")
        
        if download_source == "github":
            return check_ver_github(self.config.get("use_proxy", True))
        else:
            note_content = get_note_content()
            return str(note_content.get('llc_version', '0.0.0'))
        
    def check_update(self) -> bool:
        last_version = self.get_last_installed_version('llc')
        self.latest_version = self.get_latest_version()
        return last_version != self.latest_version
        
    def perform_update(self) -> Optional[str]:
        """执行LLC更新"""
        return function_llc_main(
            "llc_update", 
            self.logger,
            download_source=self.config.get("download_source", "github"),
            from_proxy=self.config.get("use_proxy", True),
            zip_type=self.config.get("zip_type", "zip"),
            use_cache=True,
            cache_path=self.cache_path
        )
        
    def update_config(self) -> bool:
        update_config_last('llc', self.latest_version)

class OurPlayUpdate(UpdateBase):
    """OurPlay更新类"""
    
    def __init__(self, logger: LogManager):
        super().__init__(logger)
        self.config: dict = self.config_whole.get("ourplay", {})
    
    def get_latest_version(self) -> str:
        """获取OurPlay最新版本号"""
        if self.config.get("use_api", True):
            note_content = get_note_content()
            return str(note_content.get('ourplay_version', '0.0.0'))
        else:
            return str(check_ver_ourplay(self.logger))
        
    def check_update(self) -> bool:
        last_version = self.get_last_installed_version('ourplay')
        self.latest_version = self.get_latest_version()
        return last_version != self.latest_version
        
    def update_config(self) -> bool:
        update_config_last('ourplay', self.latest_version)
    
    def perform_update(self) -> Optional[str]:
        """执行OurPlay更新"""
        if not self.config.get("use_api", True):
            function_ourplay_main(
                "ourplay_update", 
                self.logger,
                check_hash=self.config.get("check_hash", True),
                font_option=self.config.get("font_option", "simplify")
            )
        else:
            function_ourplay_api(
                "ourplay_update", 
                self.logger,
                check_hash=self.config.get("check_hash", True),
                font_option=self.config.get("font_option", "simplify")
            )
        return "ourplay.zip"

class LOUpdate(UpdateBase):
    """同时更新LLC和OurPlay（根据时间戳选择最新的一个）"""
    
    def __init__(self, logger: LogManager):
        super().__init__(logger)
        self.llc_update = LLCUpdate(logger)
        self.ourplay_update = OurPlayUpdate(logger)
    
    def get_latest_type(self) -> str:
        """获取最新源"""
        note_content = get_note_content()
        
        try:
            ourplay_last_update = datetime.fromisoformat(
                note_content.get('ourplay_last_update_time', '1970-01-01T00:00:00')
            )
        except (ValueError, TypeError):
            ourplay_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
        try:
            llc_last_update = datetime.fromisoformat(
                note_content.get('llc_last_update_time', '1970-01-01T00:00:00')
            )
        except (ValueError, TypeError):
            llc_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
        
        # 返回时间戳较新的版本类型
        return "ourplay" if llc_last_update < ourplay_last_update else "llc"
    
    def perform_update(self) -> Optional[str]:
        """根据时间戳选择执行哪个更新"""
        select_type = self.get_latest_type()
        if select_type == "ourplay":
            self.ourplay_update.run()
        elif select_type == "llc":
            self.llc_update.run()
        else:
            return False
        
    def check_update(self) -> bool:
        logger.log('尝试进行检查')
        return True
        
    def update_config(self) -> bool:
        return True

class LMAUpdate(UpdateBase):
    """同时更新LLC和LCTA-AU（通过api根据时间戳选择最新的一个）"""
    
    def __init__(self, logger: LogManager):
        super().__init__(logger)
        self.llc_update = LLCUpdate(logger)
        self.LCTA_AU_update = MachineUpdate(logger)
    
    def get_latest_type(self) -> str:
        """获取最新源"""
        note_content = get_note_content()
        
        try:
            machine_last_update = datetime.fromisoformat(
                note_content.get('machine_last_update_time', '1970-01-01T00:00:00')
            )
        except (ValueError, TypeError):
            machine_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
        try:
            llc_last_update = datetime.fromisoformat(
                note_content.get('llc_last_update_time', '1970-01-01T00:00:00')
            )
        except (ValueError, TypeError):
            llc_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
        
        # 返回时间戳较新的版本类型
        return "machine" if llc_last_update < machine_last_update else "llc"
    
    def perform_update(self) -> Optional[str]:
        """根据时间戳选择执行哪个更新"""
        select_type = self.get_latest_type()
        if select_type == "machine":
            self.LCTA_AU_update.run()
        elif select_type == "llc":
            self.llc_update.run()
        else:
            return False
        
    def check_update(self) -> bool:
        logger.log('尝试进行检查')
        return True
        
    def update_config(self) -> bool:
        return True

class LMGUpdate(UpdateBase):
    """同时更新LLC和LCTA-AU（通过github根据时间戳选择最新的一个）"""
    
    def __init__(self, logger: LogManager):
        super().__init__(logger)
        self.llc_update = LLCUpdate(logger)
        self.LCTA_AU_update = MachineUpdate(logger)
    
    def get_latest_type(self) -> str:
        """获取最新源"""
        use_proxy = self.launcher_config.get('zero', {}).get('use_proxy', True)
        
        try:
            GithubDownload.GithubRequester.update_config(use_proxy)

            machine_last_update = GithubDownload.GithubRequester.get_latest_release("HZBHZB1234",
                                        "LCTA_auto_update").published_at

            machine_last_update = datetime.fromisoformat(machine_last_update.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            machine_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
        try:
            GithubDownload.GithubRequester.update_config(use_proxy)

            llc_last_update = GithubDownload.GithubRequester.get_latest_release("HZBHZB1234",
                                        "LCTA_auto_update").published_at

            llc_last_update = datetime.fromisoformat(llc_last_update.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            llc_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
        
        # 返回时间戳较新的版本类型
        return "machine" if llc_last_update < machine_last_update else "llc"
    
    def perform_update(self) -> Optional[str]:
        """根据时间戳选择执行哪个更新"""
        select_type = self.get_latest_type()
        if select_type == "machine":
            self.LCTA_AU_update.run()
        elif select_type == "llc":
            self.llc_update.run()
        else:
            return False
        
    def check_update(self) -> bool:
        logger.log('尝试进行检查')
        return True
        
    def update_config(self) -> bool:
        return True

class UpdateFactory:
    """更新工厂类，根据配置创建对应的更新对象"""
    
    @staticmethod
    def create_update(config: Dict[str, Any], logger: LogManager) -> UpdateBase:
        """根据配置创建更新对象"""
        update_type = config.get("work", {}).get("update", "no")
        
        if update_type == "llc":
            return LLCUpdate(logger)
        elif update_type == "ourplay":
            return OurPlayUpdate(logger)
        elif update_type == "LCTA-AU":
            return MachineUpdate(logger)
        elif update_type == "LO":
            return LOUpdate(logger)
        elif update_type == "LM-A":
            return LMAUpdate(logger)
        elif update_type == "LM-G":
            return LMGUpdate(logger)
        else:  # "no" or any other value
            return NoUpdate(logger)

def main_pre():
    global config_whole
    global logger
    global steam_argv
    # 使用 RotatingFileHandler 实现日志文件轮换，最大100KB，保留5个备份文件
    rotating_handler = RotatingFileHandler(".\\logs\\launcher.log", maxBytes=1024*100,
                                           backupCount=5, encoding='utf-8')
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            rotating_handler,
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

    steam_argv = os.getenv('steam_argv', '')

    config_whole = LoadUtils.load_config()
    
    if steam_argv == '':
        logger.log("unexpectedly missing steam_argv environment variable")
        logger.log("use path in config instead")
        
        steam_argv = config_whole.get("game_path", "")+'LimbusCompany.exe'
    logger.log(f"steam_argv: {steam_argv}")
    
    GithubDownload.init_request()
    
    # 使用工厂模式创建更新对象并执行更新
    update_obj = UpdateFactory.create_update(logger)
    update_obj.run()

def main_after_mod():
    from launcher.modfolder import get_mod_folder
    import launcher.patch as patch
    import launcher.sound as sound

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
        #atexit.register(cleanup_assets)
        logging.info("Detecting lunartique mods")
        patch.detect_lunartique_mods(mod_zips_root_path)
        tmp_asset_root = tempfile.mkdtemp()
        logging.info("Extracting mod assets to %s", tmp_asset_root)
        patch.extract_assets(tmp_asset_root, mod_zips_root_path)
        logging.info("Backing up data and patching assets....")
        patch.patch_assets(tmp_asset_root)
        patch.shutil.rmtree(tmp_asset_root)
        sound.replace_sound(mod_zips_root_path,steam_argv)
        logging.info("Starting game")
        subprocess.call(steam_argv)
        cleanup_assets()

    except Exception as e:
        logging.error("Error: %s", e)
        sys.exit(1)

def main_after_game():
    subprocess.call(steam_argv)

def main():
    try:
        main_pre()
    except Exception as e:
        if logger:
            logger.log_error(e)
        else:
            print(f"Error in main_pre: {e}")
    try:
        if config_whole.get("launcher", {}).get("work", {}).get("mod", False):
            main_after_mod()
        else:
            main_after_game()
    except Exception as e:
        if logger:
            logger.log_error(e)
        else:
            print(f"Error in main_after: {e}")
    if logger:
        logger.log('正常退出')

if __name__ == '__main__':
    main()