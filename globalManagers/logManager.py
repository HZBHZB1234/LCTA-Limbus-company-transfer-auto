import logging
import time
import traceback
from functools import wraps
from contextlib import suppress
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor
from webview import Window

def messageWrapper(Func):
    @wraps
    def resultFunc(self, message, *args, **kwargs):
        try:
            Func(message, *args, **kwargs)
        except AttributeError:
            raise
        except Exception:
            print(message)
    return resultFunc


class LogManager:
    def __init__(self):
        self.logger: Optional[logging.Logger] = None
        self._window: Optional[Window] = None
        self.check_running: Optional[Callable] = None
        self.executor = ThreadPoolExecutor(max_workers=1)

    def threadWrapper(self, func):
        @wraps
        def resultFunc(*args, **kwargs):
            self.executor.submit(func, *args, **kwargs)

        return resultFunc

    @messageWrapper
    def debug(self, message: str, *args, **kwargs):
        self.logger.debug(message, *args, **kwargs)

    @messageWrapper
    def info(self, message: str, *args, **kwargs):
        self.logger.info(message, *args, **kwargs)

    @messageWrapper
    def warn(self, message: str, *args, **kwargs):
        self.logger.warn(message, *args, **kwargs)

    @messageWrapper
    def error(self, message: str, *args, **kwargs):
        self.logger.error(message, *args, **kwargs)
    
    @messageWrapper
    def critical(self, message: str, *args, **kwargs):
        self.logger.critical(message, *args, **kwargs)

    def exception(self, e: str, *args, **kwargs):
        if self.logger:
            with suppress(Exception):
                self.logger.exception(e, *args, **kwargs)
        else:
            with suppress(Exception):
                traceback.print_exception(e)

    @threadWrapper
    @messageWrapper
    def logUI(self, message: str, level=logging.INFO):
        self._log_ui(message, level)

    @threadWrapper
    @messageWrapper
    def ModalStatus(self, status, modal_id = None):
        self._set_modal_status(status, modal_id)

    @threadWrapper
    @messageWrapper
    def ModalLog(self, message, modal_id = None):
        self._add_modal_log(message, modal_id)

    def _log_ui(self, message: str, level=logging.INFO):
        self.info(message)
        timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
        full_message = f"{timestamp} {message}"
        escaped_message = message.replace("'", "\\'").replace("\n", "\\n")
        js_code = f"addLogMessage('{escaped_message}');"
        try:
            self._window.run_js(js_code)
        except:
            self.info(full_message)

    def _set_modal_status(self, status, modal_id):
        """设置模态窗口状态"""
        self.info(f"[{modal_id}] 状态变更{status}")
        escaped_status = status.replace("'", "\\'").replace("\n", "\\n")
        if not modal_id:
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === '{modal_id}');
        if (modal) {{
            modal.setStatus('{escaped_status}');
        }}
        """
        self._window.evaluate_js(js_code)

    def _add_modal_log(self, message, modal_id):
        """向模态窗口添加日志"""
        self.info(f"[{modal_id}] {message}")
        escaped_message = message.replace("'", "\\'").replace("\n", "\\n")
        if not modal_id:
            self.logUI(escaped_message)
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === '{modal_id}');
        if (modal) {{
            modal.addLog('{escaped_message}');
        }}
        """
        self._window.evaluate_js(js_code)

    @threadWrapper
    def modalProgress(self, percent, text, modal_id,log=True):
        """更新模态窗口进度"""
        if log:
            self.info(f"[{modal_id}] 进度变更至{percent}% 消息内容[{text}]")
        escaped_text = text.replace("'", "\\'").replace("\n", "\\n")
        if not modal_id:
            return
        js_code = f"""
        const modal = modalWindows.find(m => m.id === '{modal_id}');
        if (modal) {{
            modal.updateProgress({percent}, '{escaped_text}');
        }}
        """
        with suppress(Exception):
            self._window.evaluate_js(js_code)


logManager = LogManager()