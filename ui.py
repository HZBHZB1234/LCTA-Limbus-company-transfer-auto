print('正在启动')
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import zipfile
import threading
import time
from shutil import rmtree,copytree
import install,search_result,functions,lighter,get_font,organization
print('启动完毕')

class AdvancedTranslateUI:
    def __init__(self, root):
        self.root = root
        self.root.title("LCTA v3.0.0")
        self.root.geometry("900x650")
        
        # 初始化变量
        self.custom_script_var = tk.BooleanVar(value=False)
        self.cache_trans_var = tk.BooleanVar(value=False)
        self.team_trans_var = tk.BooleanVar(value=False)
        self.excel_output_var = tk.BooleanVar(value=False)
        self.log_enabled_var = tk.BooleanVar(value=True)
        self.half_trans_var = tk.BooleanVar(value=False)
        self.backup_var = tk.BooleanVar(value=False)
        # 下载相关变量
        self.download_progress = tk.DoubleVar(value=0.0)
        self.download_thread = None
        self.stop_download = False
        
        # 创建菜单栏
        self.create_menu()
        
        # 创建主框架
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置网格权重
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        
        # 创建左右分栏
        self.create_sidebar()
        
        # 创建功能区域
        self.create_function_area()
        
        # 绑定事件
        self.bind_events()
        
        # 初始显示翻译界面
        self.show_translate_frame()
    
    def create_sidebar(self):
        # 创建左侧边栏
        self.sidebar_frame = ttk.Frame(self.main_frame, width=150)
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.sidebar_frame.pack_propagate(False)
        
        # 边栏标题
        ttk.Label(self.sidebar_frame, text="功能列表", font=('TkDefaultFont', 10, 'bold')).pack(pady=(0, 10))
        
        # 功能按钮
        self.functions = {
            "翻译工具": self.show_translate_frame,
            "安装已有汉化": self.show_install_frame,
            "使用excel表格附加": self.show_excel_frame,
            "从ourplay下载汉化": self.show_ourplay_frame,
            "清除本地缓存": self.show_clean_frame,
            "从零协下载汉化": self.show_llc_frame,
            "进行文本搜索": self.show_search_frame,
            "备份原文": self.show_backup_frame,
            "缓存文件夹管理": self.show_cache_frame,
            "黑影图调色": self.show_lighter_window
        }
        
        for func_name, func_command in self.functions.items():
            btn = ttk.Button(
                self.sidebar_frame, 
                text=func_name, 
                command=func_command,
                width=15
            )
            btn.pack(pady=5)
        
        # 创建右侧内容区域
        self.content_frame = ttk.Frame(self.main_frame)
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
    
    def create_function_area(self):
        # 创建各个功能框架
        self.frames = {}
        
        # 翻译工具框架
        self.frames["translate"] = ttk.Frame(self.content_frame)
        self.create_translate_frame(self.frames["translate"])
        
        # 安装已有汉化框架
        self.frames["install"] = ttk.Frame(self.content_frame)
        self.create_install_frame(self.frames["install"])
        
        # Excel表格附加框架
        self.frames["excel"] = ttk.Frame(self.content_frame)
        self.create_excel_frame(self.frames["excel"])
        
        # ourplay下载框架
        self.frames["ourplay"] = ttk.Frame(self.content_frame)
        self.create_ourplay_frame(self.frames["ourplay"])
        
        # 清除配置框架
        self.frames["clean"] = ttk.Frame(self.content_frame)
        self.create_clean_frame(self.frames["clean"])
        
        # 零协下载框架
        self.frames["llc"] = ttk.Frame(self.content_frame)
        self.create_llc_frame(self.frames["llc"])

        self.frames["search"] = ttk.Frame(self.content_frame)
        self.create_search_frame(self.frames["search"])

        self.frames["backup"] = ttk.Frame(self.content_frame)
        self.create_backup_frame(self.frames["backup"])
    
        self.frames["cache"] = ttk.Frame(self.content_frame)
        self.create_cache_frame(self.frames["cache"])

    def create_translate_frame(self, parent):
        # 翻译工具界面
        parent.columnconfigure(1, weight=1)
        
        # 自定义脚本选项
        self.custom_script_cb = ttk.Checkbutton(
            parent, 
            text="启用自定义汉化脚本", 
            variable=self.custom_script_var,
            style='TCheckbutton'
        )
        self.custom_script_cb.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(parent, text="脚本文件:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.script_path = ttk.Entry(parent, width=50)
        self.script_path.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        self.browse_script_btn = ttk.Button(parent, text="浏览...", command=self.browse_script)
        self.browse_script_btn.grid(row=1, column=2, padx=(5, 0))
        
        # 实验室功能选项
        ttk.Label(parent, text="实验室功能:", font=('TkDefaultFont', 10, 'bold')).grid(
            row=2, column=0, sticky=tk.W, pady=(10, 5))
        
        self.cache_trans_cb = ttk.Checkbutton(
            parent, 
            text="缓存翻译结果", 
            variable=self.cache_trans_var,
            style='TCheckbutton'
        )
        self.cache_trans_cb.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        self.team_trans_cb = ttk.Checkbutton(
            parent, 
            text="整文件翻译", 
            variable=self.team_trans_var,
            style='TCheckbutton'
        )
        self.team_trans_cb.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Excel输出选项
        self.excel_output_cb = ttk.Checkbutton(
            parent, 
            text="将修改输出至Excel文件", 
            variable=self.excel_output_var,
            style='TCheckbutton'
        )
        self.excel_output_cb.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # 日志选项
        self.log_enabled_cb = ttk.Checkbutton(
            parent, 
            text="启用日志", 
            variable=self.log_enabled_var,
            style='TCheckbutton'
        )
        self.log_enabled_cb.grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # 使用半完成项目选项
        self.half_trans_cb = ttk.Checkbutton(
            parent, 
            text="使用翻译至一半的项目", 
            variable=self.half_trans_var,
            style='TCheckbutton'
        )
        self.half_trans_cb.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(parent, text="半完成项目路径:").grid(row=8, column=0, sticky=tk.W, pady=2)
        self.half_trans_path = ttk.Entry(parent, width=50)
        self.half_trans_path.grid(row=8, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        self.browse_half_trans_btn = ttk.Button(parent, text="浏览...", command=self.browse_half_trans)
        self.browse_half_trans_btn.grid(row=8, column=2, padx=(5, 0))

        self.backup_cb = ttk.Checkbutton(
            parent, 
            text="使用上版本备份原文(需与零协版本一致)", 
            variable=self.backup_var,
            style='TCheckbutton'
        )
        self.backup_cb.grid(row=9, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(parent, text="备份原文路径:").grid(row=10, column=0, sticky=tk.W, pady=2)
        self.backup_path = ttk.Entry(parent, width=50)
        self.backup_path.grid(row=10, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        self.browse_backup_btn = ttk.Button(parent, text="浏览...", command=self.browse_backup)
        self.browse_backup_btn.grid(row=10, column=2, padx=(5, 0))
        ttk.Label(parent, text="选择上一版本零协汉化", font=('TkDefaultFont', 10, 'bold')).grid(
            row=11, column=0, sticky=tk.W, pady=(11, 5))
        ttk.Label(parent, text="零协汉化(或其他汉化包)路径:").grid(row=12, column=0, sticky=tk.W, pady=2)
        self.LLC_path = ttk.Entry(parent, width=50)
        self.LLC_path.grid(row=12, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        self.browse_LLC_btn = ttk.Button(parent, text="浏览...", command=self.browse_LLC)
        self.browse_LLC_btn.grid(row=12, column=2, padx=(5, 0))
        # 翻译原语言选择
        ttk.Label(parent, text="翻译原语言:").grid(row=13, column=0, sticky=tk.W, pady=(10, 5))
        self.lang_var = tk.StringVar(value="kor")
        lang_frame = ttk.Frame(parent)
        lang_frame.grid(row=13, column=1, columnspan=2, sticky=tk.W, pady=(10, 5))
        ttk.Radiobutton(lang_frame, text="韩语", variable=self.lang_var, value="kor").pack(side=tk.LEFT)
        ttk.Radiobutton(lang_frame, text="英语", variable=self.lang_var, value="en").pack(side=tk.LEFT)
        ttk.Radiobutton(lang_frame, text="日文", variable=self.lang_var, value="jp").pack(side=tk.LEFT)
        
        # 按钮框架
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=14, column=0, columnspan=3, pady=20)
        
        ttk.Button(button_frame, text="开始翻译", command=self.start_translation).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重置", command=self.reset_fields).pack(side=tk.LEFT, padx=5)
        
        # 初始状态设置
        self.toggle_custom_script()
        self.toggle_half_trans()
        self.toggle_backup()
    
    def create_install_frame(self, parent):
        # 安装已有汉化界面
        ttk.Label(parent, text="安装已有汉化", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 刷新按钮
        refresh_frame = ttk.Frame(parent)
        refresh_frame.pack(fill=tk.X, pady=5)
        ttk.Button(refresh_frame, text="刷新列表", command=self.refresh_package_list).pack(side=tk.RIGHT)
        
        # 汉化包列表
        ttk.Label(parent, text="可用汉化包:").pack(anchor=tk.W, pady=5)
        
        # 创建框架包含列表和滚动条
        list_frame = ttk.Frame(parent)
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
        button_frame1 = ttk.Frame(parent)
        button_frame1.pack(pady=10)
        
        ttk.Button(button_frame1, text="安装选中汉化包", command=self.install_selected_package).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame1, text="删除选中汉化包", command=self.delete_selected_package).pack(side=tk.LEFT, padx=5)
        
        # 按钮框架 - 第二行
        button_frame2 = ttk.Frame(parent)
        button_frame2.pack(pady=10)
        
        ttk.Button(button_frame2, text="更换选中汉化包字体", command=self.change_font).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame2, text="从已安装字体中获取文件", command=self.get_font_).pack(side=tk.LEFT, padx=5)
        
        # 初始刷新列表
        self.refresh_package_list()
    def get_font_(self):
        """从已安装字体中获取文件"""
        self.get_font_ui=get_font.FontViewer(self.root)
    def change_font(self):
        """更换汉化包字体"""
        font_file = filedialog.askopenfilename(title="选择字体文件", filetypes=[("字体文件", "*.ttf")])
        if not font_file: return
        if not os.path.exists(font_file):
            self.log(f"字体文件不存在: {font_file}")
            return
        selected_package = self.package_listbox.get(tk.ACTIVE)
        install.set_log_callback(self.log)
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
            self.log("未找到可用的汉化包")
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
        
        self.log(f"开始安装汉化包: {package_name}")
        
        # 设置日志回调
        install.set_log_callback(self.log)
        if game_path =='skip':
            messagebox.showinfo("提示", "请选择游戏目录")
            return
        # 调用安装函数
        success, message = install.install(package_path, game_path)
        
        if success:
            self.log("汉化包安装完成")
            messagebox.showinfo("成功", message)
        else:
            self.log(f"安装失败: {message}")
            messagebox.showerror("错误", message)
    def perform_search(self):
        """
        执行搜索操作
        """
        search_term = self.search_var.get()
        search_path = self.search_path_var.get()
        use_regex = self.use_regex_var.get()

        if not search_path:
            self.log("请选择要搜索的文件夹")
            messagebox.showerror("错误", "请选择要搜索的文件夹")
            return
        
        if search_term:
            self.log(f"在 {search_path} 中执行搜索: {search_term}" + (" (正则表达式)" if use_regex else ""))
            if not os.path.exists(search_path):
                self.log("路径不存在")
                messagebox.showerror("错误", "路径不存在")
                return
            
            ok_list = []
            self.log('正在遍历文件夹...')
            file_list = functions.walk_all_files(search_path,search_path)
            self.log(f"遍历完成，共有 {len(file_list)} 个文件")
            
            for i in file_list:
                if not i['file'].endswith('.json'): 
                    continue
                
                with open(i['path'], 'r', encoding='utf-8') as f:
                    text = f.read()
                    
                    if use_regex:
                        import re
                        try:
                            if re.search(search_term, text):
                                self.log(f"找到匹配项: {i['relpath']}")
                                ok_list.append(i)
                        except re.error as e:
                            self.log(f"正则表达式错误: {e}")
                            messagebox.showerror("正则表达式错误", f"正则表达式格式错误: {e}")
                            return
                    else:
                        if search_term in text:
                            self.log(f"找到匹配项: {i['relpath']}")
                            ok_list.append(i)
            if ok_list:
                search_result.SearchResultUI(self.root, ok_list, self.log)
            else:
                messagebox.showinfo("搜索结果", "未找到匹配项")
        else:
            self.log("请输入搜索内容")
            messagebox.showerror("错误", "请输入搜索内容")
    
    def create_excel_frame(self, parent):
        # Excel表格附加界面
        ttk.Label(parent, text="使用Excel表格附加", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        ttk.Label(parent, text="此功能暂未实现").pack(pady=20)
    
    def create_ourplay_frame(self, parent):
        # ourplay下载界面
        ttk.Label(parent, text="从ourplay下载汉化", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 说明文本
        ttk.Label(parent, text="从OurPlay平台下载汉化包").pack(pady=5)
        self.font_option_var = tk.StringVar(value="keep")
        font_frame = ttk.Frame(parent)
        font_frame.pack(pady=10)
        
        ttk.Label(font_frame, text="字体处理:").pack(side=tk.LEFT)
        ttk.Radiobutton(font_frame, text="保留原字体", variable=self.font_option_var, value="keep").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(font_frame, text="精简字体", variable=self.font_option_var, value="simplify").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(font_frame, text="从零协下载字体", variable=self.font_option_var, value="llc").pack(side=tk.LEFT, padx=5)

        # 进度条
        ttk.Label(parent, text="下载进度:").pack(anchor=tk.W, pady=(10, 5))
        self.ourplay_progress = ttk.Progressbar(parent, variable=self.download_progress, maximum=100)
        self.ourplay_progress.pack(fill=tk.X, pady=5)
        
        # 按钮框架
        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="开始下载", command=self.start_ourplay_download).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消下载", command=self.cancel_download).pack(side=tk.LEFT, padx=5)
    def create_clean_frame(self, parent):
        # 清除配置界面
        ttk.Label(parent, text="清除本地缓存文件", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        ttk.Label(parent, text="这将清除所有选中的文件").pack(pady=5)
        ttk.Label(parent, text="操作不可逆，请谨慎操作").pack(pady=5)
        ttk.Label(parent, text="确保你的缓存文件夹链接正确").pack(pady=5)
        self.clean_progress_var = tk.BooleanVar(value=False)
        self.clean_notice_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            parent, 
            text="清除本地进度文件(如教程进度，困牢还是普牢)", 
            variable=self.clean_progress_var
        ).pack(pady=5)
        ttk.Checkbutton(
            parent, 
            text="清除本地通知文件", 
            variable=self.clean_notice_var
        ).pack(pady=5)
        
        # 添加自定义文件选择部分
        ttk.Label(parent, text="自定义要清除的mod修改:").pack(anchor=tk.W, pady=(10, 5))
        
        # 创建文件列表框架
        file_list_frame = ttk.Frame(parent)
        file_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建列表框和滚动条
        self.custom_files_listbox = tk.Listbox(file_list_frame, selectmode=tk.EXTENDED, height=6)
        scrollbar_y = ttk.Scrollbar(file_list_frame, orient=tk.VERTICAL, command=self.custom_files_listbox.yview)
        scrollbar_x = ttk.Scrollbar(file_list_frame, orient=tk.HORIZONTAL, command=self.custom_files_listbox.xview)
        self.custom_files_listbox.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        # 布局
        self.custom_files_listbox.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))
        scrollbar_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        scrollbar_x.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        file_list_frame.columnconfigure(0, weight=1)
        file_list_frame.rowconfigure(0, weight=1)
        
        # 文件操作按钮框架
        file_buttons_frame = ttk.Frame(parent)
        file_buttons_frame.pack(pady=5)
        
        ttk.Button(file_buttons_frame, text="添加文件", command=self.add_custom_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_buttons_frame, text="添加文件夹", command=self.add_custom_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_buttons_frame, text="移除选中", command=self.remove_custom_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_buttons_frame, text="清空列表", command=self.clear_custom_files).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(parent, text="清除配置", command=self.clean_config).pack(pady=20)
        
        # 存储自定义文件路径的列表
        self.custom_files_to_delete = [] 
    def create_llc_frame(self, parent):
        # 零协下载界面
        ttk.Label(parent, text="从零协下载汉化", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 说明文本
        ttk.Label(parent, text="从零协下载汉化包").pack(pady=5)
        
        # 进度条
        ttk.Label(parent, text="下载进度:").pack(anchor=tk.W, pady=(10, 5))
        self.llc_progress = ttk.Progressbar(parent, variable=self.download_progress, maximum=100)
        self.llc_progress.pack(fill=tk.X, pady=5)
        
        # 选项框架
        option_frame = ttk.Frame(parent)
        option_frame.pack(fill=tk.X, pady=5)
        
        self.convert_llc_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(option_frame, text="自动转换零协文本", variable=self.convert_llc_var).pack(anchor=tk.W)
        
        self.clean_temp_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(option_frame, text="下载完成后清理临时文件", variable=self.clean_temp_var).pack(anchor=tk.W)
        
        # 按钮框架
        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="开始下载", command=self.start_llc_download).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消下载", command=self.cancel_download).pack(side=tk.LEFT, padx=5)
    def create_search_frame(self, parent):
        ttk.Label(parent, text="搜索指定文本", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 添加搜索路径选择部分
        ttk.Label(parent, text="选择搜索对象路径:").pack(anchor=tk.W, pady=(10, 5))
        
        # 创建路径选择框架
        path_frame = ttk.Frame(parent)
        path_frame.pack(fill=tk.X, pady=5)
        
        # 路径输入框
        self.search_path_var = tk.StringVar()
        self.search_path_entry = ttk.Entry(path_frame, textvariable=self.search_path_var)
        self.search_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # 文件夹浏览按钮
        self.browse_folder_btn = ttk.Button(path_frame, text="选择文件夹", command=self.browse_search_folder)
        self.browse_folder_btn.pack(side=tk.LEFT, padx=2)
        
        # 搜索内容输入部分
        ttk.Label(parent, text="输入要搜索的内容:").pack(anchor=tk.W, pady=(10, 5))
        
        # 创建搜索框框架
        search_frame = ttk.Frame(parent)
        search_frame.pack(pady=10)
        
        # 创建搜索框
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        
        # 创建正则表达式选项
        self.use_regex_var = tk.BooleanVar(value=False)
        self.regex_checkbox = ttk.Checkbutton(search_frame, text="使用正则表达式", variable=self.use_regex_var)
        self.regex_checkbox.pack(side=tk.LEFT, padx=5)
        
        # 创建搜索按钮
        self.search_button = ttk.Button(search_frame, text="搜索", command=self.perform_search)
        self.search_button.pack(side=tk.LEFT, padx=5)
        
        # 绑定回车键触发搜索
        self.search_entry.bind('<Return>', lambda event: self.perform_search())
        
        # 添加搜索提示标签
        self.search_tip = ttk.Label(search_frame, text="", foreground="gray")
        self.search_tip.pack(side=tk.LEFT, padx=5)

    def browse_search_folder(self):
        """浏览并选择文件夹"""
        folder_path = filedialog.askdirectory(title="选择要搜索的文件夹")
        if folder_path:
            self.search_path_var.set(folder_path)
    def create_backup_frame(self, parent):
        # 备份原文界面
        ttk.Label(parent, text="备份原文", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 说明文本
        ttk.Label(parent, text="此功能用于备份游戏原文文件，以便下次翻译使用").pack(pady=5)
        
        # 备份路径选择
        path_frame = ttk.Frame(parent)
        path_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(path_frame, text="备份保存路径:").pack(anchor=tk.W)
        
        path_input_frame = ttk.Frame(path_frame)
        path_input_frame.pack(fill=tk.X, pady=5)
        
        self.backup_save_path = ttk.Entry(path_input_frame)
        self.backup_save_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        ttk.Button(path_input_frame, text="浏览...", command=self.browse_backup_save_path).pack(side=tk.LEFT)

        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="开始备份", command=self.start_backup).pack(side=tk.LEFT, padx=5)
        #ttk.Button(button_frame, text="从备份恢复", command=self.restore_backup).pack(side=tk.LEFT, padx=5)
    def create_cache_frame(self, parent):
        # 缓存管理界面
        ttk.Label(parent, text="缓存文件管理", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 说明文本
        ttk.Label(parent, text="管理游戏缓存数据包").pack(pady=5)
        

        # 缓存文件列表
        ttk.Label(parent, text="缓存文件:").pack(anchor=tk.W, pady=5)
        
        # 创建框架包含列表和滚动条
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建滚动条
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 创建列表框
        self.cache_listbox = tk.Listbox(
            list_frame, 
            yscrollcommand=scrollbar.set,
            selectmode=tk.EXTENDED,  # 允许多选
            height=10
        )
        self.cache_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 配置滚动条
        scrollbar.config(command=self.cache_listbox.yview)
        
        # 按钮框架
        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=10)
        # 统计信息
        self.cache_stats_label = ttk.Label(parent, text="缓存文件数量: 0, 总大小: 0 KB")
        self.cache_stats_label.pack(pady=5)

    def browse_backup_save_path(self):
        """浏览备份保存路径"""
        folder_path = filedialog.askdirectory(title="选择备份保存路径")
        if folder_path:
            self.backup_save_path.delete(0, tk.END)
            self.backup_save_path.insert(0, folder_path)

    def start_backup(self):
        """开始备份原文"""
        if game_path == 'skip':
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
        
        self.log("开始备份原文...")
        backup_thread = threading.Thread(target=self.backup_thread, args=(save_path,))
        backup_thread.daemon = True
        backup_thread.start()


    def backup_thread(self, save_path):
        """备份线程函数"""
        try:
            self.log(f"正在备份到: {save_path}")
            path_for=game_path+r"LimbusCompany_Data\Assets\Resources_moved\Localize"
            if os.path.exists(f'{save_path}\\LCB_backup.zip'):
                self.log("已存在备份文件")
                messagebox.showinfo("提示", "已存在备份文件")
                return
            functions.zip_folder(path_for, f'{save_path}\\LCB_backup.zip')
            self.log("备份完成")
            messagebox.showinfo("成功", "原文备份完成")
        except Exception as e:
            self.log(f"备份失败: {e}")
            messagebox.showerror("错误", f"备份失败: {e}")

    def show_frame(self, frame_name):
        # 隐藏所有框架
        for frame in self.frames.values():
            frame.pack_forget()
        
        # 显示选中的框架
        self.frames[frame_name].pack(fill=tk.BOTH, expand=True)
    
    def show_translate_frame(self):
        self.show_frame("translate")
        self.log("切换到翻译工具")
    
    def show_install_frame(self):
        self.show_frame("install")
        self.log("切换到安装已有汉化")
    
    def show_excel_frame(self):
        self.show_frame("excel")
        self.log("切换到Excel表格附加")
    
    def show_ourplay_frame(self):
        self.show_frame("ourplay")
        self.log("切换到ourplay下载")
    
    def show_clean_frame(self):
        self.show_frame("clean")
        self.log("切换到清除配置")
    
    def show_llc_frame(self):
        self.show_frame("llc")
        self.log("切换到零协下载")
    
    def show_search_frame(self):
        self.show_frame("search")
        self.log("切换到文本搜索")
    def show_backup_frame(self):
        self.show_frame("backup")
        self.log("切换到备份原文")
    def show_cache_frame(self):
        self.show_frame("cache")
        self.log("切换到缓存文件管理")

    def show_lighter_window(self):
        self.log("启动图片亮度工具")
        lighter.ImageEnhancementApp(self.root)
    def create_menu(self):
        menubar = tk.Menu(self.root)
        
        # 关于菜单
        about_menu = tk.Menu(menubar, tearoff=0)
        about_menu.add_command(label="项目简介", command=self.show_project_info)
        about_menu.add_command(label="更新内容", command=self.show_update_info)
        about_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="关于", menu=about_menu)
        
        self.root.config(menu=menubar)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        # 确保程序完全退出
        self.root.destroy()
        import sys
        sys.exit(0)
    
    def bind_events(self):
        # 绑定变量变化事件
        self.custom_script_var.trace_add('write', self.on_custom_script_change)
        self.half_trans_var.trace_add('write', self.on_half_trans_change)
        self.cache_trans_var.trace_add('write', self.on_cache_trans_change)
        self.team_trans_var.trace_add('write', self.on_team_trans_change)
        self.backup_var.trace_add('write', self.on_backup_change)

    
    def on_custom_script_change(self, *args):
        self.toggle_custom_script()
    
    def on_half_trans_change(self, *args):
        self.toggle_half_trans()
    
    def on_cache_trans_change(self, *args):
        if self.cache_trans_var.get():
            self.team_trans_var.set(False)
    
    def on_team_trans_change(self, *args):
        if self.team_trans_var.get():
            self.cache_trans_var.set(False)
    def on_backup_change(self, *args):
        self.toggle_backup()

    def toggle_backup(self):
        state = "normal" if self.backup_var.get() else "disabled"
        self.backup_path.config(state=state)
        self.browse_backup_btn.config(state=state)
    def toggle_custom_script(self):
        state = "normal" if self.custom_script_var.get() else "disabled"
        self.script_path.config(state=state)
        self.browse_script_btn.config(state=state)
    
    def toggle_half_trans(self):
        state = "normal" if self.half_trans_var.get() else "disabled"
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
        if self.excel_output_var.get():
            file_path = filedialog.askopenfilename(
                title="选择Excel文件",
                filetypes=[("Excel文件", "*.xlsx"), ("所有文件", "*.*")]
            )
        else:
            file_path = filedialog.askdirectory(title="选择半完成项目文件夹")
        
        if file_path:
            self.half_trans_path.delete(0, tk.END)
            self.half_trans_path.insert(0, file_path)
    
    def browse_install_file(self):
        file_path = filedialog.askopenfilename(
            title="选择汉化包文件",
            filetypes=[("Zip文件", "*.zip"), ("所有文件", "*.*")]
        )
        if file_path:
            self.install_path.delete(0, tk.END)
            self.install_path.insert(0, file_path)
    
    def start_translation(self):
        self.log("开始翻译过程...")
        if game_path=='skip':
            messagebox.showinfo("提示", "请选择游戏安装目录")
            return
        # 验证必要的参数
        if self.custom_script_var.get() and not self.script_path.get():
            messagebox.showerror("错误", "请选择自定义脚本文件")
            return
        
        if self.half_trans_var.get() and not self.half_trans_path.get():
            messagebox.showerror("错误", "请选择半完成项目路径")
            return
        
        if self.backup_var.get() and not self.backup_path.get():
            messagebox.showerror("错误", "请选择半完成项目路径")
            return
        if not self.LLC_path.get():
            if messagebox.askyesno("提示", "未选择LLC路径，是否使用默认路径？"):
                cache=(fr'{game_path}LimbusCompany_Data\lang\LLC_zh-CN')
                if os.path.exists(cache):
                    self.LLC_path.delete(0, tk.END)
                    self.LLC_path.insert(0, cache)
                else:
                    messagebox.showerror("错误", "未找到默认路径")
                    return
            else:
                if not messagebox.askyesno('LCTA','从零开始进行翻译?'):
                    return
        config={
            "custom_script":self.custom_script_var.get(),
            "cache_trans":self.cache_trans_var.get(),
            "team_trans":self.team_trans_var.get(),
            "excel_output":self.excel_output_var.get(),
            "log_enabled":self.log_enabled_var.get(),
            "half_trans":self.half_trans_var.get(),
            "backup_enabled":self.backup_var.get(),
            "script_path":self.script_path.get(),
            "half_trans_path":self.half_trans_path.get(),
            "backup_path":self.backup_path.get(),
            "game_path":game_path,
            "LLC_path":self.LLC_path.get(),
            "formal_language":self.lang_var.get()
        }
        organization.translate_organize(config,self.log)
        # 这里应该调用实际的翻译函数
        self.log("翻译完成")
    
    def start_ourplay_download(self):
        """开始OurPlay下载"""
        if self.download_thread and self.download_thread.is_alive():
            messagebox.showwarning("警告", "已有下载任务正在进行中")
            return
        
        self.log("开始从OurPlay下载汉化包...")
        self.stop_download = False
        self.download_progress.set(0)
        
        # 在新线程中执行下载
        self.download_thread = threading.Thread(target=self.download_ourplay_thread)
        self.download_thread.daemon = True
        self.download_thread.start()
    
    def start_llc_download(self):
        """开始零协下载"""
        if self.download_thread and self.download_thread.is_alive():
            messagebox.showwarning("警告", "已有下载任务正在进行中")
            return
        
        self.log("开始从零协下载汉化包...")
        self.stop_download = False
        self.download_progress.set(0)
        
        # 在新线程中执行下载
        self.download_thread = threading.Thread(target=self.download_llc_thread)
        self.download_thread.daemon = True
        self.download_thread.start()
    
    def download_ourplay_thread(self):
        """OurPlay下载线程"""
        try:
            # 设置下载回调函数
            functions.set_log_callback(self.log)
            def progress_callback(progress):
                if self.stop_download:
                    return False
                self.download_progress.set(progress)
                self.root.update_idletasks()
                return True
            
            # 执行下载
            success = functions.download_and_verify_file(progress_callback)
            
            if success and not self.stop_download:
                self.log("下载完成，正在处理文件...")
                self.download_progress.set(50)
                
                # 处理下载的文件
                font_option = self.font_option_var.get()
                functions.get_true_zip('transfile.zip', font_option)
                self.download_progress.set(100)
                self.log("OurPlay汉化包下载和处理完成")
                messagebox.showinfo("成功", "OurPlay汉化包下载和处理完成")
            elif not self.stop_download:
                self.log("下载失败")
                self.download_progress.set(0)
                messagebox.showerror("错误", "下载失败，请检查网络连接")
            else:
                self.download_progress.set(0)
            
        except Exception as e:
            self.log(f"下载过程中发生错误: {e}")
            self.download_progress.set(0)
            messagebox.showerror("错误", f"下载过程中发生错误: {e}")
    
    def download_llc_thread(self):
        """零协下载线程"""
        try:
            # 设置下载回调函数
            functions.set_log_callback(self.log)
            def progress_callback(progress):
                if self.stop_download:
                    return False
                self.download_progress.set(progress)
                self.root.update_idletasks()
                return True
            
            # 执行下载
            success = functions.download_llc(
                progress_callback=progress_callback,
                convert=self.convert_llc_var.get(),
                clean_temp=self.clean_temp_var.get()
            )
            
            if success and not self.stop_download:
                self.download_progress.set(100)
                self.log("零协汉化包下载和处理完成")
                messagebox.showinfo("成功", "零协汉化包下载和处理完成")
            elif not self.stop_download:
                self.log("下载失败")
                self.download_progress.set(0)
                messagebox.showerror("错误", "下载失败，请检查网络连接")
            
        except Exception as e:
            self.log(f"下载过程中发生错误: {e}")
            self.download_progress.set(0)
            messagebox.showerror("错误", f"下载过程中发生错误: {e}")
    
    def cancel_download(self):
        """取消下载"""
        self.stop_download = True
        self.download_progress.set(0)
        self.log("下载已取消")
    def add_custom_file(self):
        """添加自定义文件到删除列表"""
        files = filedialog.askopenfilenames(title="选择要删除的文件")
        for file_path in files:
            if file_path not in self.custom_files_to_delete:
                self.custom_files_to_delete.append(file_path)
                self.custom_files_listbox.insert(tk.END, file_path)

    def add_custom_folder(self):
        """添加自定义文件夹到删除列表"""
        folder = filedialog.askdirectory(title="选择要删除的文件夹")
        if folder and folder not in self.custom_files_to_delete:
            self.custom_files_to_delete.append(folder)
            self.custom_files_listbox.insert(tk.END, f"[文件夹] {folder}")

    def remove_custom_files(self):
        """从列表中移除选中的文件"""
        selected_indices = self.custom_files_listbox.curselection()
        # 从后往前删除，避免索引变化问题
        for index in reversed(selected_indices):
            self.custom_files_listbox.delete(index)
            self.custom_files_to_delete.pop(index)

    def clear_custom_files(self):
        """清空文件列表"""
        self.custom_files_listbox.delete(0, tk.END)
        self.custom_files_to_delete.clear()
    def clean_config(self):
        result = messagebox.askyesno("确认", "确定要清除所有本地配置和缓存文件吗？此操作不可逆。")
        if not result:
            return
        local_low_path = os.path.join(os.environ['APPDATA'], '..', 'LocalLow')
        local_low_path = os.path.abspath(local_low_path)
        if self.clean_progress_var.get():
            self.log("清除本地进程文件...")
            lists=os.listdir(local_low_path+r'\ProjectMoon\LimbusCompany')
            progress_file=[i for i in lists if 'save' in i][0]
            path_config=local_low_path+rf'\ProjectMoon\LimbusCompany\{progress_file}'
            if os.path.exists(path_config):
                os.remove(path_config)
                self.log("本地进程文件已清除")
            else:
                self.log("本地进程文件不存在")
        if self.clean_notice_var.get():
            self.log("清除本地通知文件...")
            path_notice=local_low_path+r'\ProjectMoon\LimbusCompany\synchronous-data_product.json'
            path_notice_dir=local_low_path+r'\ProjectMoon\LimbusCompany\notice'
            try:os.remove(path_notice)    
            except:None
            try:rmtree(path_notice_dir)
            except:None
            self.log("本地通知文件已清除")
        # 清除自定义选择的文件
        self.deleted_count = 0
        for file_path in self.custom_files_to_delete:
            try:
                if os.path.isfile(file_path):
                    self.clear_by_mod(file_path)
                else:
                    self.log(f"{file_path} 不是一个文件")
            except Exception as e:
                self.log(f"删除 {file_path} 失败: {str(e)}")
        
        if self.custom_files_to_delete:
            self.log(f"已删除 {self.deleted_count} 个自定义文件/文件夹")
            
            # 清空列表
            self.clear_custom_files()
    def clear_by_mod(self,mod_path):
        local_low_path = os.path.join(os.environ['APPDATA'], '..', 'LocalLow')
        local_low_path = os.path.abspath(local_low_path)
        for i in self.check_by_mod(mod_path):
            if not i.endswith('Installation/'):
                if 'Installation/' in i:
                    path_del=i.split('/')[-1]
                else:
                    path_del=i.split('/')[0]
        if path_del:
            path=local_low_path+fr'\Unity\ProjectMoon_LimbusCompany\{path_del}'
            if os.path.isdir(path):
                try:
                    rmtree(path)
                    self.deleted_count += 1
                    self.log(f"已删除 {path_del}")
                except Exception as e:
                    self.log(f"删除 {path_del} 失败: {str(e)}")
            else:
                self.log(f"{path_del} 不是一个目录")
    def check_by_mod(self, mod_path):
        try:
            with zipfile.ZipFile(mod_path, 'r') as zip_file:
                # 获取所有文件列表
                all_files = zip_file.namelist()
                
                # 提取第一层目录结构
                first_level_dirs = set()
                for file_path in all_files:
                    # 分割路径，获取第一层目录
                    parts = file_path.split('/')
                    if parts and parts[0]:
                        first_level_dirs.add(parts[0])
                
                # 判断第二层目录中是否存在Assets文件夹
                assets_found = False
                second_level_items = set()
                
                for file_path in all_files:
                    parts = file_path.split('/')
                    # 检查是否为第二层目录的文件或文件夹
                    if len(parts) >= 2 and parts[0] in first_level_dirs:
                        # 只取第二层的项目（文件或文件夹）
                        second_level_item = '/'.join(parts[:2]) + ('/' if not file_path.endswith('/') and len(parts) > 2 else '')
                        second_level_items.add(second_level_item)
                        # 检查是否存在Assets文件夹
                        if parts[1] == 'Assets':
                            assets_found = True
                
                # 如果找到Assets文件夹，返回Assets\Installation\目录中的一层文件和文件夹
                if assets_found:
                    installation_items = set()
                    for file_path in all_files:
                        parts = file_path.split('/')
                        # 检查是否在Assets\Installation\路径下
                        if len(parts) >= 3 and parts[1] == 'Assets' and parts[2] == 'Installation':
                            # 只取Installation目录下的一层
                            installation_item = '/'.join(parts[:4]) + ('/' if len(parts) > 4 else '')
                            installation_items.add(installation_item)
                    return list(installation_items)
                else:
                    # 否则返回第二层目录的一层文件和文件夹
                    return list(second_level_items)
                    
        except zipfile.BadZipFile:
            raise ValueError("无效的zip文件")
        except FileNotFoundError:
            raise FileNotFoundError("找不到指定的zip文件")
        except Exception as e:
            raise Exception(f"处理zip文件时发生错误: {str(e)}")
    def reset_fields(self):
        # 重置所有变量
        self.custom_script_var.set(False)
        self.cache_trans_var.set(False)
        self.team_trans_var.set(False)
        self.excel_output_var.set(False)
        self.log_enabled_var.set(True)
        self.half_trans_var.set(False)
        self.backup_var.set(False)
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
        
        self.log("已重置所有设置")
    
    def log(self, message):
        # 确保日志区域存在
        if hasattr(self, 'log_area'):
            self.log_area.config(state='normal')
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.config(state='disabled')
            self.log_area.see(tk.END)
        else:
            # 如果日志区域尚未创建，打印到控制台
            print(message)
    
    # 关于功能
    def show_project_info(self):
        info = """LCTA即LimbusCompany Translate Automation，是一项开源边狱公司自动翻译软件
当前版本2.0.0
github开源链接HZBHZB1234/LCTA-Limbus-company-transfer-auto
使用本软件产出的项目需要在引用时标明"""
        messagebox.showinfo("项目简介", info)
    
    def show_update_info(self):
        info = """2.0.0(未发布)与3.0.0版本更新内容:
增加了UI
添加了翻译选项功能
添加了工具箱功能
修复了在翻译文件缺失时的错误处理
挖了更多的坑
修复了少量bug
增加了更多bug"""
        messagebox.showinfo("更新内容", info)
    
    def show_about(self):
        info = """LCTA高级汉化工具
作者: HZBHZB1234
贴吧: HZBHZB31415926
GitHub: HZBHZB1234
Bilibili: ygdtpnn"""
        messagebox.showinfo("关于", info)

def check_path():
    global game_path
    if not (os.path.isfile(os.path.expanduser("~")+'\\limbus.txt') and os.path.isfile("path.txt")):
        path_final=install.find_lcb()
        if path_final is None or (not messagebox.askyesno('LCTA','这是你的游戏地址吗\n'+path_final)):
            if not messagebox.askyesno('LCTA',"请指定游戏路径(选择游戏exe文件)(否以强行跳过，可能导致bug)"):
                path_final='skip'
            else:
                path_final=install.has_change()
        else:
            install.write_path(path_final)
    else:
        with open("path.txt", "r") as f:
            data_path = f.readline()
        with open(os.path.expanduser("~")+'\\limbus.txt', "r") as f:
            data_limbus = f.readline()
        if not data_path==data_limbus:
            path_final=install.find_lcb()
            if path_final is None or (not messagebox.askyesno('LCTA','这是你的游戏地址吗\n'+path_final)):
                if not messagebox.askyesno('LCTA',"请指定游戏路径(选择游戏exe文件)(否以强行跳过，可能导致bug)"):
                    path_final='skip'
                else:
                    path_final=install.has_change()
            else:
                install.write_path(path_final)
        else:
            path_final=data_path
    game_path=path_final

def start():
    root = tk.Tk()
    root.withdraw()
    check_path()
    root.deiconify()
    
    app = AdvancedTranslateUI(root)
    # 创建日志区域并放置在主框架下方
    log_frame = ttk.Frame(root, padding="10")
    log_frame.pack(fill=tk.BOTH, expand=False, side=tk.BOTTOM)
    
    ttk.Label(log_frame, text="操作日志:").pack(anchor=tk.W)
    log_area = scrolledtext.ScrolledText(log_frame, width=70, height=10, state='disabled')
    log_area.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
    
    # 将日志区域添加到应用程序实例中
    app.log_area = log_area
    
    root.mainloop()

if __name__ == "__main__":
    start()