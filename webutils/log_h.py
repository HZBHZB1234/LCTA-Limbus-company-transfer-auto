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
        
        # 设置标准日志记录器
        self.logger = logging.getLogger('LCTA')
        self.logger.setLevel(logging.DEBUG)
        
        # 如果没有处理器，则添加一个
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def set_log_callback(self, callback):
        """设置普通日志回调函数"""
        self.log_callback = callback
    
    def set_error_callback(self, callback):
        """设置错误日志回调函数"""
        self.error_callback = callback
    
    def set_ui_callback(self, callback):
        """设置UI日志回调函数"""
        self.ui_callback = callback
    
    def log(self, message, level=logging.INFO, *args, **kwargs):
        """
        记录普通日志
        
        Args:
            message: 要记录的消息
            level: 日志级别，默认为INFO
            *args, **kwargs: 其他传递给日志记录器的参数
        """
        # 如果有回调函数则使用回调，否则使用标准日志记录器
        if self.log_callback:
            # 使用partial来处理可能的格式化参数
            formatted_message = message % args if args else message
            self.log_callback(formatted_message)
        else:
            self.logger.log(level, message, *args, **kwargs)
    
    def log_error(self, error, *args, **kwargs):
        """
        记录错误日志
        
        Args:
            error: 错误信息或异常对象
            *args, **kwargs: 其他传递给日志记录器的参数
        """
        # 格式化错误消息
        if isinstance(error, Exception):
            error_message = f"{type(error).__name__}: {str(error)}"
        else:
            error_message = str(error)
            
        # 如果有错误回调函数则使用回调，否则使用标准日志记录器
        if self.error_callback:
            # 使用partial来处理可能的格式化参数
            formatted_message = error_message % args if args else error_message
            self.error_callback(formatted_message)
        else:
            self.logger.error(error_message, *args, **kwargs)
    
    def log_ui(self, message, level=logging.INFO, *args, **kwargs):
        """
        记录UI相关的日志
        
        Args:
            message: 要记录的消息
            level: 日志级别，默认为INFO
            *args, **kwargs: 其他传递给日志记录器的参数
        """
        # 添加UI前缀
        ui_message = f"[UI] {message}"
        
        # 如果有UI回调函数则使用回调，否则使用标准日志记录器
        if self.ui_callback:
            # 使用partial来处理可能的格式化参数
            formatted_message = ui_message % args if args else ui_message
            self.ui_callback(formatted_message)
        else:
            self.logger.log(level, ui_message, *args, **kwargs)

# 创建全局实例供其他模块使用
log_manager = LogManager()

# 创建便捷函数供直接调用
log = log_manager.log
log_error = log_manager.log_error
log_ui = log_manager.log_ui