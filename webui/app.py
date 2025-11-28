import webview
import os
import sys
from pathlib import Path
import json
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
import shutil
import threading
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


from webutils.log_h import LogManager
import webutils.load as load_util

class LCTA_API:
    def __init__(self,logger:logging):
        self._window = None
        self.game_path = None
        # 初始化日志管理器
        self.logger =logger
        self.log_manager = LogManager()
        self.log_manager.set_log_callback(self.logger.info)
        self.log_manager.set_error_callback(self.logger.exception)
        self.log_manager.set_ui_callback(self.log_ui)

        #设置函数
        self.find_lcb=load_util.find_lcb


    def set_logger(self):
        load_util.set_log(self.log_manager)


    def set_window(self, window):
        self._window = window

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
        
        # 同时记录到文件和日志管理器
        self.log_manager.log_ui(message, level)
        print(f"[UI] {full_message}")

    def get_system_info(self):
        """获取系统信息"""
        game_path = self.get_game_path()
        return {
            'game_path': game_path if game_path else '未找到',
            'status': '就绪' if game_path else '游戏路径未设置'
        }

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

    # 以下为新添加的API方法，用于支持模态窗口功能
    def start_translation(self):
        """开始翻译"""
        try:
            # 这里应该调用实际的翻译逻辑
            self.log_ui("开始翻译...")
            time.sleep(2)  # 模拟翻译过程
            return {"success": True, "message": "翻译完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def install_translation(self):
        """安装翻译"""
        try:
            self.log_ui("开始安装汉化包...")
            time.sleep(1)  # 模拟安装过程
            return {"success": True, "message": "汉化包安装成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def download_ourplay_translation(self):
        """下载ourplay翻译"""
        try:
            self.log_ui("开始下载OurPlay汉化包...")
            time.sleep(1)  # 模拟下载过程
            return {"success": True, "message": "OurPlay汉化包下载成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def clean_cache(self):
        """清理缓存"""
        try:
            self.log_ui("开始清除缓存...")
            time.sleep(1)  # 模拟清理过程
            return {"success": True, "message": "缓存清除成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def download_llc_translation(self):
        """下载LLC翻译"""
        try:
            self.log_ui("开始下载零协汉化包...")
            time.sleep(1)  # 模拟下载过程
            return {"success": True, "message": "零协汉化包下载成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def save_api_config(self):
        """保存API配置"""
        try:
            self.log_ui("正在保存API配置...")
            time.sleep(1)  # 模拟保存过程
            return {"success": True, "message": "API配置保存成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def fetch_proper_nouns(self):
        """获取专有词汇"""
        try:
            self.log_ui("开始抓取专有词汇...")
            time.sleep(1)  # 模拟抓取过程
            return {"success": True, "message": "专有词汇抓取成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def search_text(self):
        """搜索文本"""
        try:
            self.log_ui("开始文本搜索...")
            time.sleep(1)  # 模拟搜索过程
            return {"success": True, "message": "文本搜索完成", "results": []}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def backup_text(self):
        """备份文本"""
        try:
            self.log_ui("开始备份原文...")
            time.sleep(1)  # 模拟备份过程
            return {"success": True, "message": "原文备份成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def manage_fonts(self):
        """管理字体"""
        try:
            self.log_ui("开始管理字体...")
            time.sleep(1)  # 模拟管理过程
            return {"success": True, "message": "字体管理完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def manage_images(self):
        """管理图片"""
        try:
            self.log_ui("开始管理图片...")
            time.sleep(1)  # 模拟管理过程
            return {"success": True, "message": "图片管理完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def manage_audio(self):
        """管理音频"""
        try:
            self.log_ui("开始管理音频...")
            time.sleep(1)  # 模拟管理过程
            return {"success": True, "message": "音频管理完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def adjust_image(self):
        """调整图片"""
        try:
            self.log_ui("开始调整图片...")
            time.sleep(1)  # 模拟调整过程
            return {"success": True, "message": "图片调整完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def calculate_gacha(self):
        """计算抽卡概率"""
        try:
            self.log_ui("开始计算抽卡概率...")
            time.sleep(1)  # 模拟计算过程
            return {"success": True, "message": "抽卡概率计算完成"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    # 模态窗口相关API方法
    def set_modal_status(self, status, modal_id):
        """设置模态窗口状态"""
        escaped_status = status.replace("'", "\\'").replace("\n", "\\n")
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
        escaped_message = message.replace("'", "\\'").replace("\n", "\\n")
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
        escaped_text = text.replace("'", "\\'").replace("\n", "\\n")
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
    
    # 创建轮转文件处理器，最大5KB，保留5个备份文件
    handler = RotatingFileHandler(
        'logs/app.log', 
        maxBytes=1024*5,  # 5kb
        backupCount=5,       # 保留5个旧日志文件
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
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    
    # 设置日志
    logger = setup_logging()
    logger.info("正在启动LCTA WebUI")
    

    # 创建API实例
    api = LCTA_API(logger)
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
        progress_callback=api.update_modal_progress
    )
    
    logger.info("WebUI窗口已创建")
    
    # 启动应用
    webview.start(
        debug=True,  # 开启调试模式便于开发
        http_server=True  # 使用内置HTTP服务器
    )

if __name__ == "__main__":
    main()