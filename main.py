import tkinter as tk
from tkinter import ttk, scrolledtext
import os
from ui_main import AdvancedTranslateUI
import utils.install as install

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
    # 设置matplotlib后端
    import matplotlib
    matplotlib.use('Agg')
    
    print('正在启动')
    
    # 导入必要的模块
    import sys
    import importlib
    
    # 延迟导入以减少启动时间
    import utils.install as install, search_result, utils.functions as functions, lighter, get_font, organization, calculate, about
    from custom_api_check import check_custom_script
    
    print('启动完毕')
    
    root = tk.Tk()
    root.withdraw()
    game_path = check_path()
    root.deiconify()
    
    app = AdvancedTranslateUI(root, game_path)
    
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