import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import shutil
from pathlib import Path
import winreg

class FontViewer:
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("字体查看与导出工具")
        self.window.geometry("800x600")
        
        # 创建主框架
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 搜索框
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(search_frame, text="搜索字体:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.update_font_list)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # 字体列表
        ttk.Label(main_frame, text="已安装字体:").pack(anchor=tk.W, pady=(0, 5))
        
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.font_listbox = tk.Listbox(list_frame, width=40)
        self.font_listbox_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.font_listbox.yview)
        self.font_listbox.configure(yscrollcommand=self.font_listbox_scrollbar.set)
        
        self.font_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.font_listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 预览区域
        ttk.Label(main_frame, text="字体预览:").pack(anchor=tk.W, pady=(0, 5))
        
        preview_frame = ttk.Frame(main_frame, relief=tk.SUNKEN, padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.preview_text = tk.Text(preview_frame, width=40, height=10, wrap=tk.WORD)
        self.preview_text.insert(tk.END, "中文示例文本\nABCDEFGabcdefg\n1234567890")
        self.preview_text.config(state=tk.DISABLED)
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="导出选中字体", command=self.export_font).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="刷新列表", command=self.load_fonts).pack(side=tk.LEFT)
        
        # 绑定事件
        self.font_listbox.bind('<<ListboxSelect>>', self.on_font_select)
        
        # 加载字体
        self.fonts = []
        self.font_files = {}  # 字体名称到文件路径的映射
        self.load_fonts()
        
        # 设置窗口关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        """处理窗口关闭事件"""
        self.window.destroy()

    def load_fonts(self):
        """加载系统已安装的字体"""
        self.font_listbox.delete(0, tk.END)
        self.fonts.clear()
        self.font_files.clear()
        
        # 获取Windows字体目录
        fonts_dir = os.path.join(os.environ['WINDIR'], 'Fonts')
        
        # 从注册表获取已安装字体信息
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as key:
                i = 0
                while True:
                    try:
                        value_name, value_data, _ = winreg.EnumValue(key, i)
                        i += 1
                        
                        # 提取字体名称（移除可能的后缀如 (TrueType)）
                        font_name = value_name
                        for suffix in [" (TrueType)", " (OpenType)", " (Variable)"]:
                            if font_name.endswith(suffix):
                                font_name = font_name[:-len(suffix)]
                                break
                        
                        # 构建完整字体文件路径
                        font_path = os.path.join(fonts_dir, value_data)
                        if not os.path.isfile(font_path):
                            continue
                            
                        self.fonts.append(font_name)
                        self.font_files[font_name] = font_path
                        
                    except OSError:
                        break
        except Exception as e:
            messagebox.showerror("错误", f"无法读取字体注册表信息: {e}")
            return
        
        # 按字母顺序排序字体列表
        self.fonts.sort(key=lambda x: x.lower())
        
        # 更新列表框
        for font in self.fonts:
            self.font_listbox.insert(tk.END, font)
        
        self.update_font_list()

    def update_font_list(self, *args):
        """根据搜索条件更新字体列表"""
        search_term = self.search_var.get().lower()
        
        self.font_listbox.delete(0, tk.END)
        
        for font in self.fonts:
            if search_term in font.lower():
                self.font_listbox.insert(tk.END, font)

    def on_font_select(self, event):
        """当选择字体时更新预览"""
        selection = self.font_listbox.curselection()
        if not selection:
            return
            
        font_name = self.font_listbox.get(selection[0])
        
        # 更新预览文本的字体
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete(1.0, tk.END)
        self.preview_text.insert(tk.END, f"{font_name}\n\n中文示例文本\nABCDEFGabcdefg\n1234567890")
        self.preview_text.tag_add("all", 1.0, tk.END)
        
        try:
            self.preview_text.tag_configure("all", font=(font_name, 12))
        except tk.TclError:
            # 如果设置字体失败，使用默认字体
            pass
            
        self.preview_text.config(state=tk.DISABLED)

    def export_font(self):
        """导出选中的字体文件"""
        selection = self.font_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个字体")
            return
            
        font_name = self.font_listbox.get(selection[0])
        font_path = self.font_files.get(font_name)
        
        if not font_path or not os.path.isfile(font_path):
            messagebox.showerror("错误", f"找不到字体文件: {font_name}")
            return
            
        # 选择保存位置
        default_filename = os.path.basename(font_path)
        save_path = filedialog.asksaveasfilename(
            title="保存字体文件",
            initialfile=default_filename,
            defaultextension=os.path.splitext(font_path)[1],
            filetypes=[("字体文件", "*.ttf *.otf *.ttc"), ("所有文件", "*.*")]
        )
        
        if not save_path:
            return
            
        try:
            shutil.copy2(font_path, save_path)
            messagebox.showinfo("成功", f"字体已导出到: {save_path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出字体时出错: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FontViewer(root)
    root.mainloop()