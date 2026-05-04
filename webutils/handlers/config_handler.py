"""
配置操作 Handler
处理配置的读取、更新、批量操作、保存、重置
"""

import json
from . import BaseHandler


class ConfigHandler(BaseHandler):
    """配置操作处理器"""

    def get_value(self, key_path: str, default_value=None):
        """获取单个配置值"""
        return self.config.get(key_path, default_value)

    def update_value(self, key_path: str, value, create_missing: bool = True):
        """更新单个配置值"""
        try:
            keys = key_path.split('.')
            current = self.config.raw

            for key in keys[:-1]:
                if key not in current:
                    if create_missing:
                        current[key] = {}
                    else:
                        return False
                current = current[key]
                if not isinstance(current, dict):
                    return False

            current[keys[-1]] = value
            self.config.save()
            return True
        except Exception as e:
            self.log.log_error(e)
            return False

    def get_batch(self, key_paths: list) -> dict:
        """批量获取配置值"""
        result = {}
        for key_path in key_paths:
            result[key_path] = self.config.get(key_path)
        return {"success": True, "config_values": result}

    def update_batch(self, config_updates: dict) -> dict:
        """批量更新配置值"""
        success_count = 0
        total_count = len(config_updates)
        for key_path, value in config_updates.items():
            if self.update_value(key_path, value):
                success_count += 1
        return {"success": True, "updated": success_count, "total": total_count}

    def save_to_file(self) -> bool:
        """保存配置到文件"""
        return self.config.save()

    def use_default(self) -> dict:
        """使用默认配置"""
        ok = self.config.use_default_config()
        if not ok:
            return {"success": False, "message": "无法加载默认配置"}
        return {"success": True, "message": "已重置为默认配置"}

    def reset(self) -> dict:
        """重置配置（删除后重新生成）"""
        import os
        config_path = self.path.config_path
        if config_path.exists():
            config_path.unlink()
        ok = self.config.use_default_config()
        if not ok:
            return {"success": False, "message": "无法加载默认配置"}
        return {"success": True, "message": "配置已重置"}

    def save_settings(self, game_path: str, debug_mode: bool, auto_update: bool) -> dict:
        """保存基本设置"""
        self.config.set('game_path', game_path, auto_save=False)
        self.config.set('debug', debug_mode, auto_save=False)
        self.config.set('auto_check_update', auto_update, auto_save=False)
        self.config.save()
        return {"success": True, "message": "设置保存成功"}

    def export_constants(self) -> dict:
        """导出前端常量"""
        result = self.config.export_frontend_constants()
        return {"success": True, "data": result}
