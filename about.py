import tkinter as tk
from tkinter import ttk
import webbrowser
from PIL import Image, ImageTk
import bonus

class AboutWindow:
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("关于 LCTA")
        self.window.geometry("600x800")
        self.window.resizable(True, True)
        self.window.transient(parent)
        self.window.grab_set()
        
        # 设置窗口图标（如果有）
        try:
            self.window.iconbitmap("icon.ico")
        except:
            pass
        
        # 创建主框架
        self.main_frame = ttk.Frame(self.window, padding="15")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建内容
        self.create_header()
        self.create_project_info()
        self.create_author_info()
        self.create_tips_section()
        
        # 绑定窗口关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self.close_window)
    
    def create_header(self):
        """创建标题和头像区域"""
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 尝试加载头像
        try:
            # 假设头像文件名为avatar.png，位于当前目录
            avatar_image = Image.open("avatar.webp")
            avatar_image = avatar_image.resize((80, 80), Image.Resampling.LANCZOS)
            self.avatar_photo = ImageTk.PhotoImage(avatar_image)
            avatar_label = ttk.Label(header_frame, image=self.avatar_photo)
        except:
            # 如果头像加载失败，使用默认文本
            avatar_label = ttk.Label(header_frame, text="👤", font=("Arial", 40))
        
        avatar_label.pack(side=tk.LEFT, padx=(0, 15))
        
        # 标题和版本信息
        title_frame = ttk.Frame(header_frame)
        title_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(
            title_frame, 
            text="LCTA 汉化工具箱", 
            font=("Arial", 16, "bold")
        )
        title_label.pack(anchor=tk.W)
        
        version_label = ttk.Label(
            title_frame, 
            text="版本: 3.0.0", 
            font=("Arial", 10)
        )
        version_label.pack(anchor=tk.W, pady=(5, 0))
        
        # 关闭按钮
        close_btn = ttk.Button(
            header_frame, 
            text="关闭", 
            command=self.close_window,
            width=10
        )
        close_btn.pack(side=tk.RIGHT)
    
    def create_project_info(self):
        """创建项目信息区域"""
        project_frame = ttk.LabelFrame(self.main_frame, text="项目简介", padding="10")
        project_frame.pack(fill=tk.X, pady=(0, 15))
        
        project_text = """
LCTA (LimbusCompany Translate Automation) 是一项开源的《边狱公司》自动翻译软件。

主要功能：
• 自动翻译游戏文本
• 支持多种翻译选项和自定义脚本
• 从多个来源下载汉化包
• 文本搜索和备份管理
• 丰富的工具箱功能

本项目基于MIT协议开源
同时，使用本软件产出的项目例如汉化包或是模组需要在引用时标明，该条例具有继承性
"""
        
        project_label = ttk.Label(
            project_frame, 
            text=project_text,
            justify=tk.LEFT,
            wraplength=550
        )
        project_label.pack(anchor=tk.W)
        
        # GitHub链接
        github_frame = ttk.Frame(project_frame)
        github_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(github_frame, text="GitHub:").pack(side=tk.LEFT)
        
        github_link = ttk.Label(
            github_frame, 
            text="https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto",
            foreground="blue",
            cursor="hand2"
        )
        github_link.pack(side=tk.LEFT, padx=(5, 0))
        github_link.bind("<Button-1>", lambda e: self.open_url("https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto"))
    
    def create_author_info(self):
        """创建作者信息区域"""
        author_frame = ttk.LabelFrame(self.main_frame, text="作者信息", padding="10")
        author_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 作者基本信息
        author_info = """
作者: HZBHZB1234
贴吧: HZBHZB31415926
GitHub: HZBHZB1234
Bilibili: ygdtpnn
"""
        author_label = ttk.Label(
            author_frame, 
            text=author_info,
            justify=tk.LEFT
        )
        author_label.pack(anchor=tk.W)
        
        # 社交媒体链接
        social_frame = ttk.Frame(author_frame)
        social_frame.pack(fill=tk.X, pady=(10, 0))
        
        # B站链接
        bilibili_link = ttk.Label(
            social_frame, 
            text="访问B站主页",
            foreground="blue",
            cursor="hand2"
        )
        bilibili_link.pack(side=tk.LEFT, padx=(0, 15))
        bilibili_link.bind("<Button-1>", lambda e: self.open_url("https://space.bilibili.com/3493119444126599"))
        
        # GitHub链接
        github_link = ttk.Label(
            social_frame, 
            text="访问GitHub主页",
            foreground="blue",
            cursor="hand2"
        )
        github_link.pack(side=tk.LEFT)
        github_link.bind("<Button-1>", lambda e: self.open_url("https://github.com/HZBHZB1234"))
        # 贴吧链接
        baidu_link = ttk.Label(
            social_frame, 
            text="访问贴吧主页",
            foreground="blue",
            cursor="hand2"
        )
        baidu_link.pack(side=tk.LEFT)
        baidu_link.bind("<Button-1>", lambda e: self.open_url("https://tieba.baidu.com/home/main?id=tb.1.61b6e0a8.3u85IPhI8SxCTKr10fA00g&fr=userbar"))
    def create_tips_section(self):
        """创建每日一言区域"""
        tips_frame = ttk.LabelFrame(self.main_frame, text="每日一言", padding="10")
        tips_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # 每日一言内容
        self.tips_text = tk.StringVar()
        self.tips_text.set(bonus.get_bonus())  # 从bonus模块获取随机每日一言
        
        tips_label = ttk.Label(
            tips_frame, 
            textvariable=self.tips_text,
            wraplength=550,
            justify=tk.LEFT
        )
        tips_label.pack(anchor=tk.W, fill=tk.X)
        
        # 刷新每日一言按钮
        refresh_btn = ttk.Button(
            tips_frame, 
            text="刷新",
            command=self.refresh_tip
        )
        refresh_btn.pack(anchor=tk.E, pady=(10, 0))
    
    
    def refresh_tip(self):
        """刷新每日一言"""
        self.tips_text.set(bonus.get_bonus())
    
    def open_url(self, url):
        """打开URL"""
        webbrowser.open_new(url)
    
    def close_window(self):
        """关闭窗口"""
        self.window.grab_release()
        self.window.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = AboutWindow(root)
    root.mainloop()