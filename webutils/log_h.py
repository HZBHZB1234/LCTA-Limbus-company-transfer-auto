import logging
import sys
from typing import Callable, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import threading

class LogManager:
    """
    日志管理器类，用于统一处理各种日志需求
    包含log, log_error, log_ui三个主要方法
    支持与前端模态窗口进行交互
    """
    
    def __init__(self):
        # 初始化日志回调函数
        self.log_callback: Optional[Callable] = None
        self.error_callback: Optional[Callable] = None
        self.ui_callback: Optional[Callable] = None
        # 用于存储当前活动的模态窗口ID
        self.current_modal_id: Optional[str] = None
        # 模态窗口相关回调
        self.modal_status_callback: Optional[Callable] = None
        self.modal_log_callback: Optional[Callable] = None
        self.modal_progress_callback: Optional[Callable] = None
        
        # 调试模式标志
        self.debug_mode = False
        
        # 创建线程池用于处理UI日志，防止阻塞主线程
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.lock = threading.Lock()

    def set_debug_mode(self, enabled: bool):
        """设置调试模式开关"""
        self.debug_mode = enabled

    def set_log_callback(self, callback: Callable):
        """设置普通日志回调函数"""
        self.log_callback = callback
    
    def set_error_callback(self, callback: Callable):
        """设置错误日志回调函数"""
        self.error_callback = callback
    
    def set_ui_callback(self, callback: Callable):
        """设置UI日志回调函数"""
        self.ui_callback = callback
    
    def set_modal_callbacks(self, status_callback: Callable = None, 
                           log_callback: Callable = None, 
                           progress_callback: Callable = None,
                           check_running: Callable = None):
        """设置模态窗口相关回调函数"""
        self.modal_status_callback = status_callback
        self.modal_log_callback = log_callback
        self.modal_progress_callback = progress_callback
        self.check_running = check_running

    def set_current_modal(self, modal_id: str):
        """设置当前活动的模态窗口ID"""
        self.current_modal_id = modal_id

    def clear_current_modal(self):
        """清空当前活动的模态窗口ID"""
        self.current_modal_id = None

    def log(self, message: str, *args, **kwargs):
        """记录普通日志"""
        if self.log_callback:
            try:
                self.log_callback(message, *args, **kwargs)
            except Exception:
                pass  # 忽略回调中的错误
        else:
            # 默认输出到控制台
            print(f"[LOG] {message}")

    def debug(self, message: str, *args, **kwargs):
        self.log(f"[DEBUG] {message}", *args, **kwargs)

    def log_error(self, error: Any, *args, **kwargs):
        """记录错误日志"""
        error_msg = str(error) if error else "Unknown error"
        if self.error_callback:
            try:
                self.error_callback(error, *args, **kwargs)
            except Exception:
                pass  # 忽略回调中的错误
        else:
            # 默认输出到stderr
            print(f"[ERROR] {error_msg}", file=sys.stderr)

    def log_ui(self, message: str, level: int = logging.INFO, *args, **kwargs):
        """记录UI日志"""
        if self.ui_callback:
            try:
                self.executor.submit(
                    self.ui_callback, message, level, *args, **kwargs
                )
            except Exception as e:
                self.log_error(e)
        else:
            # 默认输出到控制台
            level_name = logging.getLevelName(level)
            print(f"[{level_name}] {message}")

    def log_modal_status(self, status: str, modal_id: str = None):
        """更新模态窗口状态"""
        target_modal_id = modal_id or self.current_modal_id
        if target_modal_id and self.modal_status_callback:
            try:
                self.executor.submit(
                    self.modal_status_callback, status, target_modal_id
                )
            except Exception as e:
                self.log_error(e)
        elif self.ui_callback:
            # 如果没有专门的模态状态回调，则使用常规UI日志
            self.log_ui(f"Status: {status}")

    def log_modal_process(self, message: str, modal_id: str = None):
        """向模态窗口添加日志"""
        target_modal_id = modal_id or self.current_modal_id
        if target_modal_id and self.modal_log_callback:
            try:
                self.executor.submit(
                    self.modal_log_callback, message, target_modal_id
                )
            except Exception as e:
                self.log_error(e)
        else:
            # 回退到常规UI日志
            self.log_ui(message)

    def log_modal_process_debug(self, message: str, modal_id: str = None):
        """向模态窗口添加调试日志，仅在调试模式启用时生效"""
        if self.debug_mode:
            self.log_modal_process(f"[DEBUG] {message}", modal_id)

    def update_modal_progress(self, percent: int, text: str = "", modal_id: str = None):
        """更新模态窗口进度"""
        target_modal_id = modal_id or self.current_modal_id
        if target_modal_id and self.modal_progress_callback:
            try:
                self.executor.submit(
                   self.modal_progress_callback, percent, text, target_modal_id
                )
            except Exception as e:
                self.log_error(e)
        else:
            # 回退到常规UI日志
            self.log_ui(f"Progress: {percent}% - {text}")
