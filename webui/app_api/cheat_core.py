# -*- coding: utf-8 -*-
"""LCTA_API CheatCore 密钥门 + 插件宿主：状态查询 / 解锁 / 锁定 / 插件列表 / 通用分发。"""


class CheatCoreMixin:

    def cheat_core_status(self):
        """查询解锁状态（含持久化密钥自动解锁尝试）。"""
        try:
            from webutils import cheat_core
            result = cheat_core.ensure_unlocked()
            return {
                "success": True,
                "data": {
                    "unlocked": bool(result.get("success")),
                    "reason": result.get("reason", "unknown"),
                    "source": result.get("source"),
                },
            }
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cheat_core_unlock(self, key):
        """用解密密钥解锁作弊工具箱。"""
        try:
            from webutils import cheat_core
            result = cheat_core.unlock(str(key or ""))
            if result.get("success"):
                self.log_ui("作弊工具箱已解锁")
                return {"success": True, "message": "解锁成功"}
            reason = result.get("reason", "invalid_key")
            text = {
                "invalid_key": "密钥错误，请重试",
                "blob_missing": "当前安装缺少工具箱数据（cheat_core.bin）",
                "load_error": "工具箱加载失败",
            }.get(reason, "解锁失败")
            return {"success": False, "reason": reason, "message": text}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"解锁失败: {e}"}

    def cheat_core_lock(self):
        """锁定并清除密钥。"""
        try:
            from webutils import cheat_core
            result = cheat_core.lock()
            self.log_ui("作弊工具箱已锁定（密钥已清除）")
            return {"success": True, "message": "已锁定"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"锁定失败: {e}"}

    def cheat_core_get_section_html(self, name="cheat"):
        """读取解密后的工具箱页完整 HTML（未解锁抛错）。"""
        from webutils import cheat_core
        return cheat_core.section_html(str(name))

    def cheat_core_get_script_js(self, name="cheat"):
        """读取解密后的工具箱页完整 JS（未解锁抛错）。"""
        from webutils import cheat_core
        return cheat_core.script_js(str(name))

    def cheat_plugins_list(self):
        """返回已注册插件摘要（解锁后含配置字段与 Launcher 元数据）。"""
        try:
            from webutils import CheatPluginHost
            return {"success": True, "data": CheatPluginHost.list()}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cheat_plugin_invoke(self, action, args=None):
        """按插件白名单通用分发：action 为注册表 api 中的方法名。"""
        try:
            from webutils import CheatPluginHost
            return {"success": True, "data": CheatPluginHost.invoke(str(action or ""), args)}
        except RuntimeError as e:
            return {"success": False, "reason": "locked", "message": str(e)}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"操作失败: {e}"}
