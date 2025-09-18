import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json

class SearchResultUI:
    def __init__(self, parent, search_results, log_callback=None):
        self.parent = parent
        self.search_results = search_results
        self.log_callback = log_callback
        self.selected_item = None
        
        # 创建顶层窗口
        self.window = tk.Toplevel(parent)
        self.window.title("搜索结果")
        self.window.geometry("800x600")
        
        # 创建主框架
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 结果标签
        ttk.Label(main_frame, text=f"找到 {len(search_results)} 个匹配项:", 
                 font=('TkDefaultFont', 12, 'bold')).pack(anchor=tk.W, pady=(0, 10))
        
        # 创建列表框架
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 创建滚动条
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 创建列表框
        self.result_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            height=20
        )
        self.result_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.result_listbox.yview)
        
        # 填充列表数据
        for item in self.search_results:
            self.result_listbox.insert(tk.END, item['relpath'])
        
        # 绑定选择事件
        self.result_listbox.bind('<<ListboxSelect>>', self.on_select)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        # 创建按钮
        ttk.Button(button_frame, text="导出所有匹配项地址", 
                  command=self.export_all_json).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导出所有匹配项文件", 
                  command=self.export_all_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="打开选中项", 
                  command=self.open_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="打开文件位置", 
                  command=self.open_location).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="关闭", 
                  command=self.window.destroy).pack(side=tk.RIGHT, padx=5)
        
        # 详情框架
        detail_frame = ttk.LabelFrame(main_frame, text="文件详情", padding="10")
        detail_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.detail_text = tk.Text(detail_frame, height=6, state='disabled')
        detail_scrollbar = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scrollbar.set)
        
        self.detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 如果有搜索结果，默认选择第一个
        if self.search_results:
            self.result_listbox.selection_set(0)
            self.on_select(None)
    
    def on_select(self, event):
        """当选择列表项时显示详情"""
        selection = self.result_listbox.curselection()
        if selection:
            index = selection[0]
            self.selected_item = self.search_results[index]
            
            # 显示文件详情
            self.detail_text.config(state='normal')
            self.detail_text.delete(1.0, tk.END)
            
            info = f"文件名: {self.selected_item['file']}\n"
            info += f"相对路径: {self.selected_item['relpath']}\n"
            info += f"绝对路径: {self.selected_item['path']}\n"
            info += f"文件大小: {os.path.getsize(self.selected_item['path'])} 字节"
            
            self.detail_text.insert(tk.END, info)
            self.detail_text.config(state='disabled')
            
            if self.log_callback:
                self.log_callback(f"选中文件: {self.selected_item['relpath']}")
    
    def export_all_json(self):
        """导出所有匹配项到文件"""
        if not self.search_results:
            messagebox.showinfo("提示", "没有匹配项可以导出")
            return
            
        export_file = filedialog.asksaveasfilename(
            title="导出搜索结果",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        
        if export_file:
            try:
                # 根据文件扩展名决定导出格式
                if export_file.endswith('.json'):
                    with open(export_file, 'w', encoding='utf-8') as f:
                        json.dump(self.search_results, f, ensure_ascii=False, indent=2)
                else:
                    with open(export_file, 'w', encoding='utf-8') as f:
                        for item in self.search_results:
                            f.write(f"{item['relpath']}\n{item['path']}\n\n")
                
                messagebox.showinfo("成功", f"已导出 {len(self.search_results)} 个匹配项到:\n{export_file}")
                if self.log_callback:
                    self.log_callback(f"导出 {len(self.search_results)} 个匹配项到: {export_file}")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {str(e)}")
                if self.log_callback:
                    self.log_callback(f"导出失败: {str(e)}")
    def export_all_file(self):
        """导出所有匹配项文件到指定目录，保持相对路径结构"""
        if not self.search_results:
            messagebox.showinfo("提示", "没有匹配项可以导出")
            return
            
        # 选择导出目录
        export_dir = filedialog.askdirectory(title="选择导出目录")
        
        if export_dir:
            try:
                exported_count = 0
                for item in self.search_results:
                    # 获取相对路径和源文件路径
                    rel_path = item['relpath']
                    source_path = item['path']
                    
                    # 构建目标文件路径
                    target_path = os.path.join(export_dir, rel_path)
                    
                    # 创建目标文件的目录结构
                    target_dir = os.path.dirname(target_path)
                    if not os.path.exists(target_dir):
                        os.makedirs(target_dir)
                    
                    # 复制文件
                    if os.path.exists(source_path):
                        import shutil
                        shutil.copy2(source_path, target_path)
                        exported_count += 1
                
                messagebox.showinfo("成功", f"已导出 {exported_count} 个文件到:\n{export_dir}")
                if self.log_callback:
                    self.log_callback(f"导出 {exported_count} 个文件到: {export_dir}")
                    
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {str(e)}")
                if self.log_callback:
                    self.log_callback(f"导出失败: {str(e)}")
    def open_selected(self):
        """打开选中的文件"""
        if not self.selected_item:
            messagebox.showwarning("警告", "请先选择一个文件")
            return
            
        try:
            os.startfile(self.selected_item['path'])
            if self.log_callback:
                self.log_callback(f"打开文件: {self.selected_item['path']}")
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件: {str(e)}")
            if self.log_callback:
                self.log_callback(f"打开文件失败: {str(e)}")
    
    def open_location(self):
        """打开选中文件所在的文件夹"""
        if not self.selected_item:
            messagebox.showwarning("警告", "请先选择一个文件")
            return
            
        try:
            cache=self.selected_item["path"].replace("/", "\\")
            command=f'explorer /select,\"{cache}\"'
            os.system(command)
            if self.log_callback:
                self.log_callback(f"打开文件位置: {os.path.dirname(self.selected_item['path'])}")
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件位置: {str(e)}")
            if self.log_callback:
                self.log_callback(f"打开文件位置失败: {str(e)}")

def show_search_results(parent, search_results, log_callback=None):
    """
    显示搜索结果的便捷函数
    
    参数:
    parent: 父窗口
    search_results: 搜索结果列表 (ok_list)
    log_callback: 日志回调函数 (可选)
    """
    if not search_results:
        messagebox.showinfo("搜索结果", "没有找到匹配项")
        return
    
    SearchResultUI(parent, search_results, log_callback)