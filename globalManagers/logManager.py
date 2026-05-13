"""日志管理器 —— 单例，提供统一日志接口与 UI/Modal 通信。

特性：
- 修复 exception() —— 接受 Exception 对象，记录完整 traceback
- LogContext —— 为操作链路附加唯一标识，方便日志追踪
- messageWrapper —— 降级处理：日志失败不影响主流程
- ThreadPoolExecutor 驱动的异步 UI 推送
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from functools import wraps
from contextlib import suppress
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor

from webview import Window


def messageWrapper(func):
    """装饰器：确保日志操作失败不影响主流程。"""

    @wraps(func)
    def resultFunc(self, message, *args, **kwargs):
        try:
            return func(self, message, *args, **kwargs)
        except AttributeError:
            raise
        except Exception:
            # 日志失败不应阻断主流程，输出到 stderr 防止完全静默
            import sys
            print(f"[LogError] {func.__qualname__}: 日志记录失败", file=sys.stderr)

    return resultFunc


class LogContext:
    """为操作链路附加上下文标识，便于在日志中追踪完整调用链。

    用法:
        ctx = LogContext(logManager, "translate_batch")
        ctx.info("开始处理")
        # 输出: [a1b2c3d4] 开始处理
    """

    def __init__(self, manager: 'LogManager', operation_id: str = None):
        self.manager = manager
        self.operation_id = operation_id or uuid.uuid4().hex[:8]

    def debug(self, message: str, *args, **kwargs):
        self.manager.debug(f"[{self.operation_id}] {message}", *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        self.manager.info(f"[{self.operation_id}] {message}", *args, **kwargs)

    def warn(self, message: str, *args, **kwargs):
        self.manager.warn(f"[{self.operation_id}] {message}", *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        self.manager.error(f"[{self.operation_id}] {message}", *args, **kwargs)

    def exception(self, e: Exception, *args, **kwargs):
        self.manager.exception(e, context_id=self.operation_id, *args, **kwargs)


class LogManager:
    """单例日志管理器。"""

    def __init__(self):
        self.logger: Optional[logging.Logger] = None
        self._window: Optional[Window] = None
        self.check_running: Optional[Callable] = None
        self.executor = ThreadPoolExecutor(max_workers=1)

    def setup(self, logger: logging.Logger, window: Optional[Window] = None):
        """配置日志管理器。window 仅在 WebUI 模式下需要传入。"""
        self.logger = logger
        self._window = window

    def create_context(self, operation_id: str = None) -> LogContext:
        """创建带操作 ID 的日志上下文。"""
        return LogContext(self, operation_id)

    # ─── 基本日志方法 ───

    @messageWrapper
    def debug(self, message: str, *args, **kwargs):
        self.logger.debug(message, *args, **kwargs)

    @messageWrapper
    def info(self, message: str, *args, **kwargs):
        if self.logger:
            self.logger.info(message, *args, **kwargs)

    @messageWrapper
    def warn(self, message: str, *args, **kwargs):
        if self.logger:
            self.logger.warning(message, *args, **kwargs)

    @messageWrapper
    def error(self, message: str, *args, **kwargs):
        if self.logger:
            self.logger.error(message, *args, **kwargs)

    @messageWrapper
    def critical(self, message: str, *args, **kwargs):
        if self.logger:
            self.logger.critical(message, *args, **kwargs)

    def exception(self, e: Exception, context_id: str = None, *args, **kwargs):
        """记录异常及其完整 traceback。

        Args:
            e: Exception 对象（不是字符串）
            context_id: 可选的操作上下文 ID
        """
        prefix = f"[{context_id}] " if context_id else ""
        try:
            if self.logger:
                self.logger.exception(f"{prefix}{e}", *args, **kwargs)
            else:
                traceback.print_exc()
        except Exception:
            # 即使 logging 失败也输出到 stderr
            import sys
            traceback.print_exc(file=sys.stderr)

    # ─── 线程安全的异步方法 ───

    @staticmethod
    def threadWrapper(func):
        """装饰器：将方法调用提交到 ThreadPoolExecutor 异步执行。"""

        @wraps(func)
        def resultFunc(self, *args, **kwargs):
            self.executor.submit(func, self, *args, **kwargs)

        return resultFunc

    @threadWrapper
    @messageWrapper
    def logUI(self, message: str, level=logging.INFO):
        self._log_ui(message, level)

    @threadWrapper
    @messageWrapper
    def ModalStatus(self, status: str, modal_id: str = None):
        self._set_modal_status(status, modal_id)

    @threadWrapper
    @messageWrapper
    def ModalLog(self, message: str, modal_id: str = None):
        self._add_modal_log(message, modal_id)

    @threadWrapper
    @messageWrapper
    def modalProgress(self, percent: int, text: str, modal_id: str, log: bool = True):
        self._update_modal_progress(percent, text, modal_id, log)

    # ─── JS Bridge 方法（私有，供异步方法调用） ───

    def _log_ui(self, message: str, level=logging.INFO):
        self.info(message)
        escaped_message = message.replace("'", "\\'").replace("\n", "\\n")
        timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
        js_code = f"addLogMessage('{escaped_message}');"
        try:
            if self._window:
                self._window.run_js(js_code)
        except Exception:
            self.info(f"{timestamp} {message}")

    def _set_modal_status(self, status: str, modal_id: str):
        if not modal_id:
            return
        self.info(f"[{modal_id}] 状态变更: {status}")
        escaped_status = status.replace("'", "\\'").replace("\n", "\\n")
        js_code = (
            f"const modal = modalWindows.find(m => m.id === '{modal_id}');"
            f"if (modal) {{ modal.setStatus('{escaped_status}'); }}"
        )
        with suppress(Exception):
            if self._window:
                self._window.evaluate_js(js_code)

    def _add_modal_log(self, message: str, modal_id: str):
        self.info(f"[{modal_id}] {message}")
        escaped_message = message.replace("'", "\\'").replace("\n", "\\n")
        if not modal_id:
            self.logUI(escaped_message)
            return
        js_code = (
            f"const modal = modalWindows.find(m => m.id === '{modal_id}');"
            f"if (modal) {{ modal.addLog('{escaped_message}'); }}"
        )
        with suppress(Exception):
            if self._window:
                self._window.evaluate_js(js_code)

    def _update_modal_progress(self, percent: int, text: str, modal_id: str, log: bool = True):
        if not modal_id:
            return
        if log:
            self.info(f"[{modal_id}] 进度 {percent}%: {text}")
        escaped_text = text.replace("'", "\\'").replace("\n", "\\n")
        js_code = (
            f"const modal = modalWindows.find(m => m.id === '{modal_id}');"
            f"if (modal) {{ modal.updateProgress({percent}, '{escaped_text}'); }}"
        )
        with suppress(Exception):
            if self._window:
                self._window.evaluate_js(js_code)


logManager = LogManager()
