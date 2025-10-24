import tkinter as tk
from tkinter import ttk, scrolledtext
import os
from ui_main import AdvancedTranslateUI
import utils.install as install
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    """
    配置日志系统，使用1024KB作为轮换大小
    """
    # 创建logs目录（如果不存在）
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # 配置日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 创建轮换文件处理器，最大1024KB，保留5个备份文件
    handler = RotatingFileHandler(
        'logs/app.log', 
        maxBytes=1024*1024,  # 1024KB
        backupCount=5,       # 保留5个旧日志文件
        encoding='utf-8'
    )
    
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    # 添加处理器到记录器
    logger.addHandler(handler)
    
    return logger
def check_path():
    global game_path
    if not (os.path.isfile(os.path.expanduser("~")+'\\limbus.txt') and os.path.isfile("path.txt")):
        path_final = install.find_lcb()
        if path_final is None or (not tk.messagebox.askyesno('LCTA', '这是你的游戏地址吗\n'+path_final)):
            if not tk.messagebox.askyesno('LCTA', "请指定游戏路径(选择游戏exe文件)(否以强行跳过，可能导致bug)"):
                path_final = 'skip'
            else:
                path_final = install.has_change()
        else:
            install.write_path(path_final)
    else:
        with open("path.txt", "r") as f:
            data_path = f.readline()
        with open(os.path.expanduser("~")+'\\limbus.txt', "r") as f:
            data_limbus = f.readline()
        if not data_path == data_limbus:
            path_final = install.find_lcb()
            if path_final is None or (not tk.messagebox.askyesno('LCTA', '这是你的游戏地址吗\n'+path_final)):
                if not tk.messagebox.askyesno('LCTA', "请指定游戏路径(选择游戏exe文件)(否以强行跳过，可能导致bug)"):
                    path_final = 'skip'
                else:
                    path_final = install.has_change()
            else:
                install.write_path(path_final)
        else:
            path_final = data_path
    return path_final

def start():
    # 设置matplotlib后端,防止调试错误，正式版可以删
    import matplotlib
    matplotlib.use('Agg')
    
    print('正在启动')
    
    # 导入必要的模块
    import sys
    import importlib
    
    # 延迟导入以减少启动时间
    import utils.install as install, windows.search_result as search_result, utils.functions as functions, windows.lighter as lighter, windows.get_font as get_font, organization, windows.calculate as calculate, windows.about as about
    from utils.custom_api_check import check_custom_script
    
    print('启动完毕')
    
    root = tk.Tk()
    root.withdraw()
    game_path = check_path()
    root.deiconify()
    logger = setup_logging()
    app = AdvancedTranslateUI(root, game_path, logger)
    
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