import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import functions
import os
import search_result

class SearchFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.create_widgets()
        
    def create_widgets(self):
        """创建搜索界面"""
        ttk.Label(self, text="搜索指定文本", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        # 添加搜索路径选择部分
        ttk.Label(self, text="选择搜索对象路径:").pack(anchor=tk.W, pady=(10, 5))
        
        # 创建路径选择框架
        path_frame = ttk.Frame(self)
        path_frame.pack(fill=tk.X, pady=5)
        
        # 路径输入框
        self.search_path_var = tk.StringVar()
        self.search_path_entry = ttk.Entry(path_frame, textvariable=self.search_path_var)
        self.search_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # 文件夹浏览按钮
        self.browse_folder_btn = ttk.Button(path_frame, text="选择文件夹", command=self.browse_search_folder)
        self.browse_folder_btn.pack(side=tk.LEFT, padx=2)
        
        # 搜索内容输入部分
        ttk.Label(self, text="输入要搜索的内容:").pack(anchor=tk.W, pady=(10, 5))
        
        # 创建搜索框框架
        search_frame = ttk.Frame(self)
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
            
    def perform_search(self):
        """
        执行搜索操作
        """
        search_term = self.search_var.get()
        search_path = self.search_path_var.get()
        use_regex = self.use_regex_var.get()

        if not search_path:
            self.main_app.log("请选择要搜索的文件夹")
            messagebox.showerror("错误", "请选择要搜索的文件夹")
            return
        
        if search_term:
            self.main_app.log(f"在 {search_path} 中执行搜索: {search_term}" + (" (正则表达式)" if use_regex else ""))
            if not os.path.exists(search_path):
                self.main_app.log("路径不存在")
                messagebox.showerror("错误", "路径不存在")
                return
            
            ok_list = []
            self.main_app.log('正在遍历文件夹...')
            file_list = functions.walk_all_files(search_path, search_path)
            self.main_app.log(f"遍历完成，共有 {len(file_list)} 个文件")
            
            for i in file_list:
                if not i['file'].endswith('.json'): 
                    continue
                
                with open(i['path'], 'r', encoding='utf-8') as f:
                    text = f.read()
                    
                    if use_regex:
                        import re
                        try:
                            if re.search(search_term, text):
                                self.main_app.log(f"找到匹配项: {i['relpath']}")
                                ok_list.append(i)
                        except re.error as e:
                            self.main_app.log(f"正则表达式错误: {e}")
                            messagebox.showerror("正则表达式错误", f"正则表达式格式错误: {e}")
                            return
                    else:
                        if search_term in text:
                            self.main_app.log(f"找到匹配项: {i['relpath']}")
                            ok_list.append(i)
            if ok_list:
                search_result.SearchResultUI(self.main_app.root, ok_list, self.main_app.log)
            else:
                messagebox.showinfo("搜索结果", "未找到匹配项")
        else:
            self.main_app.log("请输入搜索内容")
            messagebox.showerror("错误", "请输入搜索内容")