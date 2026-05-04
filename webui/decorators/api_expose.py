"""
@api_expose 装饰器
自动为 pywebview js_api 方法提供：
- 统一的异常处理 (try/except)
- 方法调用日志
- 标准化返回值 {"success": bool, "message": str, "data": Any}
- CancelRunning 异常处理
"""

import functools
import time
import traceback
from typing import Callable, Any


class CancelRunning(Exception):
    """用户取消操作的异常"""
    pass


def api_expose(func: Callable) -> Callable:
    """
    API暴露装饰器

    自动包装方法，提供统一的异常处理和日志记录。
    与 @modal_handler 可组合使用：@api_expose 应在最外层。

    使用示例：
        @api_expose
        def get_config_batch(self, key_paths):
            ...

        @api_expose
        @modal_handler
        def start_translation(self, translator_config, modal_id="false"):
            ...
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        func_name = func.__name__
        start_time = time.time()

        try:
            # debug模式下记录调用
            log = getattr(self, 'log', None)
            config = getattr(self, 'config', None)
            if log and config and config.is_debug:
                # 截断参数日志以免过长
                short_args = str(args)[:200] if args else ''
                log(f"[API] 调用 {func_name}({short_args}...)")

            # 执行原方法
            result = func(self, *args, **kwargs)

            # 如果返回值已经是标准格式，直接返回
            if isinstance(result, dict) and 'success' in result:
                return result

            # 封装为标准格式
            elapsed = time.time() - start_time
            if log and config and config.is_debug:
                log(f"[API] {func_name} 完成，耗时 {elapsed:.2f}s")

            return {"success": True, "data": result}

        except CancelRunning:
            if hasattr(self, 'log'):
                self.log(f"[API] {func_name} 被用户取消")
            return {"success": False, "message": "已取消", "cancelled": True}

        except Exception as e:
            elapsed = time.time() - start_time
            exc_info = traceback.format_exc()

            log_error = getattr(self, 'log_error', None)
            if log_error:
                log_error(f"[API] {func_name} 异常 (耗时 {elapsed:.2f}s): {e}")
                # 只记录截断的堆栈，避免日志爆炸
                log_error(exc_info[:1000])

            return {
                "success": False,
                "message": str(e),
                "error_type": type(e).__name__
            }

    # 保留原函数名，确保 pywebview 能正确识别
    wrapper.__name__ = func.__name__
    wrapper.__qualname__ = func.__qualname__
    return wrapper
