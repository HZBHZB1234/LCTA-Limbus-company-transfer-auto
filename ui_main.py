import tkinter as tk
from tkinter import ttk
import importlib
import sys
import os

# 导入各功能框架
from frames.frame_translate import TranslateFrame
from frames.frame_install import InstallFrame
from frames.frame_ourplay import OurPlayFrame
from frames.frame_clean import CleanFrame
from frames.frame_llc import LLCFrame
from frames.frame_config import ConfigFrame
from frames.frame_search import SearchFrame
from frames.frame_backup import BackupFrame
from frames.frame_assets import AssetsFrame

class AdvancedTranslateUI:
    def __init__(self, root, game_path):
        self.root = root
        self.game_path = game_path
        self.root.title("LCTA v3.0.0")
        self.root.geometry("900x800")
        
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
        
        # API配置存储
        self.api_config_storage = {
            "service_type": "inner",
            "service_name": "",
            "custom_scripts": [],
            "services": {}
        }
        
        # 服务存储结构
        self.services_storage = {
            'inner': {},  # 内建服务
            'custom': {}  # 自定义服务
        }
        
        # 创建主框架
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # 配置网格权重
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        
        # 服务相关属性
        self.service_widgets = {}
        self.api_test_functions = {}
        self.default_service_list = []
        self.services_ = []
        
        # 加载内建API服务
        self.load_inner_api()
        # 初始化api函数
        self.init_test_functions()
        
        # 创建界面
        self.create_sidebar()
        self.create_content_area()
        
        # 绑定事件
        self.bind_events()
        
        # 初始显示翻译界面
        self.show_translate_frame()
        
    def load_inner_api(self):
        """加载inner_api文件夹中的翻译服务"""
        inner_api_path = os.path.join(os.path.dirname(__file__), 'inner_api')
        if not os.path.exists(inner_api_path):
            self.log(f"内建API文件夹不存在: {inner_api_path}")
            return
        
        # 将inner_api添加到Python路径
        if inner_api_path not in sys.path:
            sys.path.insert(0, inner_api_path)
        
        # 遍历inner_api文件夹中的所有.py文件
        for file_name in os.listdir(inner_api_path):
            if file_name.endswith('.py') and not file_name.startswith('__'):
                module_name = file_name[:-3]  # 移除.py后缀
                try:
                    # 动态导入模块
                    spec = importlib.util.spec_from_file_location(module_name, os.path.join(inner_api_path, file_name))
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # 检查模块是否有SERVICE_DEFINITION
                    if hasattr(module, 'SERVICE_DEFINITION'):
                        for service_def in module.SERVICE_DEFINITION:
                            service_id = service_def.get('service')
                            if service_id:
                                self.services_storage['inner'][service_id] = service_def
                                self.log(f"加载内建服务: {service_def.get('name', service_id)}")
                    
                except Exception as e:
                    self.log(f"加载内建API模块 {file_name} 失败: {str(e)}")
        
        # 更新默认服务列表
        self.default_service_list = list(self.services_storage['inner'].keys())
        self.services_ = [(service_def.get('name', service_id), service_id) 
                         for service_id, service_def in self.services_storage['inner'].items()]
        
    def load_custom_api(self, script_path):
        """加载自定义翻译服务"""
        if not os.path.exists(script_path):
            self.log(f"自定义翻译服务文件不存在: {script_path}")
            return False, "文件不存在"
            
        file_name = os.path.basename(script_path)
        if file_name.endswith('.py') and not file_name.startswith('__'):
            module_name = file_name[:-3]  # 移除.py后缀
            try:
                # 动态导入模块
                spec = importlib.util.spec_from_file_location(module_name, script_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # 检查自定义脚本
                from custom_api_check import check_custom_script
                useable, msg = check_custom_script(module, self.default_service_list)
                if not useable:
                    self.log(f"自定义翻译服务文件 {script_path} 不可用: {msg}")
                    return False, msg
                
                # 检查模块是否有SERVICE_DEFINITION
                if hasattr(module, 'SERVICE_DEFINITION'):
                    # 添加到自定义服务存储
                    for service_def in module.SERVICE_DEFINITION:
                        service_id = service_def.get('service')
                        if service_id:
                            self.services_storage['custom'][service_id] = service_def
                            self.log(f"加载自定义服务: {service_def.get('name', service_id)}")
                    
                    # 保存自定义脚本信息到配置存储
                    script_info = {
                        'path': script_path,
                        'services': [service_def.get('service') for service_def in module.SERVICE_DEFINITION]
                    }
                    
                    # 检查是否已存在相同路径的脚本
                    existing_index = -1
                    for i, script in enumerate(self.api_config_storage['custom_scripts']):
                        if script['path'] == script_path:
                            existing_index = i
                            break
                    
                    if existing_index >= 0:
                        self.api_config_storage['custom_scripts'][existing_index] = script_info
                    else:
                        self.api_config_storage['custom_scripts'].append(script_info)
                    
                    return True, "加载成功"
                else:
                    return False, "未找到服务定义"
                
            except Exception as e:
                self.log(f"加载自定义API模块 {script_path} 失败: {str(e)}")
                return False, str(e)
        
        return False, "不支持的脚本格式"

    def init_test_functions(self):
        """初始化翻译服务的api函数"""
        try:
            # 导入api模块
            import api_organ
            
            # 注册api函数 - 为所有服务设置测试函数
            self.api_test_functions = {}
            
            # 为内建服务添加测试函数
            for service_type in ['inner', 'custom']:
                for service_id, service_def in self.services_storage[service_type].items():
                    if 'test_function' in service_def and service_def['test_function']:
                        self.api_test_functions[service_id] = service_def['test_function']
                    elif service_type == 'inner' and hasattr(api_organ, f'trans_{service_id}'):
                        self.api_test_functions[service_id] = getattr(api_organ, f'trans_{service_id}')
                    
        except ImportError:
            self.log("警告: 未找到api_trans模块，api功能将不可用")
            self.api_test_functions = {}
            
    def create_sidebar(self):
        """创建左侧边栏"""
        self.sidebar_frame = ttk.Frame(self.main_frame, width=150)
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.sidebar_frame.pack_propagate(False)
        
        # 边栏标题
        ttk.Label(self.sidebar_frame, text="功能列表", font=('TkDefaultFont', 10, 'bold')).pack(pady=(0, 10))
        
        # 功能按钮
        self.functions = {
            "翻译工具": self.show_translate_frame,
            "安装已有汉化": self.show_install_frame,
            "从ourplay下载汉化": self.show_ourplay_frame,
            "清除本地缓存": self.show_clean_frame,
            "从零协下载汉化": self.show_llc_frame,
            "配置汉化api": self.show_config_frame,
            "进行文本搜索": self.show_search_frame,
            "备份原文": self.show_backup_frame,
            '资源管理': self.show_assets_frame,
            "黑影图调色": self.show_lighter_window,
            "抽卡概率计算": self.show_calculate_window,
            "关于": self.show_about_window
        }
        
        for func_name, func_command in self.functions.items():
            btn = ttk.Button(
                self.sidebar_frame, 
                text=func_name, 
                command=func_command,
                width=15
            )
            btn.pack(pady=5)
    
    def create_content_area(self):
        """创建右侧内容区域"""
        self.content_frame = ttk.Frame(self.main_frame)
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # 创建各个功能框架
        self.frames = {}
        
        # 翻译工具框架
        self.frames["translate"] = TranslateFrame(self.content_frame, self)
        
        # 安装已有汉化框架
        self.frames["install"] = InstallFrame(self.content_frame, self)
          
        # ourplay下载框架
        self.frames["ourplay"] = OurPlayFrame(self.content_frame, self)
        
        # 清除配置框架
        self.frames["clean"] = CleanFrame(self.content_frame, self)
        
        # 零协下载框架
        self.frames["llc"] = LLCFrame(self.content_frame, self)

        self.frames['config'] = ConfigFrame(self.content_frame, self)

        self.frames["search"] = SearchFrame(self.content_frame, self)

        self.frames["backup"] = BackupFrame(self.content_frame, self)

        self.frames['assets'] = AssetsFrame(self.content_frame, self)

    def show_frame(self, frame_name):
        """显示指定框架"""
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
    
    def show_ourplay_frame(self):
        self.show_frame("ourplay")
        self.log("切换到ourplay下载")
    
    def show_clean_frame(self):
        self.show_frame("clean")
        self.log("切换到清除配置")
    
    def show_llc_frame(self):
        self.show_frame("llc")
        self.log("切换到零协下载")
    
    def show_config_frame(self):
        self.show_frame("config")
        self.log("切换到配置界面")
        
    def show_search_frame(self):
        self.show_frame("search")
        self.log("切换到文本搜索")
        
    def show_backup_frame(self):
        self.show_frame("backup")
        self.log("切换到备份原文")
    
    def show_assets_frame(self):
        self.show_frame("assets")
        self.log("切换到资源管理")
        
    def show_lighter_window(self):
        self.log("启动图片亮度工具")
        import lighter
        lighter.ImageEnhancementApp(self.root)
        
    def show_calculate_window(self):
        self.log("启动概率计算工具")
        import calculate
        calculate.GachaCalculator(self.root)
        
    def show_about_window(self):
        self.log("启动关于窗口")
        import about
        about.AboutWindow(self.root)

    def bind_events(self):
        """绑定事件"""
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
        if hasattr(self, 'backup_path'):
            self.backup_path.config(state=state)
        if hasattr(self, 'browse_backup_btn'):
            self.browse_backup_btn.config(state=state)
        
    def toggle_custom_script(self):
        state = "normal" if self.custom_script_var.get() else "disabled"
        if hasattr(self, 'script_path'):
            self.script_path.config(state=state)
        if hasattr(self, 'browse_script_btn'):
            self.browse_script_btn.config(state=state)
    
    def toggle_half_trans(self):
        state = "normal" if self.half_trans_var.get() else "disabled"
        if hasattr(self, 'half_trans_path'):
            self.half_trans_path.config(state=state)
        if hasattr(self, 'browse_half_trans_btn'):
            self.browse_half_trans_btn.config(state=state)
    
    def log(self, message):
        """记录日志"""
        # 确保日志区域存在
        if hasattr(self, 'log_area'):
            self.log_area.config(state='normal')
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.config(state='disabled')
            self.log_area.see(tk.END)
        else:
            # 如果日志区域尚未创建，打印到控制台
            print(message)