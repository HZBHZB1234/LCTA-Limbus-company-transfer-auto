# -*- coding: utf-8 -*-
"""LCTA_API 游戏加速：注入/弹出 DLL、速度倍率。"""
from webutils import SpeedManager
from webutils.function_speed import (
    ProcessNotFoundError,
    ProcessAccessDeniedError,
    ProcessArchitectureMismatch,
    InjectionError,
    SpeedRangeError,
)

class SpeedMixin:

    def speed_get_status(self):
        """获取游戏进程和加速状态"""
        try:
            status = SpeedManager.get_game_status()
            return {"success": True, "data": status}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def speed_inject(self):
        """注入 DLL 到 LimbusCompany.exe"""
        try:
            SpeedManager.inject()
            self.log_ui("DLL 注入成功")
            return {"success": True, "message": "注入成功"}
        except ProcessNotFoundError:
            self.log("DLL 注入失败: 游戏未运行")
            return {"success": False, "message": "游戏未运行，请先启动 LimbusCompany.exe"}
        except ProcessAccessDeniedError:
            self.log("DLL 注入失败: 权限不足")
            return {"success": False, "message": "权限不足，请以管理员权限运行 LCTA"}
        except ProcessArchitectureMismatch:
            self.log("DLL 注入失败: 架构不匹配")
            return {"success": False, "message": "架构不匹配，请使用对应版本的 Python"}
        except InjectionError as e:
            self.log_error(e)
            return {"success": False, "message": f"注入失败，请检查杀毒软件是否拦截: {e}"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"注入失败: {e}"}

    def speed_eject(self):
        """弹出 DLL"""
        try:
            SpeedManager.eject()
            self.log_ui("DLL 已弹出")
            return {"success": True, "message": "弹出成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"弹出失败: {e}"}

    def speed_set(self, factor):
        """设置速度倍率"""
        try:
            factor = float(factor)
            SpeedManager.set_speed(factor)
            self.log_ui(f"速度已设置为 {factor}x")
            return {"success": True, "message": f"速度已设置为 {factor}x", "speed": factor}
        except SpeedRangeError:
            self.log(f"设置速度失败: 倍率 {factor} 超出范围")
            return {"success": False, "message": "速度倍率必须在 0.001 – 1000 之间"}
        except ProcessNotFoundError:
            self.log("设置速度失败: 游戏未运行")
            return {"success": False, "message": "游戏未运行，请先启动 LimbusCompany.exe"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"设置速度失败: {e}"}

    def speed_enable(self):
        """启用加速"""
        try:
            if SpeedManager.enable():
                return {"success": True, "message": "加速已启用"}
            return {"success": False, "message": "请先注入 DLL"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def speed_disable(self):
        """禁用加速"""
        try:
            if SpeedManager.disable():
                return {"success": True, "message": "加速已禁用"}
            return {"success": False, "message": "请先注入 DLL"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}
