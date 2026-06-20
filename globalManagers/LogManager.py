"""
globalManagers/LogManager.py
Singleton log manager wrapping Python standard logging with modal-callback support for webview.
"""
import logging
import logging.handlers
import os
import sys
from typing import Callable, Optional, Any
from concurrent.futures import ThreadPoolExecutor


class LogManager:
    """单例日志管理器，统一处理文件日志、控制台日志和模态窗口回调"""

    _instance: Optional["LogManager"] = None
    _initialized: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        log_dir: str = "logs",
        log_file: str = "app.log",
        max_bytes: int = 1024 * 500,
        backup_count: int = 5,
        log_level: int = logging.DEBUG,
    ):
        if LogManager._initialized:
            return
        LogManager._initialized = True

        # -- 标准日志配置 --
        self._logger = logging.getLogger("LCTA")
        self._logger.setLevel(log_level)
        self._logger.propagate = False

        os.makedirs(log_dir, exist_ok=True)

        # 文件处理器（按大小轮转）
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        fh.setLevel(log_level)

        # 控制台处理器
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh.setFormatter(fmt)
        ch.setFormatter(fmt)

        self._logger.addHandler(fh)
        self._logger.addHandler(ch)

        # -- 模态回调存储（供 webview JS 桥接使用） --
        self._modal_status_callback: Optional[Callable] = None
        self._modal_log_callback: Optional[Callable] = None
        self._modal_progress_callback: Optional[Callable] = None
        self._check_running: Optional[Callable] = None
        self.debug_mode: bool = False

        # 线程池用于异步 UI 回调，防止阻塞主线程
        self._executor = ThreadPoolExecutor(max_workers=1)

    # ---------- 模态回调设置 ----------
    def set_modal_callbacks(
        self,
        *,
        status_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        check_running: Optional[Callable] = None,
    ):
        """设置模态窗口相关回调函数（仅 webui 模式需要）"""
        if status_callback is not None:
            self._modal_status_callback = status_callback
        if log_callback is not None:
            self._modal_log_callback = log_callback
        if progress_callback is not None:
            self._modal_progress_callback = progress_callback
        if check_running is not None:
            self._check_running = check_running

    def set_debug_mode(self, enabled: bool):
        """设置调试模式开关"""
        self.debug_mode = enabled

    # ---------- 核心日志方法 ----------
    def log(self, message: str, level: int = logging.INFO):
        """记录普通日志"""
        self._logger.log(level, message)

    def debug(self, message: str):
        """记录调试日志"""
        self.log(f"[DEBUG] {message}", logging.DEBUG)

    def log_error(self, error: Any):
        """记录错误日志，自动判断是否为 Exception 以包含 traceback"""
        if isinstance(error, Exception):
            self._logger.exception(str(error))
        else:
            msg = str(error) if error else "Unknown error"
            self._logger.error(msg)

    # ---------- 模态感知日志（无回调时回退到纯文件/控制台日志） ----------
    def log_modal_process(self, message: str, modal_id: Optional[str] = None):
        """向模态窗口添加日志条目"""
        self.log(message)
        if modal_id and self._modal_log_callback:
            try:
                self._executor.submit(self._modal_log_callback, message, modal_id)
            except Exception:
                pass

    def log_modal_process_debug(self, message: str, modal_id: Optional[str] = None):
        """向模态窗口添加调试日志，仅在调试模式启用时生效"""
        if self.debug_mode:
            self.log_modal_process(f"[DEBUG] {message}", modal_id)

    def log_modal_status(self, status: str, modal_id: Optional[str] = None):
        """更新模态窗口状态文本"""
        self.log(f"Status: {status}")
        if modal_id and self._modal_status_callback:
            try:
                self._executor.submit(self._modal_status_callback, status, modal_id)
            except Exception:
                pass

    def update_modal_progress(
        self,
        percent: int,
        text: str = "",
        modal_id: Optional[str] = None,
        log: bool = True,
    ):
        """更新模态窗口进度条"""
        if log:
            self.log(f"Progress {percent}%: {text}")
        if modal_id and self._modal_progress_callback:
            try:
                self._executor.submit(
                    self._modal_progress_callback, percent, text, modal_id, log
                )
            except Exception:
                pass

    def check_running(self, modal_id: Optional[str] = None, log: bool = True):
        """检查任务是否仍在运行（委托给回调，可能抛出 CancelRunning）"""
        if self._check_running:
            self._check_running(modal_id, log=log)
