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
    logger.info("WebUI窗口已创建")
    
    # 启动应用
    webview.start(
        debug=True,  # 开启调试模式便于开发
        http_server=True  # 使用内置HTTP服务器
    )

if __name__ == "__main__":
    main()