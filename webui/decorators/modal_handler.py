"""
@modal_handler 装饰器
自动管理模态窗口生命周期：
- 执行前发送开始日志
- 执行后发送完成日志
- 异常时自动发送错误日志并更新进度为0
- 处理取消逻辑

必须与 @api_expose 组合使用，@modal_handler 在内层：
    @api_expose
    @modal_handler
    def some_method(self, modal_id="false"):
        ...
"""

import functools
from typing import Callable
from .api_expose import CancelRunning


def modal_handler(func: Callable) -> Callable:
    """
    模态窗口处理器装饰器

    自动处理：
    1. 向模态窗口发送开始/完成日志
    2. 异常时清理模态窗口状态
    3. CancelRunning 异常传播
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # 从参数中提取 modal_id
        modal_id = kwargs.get('modal_id', 'false')

        func_name = func.__name__
        add_modal_log = getattr(self, 'add_modal_log', None)
        log_mgr = getattr(self, 'log_mgr', None)

        try:
            if add_modal_log:
                add_modal_log(f"开始执行...", modal_id)

            result = func(self, *args, **kwargs)

            if add_modal_log:
                add_modal_log(f"操作完成", modal_id)

            return result

        except CancelRunning:
            if log_mgr:
                log_mgr.log(f"[Modal] {func_name} 被取消")
            del_modal = getattr(self, 'del_modal_list', None)
            if del_modal:
                del_modal(modal_id)
            raise

        except Exception as e:
            if add_modal_log:
                add_modal_log(f"出现错误: {e}", modal_id)
            if log_mgr:
                log_mgr.update_modal_progress(0, "操作失败", modal_id)
                log_mgr.log_modal_status("操作失败", modal_id)
            raise

    wrapper.__name__ = func.__name__
    wrapper.__qualname__ = func.__qualname__
    return wrapper
