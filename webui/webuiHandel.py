import os
import sys
import atexit
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from .app import LCTAapp
from globalManagers.logManager import logManager

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
    

    logger.info('LCTAapp已创建')
    # 创建窗口 - 先创建窗口，不立即绑定LCTAapp
    window = webview.create_window(
        "LCTA - 边狱公司汉化工具箱",
        url=html_path,
        width=1200,
        height=800,
        resizable=True,
        fullscreen=False,
        text_select=True,
        js_LCTAapp=LCTAapp
    )
    
    LCTAapp._window = window
    logManager.setup(logger, window)
    atexit.register(LCTAapp.save_config_to_file)

    logger.info("WebUI窗口已创建")

    debug_mode = LCTAapp.config.get("debug", False)
    enable_storage = LCTAapp.config.get('enable_storage', False)

    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    webview.settings['ALLOW_DOWNLOADS'] = True
    
    if not debug_mode:
        logger_c = logging.getLogger('urllib3.connectionpool')
        logger_c.setLevel(logging.INFO)

    if enable_storage:
        stPath = LCTAapp.config.get('storage_path', 'tmp')
        webview.start(
            func=LCTAapp.start_func,
            debug=debug_mode,
            http_server=True,
            storage_path=stPath,
            private_mode=False
        )
    else:
        webview.start(
            func=LCTAapp.start_func,
            debug=debug_mode,
            http_server=True
        )

if __name__ == "__main__":
    main()