import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import functions

class BackupFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.game_path = main_app.game_path
        self.create_widgets()
        
    def create_widgets(self):
        """创建备份原文界面"""
        ttk.Label(self, text="备份原文", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 说明文本
        ttk.Label(self, text="此功能用于备份游戏原文文件，以便下次翻译使用").pack(pady=5)
        
        # 备份路径选择
        path_frame = ttk.Frame(self)
        path_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(path_frame, text="备份保存路径:").pack(anchor=tk.W)
        
        path_input_frame = ttk.Frame(path_frame)
        path_input_frame.pack(fill=tk.X, pady=5)
        
        self.backup_save_path = ttk.Entry(path_input_frame)
        self.backup_save_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        ttk.Button(path_input_frame, text="浏览...", command=self.browse_backup_save_path).pack(side=tk.LEFT)

        button_frame = ttk.Frame(self)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="开始备份", command=self.start_backup).pack(side=tk.LEFT, padx=5)
        #ttk.Button(button_frame, text="从备份恢复", command=self.restore_backup).pack(side=tk.LEFT, padx=5)

    def browse_backup_save_path(self):
        """浏览备份保存路径"""
        folder_path = filedialog.askdirectory(title="选择备份保存路径")
        if folder_path:
            self.backup_save_path.delete(0, tk.END)
            self.backup_save_path.insert(0, folder_path)

    def start_backup(self):
        """开始备份原文"""
        if self.game_path == 'skip':
            messagebox.showerror("错误", "未找到游戏路径，请先设置游戏路径")
            return
        
        save_path = self.backup_save_path.get()
        if not save_path:
            messagebox.showerror("错误", "请选择备份保存路径")
            return
        
        if not os.path.exists(save_path):
            try:
                os.makedirs(save_path)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建备份目录: {e}")
                return
        
        self.main_app.log("开始备份原文...")
        backup_thread = threading.Thread(target=self.backup_thread, args=(save_path,))
        backup_thread.daemon = True
        backup_thread.start()

    def backup_thread(self, save_path):
        """备份线程函数"""
        try:
            self.main_app.log(f"正在备份到: {save_path}")
            path_for = self.game_path + r"LimbusCompany_Data\Assets\Resources_moved\Localize"
            if os.path.exists(f'{save_path}\\LCB_backup.zip'):
                self.main_app.log("已存在备份文件")
                messagebox.showinfo("提示", "已存在备份文件")
                return
            functions.zip_folder(path_for, f'{save_path}\\LCB_backup.zip')
            self.main_app.log("备份完成")
            messagebox.showinfo("成功", "原文备份完成")
        except Exception as e:
            self.main_app.log(f"备份失败: {e}")
            messagebox.showerror("错误", f"备份失败: {e}")