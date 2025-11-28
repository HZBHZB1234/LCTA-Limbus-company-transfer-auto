import logging
import sys

class LogManager:
    """
    日志管理器类，用于统一处理各种日志需求
    包含log, log_error, log_ui三个主要方法
    """
    
    def __init__(self):
        # 初始化日志回调函数
        self.log_callback = None
        self.error_callback = None
        self.ui_callback = None
        

    
    def set_log_callback(self, callback):
        """设置普通日志回调函数"""
        self.log_callback = callback
    
    def set_error_callback(self, callback):
        """设置错误日志回调函数"""
        self.error_callback = callback
    
    def set_ui_callback(self, callback):
        """设置UI日志回调函数"""
        self.ui_callback = callback
    
    def log(self, message, *args, **kwargs):
        pass
    
    def log_error(self, error, *args, **kwargs):
        pass
    def log_ui(self, message, level=logging.INFO, *args, **kwargs):
        pass

# 创建全局实例供其他模块使用
log_manager = LogManager()

# 创建便捷函数供直接调用
log = log_manager.log
log_error = log_manager.log_error
log_ui = log_manager.log_ui