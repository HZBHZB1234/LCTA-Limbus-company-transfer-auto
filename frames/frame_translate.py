import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import organization

class TranslateFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.game_path = main_app.game_path
        self.create_widgets()
        
    def create_widgets(self):
        """创建翻译工具界面"""
        self.columnconfigure(1, weight=1)
        
        # 自定义脚本选项
        self.custom_script_cb = ttk.Checkbutton(
            self, 
            text="启用自定义汉化脚本", 
            variable=self.main_app.custom_script_var,
            style='TCheckbutton'
        )
        self.custom_script_cb.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(self, text="脚本文件:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.script_path = ttk.Entry(self, width=50)
        self.script_path.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        self.browse_script_btn = ttk.Button(self, text="浏览...", command=self.browse_script)
        self.browse_script_btn.grid(row=1, column=2, padx=(5, 0))
        
        # 实验室功能选项
        ttk.Label(self, text="实验室功能:", font=('TkDefaultFont', 10, 'bold')).grid(
            row=2, column=0, sticky=tk.W, pady=(10, 5))
        
        self.cache_trans_cb = ttk.Checkbutton(
            self, 
            text="缓存翻译结果", 
            variable=self.main_app.cache_trans_var,
            style='TCheckbutton'
        )
        self.cache_trans_cb.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        self.team_trans_cb = ttk.Checkbutton(
            self, 
            text="整文件翻译", 
            variable=self.main_app.team_trans_var,
            style='TCheckbutton'
        )
        self.team_trans_cb.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Excel输出选项
        self.excel_output_cb = ttk.Checkbutton(
            self, 
            text="将修改输出至Excel文件", 
            variable=self.main_app.excel_output_var,
            style='TCheckbutton'
        )
        self.excel_output_cb.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # 日志选项
        self.log_enabled_cb = ttk.Checkbutton(
            self, 
            text="启用日志", 
            variable=self.main_app.log_enabled_var,
            style='TCheckbutton'
        )
        self.log_enabled_cb.grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # 使用半完成项目选项
        self.half_trans_cb = ttk.Checkbutton(
            self, 
            text="使用翻译至一半的项目", 
            variable=self.main_app.half_trans_var,
            style='TCheckbutton'
        )
        self.half_trans_cb.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(self, text="半完成项目路径:").grid(row=8, column=0, sticky=tk.W, pady=2)
        self.half_trans_path = ttk.Entry(self, width=50)
        self.half_trans_path.grid(row=8, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        self.browse_half_trans_btn = ttk.Button(self, text="浏览...", command=self.browse_half_trans)
        self.browse_half_trans_btn.grid(row=8, column=2, padx=(5, 0))

        self.backup_cb = ttk.Checkbutton(
            self, 
            text="使用上版本备份原文(需与零协版本一致)", 
            variable=self.main_app.backup_var,
            style='TCheckbutton'
        )
        self.backup_cb.grid(row=9, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(self, text="备份原文路径:").grid(row=10, column=0, sticky=tk.W, pady=2)
        self.backup_path = ttk.Entry(self, width=50)
        self.backup_path.grid(row=10, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        self.browse_backup_btn = ttk.Button(self, text="浏览...", command=self.browse_backup)
        self.browse_backup_btn.grid(row=10, column=2, padx=(5, 0))
        
        ttk.Label(self, text="选择上一版本零协汉化", font=('TkDefaultFont', 10, 'bold')).grid(
            row=11, column=0, sticky=tk.W, pady=(11, 5))
        ttk.Label(self, text="零协汉化(或其他汉化包)路径:").grid(row=12, column=0, sticky=tk.W, pady=2)
        self.LLC_path = ttk.Entry(self, width=50)
        self.LLC_path.grid(row=12, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        self.browse_LLC_btn = ttk.Button(self, text="浏览...", command=self.browse_LLC)
        self.browse_LLC_btn.grid(row=12, column=2, padx=(5, 0))
        
        # 翻译原语言选择
        ttk.Label(self, text="翻译原语言:").grid(row=13, column=0, sticky=tk.W, pady=(10, 5))
        self.lang_var = tk.StringVar(value="kor")
        lang_frame = ttk.Frame(self)
        lang_frame.grid(row=13, column=1, columnspan=2, sticky=tk.W, pady=(10, 5))
        ttk.Radiobutton(lang_frame, text="韩语", variable=self.lang_var, value="kor").pack(side=tk.LEFT)
        ttk.Radiobutton(lang_frame, text="英语", variable=self.lang_var, value="en").pack(side=tk.LEFT)
        ttk.Radiobutton(lang_frame, text="日文", variable=self.lang_var, value="jp").pack(side=tk.LEFT)
        
        # 按钮框架
        button_frame = ttk.Frame(self)
        button_frame.grid(row=14, column=0, columnspan=3, pady=20)
        
        ttk.Button(button_frame, text="开始翻译", command=self.start_translation).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重置", command=self.reset_fields).pack(side=tk.LEFT, padx=5)
        
        # 初始状态设置
        self.toggle_custom_script()
        self.toggle_half_trans()
        self.toggle_backup()
    
    def toggle_backup(self):
        state = "normal" if self.main_app.backup_var.get() else "disabled"
        self.backup_path.config(state=state)
        self.browse_backup_btn.config(state=state)
        
    def toggle_custom_script(self):
        state = "normal" if self.main_app.custom_script_var.get() else "disabled"
        self.script_path.config(state=state)
        self.browse_script_btn.config(state=state)
    
    def toggle_half_trans(self):
        state = "normal" if self.main_app.half_trans_var.get() else "disabled"
        self.half_trans_path.config(state=state)
        self.browse_half_trans_btn.config(state=state)
    
    def browse_script(self):
        file_path = filedialog.askopenfilename(
            title="选择自定义脚本文件",
            filetypes=[("Python文件", "*.py"), ("所有文件", "*.*")]
        )
        if file_path:
            self.script_path.delete(0, tk.END)
            self.script_path.insert(0, file_path)
            
    def browse_LLC(self):
        file_path = filedialog.askdirectory(title="选择LLC文件夹")
        
        if file_path:
            self.LLC_path.delete(0, tk.END)
            self.LLC_path.insert(0, file_path)
            
    def browse_backup(self):
        file_path = filedialog.askopenfilename(
                title="选择备份文件",
                filetypes=[("zip文件", "*.zip"), ("所有文件", "*.*")]
            )
        if file_path:
            self.backup_path.delete(0, tk.END)
            self.backup_path.insert(0, file_path)
            
    def browse_half_trans(self):
        if self.main_app.excel_output_var.get():
            file_path = filedialog.askopenfilename(
                title="选择Excel文件",
                filetypes=[("Excel文件", "*.xlsx"), ("所有文件", "*.*")]
            )
        else:
            file_path = filedialog.askdirectory(title="选择半完成项目文件夹")
        
        if file_path:
            self.half_trans_path.delete(0, tk.END)
            self.half_trans_path.insert(0, file_path)
    
    def start_translation(self):
        self.main_app.log("开始翻译过程...")
        if self.game_path == 'skip':
            messagebox.showinfo("提示", "请选择游戏安装目录")
            return
            
        # 验证必要的参数
        if self.main_app.custom_script_var.get() and not self.script_path.get():
            messagebox.showerror("错误", "请选择自定义脚本文件")
            return
        
        if self.main_app.half_trans_var.get() and not self.half_trans_path.get():
            messagebox.showerror("错误", "请选择半完成项目路径")
            return
        
        if self.main_app.backup_var.get() and not self.backup_path.get():
            messagebox.showerror("错误", "请选择半完成项目路径")
            return
            
        if not self.LLC_path.get():
            if messagebox.askyesno("提示", "未选择LLC路径，是否使用默认路径？"):
                cache = (fr'{self.game_path}LimbusCompany_Data\lang\LLC_zh-CN')
                if os.path.exists(cache):
                    self.LLC_path.delete(0, tk.END)
                    self.LLC_path.insert(0, cache)
                else:
                    messagebox.showerror("错误", "未找到默认路径")
                    return
            else:
                if not messagebox.askyesno('LCTA', '从零开始进行翻译?'):
                    return
                    
        config = {
            "custom_script": self.main_app.custom_script_var.get(),
            "cache_trans": self.main_app.cache_trans_var.get(),
            "team_trans": self.main_app.team_trans_var.get(),
            "excel_output": self.main_app.excel_output_var.get(),
            "log_enabled": self.main_app.log_enabled_var.get(),
            "half_trans": self.main_app.half_trans_var.get(),
            "backup_enabled": self.main_app.backup_var.get(),
            "script_path": self.script_path.get(),
            "half_trans_path": self.half_trans_path.get(),
            "backup_path": self.backup_path.get(),
            "game_path": self.game_path,
            "LLC_path": self.LLC_path.get(),
            "formal_language": self.lang_var.get()
        }
        
        # 在新线程中执行翻译
        translation_thread = threading.Thread(
            target=self.translation_thread, 
            args=(config,)
        )
        translation_thread.daemon = True
        translation_thread.start()
    
    def translation_thread(self, config):
        """翻译线程函数"""
        try:
            organization.translate_organize(config, self.main_app.log)
            self.main_app.log("翻译完成")
        except Exception as e:
            self.main_app.log(f"翻译过程中发生错误: {e}")
            self.main_app.logger.exception(e)
    
    def reset_fields(self):
        # 重置所有变量
        self.main_app.custom_script_var.set(False)
        self.main_app.cache_trans_var.set(False)
        self.main_app.team_trans_var.set(False)
        self.main_app.excel_output_var.set(False)
        self.main_app.log_enabled_var.set(True)
        self.main_app.half_trans_var.set(False)
        self.main_app.backup_var.set(False)
        self.lang_var.set("kor")
        
        # 清空所有路径输入框
        self.script_path.delete(0, tk.END)
        self.half_trans_path.delete(0, tk.END)
        self.backup_path.delete(0, tk.END)
        self.LLC_path.delete(0, tk.END)
        
        # 手动调用状态更新函数以确保控件状态正确
        self.toggle_custom_script()
        self.toggle_half_trans()
        self.toggle_backup()
        
        self.main_app.log("已重置所有设置")