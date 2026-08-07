# -*- coding: utf-8 -*-
"""LCTA_API 输入反检测：注入/弹出 DLL、应用配置、状态查询。"""
from webutils import InputBypassManager


class InputBypassMixin:

    def input_bypass_get_status(self):
        """获取游戏进程与 hook 状态。"""
        try:
            return {"success": True, "data": InputBypassManager.get_status()}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def input_bypass_apply(self):
        """读取当前配置写入共享内存（含钳制）。"""
        try:
            result = InputBypassManager.apply()
            self.log_ui(
                f"输入反检测配置已应用 ({result['mode']}模式, "
                f"{'已启用' if result['armed'] else '未启用'})"
            )
            return {"success": result["success"], "data": result}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def input_bypass_inject(self):
        """注入 DLL 到 LimbusCompany.exe。"""
        try:
            InputBypassManager.apply()
            InputBypassManager.inject()
            self.log_ui("输入反检测 hook 注入成功")
            return {"success": True, "message": "注入成功"}
        except RuntimeError as e:
            self.log(f"输入反检测注入失败: {e}")
            return {"success": False, "message": str(e)}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"注入失败: {e}"}

    def input_bypass_eject(self):
        """弹出 DLL。"""
        try:
            InputBypassManager.eject()
            self.log_ui("输入反检测 hook 已弹出")
            return {"success": True, "message": "弹出成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"弹出失败: {e}"}