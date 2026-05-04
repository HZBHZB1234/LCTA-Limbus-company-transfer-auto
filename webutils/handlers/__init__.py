"""
业务 Handler 模块
每个 Handler 处理一个特定业务领域
通过 BaseHandler 访问 globalManagers 单例
"""

from globalManagers import get_config, get_path, get_log


class BaseHandler:
    """Handler 基类，提供对 globalManagers 单例的便捷访问"""

    @property
    def config(self):
        return get_config()

    @property
    def path(self):
        return get_path()

    @property
    def log(self):
        return get_log()


__all__ = [
    'BaseHandler',
]
