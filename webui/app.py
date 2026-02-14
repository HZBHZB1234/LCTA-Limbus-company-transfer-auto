import webview
import os
import sys
from pathlib import Path
import json
import socket
import time
import logging
from logging.handlers import TimedRotatingFileHandler
import shutil
import threading
import atexit
from contextlib import suppress
from typing import Optional, List, Dict, TYPE_CHECKING
if TYPE_CHECKING:
    from translatekit.base import TranslatorBase
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


import webFunc.GithubDownload as GithubDownload
from webutils.log_manage import LogManager
import webutils.load as load_util
import webutils.function_llc as function_llc
from webutils.functions import get_cache_font, get_steam_command, change_icon
from webutils.update import Updater, get_app_version
from webutils.const_apiConfig import (
    LLM_TRANSLATOR, TKIT_MACHINE, TKIT_MACHINE_OBJECT
)
from webutils.function_translate import translate_main
from webutils import *

class CancelRunning(Exception):
    pass

class LCTA_API():
    def __init__(self,logger:logging):
        self._window = None
        # 初始化日志管理器
        self.logger =logger
        self.log_manager = LogManager()
        self.log_manager.set_log_callback(self.logger.info)
        self.log_manager.set_error_callback(self.logger.exception)
        self.log_manager.set_ui_callback(self.log_ui)
        self.modal_list = []
        self.http_port = 0

        # 判断是否为打包环境
        self.is_frozen = os.getenv('is_frozen', 'false').lower() == 'true'
        self.log(f"当前运行环境: {'打包环境' if self.is_frozen else '开发环境'}")
        self.log(f"当前运行目录：{ os.getenv('path_') }")

        self.TKIT_MACHINE = TKIT_MACHINE
        self.TKIT_MACHINE_OBJECT = TKIT_MACHINE_OBJECT
        self.LLM_TRANSLATOR = LLM_TRANSLATOR
        self.set_function()
        self.init_config()

    def set_function(self):
        load_util.set_logger(self.log_manager)
        self.find_lcb = load_util.find_lcb
        self.load_config = load_util.load_config
        self.check_game_path = load_util.check_game_path
        self.validate_config = load_util.validate_config
        self.load_config_default = load_util.load_config_default
        self.fix_config = load_util.fix_config
        self.get_steam_command = get_steam_command
        self.change_icon = change_icon

    def run_func(self, func_name, *args):
        if hasattr(self, func_name):
            func = getattr(self, func_name)
            return func(*args)
        else:
            self.log(f"函数 {func_name} 不存在")
            return None
        
    def init_config(self):
        self.config = self.load_config()
        self.first_use = False
        if self.config is None:
            self.log("在初始化时未找到配置文件")
            self.config = self.load_config_default()
            if self.config is None:
                self.log("未知致命错误，理应不会触发，无法找到内置默认配置")
                return False
            else:
                try:
                    self.use_default()
                    self.log("已生成默认配置文件")
                    self.first_use = True
                except Exception as e:
                    self.log("生成默认配置文件时出现问题")
                    self.message_config=(["错误","生成默认配置文件时出现问题"])
                    self.log_error(e)
        self.config_ok, self.config_error = self.validate_config(self.config)
        if not self.config_ok:
            self.log("配置文件格式错误")
            self.log("\n".join(self.config_error))
        self.debug_mode = self.config.get('debug', False)

    def init_github(self):
        max_workers:str = self.config.get('github_max_workers', "4")
        timeout:str = self.config.get('github_timeout', "8")
        GithubDownload.init_request(
            max_workers=int(max_workers) if max_workers.isdigit() else 4,
            timeout=int(timeout) if timeout.isdigit() else 8
        )
        function_llc.font_assets_seven.proxys = GithubDownload.GithubRequester.proxy_manager
        function_llc.font_assets_raw.proxys = GithubDownload.GithubRequester.proxy_manager
    
    def init_cache(self):
        if self.config.get('enable_cache', False):
            os.makedirs(self.config.get('cache_path', ''), exist_ok=True)
            if self.config.get('game_path', ''):
                cache_path = Path(self.config.get('cache_path', '')) / 'ChineseFont.ttf'
                if not cache_path.exists():
                    shutil.copy2(get_cache_font(self.config, self.log_manager), cache_path)   

    def use_inner(self):
        """使用默认配置并保存"""
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

    def use_default(self):
        """使用内置默认配置并保存"""
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(self.load_config_default(), f, ensure_ascii=False, indent=4)
        self.log("已生成内置默认配置文件")
        
    def set_window(self, window):
        self._window = window

    def get_attr(self, attr_name):
        if hasattr(self, attr_name):
            return getattr(self, attr_name)

    def set_attr(self, attr_name, value):
        if hasattr(self, attr_name):
            setattr(self, attr_name, value)

    def browse_file(self, input_id):
        """打开文件浏览器"""
        file_path = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            save_filename='选择文件'
        )
        
        if file_path and len(file_path) > 0:
            selected_path = file_path[0]
            # 通过JavaScript更新页面中的输入框
            js_code = f"document.getElementById('{input_id}').value = '{selected_path.replace(os.sep, '/')}';"
            self._window.run_js(js_code)
            self.log_ui(f"已选择文件: {selected_path}")
            return selected_path
        return None

    def browse_folder(self, input_id):
        """打开文件夹浏览器"""
        folder_path = self._window.create_file_dialog(
            webview.FileDialog.FOLDER
        )
        
        if folder_path and len(folder_path) > 0:
            selected_path = folder_path[0]
            # 通过JavaScript更新页面中的输入框
            js_code = f"document.getElementById('{input_id}').value = '{selected_path.replace(os.sep, '/')}';"
            self._window.run_js(js_code)
            self.log_ui(f"已选择文件夹: {selected_path}")
            return selected_path
        return None
    
    def log(self,message):
        self.log_manager.log(message)
    
    def log_error(self, e):
        self.log_manager.log_error(e)
        
    def log_ui(self, message, level=logging.INFO):
        """UI日志方法"""
        # 添加时间戳
        timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
        full_message = f"{timestamp} {message}"
        
        # 通过JavaScript将日志消息发送到前端
        escaped_message = message.replace("'", "\\'").replace("\n", "\\n")
        js_code = f"addLogMessage('{escaped_message}');"
        try:
            self._window.run_js(js_code)
        except:
            # 如果窗口不可用则打印到控制台
            print(f"[UI] {full_message}")
        finally:
            self.log(full_message)


    def update_progress(self, percent, text):
        """更新进度"""
        escaped_text = text.replace("'", "\\'")
        js_code = f"updateProgress({percent}, '{escaped_text}');"
        try:
            self._window.run_js(js_code)
        except:
            pass

    def progress_callback(self, progress):
        """进度回调，用于下载等操作"""
        try:
            # 进度是0-100的数值
            self.update_progress(int(progress), f"进度: {int(progress)}%")
            return True  # 继续操作
        except:
            return True  # 即使出错也继续

    def add_modal_id(self, modal_id):
        self.log(f"添加模态窗口ID: {modal_id}")
        self.modal_list.append({
            "modal_id": modal_id,
            "running": "running"})
        return True

    def _check_modal_running(self, modal_id):
        return [i["running"] for i in self.modal_list if i["modal_id"] == modal_id][0]

    def _wait_continue(self, modal_id):
        while True:
            if self._check_modal_running(modal_id)=="pause":
                time.sleep(1)
            else:
                break

    def check_modal_running(self, modal_id, log=True):
        if log:
            self.log(f"检查模态窗口ID: {modal_id}")
        status = self._check_modal_running(modal_id)
        if status == "pause":
            self._wait_continue(modal_id)
        elif status == "cancel":
            raise CancelRunning
    def set_modal_running(self, modal_id, types="cancel"):
        self.log(f"设置模态窗口ID: {modal_id} 状态为 {types}")
        for i in self.modal_list:
            if i["modal_id"] == modal_id:
                i["running"] = str(types)
                break

    def del_modal_list(self, modal_id):
        self.log(f"删除模态窗口ID: {modal_id}")
        for times, i in enumerate(self.modal_list):
            if i["modal_id"] == modal_id:
                del self.modal_list[times]
                break

    # 以下为新添加的API方法，用于支持模态窗口功能
    def start_translation(self, translator_config: dict, modal_id= "false"):
        """开始翻译"""
        try:
            self.add_modal_log("开始翻译...", modal_id)
            translate_main(modal_id, self.log_manager,
                           self.config, translator_config,
                           formating_function=self.format_api_settings)
            self.add_modal_log("翻译完成", modal_id)
            return {"success": True, "message": "翻译完成"}
        except CancelRunning:
            self.log('用户已取消翻译流程')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def get_system_fonts(self):
        """获取系统已安装的字体列表"""
        try:
            result = get_system_fonts()
            return result
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"获取系统字体时出错: {str(e)}"}

    def get_translation_packages(self):
        '''获取翻译包列表'''
        try:
            # 从配置中获取汉化包目录，如果没有设置则使用当前工作目录
            target_dir = self.config.get("ui_default", {}).get("install", {}).get("package_directory", "")
            if not target_dir:
                target_dir = os.getcwd()
            packages = find_translation_packages(target_dir)
            self.log(f"找到 {len(packages)} 个翻译包")
            return {"success": True, "packages": packages}
        except Exception as e:
            self.log(f"获取翻译包列表失败: {str(e)}")
            self.logger.exception("获取翻译包列表失败")
            return {"success": False, "message": str(e)}

    def delete_translation_package(self, package_name):
        '''删除指定的翻译包'''
        try:
            # 从配置中获取汉化包目录，如果没有设置则使用当前工作目录
            target_path = self.config.get("ui_default", {}).get("install", {}).get("package_directory", "")
            if not target_path:
                target_path = os.getcwd()
            result = delete_translation_package(package_name, target_path, self.log_manager)
            if result["success"]:
                self.log(f"成功删除翻译包: {package_name}")
                return result
            else:
                self.log(f"删除翻译包失败: {result['message']}")
                return result
        except Exception as e:
            error_msg = f"删除翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception("删除翻译包时出错")
            return {"success": False, "message": error_msg}

    def install_translation(self, package_name=None, modal_id="false"):
        '''安装翻译包'''
        try:
            if package_name is None:
                self.log("开始安装翻译包")
                return {"success": False, "message": "传参错误"}
            
            # 获取游戏路径
            game_path = self.config.get("game_path", "")
            if not game_path:
                return {"success": False, "message": "请先设置游戏路径"}
                
            self.add_modal_log(f"开始安装汉化包: {package_name}", modal_id)
            
            # 从配置中获取汉化包目录，如果没有设置则使用当前工作目录
            package_dir = self.config.get("ui_default", {}).get("install", {}).get("package_directory", "")
            if not package_dir:
                package_dir = os.getcwd()
            
            # 构造完整包路径
            package_path = os.path.join(package_dir, package_name)
            
            # 调用安装函数
            success, message = install_translation_package(
                package_path, 
                game_path,
                logger_=self.log_manager,
                modal_id=modal_id
            )
            
            if success:
                return {"success": True, "message": message}
            else:
                return {"success": False, "message": message}
        except Exception as e:
            error_msg = f"安装翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}
        
    def toggle_installed_package(self, able):
        try:
            changed = toggle_install_package(self.config, able)
            return {"success": True, "changeed": changed}
        except Exception as e:
            self.log(f"切换可用状态失败: {str(e)}")
            self.logger.exception(e)
            return {"success": False, "message": str(e)}
        
    def get_installed_packages(self):
        '''获取翻译包列表'''
        try:
            enable = check_lang_enabled(self.config.get('game_path', ''))
            if not enable:
                return {"success": True, "enable": False}
            packages, selected = find_installed_packages(self.config)
            self.log(f"找到 {len(packages)} 个翻译包")
            return {"success": True, "packages": packages,
                    "selected": selected, 'enable': True}
        except Exception as e:
            self.log(f"获取翻译包列表失败: {str(e)}")
            self.logger.exception(e)
            return {"success": False, "message": str(e)}

    def delete_installed_package(self, package_name):
        '''删除指定的翻译包'''
        try:
            return delete_installed_package(package_name, self.config)
        except Exception as e:
            error_msg = f"删除翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}

    def use_translation(self, package_name=None, modal_id="false"):
        '''安装翻译包'''
        try:
            self.add_modal_log(f"开始切换汉化包: {package_name}", modal_id)
            # 调用安装函数
            success = use_translation_package(
                package_name, 
                self.config
            )
            if success:
                return {"success": True, "message": "成功切换汉化包"}
            else:
                return {"success": False, "message": "切换汉化包失败"}
        except Exception as e:
            error_msg = f"安装翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}
        
    def find_installed_mod(self):
        try:
            able, disable = fing_mod(self.config)
            return {"success": True, "able": able, "disable": disable}
        except Exception as e:
            error_msg = f"查找已安装mod出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}
        
    def toggle_mod(self, mod_name, enable):
        try:
            self.log_manager.log(f'修改mod可用性 {mod_name} 为 {enable}')
            changed = toggle_mod(self.config, mod_name, enable)
            return {"success": True, "changed": changed}
        except Exception as e:
            error_msg = f"切换mod出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}
        
    def delete_mod(self, mod_name, enable):
        try:
            self.log_manager.log(f'删除mod {mod_name} 状态 {enable}')
            success = delete_mod(self.config, mod_name, enable)
            return {"success": success, "message": ""}
        except Exception as e:
            error_msg = f"删除mod出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}
        
    def open_mod_path(self):
        try:
            self.log_manager.log('打开mod文件夹')
            open_mod_path(self.config)
            return {"success": True, "message": ""}
        except Exception as e:
            error_msg = f"打开mod路径出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}

    def change_font_for_package(self, package_name, font_path, modal_id="false"):
        '''为指定翻译包更换字体'''
        try:
            self.log(f"开始为翻译包 {package_name} 更换字体")
            result = change_font_for_package(package_name, font_path, self.log_manager, modal_id)
            if result[0]:  # 成功
                self.log(f"为翻译包 {package_name} 更换字体成功")
                return {"success": True, "message": result[1]}
            else:  # 失败
                self.log(f"为翻译包 {package_name} 更换字体失败: {result[1]}")
                return {"success": False, "message": result[1]}
        except Exception as e:
            error_msg = f"更换字体时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}

    def get_system_fonts_list(self):
        '''获取系统字体列表'''
        try:
            self.log("获取系统字体列表")
            result = get_system_fonts()
            if result["success"]:
                self.log(f"成功获取系统字体列表，共 {len(result['fonts'])} 个字体")
                return result
            else:
                self.log(f"获取系统字体列表失败: {result['message']}")
                return result
        except Exception as e:
            error_msg = f"获取系统字体列表时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}

    def export_selected_font(self, font_name, destination_path):
        '''导出选定的字体'''
        try:
            self.log(f"开始导出字体 {font_name} 到 {destination_path}")
            result = export_system_font(font_name, destination_path)
            if result["success"]:
                self.log(f"成功导出字体 {font_name}")
                return result
            else:
                self.log(f"导出字体 {font_name} 失败: {result['message']}")
                return result
        except Exception as e:
            error_msg = f"导出字体时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}

    def download_ourplay_translation(self, modal_id= "false"):
        """下载ourplay翻译"""
        try:
            self.add_modal_log("开始下载OurPlay汉化包...", modal_id)
            
            # 从配置中读取字体处理选项
            font_option = self.config.get("ui_default", {}).get("ourplay", {}).get("font_option", "keep")
            check_hash = self.config.get("ui_default", {}).get("ourplay", {}).get("check_hash", True)
            use_api = self.config.get("ui_default", {}).get("ourplay", {}).get("use_api", False)
            if use_api:
                function_ourplay_api(modal_id, self.log_manager, font_option=font_option, check_hash=check_hash)
            else:
                function_ourplay_main(modal_id, self.log_manager, font_option=font_option, check_hash=check_hash)
            
            self.add_modal_log("OurPlay汉化包下载成功", modal_id)
            return {"success": True, "message": "OurPlay汉化包下载成功"}
        except CancelRunning:
            self.log("ourplay下载任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"出现错误{e}，下载失败", modal_id)
            self.log_error(e)
            self.log_manager.update_modal_progress(0, "下载失败", modal_id)
            self.log_manager.log_modal_status("下载失败", modal_id)
            return {"success": False, "message": str(e)}

    def clean_cache(self, modal_id= "false", custom_files= [], clean_progress=None, clean_notice=None, clean_mods=None):
        """清理缓存"""
        try:
            self.add_modal_log("开始清除缓存...", modal_id)
            
            # 如果参数未从前端传递，则从配置中获取
            if clean_progress is None:
                clean_progress = self.config.get("ui_default", {}).get("clean", {}).get("clean_progress", False)
            if clean_notice is None:
                clean_notice = self.config.get("ui_default", {}).get("clean", {}).get("clean_notice", False)
            if clean_mods is None:
                clean_mods = self.config.get("ui_default", {}).get("clean", {}).get("clean_mods", False)
            
            if clean_mods:
                roaming_path = Path.home() / "AppData" / "Roaming"
                mods_path = roaming_path / "LimbusCompanyMods"
                custom_files.append(mods_path)
            
            # 调用清理函数
            clean_config_main(
                modal_id=modal_id,
                logger_=self.log_manager,
                clean_progress=clean_progress,
                clean_notice=clean_notice,
                custom_files=custom_files
            )
            
            self.add_modal_log("缓存清除成功", modal_id)
            return {"success": True, "message": "缓存清除成功"}
        except CancelRunning:
            self.log("清理任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"出现错误{e}，清理失败", modal_id)
            self.log_error(e)
            self.log_manager.update_modal_progress(0, "清理失败", modal_id)
            self.log_manager.log_modal_status("清理失败", modal_id)
            return {"success": False, "message": str(e)}

    def download_llc_translation(self, modal_id= "false"):
        """下载LLC翻译"""
        try:
            self.add_modal_log("开始下载零协汉化包...", modal_id)
            # 从配置中读取参数
            dump_default = self.config.get("ui_default", {}).get("zero", {}).get("dump_default", False)
            zip_type = self.config.get("ui_default", {}).get("zero", {}).get("zip_type", "zip")
            use_proxy = self.config.get("ui_default", {}).get("zero", {}).get("use_proxy", True)
            use_cache = self.config.get("ui_default", {}).get("zero", {}).get("use_cache", False)
            download_source = self.config.get("ui_default", {}).get("zero", {}).get("download_source", "github")
            cache_path = get_cache_font(self.config, self.log_manager)
            
            # 传递新参数给function_llc_main
            function_llc_main(
                modal_id, 
                self.log_manager, 
                dump_default=dump_default,
                download_source=download_source,
                from_proxy=use_proxy,
                zip_type=zip_type,
                use_cache=use_cache,
                cache_path=cache_path
            )
            self.add_modal_log("零协汉化包下载成功", modal_id)
            self.log_manager.log_modal_status("操作完成", modal_id)
            return {"success": True, "message": "零协汉化包下载成功"}
        except CancelRunning:
            self.log("llc下载任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"出现错误{e}，下载失败", modal_id)
            self.log_error(e)
            self.log_manager.update_modal_progress(0, "下载失败", modal_id)
            self.log_manager.log_modal_status("下载失败", modal_id)
            return {"success": False, "message": str(e)}
        
    def download_LCTA_auto(self, modal_id= "false"):
        """开始翻译"""
        try:
            self.add_modal_log("开始翻译...", modal_id)
            function_LCTA_auto_main(modal_id, self.log_manager,self.config)
            self.add_modal_log("翻译完成", modal_id)
            return {"success": True, "message": "翻译完成"}
        except CancelRunning:
            self.log('用户已取消翻译流程')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def fetch_proper_nouns(self, modal_id= "false"):
        """获取专有词汇"""
        try:
            self.add_modal_log("开始抓取专有词汇...", modal_id)
            proper_config = self.config.get('ui_default', {}).get('proper',{})
            function_fetch_main(
                modal_id,
                self.log_manager,
                **proper_config
            )
            self.add_modal_log("专有词汇抓取成功", modal_id)
            return {"success": True, "message": "专有词汇抓取成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}
        
    def format_api_settings(self, api_settings: dict, translator: 'TranslatorBase') -> dict:
        default_setting = translator.DEFAULT_API_KEY
        result_settings = default_setting.copy()
        for key, value in api_settings.items():
            if key in result_settings and value != "":
                result_settings[key] = value
        describe_settings = translator.DESCRIBE_API_KEY
        for i in describe_settings:
            setting_id = i.get('id')
            if setting_id in result_settings:
                setting_type = i.get('type')
                if setting_type == 'string':
                    result_settings[setting_id] = str(result_settings[setting_id])
                elif setting_type == 'number':
                    if isinstance(result_settings[setting_id], str):
                        if result_settings[setting_id].isdigit():
                            result_settings[setting_id] = int(result_settings[setting_id])
                        else:
                            result_settings[setting_id] = float(result_settings[setting_id])
        return result_settings
        
    def test_api(self, key: str, api_settings: dict) -> dict:
        """测试API密钥是否有效"""
        try:
            self.log(f"开始测试API密钥: {key}")
            translator: 'TranslatorBase' = self.TKIT_MACHINE[key]['translator']
            api_settings = self.format_api_settings(
                api_settings, translator)
            if not self.debug_mode:
                logger_c = logging.getLogger('translatekit')
                logger_c.setLevel(logging.INFO)
                self.log_manager.log('隐藏参数输出')
            translator = translator(
                api_setting=api_settings, debug_mode=True)
            if not self.debug_mode:
                logger_c.setLevel(logging.DEBUG)
            lang_dict = self.TKIT_MACHINE[key]['langCode']
            kr_result = translator.translate("안녕", lang_dict['kr'], lang_dict['zh']) if lang_dict['kr'] else '暂不支持该语言'
            en_result = translator.translate("Hello", lang_dict['en'], lang_dict['zh']) if lang_dict['en'] else '暂不支持该语言'
            jp_result = translator.translate("こんにちは", lang_dict['jp'], lang_dict['zh']) if lang_dict['jp'] else '暂不支持该语言'
            self.log("API密钥测试成功")
            result_dict = {
                'kr': kr_result,
                'en': en_result,
                'jp': jp_result
            }
            self.log(f'结果:{result_dict}')
            return {"success": True, "message": result_dict}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}
        
    def download_bubble(self, modal_id= "false"):
        """开始下载"""
        try:
            self.add_modal_log("开始下载...", modal_id)
            function_bubble_main(modal_id, self.log_manager,
                           self.config)
            self.add_modal_log("下载完成", modal_id)
            return {"success": True, "message": "下载完成"}
        except CancelRunning:
            self.log('用户已取消下载流程')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}
        
    def startTest(self):
        self._window_test = webview.create_window("模组下载测试窗口", url="https://www.nexusmods.com/games/limbuscompany")
        
    def eval_skip(self):
        self.log_manager.log('开始执行js')
        js_path = Path(os.getenv('path_')) / 'webui' / 'nexus'
        self._window_test.run_js(f"window.DICTIONARY_URL = 'http://127.0.0.1:{self.http_port}/nexus/dict.js'")
        #jss = list(js_path.glob('*.js'))
        jss = [js_path / 'simulation.js', js_path / 'dict.js', js_path / 'cn.js', js_path / 'skip.js']
        for i in jss:
            js_code = i.read_text(encoding='utf-8')
            self._window_test.run_js(js_code)
    
    def sign_eval_js(self):
        self.log_manager.log('已订阅事件')
        self._window_test.events.loaded += self.eval_skip

    # 模态窗口相关API方法
    def set_modal_status(self, status, modal_id):
        """设置模态窗口状态"""
        try:
            self.log(f"[{modal_id}] 状态变更{status}")
        except Exception:pass
        escaped_status = status.replace("'", "\\'").replace("\n", "\\n")
        if modal_id == 'false':
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === '{modal_id}');
        if (modal) {{
            modal.setStatus('{escaped_status}');
        }}
        """
        try:
            self._window.run_js(js_code)
        except Exception as e:
            self.log(f"设置模态窗口状态失败: {e}")
            self.log_error(e)

    def add_modal_log(self, message, modal_id):
        """向模态窗口添加日志"""
        try:
            self.log(f"[{modal_id}] {message}")
        except Exception:pass
        escaped_message = message.replace("'", "\\'").replace("\n", "\\n")
        if modal_id == "false":
            self.log_ui(escaped_message)
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === '{modal_id}');
        if (modal) {{
            modal.addLog('{escaped_message}');
        }}
        """
        try:
            self._window.run_js(js_code)
        except Exception as e:
            self.log(f"添加模态窗口日志失败: {e}")
            self.log_error(e)

    def update_modal_progress(self, percent, text, modal_id,log=True):
        """更新模态窗口进度"""
        try:
            if log:
                self.log(f"[{modal_id}] 进度变更至{percent}% 消息内容[{text}]")
        except Exception:pass
        escaped_text = text.replace("'", "\\'").replace("\n", "\\n")
        if modal_id == "false":
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === '{modal_id}');
        if (modal) {{
            modal.updateProgress({percent}, '{escaped_text}');
        }}
        """
        try:
            self._window.run_js(js_code)
        except Exception as e:
            self.log(f"更新模态窗口进度失败: {e}")
            self.log_error(e)

    def save_config_to_file(self):
        """将当前配置保存到文件"""
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            self.log_error(e)
            return False
        
    def save_setting_from(self):
        js_code = '''
                const updates = configManager.collectConfigFromUI();
    configManager.updateConfigValues(updates)
        .then(function(result) {
                configManager.flushPendingUpdates()
            });

            '''
        self._window.run_js(js_code)
    
    def update_config_value(self, key_path, value, create_missing=True):
        """
        更新配置中的特定值
        :param key_path: 配置键路径，例如 "ui_default.game_path" 
        :param value: 要设置的值
        :param create_missing: 是否创建缺失的键路径
        :return: 更新是否成功
        """
        try:
            keys = key_path.split('.')
            current = self.config
            
            # 遍历到倒数第二个键
            for key in keys[:-1]:
                if key not in current:
                    if create_missing:
                        current[key] = {}
                    else:
                        return False
                current = current[key]
                
                # 如果中间某个值不是字典，无法继续
                if not isinstance(current, dict):
                    self.log(f"无法设置配置值: {key_path} - 中间路径不是字典")
                    return False
            
            # 设置最终值
            final_key = keys[-1]
            current[final_key] = value
            
            # 立即保存到文件，减少前端请求
            self.save_config_to_file()
            return True
        except Exception as e:
            self.log(f"更新配置值时出错: {key_path} = {value}, 错误: {e}")
            self.log_error(e)
            return False
    
    def update_config_batch(self, config_updates):
        """
        批量更新配置
        :param config_updates: 字典，包含多个配置更新 {key_path: value, ...}
        :return: 批量更新是否成功
        """
        try:
            success_count = 0
            total_count = len(config_updates)
            
            for key_path, value in config_updates.items():
                if self.update_config_value(key_path, value, create_missing=True):
                    success_count += 1
            
            self.log(f"批量更新配置: 成功 {success_count}/{total_count} 项")
            return {"success": True, "updated": success_count, "total": total_count}
        except Exception as e:
            self.log(f"批量更新配置时出错: {e}")
            self.log_error(e)
            return {"success": False, "message": str(e)}
    
    def get_config_batch(self, key_paths):
        """
        批量获取配置值
        :param key_paths: 配置键路径列表，例如 ["ui_default.game_path", "debug"]
        :return: 字典，包含获取到的配置值
        """
        try:
            result = {}
            for key_path in key_paths:
                value = self.get_config_value(key_path)
                result[key_path] = value
            return {"success": True, "config_values": result}
        except Exception as e:
            self.log(f"批量获取配置值时出错: {e}")
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def get_config_value(self, key_path, default_value=None):
        """
        获取配置中的特定值
        :param key_path: 配置键路径，例如 "ui_default.game_path"
        :param default_value: 默认值
        :return: 配置值或默认值
        """
        try:
            keys = key_path.split('.')
            current = self.config
            
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default_value
                    
            return current
        except Exception as e:
            self.log(f"获取配置值时出错: {key_path}, 错误: {e}")
            self.log_error(e)
            return default_value

    def save_settings(self, game_path, debug_mode, auto_update):
        """保存设置"""
        try:
            # 更新配置
            self.config["game_path"] = game_path
            self.config["debug"] = debug_mode
            self.config["auto_check_update"] = auto_update
            
            # 保存到文件
            success = self.save_config_to_file()
            if not success:
                return {"success": False, "message": "保存配置文件失败"}
            
            self.log(f"设置已保存: 游戏路径={game_path}, 调试模式={debug_mode}")
            return {"success": True, "message": "设置保存成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"保存设置时出错: {str(e)}"}

    def use_default_config(self):
        """使用默认配置"""
        try:
            default_config = self.load_config_default()
            if default_config is None:
                return {"success": False, "message": "无法加载默认配置"}
            
            # 更新内存中的配置
            self.config = default_config
            
            # 保存到文件
            success = self.save_config_to_file()
            if not success:
                return {"success": False, "message": "保存配置文件失败"}
            
            self.log("已重置为默认配置")
            return {"success": True, "message": "已重置为默认配置"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"重置配置时出错: {str(e)}"}

    def reset_config(self):
        """重置配置"""
        try:
            # 删除现有配置文件
            if os.path.exists("config.json"):
                os.remove("config.json")
            
            # 重新加载默认配置
            default_config = self.load_config_default()
            if default_config is None:
                return {"success": False, "message": "无法加载默认配置"}
            
            # 更新内存中的配置
            self.config = default_config
            
            # 保存到文件
            success = self.save_config_to_file()
            if not success:
                return {"success": False, "message": "保存配置文件失败"}
            
            self.log("配置已重置")
            return {"success": True, "message": "配置已重置"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"重置配置时出错: {str(e)}"}

    def auto_check_update(self):
        """自动检查更新"""
        try:
            # 只有在配置允许时才检查更新
            if not self.config.get("auto_check_update", True):
                return {"has_update": False}
                
            self.current_version = get_app_version()
            self.log(f"当前版本: {self.current_version}")
            
            # 创建更新器实例，使用新配置
            updater = Updater(
                "HZBHZB1234", 
                "LCTA-Limbus-company-transfer-auto",
                delete_old_files=self.config.get("delete_updating", True),
                logger_=self.log_manager,
                use_proxy=self.config.get("update_use_proxy", True),
                only_stable=self.config.get("update_only_stable", False)
            )
            
            update_info = updater.check_for_updates(self.current_version)
            return update_info
        except Exception as e:
            self.log(f"检查更新时出错: {e}")
            self.log_error(e)
            return {"has_update": False}

    def manual_check_update(self):
        """手动检查更新"""
        try:                
            self.current_version = get_app_version()
            self.log(f"当前版本: {self.current_version}")
            
            # 创建更新器实例，使用新配置
            updater = Updater(
                "HZBHZB1234", 
                "LCTA-Limbus-company-transfer-auto",
                delete_old_files=self.config.get("delete_updating", True),
                logger_=self.log_manager,
                use_proxy=self.config.get("update_use_proxy", True),
                only_stable=self.config.get("update_only_stable", False)
            )
            
            update_info = updater.check_for_updates(self.current_version)
            return update_info
        except Exception as e:
            self.log(f"检查更新时出错: {e}")
            self.log_error(e)
            return {"has_update": False}

    def perform_update_in_modal(self, modal_id):
        """在模态窗口中执行更新"""
        try:
            self.add_modal_log("开始执行更新...", modal_id)
            
            if os.getenv('update') == False:
                self.add_modal_log("当前处于打包环境，跳过更新", modal_id)
                return 
    
            # 创建更新器实例，使用新配置
            updater = Updater(
                "HZBHZB1234", 
                "LCTA-Limbus-company-transfer-auto",
                delete_old_files=self.config.get("delete_updating", True),
                logger_=self.log_manager,
                use_proxy=self.config.get("update_use_proxy", True),
                only_stable=self.config.get("update_only_stable", False)
            )
            
            # 执行更新
            result = updater.check_and_update(self.current_version)
                
            return result
        except Exception as e:
            self.add_modal_log(f"更新失败：{e}", modal_id)
            self.log_error(e)
            return False

def setup_logging():
    """
    配置日志系统，使用TimedRotatingFileHandler按时间轮转日志
    """
    # 创建logs目录（如果不存在）
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # 配置日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # 使用TimedRotatingFileHandler按天轮转日志
    handler = TimedRotatingFileHandler(
        'logs/app.log', 
        when='midnight',     # 每天午夜轮转
        interval=1,          # 间隔1天
        encoding='utf-8',
        utc=False,           # 使用本地时间
        delay=False,
        atTime=None          # 午夜轮转
    )
    
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    # 添加处理器到记录器
    logger.addHandler(handler)
    
    return logger

def main():
    # 获取HTML文件的绝对路径
    html_path = os.path.join(os.getenv('path_'), "webui\\index.html")
    
    # 设置日志
    logger = setup_logging()
    logger.info("正在启动LCTA WebUI")
    

    # 创建API实例
    api = LCTA_API(logger)
    logger.info('API已创建')
    # 创建窗口 - 先创建窗口，不立即绑定API
    window = webview.create_window(
        "LCTA - 边狱公司汉化工具箱",
        url=html_path,
        width=1200,
        height=800,
        resizable=True,
        fullscreen=False,
        text_select=True,
        js_api=api
    )
    
    api.set_window(window)
    window.events.closed += api.save_setting_from
    atexit.register(api.save_config_to_file)
    # 设置模态窗口相关的回调
    api.log_manager.set_modal_callbacks(
        status_callback=api.set_modal_status,
        log_callback=api.add_modal_log,
        progress_callback=api.update_modal_progress,
        check_running=api.check_modal_running
    )
    
    logger.info("WebUI窗口已创建")

    debug_mode = api.config.get("debug", False)
    enable_storage = api.config.get('enable_storage', False)

    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    webview.settings['ALLOW_DOWNLOADS'] = True
    
    if not debug_mode:
        logger_c = logging.getLogger('urllib3.connectionpool')
        logger_c.setLevel(logging.INFO)

    if enable_storage:
        stPath = api.config.get('storage_path', 'tmp')
        webview.start(
            debug=debug_mode,
            http_server=True,
            storage_path=str(Path(stPath)),
            private_mode=False
        )
    else:
        webview.start(
            debug=debug_mode,
            http_server=True
        )

if __name__ == "__main__":
    main()