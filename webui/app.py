import webview
import os
import sys
from pathlib import Path
import json
import time
import logging
from logging.handlers import RotatingFileHandler
import shutil
import threading
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


import webutils
from webutils.log_h import LogManager
import webutils.load as load_util
from webutils.update import Updater, get_app_version
from webutils import function_llc_main

class CancelRunning(Exception):
    pass

class LCTA_API():
    def __init__(self,logger:logging):
        self._window = None
        self.game_path = None
        # 初始化日志管理器
        self.logger =logger
        self.log_manager = LogManager()
        self.log_manager.set_log_callback(self.logger.info)
        self.log_manager.set_error_callback(self.logger.exception)
        self.log_manager.set_ui_callback(self.log_ui)
        self.message_list = []
        self.modal_list = []

        # 判断是否为打包环境
        self.is_frozen = os.getenv('is_frozen', 'false').lower() == 'true'
        self.log(f"当前运行环境: {'打包环境' if self.is_frozen else '开发环境'}")
        self.log(f"当前运行目录：{ os.getenv('path_') }")

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

    def run_func(self, func_name, *args):
        if hasattr(self, func_name):
            func = getattr(self, func_name)
            return func(*args)
        else:
            self.log(f"函数 {func_name} 不存在")
            return None
        
    def init_config(self):
        self.config = self.load_config()
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
                    self.message_list.append(["提示","配置文件不存在，已生成默认配置文件"])
                except Exception as e:
                    self.log("生成默认配置文件时出现问题")
                    self.message_list.append(["错误","生成默认配置文件时出现问题"])
                    self.log_error(e)
        self.config_ok, self.config_error = self.validate_config(self.config)
        if not self.config_ok:
            self.log("配置文件格式错误")
            self.log("\n".join(self.config_error))

    
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
            self._window.evaluate_js(js_code)
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
            self._window.evaluate_js(js_code)
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
            self._window.evaluate_js(js_code)
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
            self._window.evaluate_js(js_code)
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
        self.modal_list.append({
            "modal_id": modal_id,
            "running": "running"})
        return True

    def _check_modal_running(self, modal_id):
        return [i["running"] for i in self.modal_list if i["modal_id"] == modal_id][0]

    def _wait_continue(self, modal_id):
        while True:
            if self._check_modal_running(self, modal_id)=="pause":
                time.sleep(1)
            else:
                break

    def check_modal_running(self, modal_id):
        status = self._check_modal_running(self, modal_id)
        if status == "cancel":
            raise CancelRunning
        elif status == "pause":
            self._wait_continue(self, modal_id)
    def set_modal_running(self, modal_id, types="cancel"):
        for i in self.modal_list:
            if i["modal_id"] == modal_id:
                i["running"] = str(types)
                break

    def del_modal_list(self, modal_id):
        for times, i in enumerate(self.modal_list):
            if i["modal_id"] == modal_id:
                del self.modal_list[times]
                break

    # 以下为新添加的API方法，用于支持模态窗口功能
    def start_translation(self, modal_id= "false"):
        """开始翻译"""
        try:
            # 这里应该调用实际的翻译逻辑
            self.add_modal_log("开始翻译...", modal_id)
            time.sleep(2)  # 模拟翻译过程
            self.add_modal_log("翻译完成", modal_id)
            return {"success": True, "message": "翻译完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def install_translation(self, modal_id= "false"):
        """安装翻译"""
        try:
            self.add_modal_log("开始安装汉化包...", modal_id)
            time.sleep(1)  # 模拟安装过程
            self.add_modal_log("汉化包安装成功", modal_id)
            return {"success": True, "message": "汉化包安装成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def download_ourplay_translation(self, modal_id= "false"):
        """下载ourplay翻译"""
        try:
            self.add_modal_log("开始下载OurPlay汉化包...", modal_id)
            time.sleep(1)  # 模拟下载过程
            self.add_modal_log("OurPlay汉化包下载成功", modal_id)
            return {"success": True, "message": "OurPlay汉化包下载成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def clean_cache(self, modal_id= "false"):
        """清理缓存"""
        try:
            self.add_modal_log("开始清除缓存...", modal_id)
            time.sleep(1)  # 模拟清理过程
            self.add_modal_log("缓存清除成功", modal_id)
            return {"success": True, "message": "缓存清除成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def download_llc_translation(self, modal_id= "false"):
        """下载LLC翻译"""
        try:
            self.add_modal_log("开始下载零协汉化包...", modal_id)
            function_llc_main(modal_id, self.log_manager)
            self.add_modal_log("零协汉化包下载成功", modal_id)
            return {"success": True, "message": "零协汉化包下载成功"}
        except CancelRunning:
            self.log("llc下载任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已暂停"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def save_api_config(self, modal_id= "false"):
        """保存API配置"""
        try:
            self.add_modal_log("正在保存API配置...", modal_id)
            time.sleep(1)  # 模拟保存过程
            self.add_modal_log("API配置保存成功", modal_id)
            return {"success": True, "message": "API配置保存成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def fetch_proper_nouns(self, modal_id= "false"):
        """获取专有词汇"""
        try:
            self.add_modal_log("开始抓取专有词汇...", modal_id)
            time.sleep(1)  # 模拟抓取过程
            self.add_modal_log("专有词汇抓取成功", modal_id)
            return {"success": True, "message": "专有词汇抓取成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def search_text(self, modal_id= "false"):
        """搜索文本"""
        try:
            self.add_modal_log("开始文本搜索...", modal_id)
            time.sleep(1)  # 模拟搜索过程
            self.add_modal_log("文本搜索完成", modal_id)
            return {"success": True, "message": "文本搜索完成", "results": []}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def backup_text(self, modal_id= "false"):
        """备份文本"""
        try:
            self.add_modal_log("开始备份原文...", modal_id)
            time.sleep(1)  # 模拟备份过程
            self.add_modal_log("原文备份成功", modal_id)
            return {"success": True, "message": "原文备份成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def manage_fonts(self, modal_id= "false"):
        """管理字体"""
        try:
            self.add_modal_log("开始管理字体...", modal_id)
            time.sleep(1)  # 模拟管理过程
            self.add_modal_log("字体管理完成", modal_id)
            return {"success": True, "message": "字体管理完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def manage_images(self, modal_id= "false"):
        """管理图片"""
        try:
            self.add_modal_log("开始管理图片...", modal_id)
            time.sleep(1)  # 模拟管理过程
            self.add_modal_log("图片管理完成", modal_id)
            return {"success": True, "message": "图片管理完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def manage_audio(self, modal_id= "false"):
        """管理音频"""
        try:
            self.add_modal_log("开始管理音频...", modal_id)
            time.sleep(1)  # 模拟管理过程
            self.add_modal_log("音频管理完成", modal_id)
            return {"success": True, "message": "音频管理完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def adjust_image(self, modal_id):
        """调整图片"""
        try:
            self.add_modal_log("开始调整图片...", modal_id)
            time.sleep(1)  # 模拟调整过程
            self.add_modal_log("图片调整完成", modal_id)
            return {"success": True, "message": "图片调整完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def calculate_gacha(self, modal_id= "false"):
        """计算抽卡概率"""
        try:
            self.add_modal_log("开始计算抽卡概率...", modal_id)
            time.sleep(1)  # 模拟计算过程
            self.add_modal_log("抽卡概率计算完成", modal_id)
            return {"success": True, "message": "抽卡概率计算完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    # 模态窗口相关API方法
    def set_modal_status(self, status, modal_id):
        """设置模态窗口状态"""
        try:
            self.log(f"{modal_id} 状态变更{status}")
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
            self._window.evaluate_js(js_code)
        except Exception as e:
            self.log_error(f"设置模态窗口状态失败: {e}")

    def add_modal_log(self, message, modal_id):
        """向模态窗口添加日志"""
        try:
            self.log(f"{modal_id} {message}")
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
            self._window.evaluate_js(js_code)
        except Exception as e:
            self.log_error(f"添加模态窗口日志失败: {e}")

    def update_modal_progress(self, percent, text, modal_id):
        """更新模态窗口进度"""
        try:
            self.log(f"{modal_id} 进度变更{percent}% 消息{text}")
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
            self._window.evaluate_js(js_code)
        except Exception as e:
            self.log_error(f"更新模态窗口进度失败: {e}")


    def get_game_path(self):
        """获取游戏路径"""
        if self.config and "game_path" in self.config:
            return self.config["game_path"]
        return ""

    def save_config_to_file(self):
        """将当前配置保存到文件"""
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            self.log_error(e)
            return False
    
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
            return True
        except Exception as e:
            self.log_error(f"更新配置值时出错: {key_path} = {value}, 错误: {e}")
            return False

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
            self.log_error(f"获取配置值时出错: {key_path}, 错误: {e}")
            return default_value

    def save_settings(self, game_path, debug_mode):
        """保存设置"""
        try:
            # 更新配置
            self.config["game_path"] = game_path
            self.config["debug"] = debug_mode
            
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
            
            # 创建更新器实例
            updater = Updater("HZBHZB1234", "LCTA-Limbus-company-transfer-auto", 
                             self.config.get("delete_updating", True), self.log)
            
            update_info = updater.check_for_updates(self.current_version)
            return update_info
        except Exception as e:
            self.log_error(f"检查更新时出错: {e}")
            return {"has_update": False}

    def perform_update_in_modal(self, modal_id):
        """在模态窗口中执行更新"""
        try:
            self.add_modal_log("开始执行更新...", modal_id)
            
            if os.getenv('update') == False:
                self.add_modal_log("当前处于打包环境，跳过更新", modal_id)
                return 
    
            # 创建更新器实例
            updater = Updater("HZBHZB1234", "LCTA-Limbus-company-transfer-auto", 
                             self.config.get("delete_updating", True), 
                             lambda msg: self.add_modal_log(msg, modal_id))
            
            # 执行更新
            result = updater.check_and_update(self.current_version)
            
            if result:
                self.add_modal_log("更新完成，即将重启应用...", modal_id)
            else:
                self.add_modal_log("更新失败", modal_id)
                
            return result
        except Exception as e:
            self.add_modal_log(f"更新失败：{e}", modal_id)
            self.log_error(e)
            return False

def setup_logging():
    """
    配置日志系统，使5KB作为轮换大小
    """
    # 创建logs目录（如果不存在）
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # 配置日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # 创建轮转文件处理器，最大50KB，保留5个备份文件
    handler = RotatingFileHandler(
        'logs/app.log', 
        maxBytes=1024*50,  # 50kb
        backupCount=10,       # 保留5个旧日志文件
        encoding='utf-8'
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
    # 设置模态窗口相关的回调
    api.log_manager.set_modal_callbacks(
        status_callback=api.set_modal_status,
        log_callback=api.add_modal_log,
        progress_callback=api.update_modal_progress,
        check_running=api.check_modal_running
    )
    
    logger.info("WebUI窗口已创建")

    debug_mode = api.config.get("debug", False)

    # 启动应用
    webview.start(
        debug=debug_mode,
        http_server=True  # 使用内置HTTP服务器
    )

if __name__ == "__main__":
    main()