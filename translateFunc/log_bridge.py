"""
translateFunc/log_bridge.py
LogBridge —— 同时路由日志到 Python logging 模块和 UI 回调。

解决 _on_log (UI 回调) 和 logging 模块两个独立通道的问题：
关键错误信息确保同时到达文件日志和 UI 界面。
"""
from __future__ import annotations
import logging


class LogBridge:
    """将日志消息同时发送到 Python logging 和 UI 回调。

    用法:
        bridge = LogBridge(ui_callback=my_ui_handler)
        bridge.info("开始处理文件")
        bridge.warning("术语表缺失")
        bridge.error("翻译失败")
        bridge.exception("未预期的异常")
    """

    def __init__(self, ui_callback=None, logger_name: str = "LCTA"):
        self._ui = ui_callback or (lambda msg: None)
        self._logger = logging.getLogger(logger_name)

    def debug(self, msg: str) -> None:
        self._logger.debug(msg)

    def info(self, msg: str) -> None:
        self._logger.info(msg)
        self._ui(msg)

    def warning(self, msg: str) -> None:
        self._logger.warning(msg)
        self._ui(f"警告: {msg}")

    def error(self, msg: str) -> None:
        self._logger.error(msg)
        self._ui(f"错误: {msg}")

    def exception(self, msg: str) -> None:
        self._logger.exception(msg)
        self._ui(f"异常: {msg}")

    def set_ui_callback(self, callback) -> None:
        """更新 UI 回调函数。"""
        self._ui = callback
