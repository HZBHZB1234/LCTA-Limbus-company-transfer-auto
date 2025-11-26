import datetime

class LogManager:
    """日志管理器"""
    
    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.enabled = True
        
    def set_log_callback(self, log_callback):
        """设置日志回调函数"""
        self.log_callback = log_callback
        
    def log(self, message):
        """记录日志"""
        if not self.enabled:
            return
            
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        
        # 输出到控制台
        print(log_message)
        
        # 调用日志回调（如果存在）
        if self.log_callback:
            try:
                self.log_callback(log_message)
            except Exception:
                # 回调可能已不可用
                pass
    
    def enable(self):
        """启用日志"""
        self.enabled = True
        
    def disable(self):
        """禁用日志"""
        self.enabled = False