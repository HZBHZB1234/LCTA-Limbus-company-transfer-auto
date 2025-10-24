import tkinter as tk
from tkinter import ttk, scrolledtext ,messagebox

class EditParamsDialog:
    """参数编辑对话框"""
    
    def __init__(self, parent, service_name, main_app):
        self.parent = parent
        self.service_name = service_name
        self.main_app = main_app
        self.dialog = None
        self.param_widgets = {}
        
        self.create_dialog()
    
    def create_dialog(self):
        """创建编辑对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(f"编辑 {self.service_name} 参数")
        self.dialog.geometry("600x500")
        self.dialog.resizable(True, True)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 居中显示
        self.dialog.geometry("+%d+%d" % (
            self.dialog.winfo_screenwidth()/2 - 300,
            self.dialog.winfo_screenheight()/2 - 250
        ))
        
        # 主框架
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        service_def = None
        for service_type in ['inner', 'custom']:
            if self.service_name in self.main_app.services_storage[service_type]:
                service_def = self.main_app.services_storage[service_type][self.service_name]
                break
        
        service_name_display = service_def.get('name', self.service_name) if service_def else self.service_name
        
        ttk.Label(
            main_frame, 
            text=f"编辑 {service_name_display} 参数",
            font=('TkDefaultFont', 12, 'bold')
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # 参数编辑区域
        edit_frame = ttk.LabelFrame(main_frame, text="参数配置", padding="10")
        edit_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # 创建滚动框架以支持大量参数
        canvas = tk.Canvas(edit_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(edit_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 布局滚动区域
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 创建参数输入控件
        self.create_param_widgets()
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(button_frame, text="测试连接", command=self.test_connection).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="保存", command=self.save_params).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # 绑定鼠标滚轮事件
        self.bind_mouse_wheel(canvas)
        
        # 加载现有配置
        self.load_current_config()
    
    def create_param_widgets(self):
        """创建参数输入控件 - 添加checkbox支持"""
        # 获取服务定义
        service_def = None
        for service_type in ['inner', 'custom']:
            if self.service_name in self.main_app.services_storage[service_type]:
                service_def = self.main_app.services_storage[service_type][self.service_name]
                break
        
        if not service_def:
            ttk.Label(self.scrollable_frame, text="未找到服务定义").pack(pady=10)
            return
            
        params = service_def.get('api_params', [])
        self.param_widgets = {}
        
        for i, param in enumerate(params):
            # 参数标签
            label = ttk.Label(self.scrollable_frame, text=param["label"] + ":")
            label.grid(row=i, column=0, sticky=tk.W, pady=8, padx=5)
            
            # 根据参数类型创建不同的控件
            if param.get("type") == "checkbox":
                # Checkbox类型参数
                var = tk.BooleanVar()
                checkbox = ttk.Checkbutton(
                    self.scrollable_frame, 
                    variable=var,
                    text=param.get("description", "")
                )
                checkbox.grid(row=i, column=1, sticky=tk.W, pady=5, padx=5)
                self.param_widgets[param["key"]] = var
            elif param.get("multiline", False):
                # 多行文本输入（用于LLM提示词等）
                frame = ttk.Frame(self.scrollable_frame)
                frame.grid(row=i, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
                
                # 创建带滚动条的多行文本输入
                text_widget = scrolledtext.ScrolledText(
                    frame, 
                    width=50, 
                    height=6,
                    wrap=tk.WORD
                )
                text_widget.pack(fill=tk.BOTH, expand=True)
                
                if param.get("type") == "password":
                    text_widget.config(show="*")
                
                self.param_widgets[param["key"]] = text_widget
            else:
                # 单行输入
                if param.get("type") == "password":
                    entry = ttk.Entry(self.scrollable_frame, width=50, show="*")
                else:
                    entry = ttk.Entry(self.scrollable_frame, width=50)
                    
                entry.grid(row=i, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
                self.param_widgets[param["key"]] = entry
            
            # 参数说明（如果有）
            if "description" in param and param.get("type") != "checkbox":
                desc_label = ttk.Label(
                    self.scrollable_frame, 
                    text=param["description"],
                    font=('TkDefaultFont', 8),
                    foreground="gray"
                )
                desc_label.grid(row=i, column=2, sticky=tk.W, padx=5, pady=2)
        
        # 配置网格权重
        self.scrollable_frame.columnconfigure(1, weight=1)
        
    def bind_mouse_wheel(self, canvas):
        """绑定鼠标滚轮事件"""
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        def _on_unbind(event):
            canvas.unbind_all("<MouseWheel>")
        
        self.dialog.bind("<Destroy>", _on_unbind)
    
    def load_current_config(self):
        """加载当前配置 - 添加对checkbox的支持"""
        # 从主应用的配置存储中获取配置
        if self.service_name in self.main_app.api_config_storage["services"]:
            config = self.main_app.api_config_storage["services"][self.service_name]
            for param_key, value in config.items():
                if param_key in self.param_widgets:
                    widget = self.param_widgets[param_key]
                    if isinstance(widget, tk.BooleanVar):
                        # Checkbox类型
                        widget.set(bool(value))
                    elif isinstance(widget, scrolledtext.ScrolledText):
                        # 多行文本类型
                        widget.delete("1.0", tk.END)
                        widget.insert("1.0", str(value))
                    else:
                        # 普通Entry类型
                        widget.delete(0, tk.END)
                        widget.insert(0, str(value))
    
    def get_param_values(self):
        """获取参数值 - 添加对checkbox的支持"""
        values = {}
        for param_key, widget in self.param_widgets.items():
            if isinstance(widget, tk.BooleanVar):
                # Checkbox类型
                values[param_key] = widget.get()
            elif isinstance(widget, scrolledtext.ScrolledText):
                # 多行文本类型
                values[param_key] = widget.get("1.0", tk.END).rstrip('\n')
            else:
                # 普通Entry类型
                values[param_key] = widget.get().strip()
        return values
    
    def test_connection(self):
        """测试API连接"""
        params = self.get_param_values()
        
        if self.service_name not in self.main_app.api_test_functions:
            messagebox.showerror("错误", f"未找到 {self.service_name} 的测试函数")
            return
        
        # 检查必需参数
        service_def = None
        for service_type in ['inner', 'custom']:
            if self.service_name in self.main_app.services_storage[service_type]:
                service_def = self.main_app.services_storage[service_type][self.service_name]
                break
            
        if service_def:
            required_params = service_def.get('api_params', [])
            for param in required_params:
                if not params.get(param["key"]):
                    messagebox.showerror("错误", f"请填写 {param['label']}")
                    return
        
        try:
            self.main_app.log(f"开始测试 {self.service_name} API连接...")
            
            # 调用测试函数
            test_function = self.main_app.api_test_functions[self.service_name]
            success, message = test_function(params, self.main_app.log)
            
            if success:
                self.main_app.log(f"{self.service_name} API连接测试成功")
                messagebox.showinfo("成功", f"{self.service_name} API连接测试成功")
            else:
                self.main_app.log(f"{self.service_name} API连接测试失败: {message}")
                messagebox.showerror("错误", f"{self.service_name} API连接测试失败: {message}")
                
        except Exception as e:
            self.main_app.log(f"测试过程中发生错误: {e}")
            messagebox.showerror("错误", f"测试过程中发生错误: {e}")
    
    def save_params(self):
        """保存参数到配置存储"""
        params = self.get_param_values()
        
        # 保存到主应用的配置存储中
        service_name = self.service_name
        self.main_app.api_config_storage["services"][service_name] = params
        
        # 更新界面显示
        self.main_app.update_service_display(service_name)
        
        self.main_app.log(f"{service_name} 参数已更新到配置存储")
        messagebox.showinfo("成功", f"{service_name} 参数已更新")
        
        # 关闭对话框
        self.dialog.destroy()