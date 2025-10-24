import tkinter as tk
from tkinter import scrolledtext
import datetime

class LogManager:
    """日志管理器"""
    
    def __init__(self, log_widget=None):
        self.log_widget = log_widget
        self.enabled = True
        
    def set_log_widget(self, log_widget):
        """设置日志显示控件"""
        self.log_widget = log_widget
        
    def log(self, message):
        """记录日志"""
        if not self.enabled:
            return
            
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        
        # 输出到控制台
        print(log_message)
        
        # 输出到日志控件（如果存在）
        if self.log_widget:
            try:
                self.log_widget.config(state='normal')
                self.log_widget.insert(tk.END, log_message + "\n")
                self.log_widget.config(state='disabled')
                self.log_widget.see(tk.END)
            except tk.TclError:
                # 控件可能已被销毁
                pass
    
    def enable(self):
        """启用日志"""
        self.enabled = True
        
    def disable(self):
        """禁用日志"""
        self.enabled = False