"""配置管理器 —— 单例，property 驱动的前后端双向同步。

通过点路径 get/set 读写配置，任何 set 操作自动触发去抖保存（100ms）。
监听器系统允许插件订阅配置变更。schema 导出支持前端一次性全量同步。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Optional
from contextlib import suppress

from .logManager import logManager
from .pathManager import pathManager


class ConfigManager:
    """单例配置管理器。

    核心能力：
    - 点路径读写：get('ui_default.game_path'), set('game_path', 'C:\\\\...')
    - 去抖保存：100ms 内的多次 set 合并为一次磁盘写入
    - 监听器系统：插件可订阅配置变更回调
    - Schema 导出：将 config_check.json 的结构导出为前端可用格式
    """

    def __init__(self):
        self._config: dict = {}
        self._default: dict = {}
        self._check: dict = {}
        self._save_timer: Optional[threading.Timer] = None
        self._save_lock = threading.Lock()
        self._listeners: list[Callable[[str, Any], None]] = []
        self._window = None  # JS bridge 引用，用于推送变更到前端

    # ─── Property ───

    @property
    def config(self) -> dict:
        return self._config

    @config.setter
    def config(self, value: dict):
        self._config = value
        self._schedule_save()
        self._notify_listeners('*', value)

    # ─── 点路径读写 ───

    def get(self, key_path: str, default: Any = None) -> Any:
        """点路径读取配置值。

        >>> configManager.get('ui_default.game_path')
        'C:\\\\Program Files\\\\...'
        """
        node = self._config
        for key in key_path.split('.'):
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return default
        return node

    def set(self, key_path: str, value: Any, create_missing: bool = True) -> bool:
        """点路径写入配置值。返回 True 表示值确实变更。

        >>> configManager.set('game_path', 'C:\\\\new_path')
        True
        """
        keys = key_path.split('.')
        node = self._config

        for key in keys[:-1]:
            if key not in node:
                if create_missing:
                    node[key] = {}
                else:
                    return False
            node = node[key]
            if not isinstance(node, dict):
                return False

        old_value = node.get(keys[-1])
        if old_value == value:
            return False

        node[keys[-1]] = value
        self._schedule_save()
        self._notify_listeners(key_path, value)
        return True

    def set_batch(self, updates: dict[str, Any]) -> int:
        """批量更新配置，只在所有变更完成后触发一次保存。

        返回实际变更的键数量。
        """
        changed = 0
        for key_path, value in updates.items():
            if self.set(key_path, value, create_missing=True):
                changed += 1
        return changed

    # ─── 去抖保存 ───

    def _schedule_save(self):
        """100ms 去抖：多次变更合并为一次磁盘写入。"""
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(0.1, self._do_save)
            self._save_timer.daemon = True
            self._save_timer.start()

    def _do_save(self):
        """执行磁盘写入。"""
        config_path = pathManager.work_path / 'config.json'
        try:
            config_path.write_text(
                json.dumps(self._config, ensure_ascii=False, indent=4),
                encoding='utf-8'
            )
        except Exception as e:
            logManager.error(f"保存配置文件失败: {e}")

    def save_config(self):
        """立即保存配置（跳过去抖，供 atexit 使用）。"""
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
        self._do_save()

    # ─── 监听器系统 ───

    def add_listener(self, callback: Callable[[str, Any], None]):
        """添加配置变更监听器。callback(key_path, new_value)。"""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str, Any], None]):
        """移除配置变更监听器。"""
        with suppress(ValueError):
            self._listeners.remove(callback)

    def _notify_listeners(self, key_path: str, value: Any):
        """通知所有监听器配置已变更。单个监听器异常不影响其他监听器。"""
        for cb in self._listeners:
            try:
                cb(key_path, value)
            except Exception:
                pass

    def set_window(self, window):
        """设置 JS bridge 引用，用于后续推送配置变更到前端。"""
        self._window = window

    # ─── Schema 导出（供前端 config_get_full_sync） ───

    def export_schema(self) -> dict[str, dict]:
        """导出配置 schema，格式适配前端 configManager。

        返回 {key_path: {type, default}, ...}
        """
        if not self._check:
            return {}
        result = {}
        for key_path, schema_type in self._flat_schema(self._check):
            result[key_path] = {
                'type': self._type_name(schema_type),
                'default': self._default_get(key_path),
            }
        return result

    def _flat_schema(self, check: dict, prefix: str = '') -> list[tuple[str, Any]]:
        """递归扁平化 config_check 结构。"""
        result = []
        for key, value in check.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.extend(self._flat_schema(value, full_key))
            else:
                result.append((full_key, value))
        return result

    @staticmethod
    def _type_name(schema_type: Any) -> str:
        """将 config_check 中的类型值转为字符串名。"""
        if isinstance(schema_type, list):
            return 'enum'
        return str(schema_type)

    def _default_get(self, key_path: str) -> Any:
        """从默认配置中按点路径获取值。"""
        node = self._default
        for key in key_path.split('.'):
            if isinstance(node, dict):
                node = node.get(key)
            else:
                return None
        return node

    # ─── 配置加载 ───

    def load_config(self):
        """从磁盘加载用户配置。"""
        config_path = pathManager.work_path / 'config.json'
        with suppress(FileNotFoundError, json.JSONDecodeError):
            self._config = json.loads(config_path.read_text(encoding='utf-8'))

    def load_config_default(self):
        """从代码目录加载默认配置。"""
        default_path = pathManager.code_path / 'config_default.json'
        try:
            self._default = json.loads(default_path.read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logManager.error(f"加载默认配置失败: {e}")
            self._default = {}

    def load_config_types(self):
        """从代码目录加载配置类型定义。"""
        check_path = pathManager.code_path / 'config_check.json'
        try:
            self._check = json.loads(check_path.read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logManager.error(f"加载配置类型定义失败: {e}")
            self._check = {}

    def loadConfig(self):
        """一次性加载全部配置（兼容旧接口）。"""
        self.load_config()
        self.load_config_default()
        self.load_config_types()

    # ─── 配置验证（保留原有逻辑） ───

    @staticmethod
    def validate_config_value(value: Any, expected_type: Any) -> bool:
        """验证单个配置值的类型。"""
        if expected_type == "null":
            return value is None
        elif expected_type == "str":
            return isinstance(value, str)
        elif expected_type == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        elif expected_type == "bool":
            return isinstance(value, bool)
        elif expected_type == "dict":
            return isinstance(value, dict)
        elif isinstance(expected_type, list):
            return value in expected_type
        return False

    def validate_config(self, config: dict = None, config_types: dict = None) -> tuple[bool, list[str]]:
        """验证配置对象是否符合类型定义。"""
        if config is None:
            config = self._config
        if config_types is None:
            config_types = self._check

        errors = []

        def _validate_recursive(current_config: dict, current_types: dict, path: str = ""):
            if not isinstance(current_types, dict):
                return
            for key, expected_type in current_types.items():
                current_path = f"{path}.{key}" if path else key
                if key not in current_config:
                    errors.append(f"Missing key: {current_path}")
                    continue
                value = current_config[key]
                if isinstance(expected_type, dict) and isinstance(value, dict):
                    _validate_recursive(value, expected_type, current_path)
                else:
                    if not self.validate_config_value(value, expected_type):
                        errors.append(
                            f"Type mismatch for key '{current_path}': "
                            f"expected {expected_type}, got {type(value).__name__} "
                            f"(value: {value})"
                        )

        _validate_recursive(config, config_types)
        return len(errors) == 0, errors

    def check_config_type(self, key_path: str, value: Any) -> tuple[bool, Any, str]:
        """检查特定配置项的类型。返回 (is_valid, expected_type, actual_type)。"""
        keys = key_path.split('.')
        current = self._check
        try:
            for key in keys:
                current = current[key]
            expected_type = current
            is_valid = self.validate_config_value(value, expected_type)
            return is_valid, expected_type, type(value).__name__
        except KeyError:
            return False, "unknown", type(value).__name__

    def fix_config(self, config: dict = None, config_default: dict = None,
                   config_check: dict = None) -> dict:
        """修复配置文件中的错误，返回修复后的配置副本。"""
        if config is None:
            config = self._config
        if config_default is None:
            config_default = self._default
        if config_check is None:
            config_check = self._check

        if config_default is None or config_check is None:
            logManager.warn("无法加载默认配置或配置类型定义，跳过配置修复")
            return config

        def _fix_recursive(current_config, current_default, current_check, path=""):
            if not isinstance(current_check, dict):
                return
            for key, expected_type in current_check.items():
                current_path = f"{path}.{key}" if path else key
                if key not in current_config:
                    if key in current_default:
                        current_config[key] = current_default[key]
                        logManager.info(f"修复配置: 添加缺失的键 '{current_path}' = {current_default[key]}")
                    else:
                        current_config[key] = self._default_for_type(expected_type)
                        logManager.info(f"修复配置: 添加缺失的键 '{current_path}' 并设置默认值")
                    continue

                value = current_config[key]

                if isinstance(expected_type, dict) and value is None:
                    current_config[key] = {}
                    value = current_config[key]
                    logManager.info(f"修复配置: 将None值的键 '{current_path}' 修正为空字典")

                if isinstance(expected_type, dict) and isinstance(value, dict):
                    if key not in current_default or not isinstance(current_default.get(key), dict):
                        current_default[key] = {}
                    _fix_recursive(value, current_default[key], expected_type, current_path)
                else:
                    if not self.validate_config_value(value, expected_type):
                        if key in current_default and self.validate_config_value(current_default[key], expected_type):
                            current_config[key] = current_default[key]
                            logManager.info(f"修复配置: 修正键 '{current_path}' 的值为默认值")
                        else:
                            current_config[key] = self._default_for_type(expected_type)
                            logManager.info(f"修复配置: 重置键 '{current_path}' 为类型相关的默认值")

        fixed_config = json.loads(json.dumps(config))
        _fix_recursive(fixed_config, config_default, config_check)
        return fixed_config

    @staticmethod
    def _default_for_type(expected_type: Any) -> Any:
        """根据类型定义返回合理的默认值。"""
        if expected_type == "null":
            return None
        elif expected_type == "str":
            return ""
        elif expected_type == "int":
            return 0
        elif expected_type == "bool":
            return False
        elif expected_type == "dict":
            return {}
        elif isinstance(expected_type, list):
            return expected_type[0] if expected_type else None
        return None


configManager = ConfigManager()
