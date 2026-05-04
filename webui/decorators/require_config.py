"""
@require_config 装饰器
前置条件检查：确保必需的配置项已设置
如果前置条件不满足，自动返回错误信息而不执行方法

使用方式：
    @api_expose
    @require_config(game_path="请先设置游戏路径")
    def install_translation(self, package_name, modal_id="false"):
        ...
"""

import functools
from typing import Callable, Dict


def require_config(**required_keys: str) -> Callable:
    """
    要求指定配置项存在的装饰器工厂

    Args:
        **required_keys: {配置路径: 缺失时的错误消息}
        例如: require_config(game_path="请先设置游戏路径")

    Returns:
        装饰器
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            from globalManagers import get_config
            config = get_config()

            for key_path, error_msg in required_keys.items():
                value = config.get(key_path)
                if not value:
                    return {
                        "success": False,
                        "message": error_msg,
                        "missing_config": key_path
                    }

            return func(self, *args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__qualname__ = func.__qualname__
        return wrapper

    return decorator
