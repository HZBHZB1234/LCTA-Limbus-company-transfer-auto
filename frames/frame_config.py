import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import json
import os
from ui_components import EditParamsDialog

class ConfigFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.create_widgets()
        
    def create_widgets(self):
        """创建配置汉化API界面"""
        ttk.Label(self, text="配置汉化API", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # API配置说明
        ttk.Label(self, text="配置用于翻译的API密钥和服务", font=('TkDefaultFont', 9)).pack(pady=5)
        ttk.Label(self, text="配置完key记得保存，离开时记得切换至想要用的服务并保存至文件", font=('TkDefaultFont', 9)).pack(pady=5)
        
        # 参数配置框架
        self.param_frame = ttk.LabelFrame(self, text="API参数配置", padding="10")
        self.param_frame.pack(fill=tk.X, pady=10)

        # 翻译服务类别选择
        service_type_frame = ttk.LabelFrame(self, text="翻译服务类别", padding="10")
        service_type_frame.pack(fill=tk.X, pady=10)
        
        self.type_service_var = tk.StringVar(value=self.main_app.api_config_storage["service_type"])
        service_type_col = ttk.Frame(service_type_frame)
        service_type_col.pack(fill=tk.X, expand=True)
        ttk.Radiobutton(service_type_col, text='内建翻译服务', variable=self.type_service_var, value='inner').pack(anchor=tk.W)
        ttk.Radiobutton(service_type_col, text='自定义翻译服务', variable=self.type_service_var, value='custom').pack(anchor=tk.W)
        self.type_service_var.trace('w', self.type_service_change)
        
        # 内建翻译服务选择
        self.service_frame = ttk.LabelFrame(self, text="内建翻译服务", padding="10")
        self.service_frame.pack(fill=tk.X, pady=10)
        
        self.inner_service_var = tk.StringVar(value=self.main_app.api_config_storage["service_name"])
        self.inner_service_var.trace('w', self.on_service_change)

        # 创建两列布局以容纳更多选项
        service_col1 = ttk.Frame(self.service_frame)
        service_col1.pack(side=tk.LEFT, fill=tk.X, expand=True)
        service_col2 = ttk.Frame(self.service_frame)
        service_col2.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        # 使用动态加载的服务列表
        services = self.main_app.services_
        for i, (text, value) in enumerate(services):
            frame = service_col1 if i <= len(services) // 2 else service_col2
            ttk.Radiobutton(frame, text=text, variable=self.inner_service_var, value=value).pack(anchor=tk.W)
        
        # 自定义翻译服务选择
        self.service_frame_custom = ttk.LabelFrame(self, text="自定义翻译服务", padding="10")
        
        self.custom_service_var = tk.StringVar(value=self.main_app.api_config_storage["service_name"])
        self.custom_service_var.trace('w', self.on_service_change)
        
        # 自定义脚本选择
        custom_script_frame = ttk.Frame(self.service_frame_custom)
        custom_script_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(custom_script_frame, text="自定义脚本:").pack(side=tk.LEFT)
        self.custom_script_entry = ttk.Entry(custom_script_frame, width=40)
        self.custom_script_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(custom_script_frame, text="浏览...", command=self.browse_custom_script).pack(side=tk.LEFT, padx=2)
        ttk.Button(custom_script_frame, text="加载", command=self.load_custom_script).pack(side=tk.LEFT, padx=2)
        
        # 自定义服务选择
        custom_service_frame = ttk.Frame(self.service_frame_custom)
        custom_service_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(custom_service_frame, text="选择服务:").pack(side=tk.LEFT)
        
        # 创建两列布局以容纳更多选项
        service_col1_custom = ttk.Frame(custom_service_frame)
        service_col1_custom.pack(side=tk.LEFT, fill=tk.X, expand=True)
        service_col2_custom = ttk.Frame(custom_service_frame)
        service_col2_custom.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        # 初始时没有自定义服务
        self.custom_services_radio = []
        
        # 按钮框架
        self.service_button_frame = ttk.Frame(self)
        self.service_button_frame.pack(pady=20)
        
        ttk.Button(self.service_button_frame, text="保存配置", command=self.save_api_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(self.service_button_frame, text="测试连接", command=self.test_api_connection).pack(side=tk.LEFT, padx=5)
        ttk.Button(self.service_button_frame, text="从配置文件重载", command=self.reload_config_from_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(self.service_button_frame, text="清空当前", command=self.clear_current_service).pack(side=tk.LEFT, padx=5)
        ttk.Button(self.service_button_frame, text="编辑参数", command=self.open_edit_dialog).pack(side=tk.LEFT, padx=5)
        
        # 初始创建当前服务的输入框
        if self.main_app.services_:
            if not self.inner_service_var.get():
                self.inner_service_var.set(self.main_app.services_[0][1])
            self.create_service_widgets(self.inner_service_var.get())
        self.type_service_change()
        
    def browse_custom_script(self):
        """浏览自定义脚本文件"""
        file_path = filedialog.askopenfilename(
            title="选择自定义翻译脚本",
            filetypes=[("Python文件", "*.py"), ("所有文件", "*.*")]
        )
        if file_path:
            self.custom_script_entry.delete(0, tk.END)
            self.custom_script_entry.insert(0, file_path)
            
    def load_custom_script(self):
        """加载自定义脚本"""
        script_path = self.custom_script_entry.get()
        if not script_path:
            messagebox.showerror("错误", "请先选择自定义脚本文件")
            return
            
        success, message = self.main_app.load_custom_api(script_path)
        if success:
            messagebox.showinfo("成功", "自定义脚本加载成功")
            # 更新自定义服务选择
            self.update_custom_service_selection()
            # 刷新配置界面
            self.refresh_config_frame()
        else:
            messagebox.showerror("错误", f"加载自定义脚本失败: {message}")
            
    def update_custom_service_selection(self):
        """更新自定义服务选择"""
        # 清除现有的自定义服务单选按钮
        for radio in self.custom_services_radio:
            radio.destroy()
        self.custom_services_radio = []
        
        # 添加新的自定义服务单选按钮
        custom_services = [(service_def.get('name', service_id), service_id) 
                          for service_id, service_def in self.main_app.services_storage['custom'].items()]
        
        # 获取自定义服务选择框架
        custom_service_frame = self.service_frame_custom.winfo_children()[1]  # 第二个子组件是服务选择框架
        service_col1_custom = custom_service_frame.winfo_children()[1]  # 第一列
        service_col2_custom = custom_service_frame.winfo_children()[2]  # 第二列
        
        for i, (text, value) in enumerate(custom_services):
            frame = service_col1_custom if i <= len(custom_services) // 2 else service_col2_custom
            radio = ttk.Radiobutton(frame, text=text, variable=self.custom_service_var, value=value)
            radio.pack(anchor=tk.W)
            self.custom_services_radio.append(radio)
            
        # 如果有自定义服务，选择第一个
        if custom_services:
            self.custom_service_var.set(custom_services[0][1])
            
    def type_service_change(self, _=None, __=None, ___=None):
        """服务类型切换回调"""
        if self.type_service_var.get() == 'custom':
            self.service_frame.pack_forget()
            self.service_frame_custom.pack(fill=tk.X, pady=10, before=self.service_button_frame)
            self.inner_service_var.set('')
        else:
            self.service_frame_custom.pack_forget()
            self.service_frame.pack(fill=tk.X, pady=10, before=self.service_button_frame)
            self.custom_service_var.set('')
            
    def refresh_config_frame(self):
        """
        刷新配置汉化API界面
        重新加载所有配置和服务选项
        """
        # 清除现有的配置框架中的所有内容
        for widget in self.winfo_children():
            widget.destroy()
        
        # 重新创建整个配置界面
        self.create_widgets()
        
        # 重新加载配置文件
        self.reload_config_from_file()
        
        # 触发服务变更以确保界面正确显示
        self.on_service_change()
        self.type_service_change()
        
        self.main_app.log("配置界面已刷新")
        
    def get_organization_service(self):
        """获取当前选中的服务"""
        if self.type_service_var.get() == 'inner':
            service = self.inner_service_var.get()
        else:
            service = self.custom_service_var.get()
        return service if service else None
        
    def on_service_change(self, _=None, __=None, ___=None):
        """当翻译服务改变时的回调函数"""
        new_service = self.get_organization_service()
        if not new_service:
            return
            
        self.create_service_widgets(new_service)

    def create_service_widgets(self, service_name):
        """为指定服务创建参数输入框（只读）"""
        # 清除现有控件
        for widget in self.param_frame.winfo_children():
            widget.destroy()
        
        # 获取服务定义
        service_def = None
        for service_type in ['inner', 'custom']:
            if service_name in self.main_app.services_storage[service_type]:
                service_def = self.main_app.services_storage[service_type][service_name]
                break
        
        if not service_def:
            ttk.Label(self.param_frame, text="未找到服务配置").pack(pady=10)
            return
        
        # 更新标题
        self.param_frame.configure(text=f"{service_def.get('name', service_name)} API参数配置")
        
        # 获取该服务的参数定义
        params = service_def.get('api_params', [])
        self.main_app.service_widgets[service_name] = {}
        
        # 创建参数输入框
        for i, param in enumerate(params):
            # 参数标签
            ttk.Label(self.param_frame, text=param["label"] + ":").grid(row=i, column=0, sticky=tk.W, pady=5, padx=5)
            
            # 根据参数类型创建不同的只读控件
            if param.get("type") == "checkbox":
                # Checkbox类型参数（只读）
                var = tk.BooleanVar()
                checkbox = ttk.Checkbutton(
                    self.param_frame,
                    variable=var,
                    state='disabled'  # 只读状态
                )
                checkbox.grid(row=i, column=1, sticky=tk.W, pady=5, padx=5)
                self.main_app.service_widgets[service_name][param["key"]] = var
                
                # 添加描述文本（如果有）
                if "description" in param:
                    desc_label = ttk.Label(
                        self.param_frame,
                        text=param["description"],
                        font=('TkDefaultFont', 8),
                        foreground="gray"
                    )
                    desc_label.grid(row=i, column=2, sticky=tk.W, padx=5, pady=2)
            else:
                # 普通Entry类型参数
                if param["type"] == "password":
                    entry = ttk.Entry(self.param_frame, width=40, show="*", state='readonly')
                else:
                    entry = ttk.Entry(self.param_frame, width=40, state='readonly')
                
                entry.grid(row=i, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
                self.main_app.service_widgets[service_name][param["key"]] = entry
            
            # 从配置存储中获取当前值
            if service_name in self.main_app.api_config_storage["services"]:
                config_value = self.main_app.api_config_storage["services"][service_name].get(param["key"], "")
                if param.get("type") == "checkbox":
                    # 对于checkbox类型，设置BooleanVar的值
                    widget_var = self.main_app.service_widgets[service_name][param["key"]]
                    widget_var.set(bool(config_value))
                else:
                    # 对于普通Entry类型，设置文本值
                    entry.config(state='normal')
                    entry.delete(0, tk.END)
                    entry.insert(0, config_value)
                    entry.config(state='readonly')
        
        # 添加编辑按钮
        if params:  # 只有有参数时才显示编辑按钮
            edit_btn = ttk.Button(
                self.param_frame, 
                text="编辑参数", 
                command=self.open_edit_dialog
            )
            edit_btn.grid(row=len(params), column=0, columnspan=2, pady=10)
        
        # 配置网格权重使输入框可以扩展
        self.param_frame.columnconfigure(1, weight=1)
        
    def open_edit_dialog(self):
        """打开参数编辑对话框"""
        service_name = self.get_organization_service()
        if not service_name:
            messagebox.showwarning("警告", "请先选择一个翻译服务")
            return
            
        # 检查服务是否存在
        service_exists = False
        for service_type in ['inner', 'custom']:
            if service_name in self.main_app.services_storage[service_type]:
                service_exists = True
                break
                
        if not service_exists:
            messagebox.showerror("错误", f"未找到服务 {service_name}")
            return
        
        # 创建并显示编辑对话框
        dialog = EditParamsDialog(self, service_name, self.main_app)
        
    def update_service_display(self, service_name):
        """更新服务参数显示"""
        if service_name in self.main_app.service_widgets:
            # 从配置存储中获取当前值
            current_config = self.main_app.api_config_storage["services"].get(service_name, {})
            
            # 更新显示区域内容
            for param_key, widget in self.main_app.service_widgets[service_name].items():
                value = current_config.get(param_key, "")
                # 判断控件类型
                if isinstance(widget, tk.BooleanVar):
                    # Checkbox类型
                    widget.set(bool(value))
                else:
                    # 普通Entry类型
                    widget.config(state='normal')
                    widget.delete(0, tk.END)
                    widget.insert(0, str(value))
                    widget.config(state='readonly')
                
    def clear_current_service(self):
        """清空当前服务的配置"""
        service_name = self.get_organization_service()
        if not service_name:
            messagebox.showwarning("警告", "请先选择一个翻译服务")
            return
        
        # 从配置存储中移除该服务的配置
        if service_name in self.main_app.api_config_storage["services"]:
            self.main_app.api_config_storage["services"][service_name] = {}
        
        # 清空界面显示的输入框
        if service_name in self.main_app.service_widgets:
            for param_key, widget in self.main_app.service_widgets[service_name].items():
                widget.config(state='normal')  # 先设置为可编辑
                widget.delete(0, tk.END)
                widget.config(state='readonly')  # 再设置回只读
        
        self.main_app.log(f"已清空 {service_name} 的配置")

    def save_api_config(self):
        """保存所有API配置到文件"""
        try:
            # 更新配置存储中的当前选择
            self.main_app.api_config_storage["service_type"] = self.type_service_var.get()
            self.main_app.api_config_storage["service_name"] = self.get_organization_service()
            
            # 保存到文件
            with open('api_config.json', 'w', encoding='utf-8') as f:
                json.dump(self.main_app.api_config_storage, f, ensure_ascii=False, indent=4)
            
            self.main_app.log("API配置已保存到文件")
            messagebox.showinfo("成功", "API配置已保存")
            return True
            
        except Exception as e:
            error_msg = f"保存配置失败: {e}"
            self.main_app.log(error_msg)
            self.main_app.logger.exception(e)
            messagebox.showerror("错误", error_msg)
            return False

    def reload_config_from_file(self):
        """从配置文件重载配置"""
        try:
            if not os.path.exists('api_config.json'):
                self.main_app.log("未找到配置文件")
                messagebox.showinfo("提示", "未找到配置文件")
                return
            
            with open('api_config.json', 'r', encoding='utf-8') as f:
                file_content = f.read().strip()
                if not file_content:
                    self.main_app.log("配置文件为空")
                    return
                    
                config_data = json.loads(file_content)
            
            # 验证配置结构
            if not isinstance(config_data, dict):
                self.main_app.log("配置文件格式错误")
                return
            
            # 恢复配置存储
            self.main_app.api_config_storage = config_data
            
            # 恢复服务类型和名称
            if 'service_type' in config_data:
                self.type_service_var.set(config_data['service_type'])
            
            if 'service_name' in config_data:
                service_name = config_data['service_name']
                if config_data['service_type'] == 'inner' and service_name in [s[1] for s in self.main_app.services_]:
                    self.inner_service_var.set(service_name)
                elif config_data['service_type'] == 'custom' and service_name in self.main_app.services_storage['custom']:
                    self.custom_service_var.set(service_name)
            
            # 加载自定义脚本
            if 'custom_scripts' in config_data:
                # 清空现有自定义服务
                self.main_app.services_storage['custom'] = {}
                
                for script_info in config_data['custom_scripts']:
                    script_path = script_info.get('path', '')
                    if script_path and os.path.exists(script_path):
                        success, message = self.main_app.load_custom_api(script_path)
                        if success:
                            self.main_app.log(f"自定义脚本已加载: {script_path}")
                        else:
                            self.main_app.log(f"加载自定义脚本失败 {script_path}: {message}")
            
            # 更新界面显示
            self.refresh_config_display()
            
            self.main_app.log("已从配置文件重载配置")
            
        except json.JSONDecodeError as e:
            error_msg = f"配置文件格式错误: {e}"
            self.main_app.log(error_msg)
            messagebox.showerror("错误", error_msg)
            
        except Exception as e:
            error_msg = f"重载配置失败: {e}"
            self.main_app.log(error_msg)
            self.main_app.logger.exception(e)
            messagebox.showerror("错误", error_msg)

    def refresh_config_display(self):
        """根据配置存储刷新配置界面显示"""
        current_service = self.get_organization_service()
        if not current_service:
            return
        
        # 更新当前服务的配置显示
        if current_service in self.main_app.api_config_storage["services"]:
            # 更新界面控件显示
            if current_service in self.main_app.service_widgets:
                for param_key, widget in self.main_app.service_widgets[current_service].items():
                    value = self.main_app.api_config_storage["services"][current_service].get(param_key, "")
                    if isinstance(widget, tk.BooleanVar):
                        # Checkbox类型
                        widget.set(bool(value))
                    else:
                        # 普通Entry类型
                        widget.config(state='normal')
                        widget.delete(0, tk.END)
                        widget.insert(0, str(value))
                        widget.config(state='readonly')
        
        self.main_app.log("配置界面显示已刷新")

    def test_api_connection(self):
        """测试当前选中服务的API连接"""
        service_name = self.get_organization_service()
        if not service_name:
            messagebox.showwarning("警告", "请先选择一个翻译服务")
            return
            
        if service_name not in self.main_app.api_test_functions:
            messagebox.showerror("错误", f"未找到 {service_name} 的测试函数")
            return
        
        # 从配置存储中获取配置参数
        test_params = self.main_app.api_config_storage["services"].get(service_name, {})
        
        # 检查必需参数是否完整
        service_def = None
        for service_type in ['inner', 'custom']:
            if service_name in self.main_app.services_storage[service_type]:
                service_def = self.main_app.services_storage[service_type][service_name]
                break
        
        if service_def:
            required_params = service_def.get('api_params', [])
            for param in required_params:
                if not test_params.get(param["key"]):
                    messagebox.showerror("错误", f"请先配置 {param['label']} 参数")
                    return
        
        try:
            self.main_app.log(f"开始测试 {service_name} API连接...")
            
            # 调用测试函数
            test_function = self.main_app.api_test_functions[service_name]
            success, message = test_function(test_params, self.main_app.log)
            
            if success:
                self.main_app.log(f"{service_name} API连接测试成功")
                messagebox.showinfo("成功", f"{service_name} API连接测试成功")
            else:
                self.main_app.log(f"{service_name} API连接测试失败: {message}")
                messagebox.showerror("错误", f"{service_name} API连接测试失败: {message}")
                
        except Exception as e:
            self.main_app.log(f"测试过程中发生错误: {e}")
            self.main_app.logger.exception(e)
            messagebox.showerror("错误", f"测试过程中发生错误: {e}")