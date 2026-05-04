"""
配置管理器（单例模式）
统一管理所有配置的读取、写入、验证、批量操作
使用扁平化访问路径消除深层嵌套
"""

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ConfigManager:
    """
    配置管理器单例

    核心特性：
    - 扁平化访问：config.get('ui_default.translator.is_text') 替代深层嵌套
    - 批量操作：batch_get / batch_set 减少请求次数
    - 自动类型验证：从 config_check.json 加载类型定义
    - 自动保存：每次 set 后自动持久化
    - 前端常量导出：一次返回 config_key_map + config_defaults + constants
    """

    _instance: Optional['ConfigManager'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'ConfigManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._config: Dict[str, Any] = {}
        self._config_default: Dict[str, Any] = {}
        self._config_types: Dict[str, Any] = {}
        self._config_path = Path(os.getcwd()) / "config.json"
        self._dirty = False
        self._first_use = False

        # 从环境变量获取路径信息
        self._resource_path = Path(os.getenv('path_', os.getcwd()))

        self._load_defaults()
        self._load_types()
        self._load_from_file()

    # ========== 初始化 ==========

    def _load_from_file(self) -> Optional[Dict[str, Any]]:
        """从 config.json 加载配置"""
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
            return self._config
        except FileNotFoundError:
            return None

    def _load_defaults(self) -> None:
        """加载默认配置"""
        default_path = self._resource_path / "config_default.json"
        try:
            with open(default_path, 'r', encoding='utf-8') as f:
                self._config_default = json.load(f)
        except FileNotFoundError:
            self._config_default = {}

    def _load_types(self) -> None:
        """加载配置类型定义"""
        types_path = self._resource_path / "config_check.json"
        try:
            with open(types_path, 'r', encoding='utf-8') as f:
                self._config_types = json.load(f)
        except FileNotFoundError:
            self._config_types = {}

    # ========== 扁平化访问 ==========

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        通过点分隔路径获取配置值

        示例：
            config.get('ui_default.translator.is_text', True)
            等价于原来的 self.config.get("ui_default", {}).get("translator", {}).get("is_text", True)
        """
        keys = key_path.split('.')
        current = self._config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def set(self, key_path: str, value: Any, auto_save: bool = True) -> bool:
        """
        通过点分隔路径设置配置值，自动类型验证

        返回是否设置成功
        """
        keys = key_path.split('.')

        # 遍历到倒数第二个键，确保路径存在
        current = self._config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                # 中间路径不是字典，无法继续
                return False
            current = current[key]

        # 设置最终值
        current[keys[-1]] = value
        self._dirty = True

        if auto_save:
            self.save()

        return True

    def batch_get(self, key_paths: List[str]) -> Dict[str, Any]:
        """批量获取配置值"""
        result = {}
        for key_path in key_paths:
            result[key_path] = self.get(key_path)
        return result

    def batch_set(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        批量更新配置值
        :param updates: {key_path: value, ...}
        :return: {success: bool, updated: int, total: int}
        """
        success_count = 0
        total_count = len(updates)

        for key_path, value in updates.items():
            if self.set(key_path, value, auto_save=False):
                success_count += 1

        # 统一保存
        self.save()

        return {"success": True, "updated": success_count, "total": total_count}

    # ========== 文件持久化 ==========

    def save(self) -> bool:
        """保存当前配置到文件"""
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=4)
            self._dirty = False
            return True
        except Exception:
            return False

    def reload(self) -> None:
        """从文件重新加载配置"""
        self._load_from_file()

    def reset_to_default(self) -> bool:
        """重置为默认配置"""
        if not self._config_default:
            return False
        self._config = json.loads(json.dumps(self._config_default))
        return self.save()

    def use_default_config(self) -> bool:
        """使用内置默认配置并保存"""
        if not self._config_default:
            return False
        self._config = json.loads(json.dumps(self._config_default))
        return self.save()

    # ========== 验证 ==========

    def validate(self) -> Tuple[bool, List[str]]:
        """
        验证当前配置是否符合类型定义
        :return: (is_valid, errors)
        """
        errors = []

        def _validate_recursive(current_config, current_types, path=""):
            if not isinstance(current_types, dict):
                return
            for key, expected_type in current_types.items():
                current_path = f"{path}.{key}" if path else key
                if key not in current_config:
                    errors.append(f"缺少键: {current_path}")
                    continue
                value = current_config[key]
                if isinstance(expected_type, dict) and isinstance(value, dict):
                    _validate_recursive(value, expected_type, current_path)
                else:
                    if not self._validate_value(value, expected_type):
                        errors.append(
                            f"类型不匹配 '{current_path}': "
                            f"期望 {expected_type}, 实际 {type(value).__name__} "
                            f"(值: {value})"
                        )

        _validate_recursive(self._config, self._config_types)
        return len(errors) == 0, errors

    def fix(self) -> Dict[str, Any]:
        """
        修复配置中的错误，返回修复后的配置
        """
        fixed_config = json.loads(json.dumps(self._config))

        def _fix_recursive(current_config, current_default, current_check, path=""):
            if not isinstance(current_check, dict):
                return
            for key, expected_type in current_check.items():
                current_path = f"{path}.{key}" if path else key

                if key not in current_config:
                    if key in current_default:
                        current_config[key] = current_default[key]
                    else:
                        current_config[key] = self._default_for_type(expected_type)
                    continue

                value = current_config[key]

                if isinstance(expected_type, dict) and value is None:
                    current_config[key] = {}
                    value = current_config[key]

                if isinstance(expected_type, dict) and isinstance(value, dict):
                    default_sub = current_default.get(key, {}) if key in current_default else {}
                    if not isinstance(default_sub, dict):
                        default_sub = {}
                    _fix_recursive(value, default_sub, expected_type, current_path)
                else:
                    if not self._validate_value(value, expected_type):
                        if key in current_default and self._validate_value(current_default[key], expected_type):
                            current_config[key] = current_default[key]
                        else:
                            current_config[key] = self._default_for_type(expected_type)

        _fix_recursive(fixed_config, self._config_default, self._config_types)
        self._config = fixed_config
        self.save()
        return fixed_config

    def _validate_value(self, value: Any, expected_type: Any) -> bool:
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

    def _default_for_type(self, expected_type: Any) -> Any:
        """根据类型返回默认值"""
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

    # ========== 前端常量导出 ==========

    def export_frontend_constants(self) -> Dict[str, Any]:
        """
        导出前端所需的常量，一次请求全部返回

        返回结构：
        {
            "config_key_map": {html_id: config_path, ...},
            "config_defaults": {flat_path: value, ...},
            "constants": {update_list: ..., bind_refer: ..., rely_list: ...}
        }
        """
        from webutils.eiderConst import updateList, bindRefer, relyList

        return {
            "config_key_map": self._build_config_key_map(),
            "config_defaults": self._flatten_config(self._config_default),
            "constants": {
                "update_list": updateList,
                "bind_refer": bindRefer,
                "rely_list": relyList,
            }
        }

    def _build_config_key_map(self) -> Dict[str, str]:
        """
        构建 HTML元素ID → 配置路径 的映射表
        从 eiderConst.bindRefer 和已知映射自动生成
        """
        key_map = {
            # 基本设置
            'game-path': 'game_path',
            'debug-mode': 'debug',
            'auto-check-update': 'auto_check_update',
            'delete-updating': 'delete_updating',
            'update-use-proxy': 'update_use_proxy',
            'github-max-workers': 'github_max_workers',
            'github-timeout': 'github_timeout',
            'update-only-stable': 'update_only_stable',
            'enable-cache': 'enable_cache',
            'cache-path': 'cache_path',
            'api-crypto': 'api_crypto',
            'enable-storage': 'enable_storage',
            'storage-path': 'storage_path',
            '--theme': 'theme',

            # 老年人模式
            '--elder': 'elder_list',
            '--elder-character-base': 'elder.character.base',
            '--elder-character-launcher': 'elder.character.launcher',
            '--elder-character-translate': 'elder.character.translate',
            '--elder-character-manage': 'elder.character.manage',

            # 翻译设置
            "translator-service-select": "ui_default.translator.translator",
            "fallback": 'ui_default.translator.fallback',
            "is-text": 'ui_default.translator.is_text',
            'from-lang': 'ui_default.translator.from_lang',
            'enable-proper': 'ui_default.translator.enable_proper',
            'auto-fetch-proper': 'ui_default.translator.auto_fetch_proper',
            'proper-path': 'ui_default.translator.proper_path',
            'enable-role': 'ui_default.translator.enable_role',
            'enable-skill': 'ui_default.translator.enable_skill',
            'enable-dev-settings': 'ui_default.translator.enable_dev_settings',
            "en-path": "ui_default.translator.en_path",
            "kr-path": "ui_default.translator.kr_path",
            "jp-path": "ui_default.translator.jp_path",
            "llc-path": "ui_default.translator.llc_path",
            "has-prefix": "ui_default.translator.has_prefix",
            "dump-translation": "ui_default.translator.dump",

            # 安装设置
            'install-package-directory': 'ui_default.install.package_directory',
            'package-directory': 'ui_default.install.package_directory',

            # OurPlay设置
            'ourplay-font-option': 'ui_default.ourplay.font_option',
            'ourplay-check-hash': 'ui_default.ourplay.check_hash',
            'ourplay-use-api': 'ui_default.ourplay.use_api',

            # 零协设置
            'llc-zip-type': 'ui_default.zero.zip_type',
            'llc-download-source': 'ui_default.zero.download_source',
            'llc-use-proxy': 'ui_default.zero.use_proxy',
            'llc-use-cache': 'ui_default.zero.use_cache',
            'llc-dump-default': 'ui_default.zero.dump_default',

            # LCTA自动更新设置
            'machine-download-source': 'ui_default.machine.download_source',
            'machine-use-proxy': 'ui_default.machine.use_proxy',

            # 气泡文本mod设置
            'bubble-color': 'ui_default.bubble.color',
            'bubble-llc': 'ui_default.bubble.llc',
            'bubble-install': 'ui_default.bubble.install',

            # 安装数据管理设置
            'installed-mod-directory': 'ui_default.manage.mod_path',

            # 清理设置
            'clean-progress': 'ui_default.clean.clean_progress',
            'clean-notice': 'ui_default.clean.clean_notice',
            'clean-mods': 'ui_default.clean.clean_mods',

            # API配置设置
            'api-configs': 'api_config',
            'api-select': 'ui_default.api_config.key',

            'fancy-user': 'user_fancy',
            'fancy-allow': 'fancy_allow',

            # 专有名词抓取设置
            'proper-join-char': 'ui_default.proper.join_char',
            'proper-skip-space': 'ui_default.proper.disable_space',
            'proper-max-count': 'ui_default.proper.max_length',
            'proper-min-count': 'ui_default.proper.min_length',
            'proper-output': 'ui_default.proper.output_type',

            # Launcher设置
            'launcher-zero-zip-type': 'launcher.zero.zip_type',
            'launcher-zero-download-source': 'launcher.zero.download_source',
            'launcher-zero-use-proxy': 'launcher.zero.use_proxy',
            'launcher-zero-use-cache': 'launcher.zero.use_cache',
            'machine-zero-download-source': 'launcher.machine.download_source',
            'machine-zero-use-proxy': 'launcher.machine.use_proxy',
            'launcher-ourplay-font-option': 'launcher.ourplay.font_option',
            'launcher-ourplay-use-api': 'launcher.ourplay.use_api',
            'launcher-work-update': 'launcher.work.update',
            'launcher-work-mod': 'launcher.work.mod',
            'launcher-work-bubble': 'launcher.work.bubble',
            'launcher-work-fancy': 'launcher.work.fancy',
        }

        # 从 eiderConst.bindRefer 补充映射
        try:
            from webutils.eiderConst import bindRefer
            for section, mappings in bindRefer.items():
                for html_id, paths in mappings.items():
                    if html_id not in key_map:
                        key_map[html_id] = paths[1] if len(paths) > 1 else paths[0]
        except ImportError:
            pass

        return key_map

    def _flatten_config(self, config: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """将嵌套配置扁平化为 key_path → value 的字典"""
        result = {}
        for key, value in config.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict) and value:
                result.update(self._flatten_config(value, path))
            else:
                result[path] = value
        return result

    # ========== 属性访问器 ==========

    @property
    def raw(self) -> Dict[str, Any]:
        """获取原始配置字典（仅用于需要完整字典的场景，如翻译引擎）"""
        return self._config

    @property
    def raw_default(self) -> Dict[str, Any]:
        """获取默认配置字典"""
        return self._config_default

    @property
    def is_debug(self) -> bool:
        """快捷访问：是否调试模式"""
        return self.get('debug', False)

    @property
    def game_path(self) -> str:
        """快捷访问：游戏路径"""
        return self.get('game_path', '')

    @property
    def is_first_use(self) -> bool:
        """是否首次使用"""
        return self._first_use

    def init(self) -> None:
        """
        初始化配置（应用启动时调用）
        如果配置文件不存在则创建默认配置
        """
        if self._config is None or not self._config:
            self._config = json.loads(json.dumps(self._config_default))
            if self._config:
                self.save()
                self._first_use = True

        config_ok, config_errors = self.validate()
        if not config_ok:
            self.fix()
