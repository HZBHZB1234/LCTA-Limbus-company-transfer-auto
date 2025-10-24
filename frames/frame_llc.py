import tkinter as tk
from tkinter import ttk, messagebox
import threading
import utils.functions as functions

class LLCFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.create_widgets()
        
    def create_widgets(self):
        """创建零协下载界面"""
        ttk.Label(self, text="从零协下载汉化", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 说明文本
        ttk.Label(self, text="从零协下载汉化包").pack(pady=5)
        
        # 进度条
        ttk.Label(self, text="下载进度:").pack(anchor=tk.W, pady=(10, 5))
        self.llc_progress = ttk.Progressbar(self, variable=self.main_app.download_progress, maximum=100)
        self.llc_progress.pack(fill=tk.X, pady=5)
        
        # 选项框架
        option_frame = ttk.Frame(self)
        option_frame.pack(fill=tk.X, pady=5)
        
        self.convert_llc_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(option_frame, text="自动转换零协文本", variable=self.convert_llc_var).pack(anchor=tk.W)
        
        self.clean_temp_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(option_frame, text="下载完成后清理临时文件", variable=self.clean_temp_var).pack(anchor=tk.W)
        
        # 按钮框架
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="开始下载", command=self.start_llc_download).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消下载", command=self.cancel_download).pack(side=tk.LEFT, padx=5)
    
    def start_llc_download(self):
        """开始零协下载"""
        if self.main_app.download_thread and self.main_app.download_thread.is_alive():
            messagebox.showwarning("警告", "已有下载任务正在进行中")
            return
        
        self.main_app.log("开始从零协下载汉化包...")
        self.main_app.stop_download = False
        self.main_app.download_progress.set(0)
        
        # 在新线程中执行下载
        self.main_app.download_thread = threading.Thread(target=self.download_llc_thread)
        self.main_app.download_thread.daemon = True
        self.main_app.download_thread.start()
    
    def download_llc_thread(self):
        """零协下载线程"""
        try:
            # 设置下载回调函数
            functions.set_log_callback(self.main_app.log)
            functions.set_error_log_callback(self.main_app.log_error)
            def progress_callback(progress):
                if self.main_app.stop_download:
                    return False
                self.main_app.download_progress.set(progress)
                self.main_app.root.update_idletasks()
                return True
            
            # 执行下载
            success = functions.download_llc(
                progress_callback=progress_callback,
                convert=self.convert_llc_var.get(),
                clean_temp=self.clean_temp_var.get()
            )
            
            if success and not self.main_app.stop_download:
                self.main_app.download_progress.set(100)
                self.main_app.log("零协汉化包下载和处理完成")
                messagebox.showinfo("成功", "零协汉化包下载和处理完成")
            elif not self.main_app.stop_download:
                self.main_app.log("下载失败")
                self.main_app.download_progress.set(0)
                messagebox.showerror("错误", "下载失败，请检查网络连接")
            
        except Exception as e:
            self.main_app.log(f"下载过程中发生错误: {e}")
            self.main_app.logger.exception(e)
            self.main_app.download_progress.set(0)
            messagebox.showerror("错误", f"下载过程中发生错误: {e}")
    
    def cancel_download(self):
        """取消下载"""
        self.main_app.stop_download = True
        self.main_app.download_progress.set(0)
        self.main_app.log("下载已取消")