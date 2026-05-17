"""LCTA WebUI 启动入口 —— 创建窗口、初始化框架、启动事件循环。"""

import os
import sys
import atexit
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import webview

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from webui.app import framework
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager


def setup_logging():
    """配置日志系统，使用 TimedRotatingFileHandler 按天轮转。"""
    os.makedirs('logs', exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    handler = TimedRotatingFileHandler(
        'logs/app.log',
        when='midnight',
        interval=1,
        encoding='utf-8',
        utc=False,
        delay=False,
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(handler)
    return logger


def main():
    html_path = os.path.join(os.getenv('path_'), "index.html")

    logger = setup_logging()
    logger.info("正在启动 LCTA WebUI")

    window = webview.create_window(
        "LCTA - 边狱公司汉化工具箱",
        url=html_path,
        width=1200,
        height=800,
        resizable=True,
        fullscreen=False,
        text_select=True,
        js_LCTAapp=framework,
    )

    logManager.setup(logger, window)

    # 初始化框架（config、插件发现、暴露 JS API）
    framework.init(window)

    atexit.register(lambda: configManager._do_save())

    debug_mode = configManager.get("debug", False)
    enable_storage = configManager.get("enable_storage", False)

    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    webview.settings['ALLOW_DOWNLOADS'] = True

    if not debug_mode:
        logger_c = logging.getLogger('urllib3.connectionpool')
        logger_c.setLevel(logging.INFO)

    logger.info("WebUI 窗口已创建")

    if enable_storage:
        st_path = configManager.get("storage_path", "tmp")
        webview.start(
            debug=debug_mode,
            http_server=True,
            storage_path=st_path,
            private_mode=False
        )
    else:
        webview.start(
            debug=debug_mode,
            http_server=True
        )


if __name__ == "__main__":
    main()
