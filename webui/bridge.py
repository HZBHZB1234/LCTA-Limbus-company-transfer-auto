"""
API 桥接基类
提供全局单例访问、文件浏览器、日志桥接、模态窗口管理等公共功能
所有通过 pywebview 暴露给前端的 API 方法的基类
"""

import os
import time
import logging
import webview
from pathlib import Path
from typing import Optional, List, Dict, Any

from globalManagers import get_config, get_path, get_log


class APIBridge:
    """
    API桥接基类

    提供：
    - config / path / log_mgr 属性（globalManagers 单例）
    - browse_file / browse_folder（文件对话框）
    - log / log_error / log_ui（日志桥接）
    - 模态窗口管理
    - UI 桥接方法
    """

    def __init__(self):
        self._window: Optional['webview.Window'] = None
        self.modal_list: List[Dict[str, str]] = []
        self.http_port: int = 0
        self.current_files: List[str] = []

    # ========== 单例访问属性 ==========

    @property
    def config(self):
        """ConfigManager 单例"""
        return get_config()

    @property
    def path(self):
        """PathManager 单例"""
        return get_path()

    @property
    def log_mgr(self):
        """LogManager 单例"""
        return get_log()

    # ========== 窗口管理 ==========

    def set_window(self, window: 'webview.Window'):
        """设置 pywebview 窗口实例"""
        self._window = window

    @property
    def window(self) -> 'webview.Window':
        """获取 pywebview 窗口实例"""
        return self._window

    # ========== 文件浏览器 ==========

    def browse_file(self, input_id: str) -> Optional[str]:
        """打开文件浏览器，选择文件并回填到前端 input"""
        file_path = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            save_filename='选择文件'
        )
        if file_path and len(file_path) > 0:
            selected_path = file_path[0]
            js_code = (
                f"document.getElementById('{input_id}').value = "
                f"'{selected_path.replace(os.sep, '/')}';"
            )
            self._window.evaluate_js(js_code)
            self.log_ui(f"已选择文件: {selected_path}")
            return selected_path
        return None

    def browse_folder(self, input_id: str) -> Optional[str]:
        """打开文件夹浏览器，选择文件夹并回填到前端 input"""
        folder_path = self._window.create_file_dialog(
            webview.FileDialog.FOLDER
        )
        if folder_path and len(folder_path) > 0:
            selected_path = folder_path[0]
            js_code = (
                f"document.getElementById('{input_id}').value = "
                f"'{selected_path.replace(os.sep, '/')}';"
            )
            self._window.evaluate_js(js_code)
            self.log_ui(f"已选择文件夹: {selected_path}")
            return selected_path
        return None

    # ========== 日志快捷方法 ==========

    def log(self, message: str):
        """记录普通日志"""
        self.log_mgr.log(message)

    def log_error(self, e: Exception):
        """记录错误日志"""
        self.log_mgr.log_error(e)

    def log_ui(self, message: str, level: int = logging.INFO):
        """UI日志（通过JS发送到前端日志面板）"""
        timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
        full_message = f"{timestamp} {message}"

        escaped = message.replace("'", "\\'").replace("\n", "\\n")
        js_code = f"addLogMessage('{escaped}');"
        try:
            self._window.evaluate_js(js_code)
        except Exception:
            print(f"[UI] {full_message}")
        finally:
            self.log(full_message)

    # ========== 进度更新 ==========

    def update_progress(self, percent: int, text: str):
        """更新前端进度条"""
        escaped_text = text.replace("'", "\\'")
        js_code = f"updateProgress({percent}, '{escaped_text}');"
        try:
            self._window.evaluate_js(js_code)
        except Exception:
            pass

    # ========== 模态窗口管理 ==========

    def add_modal_id(self, modal_id: str) -> bool:
        """注册模态窗口"""
        self.log(f"添加模态窗口: {modal_id}")
        self.modal_list.append({
            "modal_id": modal_id,
            "running": "running"
        })
        return True

    def del_modal_list(self, modal_id: str):
        """移除模态窗口"""
        self.log(f"删除模态窗口: {modal_id}")
        for idx, item in enumerate(self.modal_list):
            if item["modal_id"] == modal_id:
                del self.modal_list[idx]
                break

    def _check_modal_running(self, modal_id: str) -> str:
        """内部：检查模态窗口运行状态"""
        for item in self.modal_list:
            if item["modal_id"] == modal_id:
                return item["running"]
        return "running"

    def _wait_continue(self, modal_id: str):
        """内部：等待模态窗口从暂停恢复"""
        while True:
            if self._check_modal_running(modal_id) == "pause":
                time.sleep(1)
            else:
                break

    def check_modal_running(self, modal_id: str, log: bool = True):
        """检查模态窗口运行状态，处理暂停和取消"""
        if log:
            self.log(f"检查模态窗口: {modal_id}")
        status = self._check_modal_running(modal_id)
        if status == "pause":
            self._wait_continue(modal_id)
        elif status == "cancel":
            from webui.decorators import CancelRunning
            raise CancelRunning("用户取消操作")

    def set_modal_running(self, modal_id: str, types: str = "cancel"):
        """设置模态窗口运行状态"""
        self.log(f"设置模态窗口 {modal_id} 状态为 {types}")
        for item in self.modal_list:
            if item["modal_id"] == modal_id:
                item["running"] = str(types)
                break

    # ========== UI 桥接方法 ==========

    def set_modal_status(self, status: str, modal_id: str):
        """向模态窗口发送状态变更"""
        escaped_status = status.replace("'", "\\'").replace("\n", "\\n")
        if modal_id == 'false':
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === '{modal_id}');
        if (modal) {{
            modal.setStatus('{escaped_status}');
        }}
        """
        try:
            self._window.evaluate_js(js_code)
        except Exception:
            pass

    def add_modal_log(self, message: str, modal_id: str):
        """向模态窗口添加日志"""
        escaped = message.replace("'", "\\'").replace("\n", "\\n")
        if modal_id == "false":
            self.log_ui(escaped)
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === '{modal_id}');
        if (modal) {{
            modal.addLog('{escaped}');
        }}
        """
        try:
            self._window.evaluate_js(js_code)
        except Exception:
            pass

    def update_modal_progress(self, percent: int, text: str, modal_id: str, log: bool = True):
        """更新模态窗口进度"""
        escaped_text = text.replace("'", "\\'").replace("\n", "\\n")
        if modal_id == "false":
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === '{modal_id}');
        if (modal) {{
            modal.updateProgress({percent}, '{escaped_text}');
        }}
        """
        try:
            self._window.evaluate_js(js_code)
        except Exception:
            pass

    # ========== 生命周期 ==========

    def on_close(self):
        """窗口关闭时的回调"""
        pass
