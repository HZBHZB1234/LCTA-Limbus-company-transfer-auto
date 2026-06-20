"""
globalManagers/ConfigManager.py
Singleton config manager with dotted-path access, validation, auto-save, and thread safety.
"""
import json
import os
import threading
from typing import Any, Dict, List, Optional, Tuple, Union


class ConfigManager:
    """单例配置管理器，支持点号路径访问、自动保存、验证和修复"""

    _instance: Optional["ConfigManager"] = None
    _initialized: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        config_path: str = "config.json",
        default_path: Optional[str] = None,
        schema_path: Optional[str] = None,
    ):
        if ConfigManager._initialized:
            return
        ConfigManager._initialized = True

        self._lock = threading.RLock()
        self._config_path = config_path
        self._default_path = default_path or os.path.join(
            os.getenv("path_", ""), "config_default.json"
        )
        self._schema_path = schema_path or os.path.join(
            os.getenv("path_", ""), "config_check.json"
        )
        self._data: Dict[str, Any] = {}
        self._load()

    # ---------- 内部方法 ----------
    def _load(self):
        """加载配置文件，失败则加载默认配置"""
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._load_default()

    def _load_default(self) -> Dict[str, Any]:
        """加载默认配置"""
        try:
            with open(self._default_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _load_schema(self) -> Dict[str, Any]:
        """加载类型定义"""
        try:
            with open(self._schema_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _navigate(self, key_path: str, create_missing: bool = False):
        """按点号路径遍历嵌套字典，返回 (parent_dict, final_key)"""
        keys = key_path.split(".")
        current = self._data
        for key in keys[:-1]:
            if key not in current:
                if create_missing:
                    current[key] = {}
                else:
                    raise KeyError(key_path)
            current = current[key]
            if not isinstance(current, dict):
                raise TypeError(
                    f"Intermediate key '{key}' is not a dict in path '{key_path}'"
                )
        return current, keys[-1]

    @staticmethod
    def _validate_value(value: Any, expected_type: Union[str, List[Any]]) -> bool:
        """验证单个值的类型"""
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

    @staticmethod
    def _type_default(expected_type) -> Any:
        """根据类型字符串返回默认值"""
        if expected_type == "null":
            return None
        if expected_type == "str":
            return ""
        if expected_type == "int":
            return 0
        if expected_type == "bool":
            return False
        if expected_type == "dict":
            return {}
        if isinstance(expected_type, list):
            return expected_type[0] if expected_type else None
        return None

    # ---------- 公共 API ----------
    def get(self, key_path: str, default: Any = None) -> Any:
        """按点号路径获取配置值，如 'ui_default.translator.is_text'"""
        with self._lock:
            try:
                parent, final_key = self._navigate(key_path)
                return parent[final_key]
            except (KeyError, TypeError):
                return default

    def set(self, key_path: str, value: Any, auto_save: bool = True):
        """按点号路径设置配置值，默认自动保存"""
        with self._lock:
            parent, final_key = self._navigate(key_path, create_missing=True)
            parent[final_key] = value
            if auto_save:
                self.save()

    def set_batch(self, updates: Dict[str, Any], auto_save: bool = True) -> int:
        """批量更新配置，返回成功数量"""
        count = 0
        with self._lock:
            for key_path, value in updates.items():
                try:
                    parent, final_key = self._navigate(key_path, create_missing=True)
                    parent[final_key] = value
                    count += 1
                except (KeyError, TypeError):
                    continue
            if auto_save and count > 0:
                self.save()
        return count

    def save(self):
        """将当前配置写入文件"""
        with self._lock:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=4)

    def validate(self) -> Tuple[bool, List[str]]:
        """验证配置，返回 (是否通过, 错误列表)"""
        errors: List[str] = []
        schema = self._load_schema()

        def _recursive(current_config, current_schema, path=""):
            if not isinstance(current_schema, dict):
                return
            for key, expected_type in current_schema.items():
                current_path = f"{path}.{key}" if path else key
                if key not in current_config:
                    errors.append(f"Missing key: {current_path}")
                    continue
                value = current_config[key]
                if isinstance(expected_type, dict) and isinstance(value, dict):
                    _recursive(value, expected_type, current_path)
                else:
                    if not self._validate_value(value, expected_type):
                        errors.append(
                            f"Type mismatch for '{current_path}': "
                            f"expected {expected_type}, got {type(value).__name__}"
                        )

        with self._lock:
            _recursive(self._data, schema)
        return len(errors) == 0, errors

    def fix(self) -> List[str]:
        """修复配置中缺失/类型错误的键，返回修复信息列表"""
        messages: List[str] = []
        default_cfg = self._load_default()
        schema = self._load_schema()

        def _recursive(current, current_default, current_check, path=""):
            if not isinstance(current_check, dict):
                return
            for key, expected_type in current_check.items():
                current_path = f"{path}.{key}" if path else key
                if key not in current:
                    value = current_default.get(key, self._type_default(expected_type))
                    current[key] = value
                    messages.append(f"Added missing key '{current_path}'")
                    continue
                value = current[key]
                if isinstance(expected_type, dict):
                    if value is None:
                        current[key] = {}
                    if isinstance(current[key], dict):
                        _recursive(
                            current[key],
                            current_default.get(key, {}),
                            expected_type,
                            current_path,
                        )
                elif not self._validate_value(value, expected_type):
                    current[key] = current_default.get(
                        key, self._type_default(expected_type)
                    )
                    messages.append(f"Fixed '{current_path}' to default")

        with self._lock:
            _recursive(self._data, default_cfg, schema)
            self.save()
        return messages

    def use_default(self):
        """使用默认配置覆盖当前配置并保存"""
        with self._lock:
            self._data = self._load_default()
            self.save()

    def reset(self):
        """删除配置文件并重置单例（下次访问重新初始化）"""
        if os.path.exists(self._config_path):
            os.remove(self._config_path)
        self.__class__._initialized = False
        self.__class__._instance = None

    @property
    def raw(self) -> Dict[str, Any]:
        """访问原始配置字典（用于需要遍历或批量操作的场景）"""
        return self._data
