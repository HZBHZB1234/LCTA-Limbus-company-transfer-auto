# -*- coding: utf-8 -*-
"""LCTA_API 伤害倍率：偏移刷新/注入弹出/应用配置/状态查询。"""
from webutils import DamageHookManager


class DamageHookMixin:

    def damage_hook_get_status(self):
        """获取游戏进程与 hook 状态（含偏移来源/过期标记）。"""
        try:
            return {"success": True, "data": DamageHookManager.get_status()}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def damage_hook_apply(self):
        """解析偏移（带缓存）并写入共享内存。"""
        try:
            result = DamageHookManager.apply()
            if not result["success"]:
                return {"success": False, "message": result.get("message", "应用失败")}
            self.log_ui(
                f"伤害倍率配置已应用 (倍率 {result['multiplier']}, "
                f"{'已启用' if result['enabled'] else '未启用'})"
            )
            return {"success": True, "data": result}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def damage_hook_inject(self):
        """注入 DLL 到 LimbusCompany.exe。"""
        try:
            result = DamageHookManager.apply()
            if not result["success"]:
                return {"success": False, "message": result.get("message", "未获取到偏移")}
            DamageHookManager.inject()
            self.log_ui("伤害倍率 hook 注入成功")
            return {"success": True, "message": "注入成功"}
        except RuntimeError as e:
            self.log(f"伤害倍率注入失败: {e}")
            return {"success": False, "message": str(e)}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"注入失败: {e}"}

    def damage_hook_eject(self):
        """弹出 DLL。"""
        try:
            DamageHookManager.eject()
            self.log_ui("伤害倍率 hook 已弹出")
            return {"success": True, "message": "弹出成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"弹出失败: {e}"}

    def damage_hook_refresh_offsets(self):
        """强制刷新偏移（游戏更新后失效恢复）：拉取 API → 重写共享内存。"""
        try:
            result = DamageHookManager.refresh_offsets()
            if not result["success"]:
                return {"success": False, "message": result.get("message", "刷新失败")}
            stale = "（API 尚未发布当前版本偏移，降级使用旧偏移）" if result.get("stale") else ""
            self.log_ui(f"伤害倍率偏移已刷新：{result.get('message', '')}{stale}")
            return {"success": True, "data": result}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"刷新失败: {e}"}
