import tkinter as tk
from tkinter import filedialog, messagebox

def choose_path():
    """选择文件对话框"""
    return filedialog.askopenfilename()

def show_warning(title, message):
    """显示警告对话框"""
    return messagebox.showwarning(title, message)

def show_error(title, message):
    """显示错误对话框"""
    return messagebox.showerror(title, message)

def show_info(title, message):
    """显示信息对话框"""
    return messagebox.showinfo(title, message)

def ask_yes_no(title, message):
    """显示是/否对话框"""
    return messagebox.askyesno(title, message)