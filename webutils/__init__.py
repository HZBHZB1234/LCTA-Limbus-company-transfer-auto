from .function_llc import function_llc_main
from .log_h import LogManager

# 创建全局日志管理器实例
log_manager = LogManager()
__all__=[
    'function_llc_main',
    'log_manager'
]