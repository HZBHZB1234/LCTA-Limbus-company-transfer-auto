import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import json
import os

class ProperNounFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.create_widgets()
        
    def create_widgets(self):
        """创建专有名词抓取界面"""
        # 标题
        ttk.Label(self, text="专有名词抓取工具", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 说明文本
        description = "从翻译数据中提取专有名词并生成术语表"
        ttk.Label(self, text=description, wraplength=600).pack(pady=5)
        
        # 输入文件选择
        input_frame = ttk.Frame(self)
        input_frame.pack(fill=tk.X, pady=10, padx=20)
        
        ttk.Label(input_frame, text="输入文件:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.input_path = ttk.Entry(input_frame, width=50)
        self.input_path.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Button(input_frame, text="浏览", command=self.browse_input_file).grid(row=0, column=2, padx=5, pady=5)
        
        # 输出目录选择
        output_frame = ttk.Frame(self)
        output_frame.pack(fill=tk.X, pady=10, padx=20)
        
        ttk.Label(output_frame, text="输出目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.output_dir = ttk.Entry(output_frame, width=50)
        self.output_dir.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Button(output_frame, text="浏览", command=self.browse_output_dir).grid(row=0, column=2, padx=5, pady=5)
        
        # 配置网格权重
        input_frame.columnconfigure(1, weight=1)
        output_frame.columnconfigure(1, weight=1)
        
        # 选项框架
        options_frame = ttk.LabelFrame(self, text="抓取选项", padding=10)
        options_frame.pack(fill=tk.X, pady=10, padx=20)
    
        split_frame = ttk.Frame(options_frame)
        split_frame.pack(fill=tk.X, pady=5)
        ttk.Label(split_frame, text="分割符:").pack(side=tk.LEFT)
        self.split_str = ttk.Entry(split_frame, width=5)
        self.split_str.insert(0, "|||")
        self.split_str.pack(side=tk.LEFT, padx=5)

        # 包含注释
        self.skip_space = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="跳过带有空格的词汇", variable=self.skip_space).pack(anchor=tk.W, pady=2)
        
        # 最大次数设置
        max_count_frame = ttk.Frame(options_frame)
        max_count_frame.pack(fill=tk.X, pady=5)
        ttk.Label(max_count_frame, text="最大提取数量:").pack(side=tk.LEFT)
        self.max_count = ttk.Entry(max_count_frame, width=10)
        self.max_count.insert(0, "0")  # 0表示无限制
        self.max_count.pack(side=tk.LEFT, padx=5)
        ttk.Label(max_count_frame, text="(0表示无限制)").pack(side=tk.LEFT, padx=5)
        
        # 输出格式
        format_frame = ttk.Frame(options_frame)
        format_frame.pack(fill=tk.X, pady=5)
        ttk.Label(format_frame, text="输出格式:").pack(side=tk.LEFT)
        self.output_format = tk.StringVar(value="json")
        self.output_format.trace('w', self.on_output_format_change)  # 添加追踪回调
        ttk.Radiobutton(format_frame, text="JSON", variable=self.output_format, value="json").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(format_frame, text="双份txt词表", variable=self.output_format, value="double").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(format_frame, text="单份txt词表", variable=self.output_format, value="single").pack(side=tk.LEFT, padx=5)
        
        status_frame = ttk.Frame(self)
        status_frame.pack(fill=tk.X, pady=10, padx=20)
        
        self.status_label = ttk.Label(status_frame, text="就绪")
        self.status_label.pack(side=tk.LEFT, pady=5)

        button_frame = ttk.Frame(self)
        button_frame.pack(pady=20)
        # 按钮框架
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="开始抓取", command=self.start_extraction).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=self.cancel_extraction).pack(side=tk.LEFT, padx=5)
        
        # 初始化控件状态
        self.on_output_format_change()

        # 线程控制
        self.extraction_thread = None
        self.stop_extraction = False
        
    def on_output_format_change(self, *args):
        """当输出格式改变时调用此方法来更新控件状态"""
        format_value = self.output_format.get()
        
        # 如果是单份txt词表，则启用分割符输入框，否则禁用
        if format_value == "single":
            self.split_str.configure(state='normal')
        else:
            self.split_str.configure(state='disabled')
            
        # 如果是JSON格式，则禁用输入文件框，否则启用
        if format_value == "json":
            self.input_path.configure(state='disabled')
            # 同时禁用浏览按钮
            for widget in self.input_path.master.winfo_children():
                if isinstance(widget, ttk.Button) and widget['text'] == '浏览':
                    widget.configure(state='disabled')
        else:
            self.input_path.configure(state='normal')
            # 同时启用浏览按钮
            for widget in self.input_path.master.winfo_children():
                if isinstance(widget, ttk.Button) and widget['text'] == '浏览':
                    widget.configure(state='normal')
        
    def browse_input_file(self):
        """浏览输入文件"""
        filename = filedialog.askopenfilename(
            title="选择翻译数据文件",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if filename:
            self.input_path.delete(0, tk.END)
            self.input_path.insert(0, filename)
    
    def browse_output_dir(self):
        """浏览输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.output_dir.delete(0, tk.END)
            self.output_dir.insert(0, directory)
    
    def check_output_dir(self):
        """检查输出目录"""
        output_format = self.output_format.get()
        output_dir = self.output_dir.get().strip()
        if not output_dir:
            messagebox.showerror("错误", "请选择输出目录")
            return False
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                self.main_app.log(f"无法创建输出目录: {e}")
                self.main_app.logger.exception(e)
        if output_format=='json':
            output_files=['proper.json']
        elif output_format=='double':
            output_files=['proper_cn.txt','proper_kr.txt']
        elif output_format=='single':
            output_files=['proper.txt']
        for file in output_files:
            if os.path.exists(os.path.join(output_dir,file)):
                if messagebox.askyesno("警告", f"{file}已存在，是否覆盖？"):
                    try:
                        os.remove(os.path.join(output_dir,file))
                    except Exception as e:
                        self.main_app.log(f"无法删除文件: {e}")
                        self.main_app.logger.exception(e)
                        return False
                else:
                    self.main_app.log("已取消")
                    return False
        return True
    
    def validate_max_count(self):
        """验证最大数量输入"""
        try:
            max_count = self.max_count.get().strip()
            if max_count == "":
                return 0
            max_count = int(max_count)
            if max_count < 0:
                messagebox.showerror("错误", "最大提取数量不能为负数")
                return None
            return max_count
        except ValueError:
            messagebox.showerror("错误", "最大提取数量必须是整数")
            return None
    
    def start_extraction(self):
        """开始专有名词抓取"""
        input_file = self.input_path.get().strip()
        output_dir = self.output_dir.get().strip()
        output_format = self.output_format.get()
        
        # 验证最大数量
        max_count = self.validate_max_count()
        if max_count is None:
            return
            
        # 对于JSON格式，不需要检查输入文件
        if output_format != "json":
            if input_file:
                if not os.path.exists(input_file):
                    messagebox.showerror("错误", "输入文件不存在")
                    return
            
        if not self.check_output_dir():
            return
            
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建输出目录: {e}")
                return
        
        # 禁用按钮，开始处理
        self.stop_extraction = False
        self.status_label.config(text="正在抓取专有名词...")
        
        # 在新线程中执行抓取
        self.extraction_thread = threading.Thread(target=self.extraction_thread_func)
        self.extraction_thread.daemon = True
        self.extraction_thread.start()
    
    def extraction_thread_func(self):
        """专有名词抓取线程"""
        try:
            input_file = self.input_path.get().strip()
            output_dir = self.output_dir.get().strip()
            split_str = self.split_str.get()  # 获取字符串而不是整数
            skip_space = self.skip_space.get()  # 修复变量名
            output_format = self.output_format.get()
            max_count = self.validate_max_count()  # 获取最大数量限制
            
            # 导入工具函数
            import utils.proper as proper
            
            def progress_callback(status):
                if self.stop_extraction:
                    return False
                self.status_label.config(text=status)  # 移除了不存在的progress_var
                self.main_app.root.update_idletasks()
                return True
            
            # 执行抓取
            success = proper.make_proper(
                progress_callback,
                output_type=output_format,
                output_path=output_dir,
                input_file=input_file,
                split_char=split_str,
                skip_space=skip_space,
                max_count=max_count if max_count > 0 else None  # 传递最大数量参数
            )
            
            if success and not self.stop_extraction:
                self.status_label.config(text="抓取完成")
                self.main_app.log("专有名词抓取完成")
                messagebox.showinfo("成功", "专有名词抓取完成")
            elif not self.stop_extraction:
                self.status_label.config(text="抓取失败")
                self.main_app.log("专有名词抓取失败")
                messagebox.showerror("错误", "专有名词抓取失败")
            else:
                self.status_label.config(text="已取消")
                self.main_app.log("专有名词抓取已取消")
                
        except Exception as e:
            self.status_label.config(text=f"错误: {str(e)}")
            self.main_app.log(f"专有名词抓取错误: {e}")
            self.main_app.logger.exception(e)
            messagebox.showerror("错误", f"抓取过程中发生错误: {e}")
    
    def cancel_extraction(self):
        """取消抓取"""
        self.stop_extraction = True
        self.status_label.config(text="正在取消...")