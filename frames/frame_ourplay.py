import tkinter as tk
from tkinter import ttk, messagebox
import threading
import functions

class OurPlayFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.create_widgets()
        
    def create_widgets(self):
        """创建ourplay下载界面"""
        ttk.Label(self, text="从ourplay下载汉化", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 说明文本
        ttk.Label(self, text="从OurPlay平台下载汉化包").pack(pady=5)
        self.font_option_var = tk.StringVar(value="keep")
        font_frame = ttk.Frame(self)
        font_frame.pack(pady=10)
        
        ttk.Label(font_frame, text="字体处理:").pack(side=tk.LEFT)
        ttk.Radiobutton(font_frame, text="保留原字体", variable=self.font_option_var, value="keep").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(font_frame, text="精简字体", variable=self.font_option_var, value="simplify").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(font_frame, text="从零协下载字体", variable=self.font_option_var, value="llc").pack(side=tk.LEFT, padx=5)

        # 进度条
        ttk.Label(self, text="下载进度:").pack(anchor=tk.W, pady=(10, 5))
        self.ourplay_progress = ttk.Progressbar(self, variable=self.main_app.download_progress, maximum=100)
        self.ourplay_progress.pack(fill=tk.X, pady=5)
        
        # 按钮框架
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="开始下载", command=self.start_ourplay_download).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消下载", command=self.cancel_download).pack(side=tk.LEFT, padx=5)
    
    def start_ourplay_download(self):
        """开始OurPlay下载"""
        if self.main_app.download_thread and self.main_app.download_thread.is_alive():
            messagebox.showwarning("警告", "已有下载任务正在进行中")
            return
        
        self.main_app.log("开始从OurPlay下载汉化包...")
        self.main_app.stop_download = False
        self.main_app.download_progress.set(0)
        
        # 在新线程中执行下载
        self.main_app.download_thread = threading.Thread(target=self.download_ourplay_thread)
        self.main_app.download_thread.daemon = True
        self.main_app.download_thread.start()
    
    def download_ourplay_thread(self):
        """OurPlay下载线程"""
        try:
            # 设置下载回调函数
            functions.set_log_callback(self.main_app.log)
            def progress_callback(progress):
                if self.main_app.stop_download:
                    return False
                self.main_app.download_progress.set(progress)
                self.main_app.root.update_idletasks()
                return True
            
            # 执行下载
            success = functions.download_and_verify_file(progress_callback)
            
            if success and not self.main_app.stop_download:
                self.main_app.log("下载完成，正在处理文件...")
                self.main_app.download_progress.set(50)
                
                # 处理下载的文件
                font_option = self.font_option_var.get()
                functions.get_true_zip('transfile.zip', font_option)
                self.main_app.download_progress.set(100)
                self.main_app.log("OurPlay汉化包下载和处理完成")
                messagebox.showinfo("成功", "OurPlay汉化包下载和处理完成")
            elif not self.main_app.stop_download:
                self.main_app.log("下载失败")
                self.main_app.download_progress.set(0)
                messagebox.showerror("错误", "下载失败，请检查网络连接")
            else:
                self.main_app.download_progress.set(0)
            
        except Exception as e:
            self.main_app.log(f"下载过程中发生错误: {e}")
            self.main_app.download_progress.set(0)
            messagebox.showerror("错误", f"下载过程中发生错误: {e}")
    
    def cancel_download(self):
        """取消下载"""
        self.main_app.stop_download = True
        self.main_app.download_progress.set(0)
        self.main_app.log("下载已取消")