"""
日志管理器（单例模式）
从 webutils/log_manage.py 迁移，增加单例模式
统一管理日志输出、UI消息、模态窗口交互
"""

import logging
import sys
import threading
from typing import Callable, Optional, Any
from concurrent.futures import ThreadPoolExecutor


class LogManager:
    """
    日志管理器单例
    负责：
    - 普通日志记录 (log)
    - 错误日志记录 (log_error)
    - UI日志（发送到前端）(log_ui)
    - 模态窗口交互 (log_modal_*, update_modal_progress)
    - 回调函数管理
    """

    _instance: Optional['LogManager'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'LogManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 日志回调
        self.log_callback: Optional[Callable] = None
        self.error_callback: Optional[Callable] = None
        self.ui_callback: Optional[Callable] = None

        # 模态窗口回调
        self.modal_status_callback: Optional[Callable] = None
        self.modal_log_callback: Optional[Callable] = None
        self.modal_progress_callback: Optional[Callable] = None
        self.check_running: Optional[Callable] = None

        # 调试模式
        self.debug_mode = False

        # 线程池，防止UI日志阻塞主线程
        self.executor = ThreadPoolExecutor(max_workers=1)

    def set_debug_mode(self, enabled: bool):
        """设置调试模式开关"""
        self.debug_mode = enabled

    def set_log_callback(self, callback: Callable):
        """设置普通日志回调"""
        self.log_callback = callback

    def set_error_callback(self, callback: Callable):
        """设置错误日志回调"""
        self.error_callback = callback

    def set_ui_callback(self, callback: Callable):
        """设置UI日志回调"""
        self.ui_callback = callback

    def set_modal_callbacks(
        self,
        status_callback: Callable = None,
        log_callback: Callable = None,
        progress_callback: Callable = None,
        check_running: Callable = None
    ):
        """设置模态窗口相关回调函数"""
        self.modal_status_callback = status_callback
        self.modal_log_callback = log_callback
        self.modal_progress_callback = progress_callback
        self.check_running = check_running

    def log(self, message: str, *args, **kwargs):
        """记录普通日志"""
        if self.log_callback:
            try:
                self.log_callback(message, *args, **kwargs)
            except Exception:
                pass
        else:
            print(f"[LOG] {message}")

    def debug(self, message: str, *args, **kwargs):
        """记录调试日志（仅在debug模式）"""
        self.log(f"[DEBUG] {message}", *args, **kwargs)

    def log_error(self, error: Any, *args, **kwargs):
        """记录错误日志"""
        error_msg = str(error) if error else "未知错误"
        if self.error_callback:
            try:
                self.error_callback(error, *args, **kwargs)
            except Exception:
                pass
        else:
            print(f"[ERROR] {error_msg}", file=sys.stderr)

    def log_ui(self, message: str, level: int = logging.INFO, *args, **kwargs):
        """记录UI日志（通过JS发送到前端）"""
        if self.ui_callback:
            try:
                self.executor.submit(
                    self.ui_callback, message, level, *args, **kwargs
                )
            except Exception as e:
                self.log_error(e)
            self.log(message)
        else:
            level_name = logging.getLevelName(level)
            print(f"[{level_name}] {message}")

    def log_modal_status(self, status: str, modal_id: str = None):
        """更新模态窗口状态"""
        target_modal_id = modal_id
        if target_modal_id and self.modal_status_callback:
            try:
                self.executor.submit(
                    self.modal_status_callback, status, target_modal_id
                )
            except Exception as e:
                self.log_error(e)
        elif self.ui_callback:
            self.log_ui(f"状态: {status}")

    def log_modal_process(self, message: str, modal_id: str = None):
        """向模态窗口添加日志消息"""
        target_modal_id = modal_id
        if target_modal_id and self.modal_log_callback:
            try:
                self.executor.submit(
                    self.modal_log_callback, message, target_modal_id
                )
            except Exception as e:
                self.log_error(e)
        else:
            self.log_ui(message)

    def log_modal_process_debug(self, message: str, modal_id: str = None):
        """向模态窗口添加调试日志（仅在调试模式）"""
        if self.debug_mode:
            self.log_modal_process(f"[DEBUG] {message}", modal_id)

    def update_modal_progress(self, percent: int, text: str = "", modal_id: str = None, log: bool = True):
        """更新模态窗口进度"""
        target_modal_id = modal_id
        if target_modal_id and self.modal_progress_callback:
            try:
                self.executor.submit(
                    self.modal_progress_callback, percent, text, target_modal_id, log
                )
            except Exception as e:
                self.log_error(e)
