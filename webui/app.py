import webview
from webview.dom import DOMEventHandler
import os
import sys
from pathlib import Path
import json
import socket
import time
import logging
import ctypes
import shutil
import threading
import zipfile
import atexit
from functools import wraps
from contextlib import suppress
from typing import Optional, List, Dict, TYPE_CHECKING
from globalManagers.configManager import configManager
if TYPE_CHECKING:
    from translatekit.base import TranslatorBase
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from globalManagers.logManager import logManager
import webFunc.GithubDownload as GithubDownload
from webutils.log_manage import LogManager
import webutils.load as load_util
import webutils.function_llc as function_llc
from webutils.functions import get_cache_font, get_steam_command, change_icon, _move_folders
from webutils.update import Updater, get_app_version
from webutils.const_apiConfig import (
    LLM_TRANSLATOR, TKIT_MACHINE, TKIT_MACHINE_OBJECT
)
from webutils.function_translate import translate_main
from webutils import *


class CancelRunning(Exception):
    pass


class LCTA_API:
    def __init__(self):
        self._window: webview.Window = None
        self.modal_list = []
        self.http_port = 0

        # 判断是否为打包环境
        self.is_frozen = os.getenv('is_frozen', 'false').lower() == 'true'
        logManager.info(f"当前运行环境: {'打包环境' if self.is_frozen else '开发环境'}")
        logManager.info(f"当前运行目录：{os.getenv('path_')}")
        self.debug = os.getenv('debug', '')

        self.logger = logging.getLogger("LCTA_WEBUI")
        self.log_manager = LogManager()
        self.log_manager.set_log_callback(logManager.info)
        self.log_manager.set_error_callback(logManager.exception)
        self.log_manager.set_ui_callback(self.log_ui)
        self.log_manager.set_modal_callbacks(
            status_callback=self.set_modal_status,
            log_callback=self.add_modal_log,
            progress_callback=self.update_modal_progress,
            check_running=self.check_modal_running
        )

        self.current_files = []
        self.set_function()
        self._config = {}
        self.init_config()
        self.bindConst()

    def bindConst(self):
        self.TKIT_MACHINE = TKIT_MACHINE
        self.TKIT_MACHINE_OBJECT = TKIT_MACHINE_OBJECT
        self.LLM_TRANSLATOR = LLM_TRANSLATOR
        self.updateList = updateList
        self.bindRefer = bindRefer
        self.relyList = relyList

    def set_function(self):
        self.find_lcb = load_util.find_lcb
        self.load_config = load_util.load_config
        self.check_game_path = load_util.check_game_path
        self.validate_config = load_util.validate_config
        self.load_config_default = load_util.load_config_default
        self.fix_config = load_util.fix_config
        self.get_steam_command = get_steam_command
        self.change_icon = change_icon
        self.open_explorer = open_explorer
        self.evaluate_path = evaluate_path
        self.create_symlink = create_symlink_for
        self.remove_symlink = remove_symlink_for

    def start_func(self):
        print('加载函数')
        self._window.dom.document.events.dragenter += DOMEventHandler(LCTAapp.drag_in, True, True)
        self._window.dom.document.events.dragstart += DOMEventHandler(LCTAapp.drag_in, True, True)
        self._window.dom.document.events.dragover += DOMEventHandler(LCTAapp.drag_in, True, True, debounce=500)
        self._window.dom.document.events.drop += DOMEventHandler(LCTAapp.on_drop, True, True)
        self._window.events.closed += LCTAapp.save_setting_from

    @property
    def config(self):
        return self._config

    @config.setter
    def config(self, value):
        self._config = value
        configManager.config = value

    def processModalWrapper(self, processName=None):
        def wrapper(func):
            @wraps(func)
            def resultFunc(*args, modal_id=None, **kwargs):
                try:
                    logManager.ModalLog('已开始执行', modal_id)
                    if processName:
                        logManager.ModalLog(f"开始{processName}...", modal_id)
                    func(*args, modal_id=modal_id, config=self.config, **kwargs)
                    logManager.ModalLog("执行完毕", modal_id)
                    logManager.ModalLog(f"{processName}完成", modal_id)
                    return {"success": True, "message": f"{processName}完成"}
                except CancelRunning:
                    logManager.info('用户已取消流程')
                    self.del_modal_list(modal_id)
                    return {"success": False, "message": "已取消"}
                except Exception as e:
                    logManager.exception(e)
                    return {"success": False, "message": str(e)}
            return resultFunc
        return wrapper

    def _response(self, success: bool, message=None, **extra):
        result = {"success": success}
        if message is not None:
            result["message"] = message
        result.update(extra)
        return result

    def _execute_api(self, action, *, modal_id="false", process_name=None, cancel_message="已取消"):
        try:
            if process_name:
                self.add_modal_log(f"开始{process_name}...", modal_id)
            return action()
        except CancelRunning:
            self.log('用户已取消流程')
            self.del_modal_list(modal_id)
            return self._response(False, cancel_message)
        except Exception as e:
            self.log_error(e)
            return self._response(False, str(e))

    def _build_updater(self, modal_id=""):
        return Updater(
            "HZBHZB1234",
            "LCTA-Limbus-company-transfer-auto",
            delete_old_files=self.config.get("delete_updating", True),
            logger_=self.log_manager,
            use_proxy=self.config.get("update_use_proxy", True),
            only_stable=self.config.get("update_only_stable", False),
            modal_id=modal_id
        )

    def log(self, message, *args, **kwargs):
        logManager.info(message, *args, **kwargs)

    def log_error(self, error):
        logManager.exception(error)

    def log_ui(self, message):
        escaped_message = str(message).replace("'", "\\'").replace("\n", "\\n")
        if not self._window:
            return
        js_code = f"addLogMessage('{escaped_message}')"
        with suppress(Exception):
            self._window.evaluate_js(js_code)

    def run_func(self, func_name, *args):
        if hasattr(self, func_name):
            func = getattr(self, func_name)
            return func(*args)
        logManager.warn(f"函数 {func_name} 不存在")
        return None

    def init_config(self):
        try:
            configManager.loadConfig()
        except Exception as e:
            logManager.exception(e)
        self.config = configManager.config
        self.first_use = False
        if self.config is None:
            logManager.warn("在初始化时未找到配置文件")
            try:
                configManager.config = configManager.default
                configManager.save_config()
                self.config = configManager.default
                logManager.info("已生成默认配置文件")
                self.first_use = True
            except Exception as e:
                logManager.error("生成默认配置文件时出现问题")
                self.message_config = (["错误", "生成默认配置文件时出现问题"])
                logManager.exception(e)
        self.config_ok, self.config_error = configManager.validate_config()
        if not self.config_ok:
            logManager.warn("配置文件格式错误")
            logManager.warn("\n".join(self.config_error))

    def init_github(self):
        max_workers: str = self.config.get('github_max_workers', "4")
        timeout: str = self.config.get('github_timeout', "8")
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

    def init_log(self):
        for i in Path('logs').glob('app.log.*'):
            if i.name.endswith('.zip'):
                continue
            try:
                with zipfile.ZipFile((Path('logs') / f'{i.name}.zip'), 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(i, arcname=i.name)
                i.unlink()
            except Exception as e:
                self.log(f"压缩日志文件 {i} 时出错: {e}")
                self.log_error(e)

    def check_show(self):
        last_version = self.config.get('last_version', 'v1.0.0')
        if last_version != os.environ["__version__"]:
            self.config['last_version'] = os.environ["__version__"]
            update_note = (Path(__file__).parent / 'assets' / 'update.md').read_text(encoding='utf-8').split('\n')
            r = []
            flag = False
            for i in update_note:
                if i.startswith('##'):
                    if flag:
                        break
                    flag = True
                r.append(i)
            r = '\n'.join(r)
            r += '''\n<button class="primary-btn" onclick="goAndShow('elder');elderManager.initPage();">
    <i class="fas fa-play"></i>
    进入老年人模式来配置更新的内容
</button>
'''
            return {'show': True, 'message': r}
        return {'show': False}

    def resetElder(self):
        self.config['elder'] = configManager.config.get('elder', {})

    def get_attr(self, attr_name):
        if hasattr(self, attr_name):
            return getattr(self, attr_name)

    def set_attr(self, attr_name, value):
        if hasattr(self, attr_name):
            setattr(self, attr_name, value)

    def browse_file(self, input_id):
        file_path = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            save_filename='选择文件'
        )

        if file_path and len(file_path) > 0:
            selected_path = file_path[0]
            js_code = f"""document.getElementById('{input_id}').value = '{selected_path.replace(os.sep, '/')}';
            addLogMessage('已选择文件: {selected_path}')"""
            self._window.run_js(js_code)
            return selected_path
        return None

    def browse_folder(self, input_id):
        folder_path = self._window.create_file_dialog(
            webview.FileDialog.FOLDER
        )

        if folder_path and len(folder_path) > 0:
            selected_path = folder_path[0]
            js_code = f"""document.getElementById('{input_id}').value = '{selected_path.replace(os.sep, '/')}';
            addLogMessage('已选择文件夹: {selected_path}');"""
            self._window.run_js(js_code)
            return selected_path
        return None

    def add_modal_id(self, modal_id):
        logManager.info(f"添加模态窗口ID: {modal_id}")
        self.modal_list.append({
            "modal_id": modal_id,
            "running": "running"
        })
        return True

    def _check_modal_running(self, modal_id):
        return [i["running"] for i in self.modal_list if i["modal_id"] == modal_id][0]

    def _wait_continue(self, modal_id):
        while self._check_modal_running(modal_id) == "pause":
            time.sleep(1)

    def check_modal_running(self, modal_id, log=True):
        logManager.info(f"检查模态窗口ID: {modal_id}")
        status = self._check_modal_running(modal_id)
        if status == "pause":
            self._wait_continue(modal_id)
        elif status == "cancel":
            raise CancelRunning

    def set_modal_running(self, modal_id, types="cancel"):
        logManager.info(f"设置模态窗口ID: {modal_id} 状态为 {types}")
        for i in self.modal_list:
            if i["modal_id"] == modal_id:
                i["running"] = str(types)
                break

    def del_modal_list(self, modal_id):
        logManager.info(f"删除模态窗口ID: {modal_id}")
        for times, i in enumerate(self.modal_list):
            if i["modal_id"] == modal_id:
                del self.modal_list[times]
                break

    def start_translation(self, translator_config: dict, modal_id=None):
        os.environ['DUMP'] = str(self.config.get('ui_default', {}).get('translator', {})
                                .get('dump', False)).lower()
        translate_main(modal_id, self.log_manager,
                       self.config, translator_config,
                       formating_function=self.format_api_settings)

    def get_system_fonts(self):
        try:
            result = get_system_fonts()
            return result
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"获取系统字体时出错: {str(e)}"}

    def get_translation_packages(self):
        try:
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
        try:
            target_path = self.config.get("ui_default", {}).get("install", {}).get("package_directory", "")
            if not target_path:
                target_path = os.getcwd()
            result = delete_translation_package(package_name, target_path, self.log_manager)
            if result["success"]:
                self.log(f"成功删除翻译包: {package_name}")
                return result
            self.log(f"删除翻译包失败: {result['message']}")
            return result
        except Exception as e:
            error_msg = f"删除翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception("删除翻译包时出错")
            return {"success": False, "message": error_msg}

    def install_translation(self, package_name=None, modal_id="false"):
        try:
            if package_name is None:
                self.log("开始安装翻译包")
                return {"success": False, "message": "传参错误"}

            game_path = self.config.get("game_path", "")
            if not game_path:
                return {"success": False, "message": "请先设置游戏路径"}

            self.add_modal_log(f"开始安装汉化包: {package_name}", modal_id)

            package_dir = self.config.get("ui_default", {}).get("install", {}).get("package_directory", "")
            if not package_dir:
                package_dir = os.getcwd()

            package_path = os.path.join(package_dir, package_name)
            success, message = install_translation_package(
                package_path,
                game_path,
                logger_=self.log_manager,
                modal_id=modal_id
            )

            if success:
                return {"success": True, "message": message}
            return {"success": False, "message": message}
        except Exception as e:
            error_msg = f"安装翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}

    def toggle_installed_package(self, able):
        try:
            changed = toggle_install_package(self.config, able)
            return {"success": True, "changed": changed}
        except Exception as e:
            self.log(f"切换可用状态失败: {str(e)}")
            self.logger.exception(e)
            return {"success": False, "message": str(e)}

    def get_installed_packages(self):
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
        try:
            return delete_installed_package(package_name, self.config)
        except Exception as e:
            error_msg = f"删除翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}

    def use_translation(self, package_name=None, modal_id="false"):
        try:
            self.add_modal_log(f"开始切换汉化包: {package_name}", modal_id)
            success = use_translation_package(package_name, self.config)
            if success:
                return {"success": True, "message": "成功切换汉化包"}
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

    def get_symlink_status(self):
        try:
            result = check_symlink()
            return {"success": True, "status": result}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def move_folders(self, from_path: str, target_path: str):
        frPath = Path(from_path)
        user32 = ctypes.windll.user32
        paths = [[str(i)[idx:] for idx, letter in enumerate(str(i)) if letter.isalpha()][0]
                 for i in frPath.iterdir()]
        return _move_folders(
            paths, target_path,
            hwnd=user32.FindWindowW(None, 'LCTA - 边狱公司汉化工具箱'))

    def change_font_for_package(self, package_name, font_path, modal_id="false"):
        try:
            self.log(f"开始为翻译包 {package_name} 更换字体")
            result = change_font_for_package(package_name, font_path, self.log_manager, modal_id)
            if result[0]:
                self.log(f"为翻译包 {package_name} 更换字体成功")
                return {"success": True, "message": result[1]}
            self.log(f"为翻译包 {package_name} 更换字体失败: {result[1]}")
            return {"success": False, "message": result[1]}
        except Exception as e:
            error_msg = f"更换字体时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}

    def get_system_fonts_list(self):
        try:
            self.log("获取系统字体列表")
            result = get_system_fonts()
            if result["success"]:
                self.log(f"成功获取系统字体列表，共 {len(result['fonts'])} 个字体")
                return result
            self.log(f"获取系统字体列表失败: {result['message']}")
            return result
        except Exception as e:
            error_msg = f"获取系统字体列表时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}

    def export_selected_font(self, font_name, destination_path):
        try:
            self.log(f"开始导出字体 {font_name} 到 {destination_path}")
            result = export_system_font(font_name, destination_path, self.log_manager)
            if result["success"]:
                self.log(f"成功导出字体 {font_name}")
                return result
            self.log(f"导出字体 {font_name} 失败: {result['message']}")
            return result
        except Exception as e:
            error_msg = f"导出字体时出错: {str(e)}"
            self.log(error_msg)
            self.logger.exception(e)
            return {"success": False, "message": error_msg}

    def download_ourplay_translation(self, modal_id="false"):
        def action():
            font_option = self.config.get("ui_default", {}).get("ourplay", {}).get("font_option", "keep")
            check_hash = self.config.get("ui_default", {}).get("ourplay", {}).get("check_hash", True)
            use_api = self.config.get("ui_default", {}).get("ourplay", {}).get("use_api", False)
            if use_api:
                function_ourplay_api(modal_id, self.log_manager, font_option=font_option, check_hash=check_hash)
            else:
                function_ourplay_main(modal_id, self.log_manager, font_option=font_option, check_hash=check_hash)
            self.add_modal_log("OurPlay汉化包下载成功", modal_id)
            return self._response(True, "OurPlay汉化包下载成功")

        return self._execute_api(action, modal_id=modal_id, process_name="下载OurPlay汉化包")

    def clean_cache(self, modal_id="false", custom_files=[], clean_progress=None, clean_notice=None, clean_mods=None):
        def action():
            nonlocal custom_files, clean_progress, clean_notice, clean_mods
            if clean_progress is None:
                clean_progress = self.config.get("ui_default", {}).get("clean", {}).get("clean_progress", False)
            if clean_notice is None:
                clean_notice = self.config.get("ui_default", {}).get("clean", {}).get("clean_notice", False)
            if clean_mods is None:
                clean_mods = self.config.get("ui_default", {}).get("clean", {}).get("clean_mods", False)

            files_to_clean = list(custom_files)
            if clean_mods:
                roaming_path = Path.home() / "AppData" / "Roaming"
                files_to_clean.append(roaming_path / "LimbusCompanyMods")

            clean_config_main(
                modal_id=modal_id,
                logger_=self.log_manager,
                clean_progress=clean_progress,
                clean_notice=clean_notice,
                custom_files=files_to_clean
            )
            self.add_modal_log("缓存清除成功", modal_id)
            return self._response(True, "缓存清除成功")

        return self._execute_api(action, modal_id=modal_id, process_name="清理缓存")

    def get_fancy_rulesets(self):
        return {'success': True, 'data': {
            'builtin': builtinFancyConfig,
            'user': json.loads(self.config.get('user_fancy', [])),
            'enabled': json.loads(self.config.get('fancy_allow',
                 "{\"技能文本美化(FL Like)\": true,\"气泡文本渐变(FL Like)\": true,\"EGO文本渐变(FL Like)\": true}"))
        }}

    def download_llc_translation(self, modal_id="false"):
        def action():
            dump_default = self.config.get("ui_default", {}).get("zero", {}).get("dump_default", False)
            zip_type = self.config.get("ui_default", {}).get("zero", {}).get("zip_type", "zip")
            use_proxy = self.config.get("ui_default", {}).get("zero", {}).get("use_proxy", True)
            use_cache = self.config.get("ui_default", {}).get("zero", {}).get("use_cache", False)
            download_source = self.config.get("ui_default", {}).get("zero", {}).get("download_source", "github")
            cache_path = get_cache_font(self.config, self.log_manager)

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
            self.log_manager.log_modal_status("操作完成", modal_id)
            return self._response(True, "零协汉化包下载成功")

        return self._execute_api(action, modal_id=modal_id, process_name="下载零协汉化包")

    def download_LCTA_auto(self, modal_id="false"):
        def action():
            function_LCTA_auto_main(modal_id, self.log_manager, self.config)
            return self._response(True, "翻译完成")

        return self._execute_api(action, modal_id=modal_id, process_name="翻译")

    def fancy_main(self, config_list, enableMap):
        try:
            gamePath = self.config['game_path']
            lang_path = Path(gamePath) / 'LimbusCompany_Data' / 'lang'
            config_lang = json.loads((lang_path / 'config.json').read_text(encoding='utf-8')).get('lang', '')
        except Exception as e:
            self.logger.exception(e)
            raise RuntimeError('获取当前安装汉化包失败')
        fancy_main(gamePath, config_lang, [i for i in config_list if enableMap.get(i.get('name', ''), False)])

    def fetch_proper_nouns(self, modal_id="false"):
        def action():
            proper_config = self.config.get('ui_default', {}).get('proper', {})
            function_fetch_main(
                modal_id,
                self.log_manager,
                **proper_config
            )
            return self._response(True, "专有词汇抓取成功")

        return self._execute_api(action, modal_id=modal_id, process_name="抓取专有词汇")

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
        try:
            self.log(f"开始测试API密钥: {key}")
            translator: 'TranslatorBase' = self.TKIT_MACHINE[key]['translator']
            api_settings = self.format_api_settings(api_settings, translator)
            if not self.debug_mode:
                logger_c = logging.getLogger('translatekit')
                logger_c.setLevel(logging.INFO)
                self.log_manager.log('隐藏参数输出')
            translator = translator(api_setting=api_settings, debug_mode=True)
            if not self.debug_mode:
                logger_c.setLevel(logging.DEBUG)
            lang_dict = self.TKIT_MACHINE[key]['langCode']
            kr_result = translator.translate("안녕", lang_dict['kr'], lang_dict['zh']) if lang_dict['kr'] else '暂不支持该语言'
            en_result = translator.translate("Hello", lang_dict['en'], lang_dict['zh']) if lang_dict['en'] else '暂不支持该语言'
            jp_result = translator.translate("こんにちは", lang_dict['jp'], lang_dict['zh']) if lang_dict['jp'] else '暂不支持该语言'
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

    def download_bubble(self, modal_id="false"):
        def action():
            function_bubble_main(modal_id, self.log_manager, self.config)
            return self._response(True, "下载完成")

        return self._execute_api(action, modal_id=modal_id, process_name="下载气泡文本")

    def startTest(self):
        self._window_test = webview.create_window("模组下载测试窗口", url="https://www.nexusmods.com/games/limbuscompany")

    def eval_skip(self):
        self.log_manager.log('开始执行js')
        js_path = Path(os.getenv('path_')) / 'webui' / 'nexus'
        self._window_test.run_js(f"window.DICTIONARY_URL = 'http://127.0.0.1:{self.http_port}/nexus/dict.js'")
        jss = [js_path / 'simulation.js', js_path / 'dict.js', js_path / 'cn.js', js_path / 'skip.js']
        for i in jss:
            js_code = i.read_text(encoding='utf-8')
            self._window_test.run_js(js_code)

    def sign_eval_js(self):
        self.log_manager.log('已订阅事件')
        self._window_test.events.loaded += self.eval_skip

    def set_modal_status(self, status, modal_id):
        try:
            self.log(f"[{modal_id}] 状态变更{status}")
        except Exception:
            pass
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
            self._window.evaluate_js(js_code)
        except Exception as e:
            self.log(f"设置模态窗口状态失败: {e}")
            self.log_error(e)

    def add_modal_log(self, message, modal_id):
        try:
            self.log(f"[{modal_id}] {message}")
        except Exception:
            pass
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
            self._window.evaluate_js(js_code)
        except Exception as e:
            self.log(f"添加模态窗口日志失败: {e}")
            self.log_error(e)

    def update_modal_progress(self, percent, text, modal_id, log=True):
        try:
            if log:
                self.log(f"[{modal_id}] 进度变更至{percent}% 消息内容[{text}]")
        except Exception:
            pass
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
            self._window.evaluate_js(js_code)
        except Exception as e:
            self.log(f"更新模态窗口进度失败: {e}")
            self.log_error(e)

    def save_config_to_file(self):
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
        try:
            keys = key_path.split('.')
            current = self.config

            for key in keys[:-1]:
                if key not in current:
                    if create_missing:
                        current[key] = {}
                    else:
                        return False
                current = current[key]

                if not isinstance(current, dict):
                    self.log(f"无法设置配置值: {key_path} - 中间路径不是字典")
                    return False

            final_key = keys[-1]
            current[final_key] = value
            self.save_config_to_file()
            return True
        except Exception as e:
            self.log(f"更新配置值时出错: {key_path} = {value}, 错误: {e}")
            self.log_error(e)
            return False

    def update_config_batch(self, config_updates):
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
        try:
            self.config["game_path"] = game_path
            self.config["debug"] = debug_mode
            self.config["auto_check_update"] = auto_update

            success = self.save_config_to_file()
            if not success:
                return {"success": False, "message": "保存配置文件失败"}

            self.log(f"设置已保存: 游戏路径={game_path}, 调试模式={debug_mode}")
            return {"success": True, "message": "设置保存成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"保存设置时出错: {str(e)}"}

    def use_default_config(self):
        try:
            default_config = self.load_config_default()
            if default_config is None:
                return {"success": False, "message": "无法加载默认配置"}

            self.config = default_config

            success = self.save_config_to_file()
            if not success:
                return {"success": False, "message": "保存配置文件失败"}

            self.log("已重置为默认配置")
            return {"success": True, "message": "已重置为默认配置"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"重置配置时出错: {str(e)}"}

    def reset_config(self):
        try:
            if os.path.exists("config.json"):
                os.remove("config.json")

            default_config = self.load_config_default()
            if default_config is None:
                return {"success": False, "message": "无法加载默认配置"}

            self.config = default_config

            success = self.save_config_to_file()
            if not success:
                return {"success": False, "message": "保存配置文件失败"}

            self.log("配置已重置")
            return {"success": True, "message": "配置已重置"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"重置配置时出错: {str(e)}"}

    def auto_check_update(self):
        try:
            if not self.config.get("auto_check_update", True):
                return {"has_update": False}

            self.current_version = get_app_version()
            self.log(f"当前版本: {self.current_version}")
            updater = self._build_updater()
            return updater.check_for_updates(self.current_version)
        except Exception as e:
            self.log(f"检查更新时出错: {e}")
            self.log_error(e)
            return {"has_update": False}

    def manual_check_update(self):
        try:
            self.current_version = get_app_version()
            self.log(f"当前版本: {self.current_version}")
            updater = self._build_updater()
            return updater.check_for_updates(self.current_version)
        except Exception as e:
            self.log(f"检查更新时出错: {e}")
            self.log_error(e)
            return {"has_update": False}

    def perform_update_in_modal(self, modal_id):
        def action():
            if os.getenv('update') == False:
                self.add_modal_log("当前处于打包环境，跳过更新", modal_id)
                return False
            updater = self._build_updater(modal_id=modal_id)
            return updater.check_and_update(self.current_version)

        return self._execute_api(action, modal_id=modal_id, process_name="更新程序", cancel_message="更新已取消")

    def handle_dropped_files(self):
        files_data = self.current_files
        self.current_files = []
        file_info = {file: evalFile(file) for file in files_data}
        message = makeMessage(file_info)
        if message == 'invalid':
            return {"success": False, "message": "禁止同时进行更新与其他操作"}
        if message == 'none':
            return {"success": False, "message": "无文件"}
        return {"success": True, "message": message, "file_info": file_info}

    def drag_in(self, e):
        print("drag in")

    def on_drop(self, e):
        files = e['dataTransfer']['files']
        self.current_files = [file['pywebviewFullPath'] for file in files]
        self._window.evaluate_js("dragDropManager.hideMask();dragDropManager.onFileDropCallback()")

        print(f'Event: {e["type"]}. Dropped files:')
        for file in files:
            print(file.get('pywebviewFullPath'))

    def eval_dropped_files(self, files_data, modal_id="false"):
        evalFiles(files_data, self.config, self.log_manager, modal_id)
        return {"success": True, "message": "安装完成"}


LCTAapp = LCTA_API()
