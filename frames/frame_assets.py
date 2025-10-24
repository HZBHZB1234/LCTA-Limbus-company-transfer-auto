import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os

class AssetsFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.create_widgets()
        self.load_assets_config()
        
    def create_widgets(self):
        """
        创建资源管理器界面
        """
        # 主标题
        ttk.Label(self, text="资源管理", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 说明文本
        ttk.Label(self, text="管理系统中的项目资源，包括项目名称和对应文件夹路径").pack(pady=5)
        ttk.Label(self, text="设置完了记得保存").pack(pady=5)

        # 创建列表框架
        list_frame = ttk.LabelFrame(self, text="项目列表", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # 创建Treeview来显示项目列表
        columns = ('name', 'project_path', 'unity_path')
        self.assets_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)
        
        # 定义列标题
        self.assets_tree.heading('name', text='项目名称')
        self.assets_tree.heading('project_path', text='Project文件夹位置')
        self.assets_tree.heading('unity_path', text='Unity文件夹位置')
        
        # 设置列宽
        self.assets_tree.column('name', width=150)
        self.assets_tree.column('project_path', width=300)
        self.assets_tree.column('unity_path', width=300)
        
        # 添加滚动条
        assets_scrollbar_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.assets_tree.yview)
        assets_scrollbar_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.assets_tree.xview)
        self.assets_tree.configure(yscrollcommand=assets_scrollbar_y.set, xscrollcommand=assets_scrollbar_x.set)
        
        # 布局Treeview和滚动条
        self.assets_tree.grid(row=0, column=0, sticky='nsew')
        assets_scrollbar_y.grid(row=0, column=1, sticky='ns')
        assets_scrollbar_x.grid(row=1, column=0, sticky='ew')
        
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # 按钮框架
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, pady=10)
        
        # 添加项目按钮
        ttk.Button(button_frame, text="添加项目", command=self.add_asset_project).pack(side=tk.LEFT, padx=5)
        
        # 删除选中项目按钮
        ttk.Button(button_frame, text="删除选中", command=self.delete_selected_asset).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="应用选中", command=self.using_selected_asset).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="清空链接", command=self.cancel_asset_connect).pack(side=tk.LEFT, padx=5)
        
        # 保存配置按钮
        ttk.Button(button_frame, text="保存配置", command=self.save_assets_config).pack(side=tk.RIGHT, padx=5)
        
        # 刷新配置按钮
        ttk.Button(button_frame, text="刷新配置", command=self.load_assets_config).pack(side=tk.RIGHT, padx=5)
        
        # 存储项目数据
        self.asset_projects = []
        
    def using_selected_asset(self):
        """
        应用选中的项目资源链接
        """
        selected_items = self.assets_tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请先选择一个项目")
            return
        
        # 只使用第一个选中的项目（单选）
        item = selected_items[0]
        values = self.assets_tree.item(item, 'values')
        name = values[0]
        project_path = values[1]
        unity_path = values[2]
        
        # 检查路径是否存在
        if not os.path.exists(project_path):
            messagebox.showerror("错误", f"Project路径不存在: {project_path}")
            return
            
        if not os.path.exists(unity_path):
            messagebox.showerror("错误", f"Unity路径不存在: {unity_path}")
            return
        self.cancel_asset_connect(True)
        local_low_path = os.path.join(os.environ['APPDATA'], '..', 'LocalLow')
        local_low_path = os.path.abspath(local_low_path)
        try:
            os.symlink(project_path, local_low_path+'\\ProjectMoon')
            os.symlink(unity_path, local_low_path+'\\Unity')
            self.main_app.log(f"已应用项目 '{name}' 的资源链接")
            messagebox.showinfo("成功", f"已应用项目 '{name}' 的资源链接")
        except Exception as e:
            self.main_app.log(f"应用项目 '{name}' 的资源链接失败: {str(e)}")
            self.main_app.logger.exception(e)
            messagebox.showerror("错误", f"应用项目 '{name}' 的资源链接失败: {str(e)}")
            return

    def cancel_asset_connect(self, use=False):
        """
        清空资源链接
        """
        local_low_path = os.path.join(os.environ['APPDATA'], '..', 'LocalLow')
        local_low_path = os.path.abspath(local_low_path)
        if os.path.exists(local_low_path+'\\ProjectMoon'):
            if os.path.islink(local_low_path+'\\ProjectMoon'):
                try:
                    os.unlink(local_low_path+'\\ProjectMoon')
                    self.main_app.log("已清空ProjectMoon链接")
                except Exception as e:
                    self.main_app.log(f"清空ProjectMoon链接失败: {str(e)}")
                    self.main_app.logger.exception(e)
            else:
                self.main_app.log("ProjectMoon文件夹不是链接")
        if os.path.exists(local_low_path+'\\Unity'):
            if os.path.islink(local_low_path+'\\Unity'):
                try:
                    os.unlink(local_low_path+'\\Unity')
                    self.main_app.log("已清空Unity链接")
                except Exception as e:
                    self.main_app.log(f"清空Unity链接失败: {str(e)}")
                    self.main_app.logger.exception(e)
            else:
                self.main_app.log("Unity文件夹不是链接")
        self.main_app.log("已清空资源链接")
        if not use:
            messagebox.showinfo("提示", "已清空资源链接")
            
    def add_asset_project(self):
        """
        添加新的项目资源
        """
        # 创建添加项目的对话框
        dialog = tk.Toplevel(self.main_app.root)
        dialog.title("添加项目")
        dialog.geometry("600x250")
        dialog.resizable(False, False)
        dialog.grab_set()  # 模态对话框
        
        # 居中显示
        dialog.transient(self.main_app.root)
        dialog.geometry("+%d+%d" % (dialog.winfo_screenwidth()/2 - 300, dialog.winfo_screenheight()/2 - 125))
        
        # 项目名称
        ttk.Label(dialog, text="项目名称:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=10)
        name_var = tk.StringVar()
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=50)
        name_entry.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=10, pady=10)
        
        # Project文件夹路径
        ttk.Label(dialog, text="ProjectMoon文件夹:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        project_path_var = tk.StringVar()
        project_path_entry = ttk.Entry(dialog, textvariable=project_path_var, width=50)
        project_path_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)
        ttk.Button(dialog, text="浏览...", command=lambda: self.browse_asset_folder(project_path_var)).grid(row=1, column=2, padx=(0, 10), pady=5)
        
        # Unity文件夹路径
        ttk.Label(dialog, text="Unity文件夹:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        unity_path_var = tk.StringVar()
        unity_path_entry = ttk.Entry(dialog, textvariable=unity_path_var, width=50)
        unity_path_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)
        ttk.Button(dialog, text="浏览...", command=lambda: self.browse_asset_folder(unity_path_var)).grid(row=2, column=2, padx=(0, 10), pady=5)
        
        # 按钮框架
        button_box = ttk.Frame(dialog)
        button_box.grid(row=3, column=0, columnspan=3, pady=20)
        
        def save_project():
            name = name_var.get().strip()
            project_path = project_path_var.get().strip()
            unity_path = unity_path_var.get().strip()
            
            if not name:
                messagebox.showerror("错误", "请输入项目名称")
                return
                
            if not project_path or not os.path.isdir(project_path):
                messagebox.showerror("错误", "请选择有效的Project文件夹路径")
                return
                
            if not unity_path or not os.path.isdir(unity_path):
                messagebox.showerror("错误", "请选择有效的Unity文件夹路径")
                return
            
            # 添加到列表
            self.asset_projects.append({
                'name': name,
                'project_path': project_path,
                'unity_path': unity_path
            })
            
            # 更新显示
            self.refresh_assets_tree()
            
            # 关闭对话框
            dialog.destroy()
            
            self.main_app.log(f"已添加项目: {name}")
        
        ttk.Button(button_box, text="确定", command=save_project).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_box, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # 配置列权重
        dialog.columnconfigure(1, weight=1)

    def browse_asset_folder(self, path_var):
        """
        浏览文件夹并设置路径
        """
        folder_path = filedialog.askdirectory(title="选择文件夹")
        if folder_path:
            path_var.set(folder_path)

    def refresh_assets_tree(self):
        """
        刷新项目列表显示
        """
        # 清空现有项目
        for item in self.assets_tree.get_children():
            self.assets_tree.delete(item)
        
        # 添加所有项目到列表
        for project in self.asset_projects:
            self.assets_tree.insert('', tk.END, values=(
                project['name'],
                project['project_path'],
                project['unity_path']
            ))

    def delete_selected_asset(self):
        """
        删除选中的项目
        """
        selected_items = self.assets_tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请先选择要删除的项目")
            return
        
        # 确认删除
        if not messagebox.askyesno("确认删除", "确定要删除选中的项目吗？"):
            return
        
        # 获取选中项目的索引并删除
        for item in selected_items:
            # 获取项目在Treeview中的值
            values = self.assets_tree.item(item, 'values')
            name = values[0]
            
            # 从数据列表中删除
            self.asset_projects = [p for p in self.asset_projects if p['name'] != name]
            
            # 从Treeview中删除
            self.assets_tree.delete(item)
        
        self.main_app.log(f"已删除 {len(selected_items)} 个项目")

    def save_assets_config(self):
        """
        保存资源配置到文件
        """
        try:
            with open('assets_config.json', 'w', encoding='utf-8') as f:
                json.dump(self.asset_projects, f, ensure_ascii=False, indent=4)
            self.main_app.log("资源配置已保存")
            messagebox.showinfo("成功", "资源配置已保存")
        except Exception as e:
            self.main_app.log(f"保存配置失败: {e}")
            self.main_app.logger.exception(e)
            messagebox.showerror("错误", f"保存配置失败: {e}")

    def load_assets_config(self):
        """
        从文件加载资源配置
        """
        try:
            if os.path.exists('assets_config.json'):
                with open('assets_config.json', 'r', encoding='utf-8') as f:
                    self.asset_projects = json.load(f)
                
                # 更新显示
                self.refresh_assets_tree()
                
                self.main_app.log("资源配置已加载")
            else:
                self.main_app.log("未找到配置文件")
        except Exception as e:
            self.main_app.log(f"刷新配置失败: {e}")
            self.main_app.logger.exception(e)
            messagebox.showerror("错误", f"刷新配置失败: {e}")