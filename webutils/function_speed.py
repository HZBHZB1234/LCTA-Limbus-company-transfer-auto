"""游戏加速模块 - 基于 OpenSpeedy 的 DLL 注入加速

封装 OpenSpeedy SpeedController，提供针对 LimbusCompany.exe 的
进程检测、DLL 注入/弹出、速度控制功能。
"""

import ctypes
import logging
from typing import Optional, Any

from openspeedy import SpeedController, ProcessInfo
from openspeedy import (
    OpenSpeedyError,
    PlatformNotSupportedError,
    DLLNotFoundError,
    ProcessAccessDeniedError,
    ProcessNotFoundError,
    ProcessArchitectureMismatch,
    InjectionError,
    EjectionError,
    SpeedRangeError,
    SpeedControlError,
)

from globalManagers.LogManager import LogManager
_log_manager = LogManager()

logger = logging.getLogger(__name__)

TARGET_PROCESS = "LimbusCompany.exe"

# 快速 PID 存活检查（避免每 2 秒全量枚举进程）
_kernel32 = ctypes.windll.kernel32
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _pid_alive(pid: int) -> bool:
    """用 OpenProcess 快速检查 PID 是否仍然存在。"""
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        _kernel32.CloseHandle(handle)
        return True
    return False


class SpeedManager:
    """封装 OpenSpeedy SpeedController 的单例管理器。

    始终针对 LimbusCompany.exe 操作，不管理多进程。
    Controller 实例懒初始化，首次注入/变速时创建。
    """

    _instance: Optional[Any] = None  # SpeedController | None
    _injected_pid: Optional[int] = None
    _cached_process: Optional[dict] = None  # 缓存 _find_game() 结果

    # ---- 进程检测 ----

    @staticmethod
    def _find_game() -> Optional[dict]:
        """查找 LimbusCompany.exe 进程（带 PID 缓存）。

        优先用 OpenProcess 验证上次缓存的 PID 是否存活，
        避免每 2 秒全量枚举进程列表。

        Returns:
            dict | None: {'pid': int, 'name': str, 'arch': str}
        """
        # 优先验证缓存
        cached = SpeedManager._cached_process
        if cached is not None and _pid_alive(cached["pid"]):
            return cached

        # 缓存失效，全量枚举
        SpeedManager._cached_process = None
        with SpeedController() as sc:
            processes = sc.list_processes(fast=False)
        for p in processes:
            if p.name == TARGET_PROCESS:
                info = {"pid": p.pid, "name": p.name, "arch": p.arch}
                SpeedManager._cached_process = info
                return info
        return None

    @staticmethod
    def get_game_status() -> dict:
        """获取 LimbusCompany.exe 的完整状态。

        Returns:
            dict: {
                "running": bool,
                "pid": int | None,
                "arch": str | None,
                "injected": bool,
                "enabled": bool,
                "speed": float | None,
                "error": str | None,
            }
        """
        result = {
            "running": False,
            "pid": None,
            "arch": None,
            "injected": False,
            "enabled": False,
            "speed": None,
            "error": None,
        }

        try:
            game = SpeedManager._find_game()
        except Exception as e:
            _log_manager.log_error(e)
            result["error"] = f"进程检测失败: {e}"
            return result

        if game is None:
            return result

        result["running"] = True
        result["pid"] = game["pid"]
        result["arch"] = game["arch"]

        # 检查注入和速度状态 —— 必须使用单例 _instance，
        # 否则临时 SpeedController 的 _injected_pids 为空，
        # is_injected() 永远返回 False。
        pid = game["pid"]
        sc = SpeedManager._instance
        if sc is not None:
            result["injected"] = SpeedManager._injected_pid == pid
            try:
                result["enabled"] = sc.is_enabled(pid)
            except Exception as e:
                _log_manager.log_error(e)
                result["enabled"] = False
            try:
                result["speed"] = sc.get_speed()
            except Exception as e:
                _log_manager.log_error(e)
                result["speed"] = 1.0
        else:
            # 尚未注入，用临时控制器读取全局速度（共享内存可跨实例）
            try:
                with SpeedController() as sc:
                    result["speed"] = sc.get_speed()
            except Exception as e:
                _log_manager.log_error(e)
                result["speed"] = None

        return result

    # ---- 注入 / 弹出 ----

    @staticmethod
    def _get_or_create_controller() -> Any:
        """获取或创建 SpeedController 实例。"""
        if SpeedManager._instance is None:
            SpeedManager._instance = SpeedController()
        return SpeedManager._instance

    @staticmethod
    def inject() -> bool:
        """自动查找 LimbusCompany.exe 并注入 DLL。

        若已注入则直接返回 True。

        Returns:
            bool: 是否注入成功。

        Raises:
            ProcessNotFoundError: 游戏进程未找到。
            ProcessAccessDeniedError: 权限不足。
            ProcessArchitectureMismatch: 架构不匹配。
            InjectionError: 注入失败（杀软拦截等）。
        """
        game = SpeedManager._find_game()
        if game is None:
            raise ProcessNotFoundError("游戏未运行，请先启动 LimbusCompany.exe")

        pid = game["pid"]

        if SpeedManager._injected_pid == pid and SpeedManager._instance is not None:
            return True

        sc = SpeedManager._get_or_create_controller()
        sc.inject(pid)
        SpeedManager._injected_pid = pid
        logger.info(f"已注入进程 {TARGET_PROCESS} (PID: {pid})")
        return True

    @staticmethod
    def is_injected() -> bool:
        """检查 LimbusCompany.exe 是否已注入。

        SpeedController 不暴露公共 is_injected 方法，因此以 Python 侧
        记录的注入状态为准（SpeedManager 持有单例 _instance）。

        Returns:
            bool: 是否已注入。
        """
        return SpeedManager._instance is not None and SpeedManager._injected_pid is not None

    @staticmethod
    def eject() -> bool:
        """弹出 DLL 并释放 SpeedController。

        Returns:
            bool: 是否成功弹出。
        """
        if SpeedManager._instance is None or SpeedManager._injected_pid is None:
            return True  # 已经弹出，算成功

        try:
            SpeedManager._instance.eject(SpeedManager._injected_pid)
            logger.info(f"已从 PID {SpeedManager._injected_pid} 弹出 DLL")
        except Exception as e:
            _log_manager.log_error(e)
            logger.warning(f"弹出 DLL 时出错（可能已自动弹出）: {e}")
        finally:
            SpeedManager._instance = None
            SpeedManager._injected_pid = None
            SpeedManager._cached_process = None
        return True

    @staticmethod
    def set_speed(factor: float) -> bool:
        """设置全局速度倍率。若未注入则先注入。

        Args:
            factor: 速度倍率，范围 0.001 – 1000.0。

        Returns:
            bool: 是否设置成功。

        Raises:
            SpeedRangeError: 倍率超出范围。
        """
        if not SpeedManager.is_injected():
            SpeedManager.inject()

        sc = SpeedManager._instance
        sc.set_speed(factor)
        logger.info(f"速度已设置为 {factor}x")
        return True

    @staticmethod
    def get_speed() -> Optional[float]:
        """获取当前全局速度倍率。"""
        if SpeedManager._instance is None:
            return None
        try:
            return SpeedManager._instance.get_speed()
        except Exception as e:
            _log_manager.log_error(e)
            return None

    @staticmethod
    def enable() -> bool:
        """启用当前进程的加速效果。"""
        if SpeedManager._injected_pid is None:
            return False
        try:
            SpeedManager._instance.enable(SpeedManager._injected_pid)
            logger.info(f"已启用 PID {SpeedManager._injected_pid} 的加速")
            return True
        except Exception as e:
            _log_manager.log_error(e)
            logger.warning(f"启用加速失败: {e}")
            return False

    @staticmethod
    def disable() -> bool:
        """禁用当前进程的加速效果。"""
        if SpeedManager._injected_pid is None:
            return False
        try:
            SpeedManager._instance.disable(SpeedManager._injected_pid)
            logger.info(f"已禁用 PID {SpeedManager._injected_pid} 的加速")
            return True
        except Exception as e:
            _log_manager.log_error(e)
            logger.warning(f"禁用加速失败: {e}")
            return False

    @staticmethod
    def close():
        """弹出所有注入并清理资源。"""
        try:
            if SpeedManager._instance is not None:
                SpeedManager._instance.close()
                SpeedManager._instance = None
                SpeedManager._injected_pid = None
                SpeedManager._cached_process = None
                logger.info("SpeedManager 资源已清理")
        except Exception as e:
            _log_manager.log_error(e)
            logger.warning(f"清理资源时出错: {e}")
            SpeedManager._instance = None
            SpeedManager._injected_pid = None
            SpeedManager._cached_process = None
