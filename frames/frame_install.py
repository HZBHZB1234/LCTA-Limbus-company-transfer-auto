import tkinter as tk
from tkinter import ttk, messagebox
import os
import zipfile
from shutil import rmtree
import install
import get_font

class InstallFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.game_path = main_app.game_path
        self.create_widgets()
        
    def create_widgets(self):
        """创建安装已有汉化界面"""
        ttk.Label(self, text="安装已有汉化", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 刷新按钮
        refresh_frame = ttk.Frame(self)
        refresh_frame.pack(fill=tk.X, pady=5)
        ttk.Button(refresh_frame, text="刷新列表", command=self.refresh_package_list).pack(side=tk.RIGHT)
        
        # 汉化包列表
        ttk.Label(self, text="可用汉化包:").pack(anchor=tk.W, pady=5)
        
        # 创建框架包含列表和滚动条
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建滚动条
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 创建列表框
        self.package_listbox = tk.Listbox(
            list_frame, 
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            height=10
        )
        self.package_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 配置滚动条
        scrollbar.config(command=self.package_listbox.yview)
        
        # 按钮框架 - 第一行
        button_frame1 = ttk.Frame(self)
        button_frame1.pack(pady=10)
        
        ttk.Button(button_frame1, text="安装选中汉化包", command=self.install_selected_package).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame1, text="删除选中汉化包", command=self.delete_selected_package).pack(side=tk.LEFT, padx=5)
        
        # 按钮框架 - 第二行
        button_frame2 = ttk.Frame(self)
        button_frame2.pack(pady=10)
        
        ttk.Button(button_frame2, text="更换选中汉化包字体", command=self.change_font).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame2, text="从已安装字体中获取文件", command=self.get_font_).pack(side=tk.LEFT, padx=5)
        
        # 初始刷新列表
        self.refresh_package_list()
        
    def get_font_(self):
        """从已安装字体中获取文件"""
        self.get_font_ui = get_font.FontViewer(self.main_app.root)
        
    def change_font(self):
        """更换汉化包字体"""
        from tkinter import filedialog
        font_file = filedialog.askopenfilename(title="选择字体文件", filetypes=[("字体文件", "*.ttf")])
        if not font_file: return
        if not os.path.exists(font_file):
            self.main_app.log(f"字体文件不存在: {font_file}")
            return
        selected_package = self.package_listbox.get(tk.ACTIVE)
        install.set_log_callback(self.main_app.log)
        install.change_font(selected_package, font_file)
        self.refresh_package_list()

    def refresh_package_list(self):
        """刷新可用汉化包列表"""
        self.package_listbox.delete(0, tk.END)
        
        # 获取当前目录下的文件和文件夹
        current_dir = os.getcwd()
        items = os.listdir(current_dir)
        
        valid_packages = []
        
        # 检查zip文件
        for item in items:
            if item.endswith('.zip'):
                zip_path = os.path.join(current_dir, item)
                try:
                    with zipfile.ZipFile(zip_path, "r") as zipf:
                        # 检查zip文件是否损坏
                        result = zipf.testzip()
                        if result is not None:
                            continue
                        
                        # 检查是否包含必要的文件夹
                        namelist = zipf.namelist()
                        has_battle_announcer = any('BattleAnnouncerDlg' in name for name in namelist)
                        has_font = any('Font' in name for name in namelist)
                        
                        if has_battle_announcer and has_font:
                            valid_packages.append(item)
                except:
                    continue
        
        # 检查文件夹
        for item in items:
            item_path = os.path.join(current_dir, item)
            if os.path.isdir(item_path) and '.' not in item:
                # 检查是否包含必要的子文件夹
                battle_announcer_path = os.path.join(item_path, 'BattleAnnouncerDlg')
                font_path = os.path.join(item_path, 'Font')
                
                if os.path.exists(battle_announcer_path) and os.path.exists(font_path):
                    valid_packages.append(item)
        
        # 添加到列表框
        for package in valid_packages:
            self.package_listbox.insert(tk.END, package)
        
        if not valid_packages:
            self.package_listbox.insert(tk.END, "未找到可用的汉化包")
            self.main_app.log("未找到可用的汉化包")
            
    def delete_selected_package(self):
        """删除选中的汉化包"""
        selection = self.package_listbox.curselection()
        if not selection:
            messagebox.showerror("错误", "请先选择一个汉化包")
            return
        package_name = self.package_listbox.get(selection[0])
        package_path = os.path.join(os.getcwd(), package_name)
        if os.path.isdir(package_path):
            rmtree(package_path)
        elif os.path.isfile(package_path):
            os.remove(package_path)
        self.refresh_package_list()

    def install_selected_package(self):
        """安装选中的汉化包"""
        selection = self.package_listbox.curselection()
        if not selection:
            messagebox.showerror("错误", "请先选择一个汉化包")
            return
        
        package_name = self.package_listbox.get(selection[0])
        package_path = os.path.join(os.getcwd(), package_name)
        
        self.main_app.log(f"开始安装汉化包: {package_name}")
        
        # 设置日志回调
        install.set_log_callback(self.main_app.log)
        if self.game_path == 'skip':
            messagebox.showinfo("提示", "请选择游戏目录")
            return
            
        # 调用安装函数
        success, message = install.install(package_path, self.game_path)
        
        if success:
            self.main_app.log("汉化包安装完成")
            messagebox.showinfo("成功", message)
        else:
            self.main_app.log(f"安装失败: {message}")
            messagebox.showerror("错误", message)