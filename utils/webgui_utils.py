import webview
import os
import threading
import time
from pathlib import Path


def browse_file(window, title="选择文件"):
    """打开文件浏览器"""
    file_path = window.create_file_dialog(
        webview.OPEN_DIALOG,
        allow_multiple=False,
        save_filename=title
    )
    
    if file_path and len(file_path) > 0:
        return file_path[0]
    return None


def browse_folder(window, title="选择文件夹"):
    """打开文件夹浏览器"""
    folder_path = window.create_file_dialog(
        webview.FOLDER_DIALOG
    )
    
    if folder_path and len(folder_path) > 0:
        return folder_path[0]
    return None


def show_message(window, message, title="提示"):
    """显示消息对话框"""
    # 在WebGUI中，我们通常将消息显示在界面中而不是弹出对话框
    # 这里可以实现将消息发送到前端的日志区域
    pass


def execute_with_progress(func, progress_callback=None, *args, **kwargs):
    """执行带进度的函数"""
    def worker():
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            if progress_callback:
                progress_callback(0, f"错误: {str(e)}")
            raise e
    
    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()
    return thread


def update_progress(window, percent, text):
    """更新进度"""
    escaped_text = text.replace("'", "\\'")
    js_code = f"updateProgress({percent}, '{escaped_text}');"
    try:
        window.evaluate_js(js_code)
    except:
        pass


def add_log_message(window, message):
    """添加日志消息"""
    # 添加时间戳
    timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
    full_message = f"{timestamp} {message}"
    
    # 通过JavaScript将日志消息发送到前端
    escaped_message = message.replace("'", "\\'")
    js_code = f"addLogMessage('{escaped_message}');"
    try:
        window.evaluate_js(js_code)
    except:
        # 如果窗口不可用则打印到控制台
        print(f"[LOG] {message}")


def search_files(directory, extensions, keyword, case_sensitive=False):
    """
    在指定目录中搜索包含关键词的文件
    :param directory: 搜索目录
    :param extensions: 文件扩展名列表，如 ['.txt', '.json']
    :param keyword: 搜索关键词
    :param case_sensitive: 是否区分大小写
    :return: 搜索结果列表
    """
    results = []
    count = 0
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if any(file.lower().endswith(ext.lower()) for ext in extensions):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            search_line = line if case_sensitive else line.lower()
                            search_keyword = keyword if case_sensitive else keyword.lower()
                            
                            if search_keyword in search_line:
                                results.append({
                                    "file": os.path.relpath(file_path, directory),
                                    "line": line_num,
                                    "content": line.strip()
                                })
                                count += 1
                                
                                # 限制结果数量以避免过多结果
                                if count >= 100:  # 最多返回100个结果
                                    break
                        if count >= 100:
                            break
                except Exception:
                    # 跳过无法读取的文件
                    continue
    
    return results


def adjust_image(image_path, brightness=0, contrast=0, output_path=None):
    """
    调整图片亮度和对比度
    :param image_path: 原图片路径
    :param brightness: 亮度调整值 (-100 to 100)
    :param contrast: 对比度调整值 (-100 to 100)
    :param output_path: 输出路径，如果为None则自动生成
    :return: 调整后的图片路径
    """
    try:
        from PIL import Image, ImageEnhance
    except ImportError:
        raise ImportError("需要安装PIL库: pip install Pillow")
    
    # 打开图片
    img = Image.open(image_path)
    
    # 调整亮度 (brightness_value: 0.0-2.0, 1.0为原始亮度)
    brightness_factor = 1.0 + brightness / 100.0
    if brightness_factor > 0:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(brightness_factor)
    
    # 调整对比度 (contrast_value: 0.0-2.0, 1.0为原始对比度)
    contrast_factor = 1.0 + contrast / 100.0
    if contrast_factor > 0:
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(contrast_factor)
    
    # 生成输出文件名
    if output_path is None:
        dir_path = os.path.dirname(image_path)
        file_name, file_ext = os.path.splitext(os.path.basename(image_path))
        output_path = os.path.join(dir_path, f"{file_name}_adjusted{file_ext}")
    
    # 保存调整后的图片
    img.save(output_path)
    
    return output_path
