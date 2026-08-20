# -*- coding: utf-8 -*-
"""LCTA_API 核心管道：窗口/日志/模态窗口/文件选择/初始化。"""
import os
import json
import time
import logging
import shutil
import threading
import zipfile
from pathlib import Path
import webview

import webFunc.GithubDownload as GithubDownload
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
import webutils.load as load_util
import webutils.function_llc as function_llc
from webutils import open_explorer, evaluate_path, create_symlink_for, remove_symlink_for
from webutils.utils import get_cache_font, get_steam_command, change_icon
from webutils import get_steam_launcher_status, set_steam_launch_options, clear_steam_launch_options, start_game
from webutils.translator_constants import (
    LLM_TRANSLATOR, TKIT_MACHINE, TKIT_MACHINE_OBJECT
)
from resource_updater.web_api import ResourceUpdaterAPI, ServerSwitchAPI
from webui.app_api.exceptions import CancelRunning

_MODAL_WAIT_MAX_SECONDS = 300

class CoreMixin:

    @property
    def config(self):
        """提供 config 属性给前端 JS 通过 get_attr('config') 访问"""
        return ConfigManager().raw

    def __init__(self):
        self._window: webview.Window = None
        self.resource_updater_api = ResourceUpdaterAPI()
        self.server_switch_api = ServerSwitchAPI()
        # 初始化单例管理器
        self.log_manager = LogManager()
        ConfigManager()
        self.modal_list = []
        self._modal_lock = threading.Lock()
        self.http_port = 0

        # 判断是否为打包环境
        self.is_frozen = os.getenv('is_frozen', 'false').lower() == 'true'
        self.log(f"当前运行环境: {'打包环境' if self.is_frozen else '开发环境'}")
        self.log(f"当前运行目录：{ os.getenv('path_') }")
        self.debug = os.getenv('debug', '')

        self.TKIT_MACHINE = TKIT_MACHINE
        self.TKIT_MACHINE_OBJECT = TKIT_MACHINE_OBJECT
        self.LLM_TRANSLATOR = LLM_TRANSLATOR
        self.set_function()
        self.init_config()

    def set_function(self):
        self.find_lcb = load_util.find_lcb
        self.load_config = load_util.load_config
        self.check_game_path = load_util.check_game_path
        self.validate_config = load_util.validate_config
        self.load_config_default = load_util.load_config_default
        self.fix_config = load_util.fix_config
        self.get_steam_command = get_steam_command
        self.get_steam_launcher_status = get_steam_launcher_status
        self.set_steam_launch_options = set_steam_launch_options
        self.clear_steam_launch_options = clear_steam_launch_options
        self.start_game = start_game
        self.change_icon = change_icon
        self.open_explorer = open_explorer
        self.evaluate_path = evaluate_path
        self.create_symlink = create_symlink_for
        self.remove_symlink = remove_symlink_for

    def run_func(self, func_name, *args):
        if hasattr(self, func_name):
            func = getattr(self, func_name)
            return func(*args)
        else:
            self.log(f"函数 {func_name} 不存在")
            return None

    def init_config(self):
        self.first_use = False
        if not ConfigManager().from_disk:
            self.log("在初始化时未找到配置文件")
            ConfigManager().use_default()
            if not ConfigManager().raw:
                self.log("未知致命错误，理应不会触发，无法找到内置默认配置")
                return False
            else:
                try:
                    self.log("已生成默认配置文件")
                    self.first_use = True
                except Exception as e:
                    self.log("生成默认配置文件时出现问题")
                    self.message_config=(["错误","生成默认配置文件时出现问题"])
                    self.log_error(e)
        self.config_ok, self.config_error = ConfigManager().validate()
        if not self.config_ok:
            self.log("配置文件格式错误")
            self.log("\n".join(self.config_error))
        self.debug_mode = ConfigManager().get('debug', False)

    def init_github(self):
        max_workers:str = ConfigManager().get('github_max_workers', "4")
        timeout:str = ConfigManager().get('github_timeout', "8")
        GithubDownload.init_request(
            max_workers=int(max_workers) if max_workers.isdigit() else 4,
            timeout=int(timeout) if timeout.isdigit() else 8
        )
        function_llc.font_assets_seven.proxys = GithubDownload.GithubRequester.proxy_manager
        function_llc.font_assets_raw.proxys = GithubDownload.GithubRequester.proxy_manager

    def init_cache(self):
        if ConfigManager().get('enable_cache', False):
            os.makedirs(ConfigManager().get('cache_path', ''), exist_ok=True)
            if ConfigManager().get('game_path', ''):
                cache_path = Path(ConfigManager().get('cache_path', '')) / 'ChineseFont.ttf'
                if not cache_path.exists():
                    shutil.copy2(get_cache_font(), cache_path)

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
        last_version = str(ConfigManager().get('last_version', 'v1.0.0')).lstrip('vV')
        current_version = str(os.environ["__version__"]).lstrip('vV')
        if last_version != current_version:
            ConfigManager().set('last_version', os.environ["__version__"])
            update_note = (Path(__file__).resolve().parent.parent / 'assets' / 'update.md').read_text(encoding='utf-8').split('\n')
            r = []
            flag = False
            for i in update_note:
                if i.startswith('##'):
                    if flag:break
                    else:flag = True
                r.append(i)
            r = '\n'.join(r)
            return {'show': True, 'message': r}
        return {'show': False}

    def use_inner(self):
        """使用默认配置并保存"""
        ConfigManager().save()

    def use_default(self):
        """使用内置默认配置并保存"""
        ConfigManager().use_default()
        self.log("已生成内置默认配置文件")

    def set_window(self, window):
        self._window = window
        self.resource_updater_api.set_window(window)
        self.server_switch_api.set_window(window)

    def get_startup_data(self):
        """一次性返回启动所需的所有数据，减少多次 pywebview.api 桥接往返"""
        config = ConfigManager().raw
        config_ok = getattr(self, 'config_ok', True)
        return {
            'message_config': getattr(self, 'message_config', None),
            'first_use': getattr(self, 'first_use', False),
            'config_ok': config_ok,
            'config_error': getattr(self, 'config_error', []) if not config_ok else [],
            'config': config,
            'version': os.environ.get('__version__', ''),
        }

    def get_attr(self, attr_name):
        if hasattr(self, attr_name):
            return getattr(self, attr_name)

    def set_attr(self, attr_name, value):
        if hasattr(self, attr_name):
            # 防止对只读 @property 属性写入导致 AttributeError
            attr = getattr(type(self), attr_name, None)
            if isinstance(attr, property) and attr.fset is None:
                self.log(f"警告: 试图设置只读属性 '{attr_name}'，已忽略")
                return
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
            if input_id:
                js_code = f"document.getElementById({json.dumps(input_id, ensure_ascii=False)}).value = {json.dumps(selected_path.replace(os.sep, '/'), ensure_ascii=False)};"
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
            if input_id:
                js_code = f"document.getElementById({json.dumps(input_id, ensure_ascii=False)}).value = {json.dumps(selected_path.replace(os.sep, '/'), ensure_ascii=False)};"
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
        js_code = f"addLogMessage({json.dumps(message, ensure_ascii=False)});"
        try:
            self._window.run_js(js_code)
        except:
            # 如果窗口不可用则打印到控制台
            print(f"[UI] {full_message}")
        finally:
            self.log(full_message)

    def update_progress(self, percent, text):
        """更新进度"""
        js_code = f"updateProgress({percent}, {json.dumps(text, ensure_ascii=False)});"
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
            return True

    def add_modal_id(self, modal_id):
        self.log(f"添加模态窗口ID: {modal_id}")
        with self._modal_lock:
            self.modal_list.append({
                "modal_id": modal_id,
                "running": "running"})
        return True

    def _check_modal_running(self, modal_id):
        with self._modal_lock:
            matches = [i["running"] for i in self.modal_list if i["modal_id"] == modal_id]
        if not matches:
            return "running"  # modal 已被删除，当作正常状态
        return matches[0]

    def _wait_continue(self, modal_id):
        for _ in range(_MODAL_WAIT_MAX_SECONDS):
            status = self._check_modal_running(modal_id)
            if status == "cancel":
                raise CancelRunning
            if status != "pause":
                return
            time.sleep(1)
        # 超时兜底：最后再查一次，避免超时瞬间恰好处于 cancel
        if self._check_modal_running(modal_id) == "cancel":
            raise CancelRunning

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
        with self._modal_lock:
            for i in self.modal_list:
                if i["modal_id"] == modal_id:
                    i["running"] = str(types)
                    break

    def del_modal_list(self, modal_id):
        self.log(f"删除模态窗口ID: {modal_id}")
        with self._modal_lock:
            for times, i in enumerate(self.modal_list):
                if i["modal_id"] == modal_id:
                    del self.modal_list[times]
                    break

    def _make_cdn_callbacks(self, modal_id):
        """创建 CDN 进度回调三元组 (log_cb, progress_cb, cancel_check)"""
        def log_cb(msg):
            self.add_modal_log(msg, modal_id)

        def progress_cb(pct, msg):
            self.update_modal_progress(int(pct), msg, modal_id, log=False)
            self.check_modal_running(modal_id, log=False)

        def cancel_check():
            self.check_modal_running(modal_id, log=False)

        return log_cb, progress_cb, cancel_check

    def set_modal_status(self, status, modal_id):
        """设置模态窗口状态"""
        try:
            self.log(f"[{modal_id}] 状态变更{status}")
        except Exception:pass
        escaped_status = json.dumps(status, ensure_ascii=False)
        if modal_id == 'false':
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === {json.dumps(modal_id, ensure_ascii=False)});
        if (modal) {{
            modal.setStatus({escaped_status});
        }}
        """
        try:
            self._window.evaluate_js(js_code)
        except Exception as e:
            self.log(f"设置模态窗口状态失败: {e}")
            self.log_error(e)

    def add_modal_log(self, message, modal_id):
        """向模态窗口添加日志"""
        try:
            self.log(f"[{modal_id}] {message}")
        except Exception:pass
        escaped_message = json.dumps(message, ensure_ascii=False)
        if modal_id == "false":
            self.log_ui(message)
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === {json.dumps(modal_id, ensure_ascii=False)});
        if (modal) {{
            modal.addLog({escaped_message});
        }}
        """
        try:
            self._window.evaluate_js(js_code)
        except Exception as e:
            self.log(f"添加模态窗口日志失败: {e}")
            self.log_error(e)

    def update_modal_progress(self, percent, text, modal_id,log=True):
        """更新模态窗口进度"""
        try:
            percent = max(0, min(100, int(percent)))
        except (TypeError, ValueError, OverflowError):
            percent = 0
        try:
            if log:
                self.log(f"[{modal_id}] 进度变更至{percent}% 消息内容[{text}]")
        except Exception:pass
        escaped_text = json.dumps(text, ensure_ascii=False)
        if modal_id == "false":
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === {json.dumps(modal_id, ensure_ascii=False)});
        if (modal) {{
            modal.updateProgress({percent}, {escaped_text});
        }}
        """
        try:
            self._window.evaluate_js(js_code)
        except Exception as e:
            self.log(f"更新模态窗口进度失败: {e}")
            self.log_error(e)
