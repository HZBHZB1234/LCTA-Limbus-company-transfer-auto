# -*- coding: utf-8 -*-
"""LCTA_API 配置读写：单键/批量读写、保存、重置。"""
from globalManagers.ConfigManager import ConfigManager
from webutils.load import load_config_types

_TRUE_STRS = {"true", "1", "on", "yes"}
_FALSE_STRS = {"false", "0", "off", "no"}


def _lookup_schema_type(key_path: str, schema) -> object:
    """按点号路径在 config_check.json 类型表中查找期望类型；未声明返回 None。"""
    current = schema
    for key in key_path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current if isinstance(current, str) else None


def _coerce_config_value(key_path: str, value):
    """按 config_check.json 声明的类型转换前端提交的值（str→int/bool）。

    - 期望 int：可转数字的 str 转 int；转换失败保留原值（不静默破坏，交给 fix() 处理）
    - 期望 bool：仅兜底处理字符串 "true/false/1/0"（checkbox 本已传 bool）
    - 期望 str / 枚举 / 未声明键：原样返回（cheat 插件动态键等不受影响）
    """
    if not isinstance(value, str):
        return value
    try:
        schema = load_config_types()
    except Exception:
        return value
    expected = _lookup_schema_type(key_path, schema)
    if expected == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if expected == "bool":
        lowered = value.strip().lower()
        if lowered in _TRUE_STRS:
            return True
        if lowered in _FALSE_STRS:
            return False
    return value


class ConfigMixin:

    def save_config_to_file(self):
        """将当前配置保存到文件"""
        try:
            ConfigManager().save()
            return True
        except Exception as e:
            self.log_error(e)
            return False

    def update_config_value(self, key_path, value, create_missing=True):
        """
        更新配置中的特定值
        :param key_path: 配置键路径，例如 "ui_default.game_path"
        :param value: 要设置的值
        :param create_missing: 是否创建缺失的键路径
        :return: 更新是否成功
        """
        try:
            ConfigManager().set(key_path, _coerce_config_value(key_path, value))
            return True
        except Exception as e:
            self.log(f"更新配置值时出错: {key_path} = {value}, 错误: {e}")
            self.log_error(e)
            return False

    def update_config_batch(self, config_updates):
        """
        批量更新配置
        :param config_updates: 字典，包含多个配置更新 {key_path: value, ...}
        :return: 批量更新是否成功
        """
        try:
            if not config_updates:
                return {"success": True, "updated": 0, "total": 0}
            coerced = {k: _coerce_config_value(k, v) for k, v in config_updates.items()}
            updated = ConfigManager().set_batch(coerced)
            total_count = len(config_updates)

            self.log(f"批量更新配置: 成功 {updated}/{total_count} 项")
            return {"success": True, "updated": updated, "total": total_count}
        except Exception as e:
            self.log(f"批量更新配置时出错: {e}")
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def get_config_batch(self, key_paths):
        """
        批量获取配置值
        :param key_paths: 配置键路径列表，例如 ["ui_default.game_path", "debug"]
        :return: 字典，包含获取到的配置值
        """
        try:
            result = {}
            for key_path in key_paths:
                value = self.get_config_value(key_path)
                result[key_path] = value
            return {"success": True, "config_values": result}
        except Exception as e:
            self.log(f"批量获取配置值时出错: {e}")
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def get_config_value(self, key_path, default_value=None):
        """
        获取配置中的特定值
        :param key_path: 配置键路径，例如 "ui_default.game_path"
        :param default_value: 默认值
        :return: 配置值或默认值
        """
        try:
            return ConfigManager().get(key_path, default_value)
        except Exception as e:
            self.log(f"获取配置值时出错: {key_path}, 错误: {e}")
            self.log_error(e)
            return default_value

    def save_settings(self, game_path, debug_mode, auto_update):
        """保存设置"""
        try:
            ConfigManager().set("game_path", game_path)
            ConfigManager().set("debug", debug_mode)
            ConfigManager().set("auto_check_update", auto_update)

            self.log(f"设置已保存: 游戏路径={game_path}, 调试模式={debug_mode}")
            return {"success": True, "message": "设置保存成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"保存设置时出错: {str(e)}"}

    def use_default_config(self):
        """使用默认配置"""
        try:
            ConfigManager().use_default()
            self.log("已重置为默认配置")
            return {"success": True, "message": "已重置为默认配置"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"重置配置时出错: {str(e)}"}

    def reset_config(self):
        """重置配置"""
        try:
            ConfigManager().reset()
            # 重新初始化
            ConfigManager()
            self.log("配置已重置")
            return {"success": True, "message": "配置已重置"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"重置配置时出错: {str(e)}"}
