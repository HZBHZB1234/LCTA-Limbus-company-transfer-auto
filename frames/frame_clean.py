import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import zipfile
from shutil import rmtree

class CleanFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.create_widgets()
        
    def create_widgets(self):
        """创建清除配置界面"""
        ttk.Label(self, text="清除本地缓存文件", font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        ttk.Label(self, text="这将清除所有选中的文件").pack(pady=5)
        ttk.Label(self, text="操作不可逆，请谨慎操作").pack(pady=5)
        ttk.Label(self, text="确保你的缓存文件夹链接正确").pack(pady=5)
        self.clean_progress_var = tk.BooleanVar(value=False)
        self.clean_notice_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self, 
            text="清除本地进度文件(如教程进度，困牢还是普牢)", 
            variable=self.clean_progress_var
        ).pack(pady=5)
        ttk.Checkbutton(
            self, 
            text="清除本地通知文件", 
            variable=self.clean_notice_var
        ).pack(pady=5)
        
        # 添加自定义文件选择部分
        ttk.Label(self, text="自定义要清除的mod修改:").pack(anchor=tk.W, pady=(10, 5))
        
        # 创建文件列表框架
        file_list_frame = ttk.Frame(self)
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
        file_buttons_frame = ttk.Frame(self)
        file_buttons_frame.pack(pady=5)
        
        ttk.Button(file_buttons_frame, text="添加文件", command=self.add_custom_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_buttons_frame, text="添加文件夹", command=self.add_custom_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_buttons_frame, text="移除选中", command=self.remove_custom_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_buttons_frame, text="清空列表", command=self.clear_custom_files).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(self, text="清除配置", command=self.clean_config).pack(pady=20)
        
        # 存储自定义文件路径的列表
        self.custom_files_to_delete = [] 
        
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
            self.main_app.log("清除本地进程文件...")
            lists = os.listdir(local_low_path + r'\ProjectMoon\LimbusCompany')
            progress_file = [i for i in lists if 'save' in i][0]
            path_config = local_low_path + rf'\ProjectMoon\LimbusCompany\{progress_file}'
            if os.path.exists(path_config):
                os.remove(path_config)
                self.main_app.log("本地进程文件已清除")
            else:
                self.main_app.log("本地进程文件不存在")
        if self.clean_notice_var.get():
            self.main_app.log("清除本地通知文件...")
            path_notice = local_low_path + r'\ProjectMoon\LimbusCompany\synchronous-data_product.json'
            path_notice_dir = local_low_path + r'\ProjectMoon\LimbusCompany\notice'
            try:
                os.remove(path_notice)    
            except:
                None
            try:
                rmtree(path_notice_dir)
            except:
                None
            self.main_app.log("本地通知文件已清除")
        # 清除自定义选择的文件
        self.deleted_count = 0
        for file_path in self.custom_files_to_delete:
            try:
                if os.path.isfile(file_path):
                    self.clear_by_mod(file_path)
                else:
                    self.main_app.log(f"{file_path} 不是一个文件")
            except Exception as e:
                self.main_app.log(f"删除 {file_path} 失败: {str(e)}")
                self.main_app.logger.exception(e)
        
        if self.custom_files_to_delete:
            self.main_app.log(f"已删除 {self.deleted_count} 个自定义文件/文件夹")
            
            # 清空列表
            self.clear_custom_files()
            
    def clear_by_mod(self, mod_path):
        local_low_path = os.path.join(os.environ['APPDATA'], '..', 'LocalLow')
        local_low_path = os.path.abspath(local_low_path)
        for i in self.check_by_mod(mod_path):
            if not i.endswith('Installation/'):
                if 'Installation/' in i:
                    path_del = i.split('/')[-1]
                else:
                    path_del = i.split('/')[0]
        if path_del:
            path = local_low_path + fr'\Unity\ProjectMoon_LimbusCompany\{path_del}'
            if os.path.isdir(path):
                try:
                    rmtree(path)
                    self.deleted_count += 1
                    self.main_app.log(f"已删除 {path_del}")
                except Exception as e:
                    self.main_app.log(f"删除 {path_del} 失败: {str(e)}")
                    self.main_app.logger.exception(e)
            else:
                self.main_app.log(f"{path_del} 不是一个目录")
                
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
            self.main_app.log(f"处理zip文件时发生错误: {str(e)}")
            self.main_app.logger.exception(e)
            raise Exception(f"处理zip文件时发生错误: {str(e)}")