"""
globalManagers 统一入口
提供全局单例管理器的便捷访问

使用方式：
    from globalManagers import get_config, get_path, get_log

    config = get_config()
    game_path = config.get('game_path')

    path_mgr = get_path()
    lang_dir = path_mgr.game_lang_dir

    log_mgr = get_log()
    log_mgr.log("消息")
"""

from .config_manager import ConfigManager
from .path_manager import PathManager
from .log_manager import LogManager

# 懒加载全局实例
_config_instance = None
_path_instance = None
_log_instance = None


def get_config() -> ConfigManager:
    """获取 ConfigManager 单例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance


def get_path() -> PathManager:
    """获取 PathManager 单例"""
    global _path_instance
    if _path_instance is None:
        _path_instance = PathManager()
    return _path_instance


def get_log() -> LogManager:
    """获取 LogManager 单例"""
    global _log_instance
    if _log_instance is None:
        _log_instance = LogManager()
    return _log_instance


def reset_all() -> None:
    """重置所有单例（主要用于测试）"""
    global _config_instance, _path_instance, _log_instance
    _config_instance = None
    _path_instance = None
    _log_instance = None
    ConfigManager._instance = None
    PathManager._instance = None
    LogManager._instance = None


__all__ = [
    'get_config', 'get_path', 'get_log', 'reset_all',
    'ConfigManager', 'PathManager', 'LogManager',
]
