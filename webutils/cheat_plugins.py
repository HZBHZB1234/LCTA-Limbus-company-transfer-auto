# -*- coding: utf-8 -*-
"""CheatCore 插件宿主（公共仓库）——解密后自动注册、通用分发

私有仓库 LCTA_CheatingCore 的作弊工具箱以「插件」自描述（cheatcore/registry.py），
解锁后由本模块注册（cheat_core 调用 CheatPluginHost.reload）。主仓库不感知具体工具：
    - 前端经 cheat_plugin_invoke(action, args) 按白名单调用管理器方法
    - Launcher 生命周期经 run_launcher_phase('start'/'stop') 通用分发
    - 插件配置键默认值在注册时播种到 ConfigManager（主仓库 config 不含工具键）

未解锁时 _plugins 为空，invoke / 生命周期分发安全短路。
"""

import logging

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager

logger = logging.getLogger(__name__)
_log_manager = LogManager()

_LOCKED_MSG = "作弊工具箱未解锁（请在作弊工具箱页面输入解密密钥）"


class CheatPluginHost:
    _plugins = []      # 插件描述符（注册表快照）
    _package = None    # 已解锁的 cheatcore 包

    # ------------------------------------------------------------------
    # 注册 / 清理
    # ------------------------------------------------------------------

    @classmethod
    def reload(cls) -> None:
        """解锁后重读插件注册表并播种配置默认值（幂等）。"""
        from webutils import cheat_core  # 延迟导入避免包初始化循环依赖
        package = cheat_core.get_package()
        cls._package = package
        cls._plugins = list(package.get_plugins() or [])
        for plugin in cls._plugins:
            cls._seed_config(plugin)
        logger.info("CheatCore 插件已注册: %s", [p.get("id") for p in cls._plugins])

    @classmethod
    def clear(cls) -> None:
        """锁定/卸载时清空注册。"""
        cls._plugins = []
        cls._package = None

    @staticmethod
    def _seed_config(plugin) -> None:
        """把插件声明的配置默认值播种到 ConfigManager（缺失才写入）。"""
        for key, spec in (plugin.get("config") or {}).items():
            try:
                if ConfigManager().get(key, None) is None:
                    ConfigManager().set(key, spec.get("default"), auto_save=False)
            except Exception as e:
                logger.warning("插件配置播种失败 %s: %s", key, e)
        try:
            ConfigManager().save()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 查询 / 分发
    # ------------------------------------------------------------------

    @classmethod
    def list(cls) -> list:
        """返回插件摘要（供前端渲染与 Launcher 动态项）。"""
        return [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "desc": p.get("desc"),
                "webui": p.get("webui"),
                "config": p.get("config"),
                "launcher": p.get("launcher"),
            }
            for p in cls._plugins
        ]

    @classmethod
    def _manager_module(cls, plugin):
        """解析插件声明 entry 到 cheatcore 子模块。"""
        pkg = cls._package or cls._package_import()
        return __import__(f"{pkg.__name__}.{plugin['entry']}", fromlist=[plugin["manager"]])

    @classmethod
    def _manager_class(cls, plugin):
        """解析插件声明 entry.manager 到管理器类。"""
        return getattr(cls._manager_module(plugin), plugin["manager"])

    @classmethod
    def _package_import(cls):
        """延迟导入并返回已解锁的 cheatcore 包（未解锁抛 RuntimeError）。"""
        from webutils import cheat_core
        return cheat_core.get_package()

    @classmethod
    def invoke(cls, action, args=None):
        """按白名单分发到插件管理器方法。未解锁/动作非法抛 RuntimeError。"""
        if not cls._plugins:
            raise RuntimeError(_LOCKED_MSG)
        plugin = cls._plugins[0]
        if action not in plugin.get("api", []):
            raise RuntimeError(f"未知的作弊工具箱操作: {action}")
        manager = cls._manager_class(plugin)
        if not hasattr(manager, action):
            raise RuntimeError(f"作弊工具箱缺少操作实现: {action}")
        return getattr(manager, action)(*(list(args or [])))

    # ------------------------------------------------------------------
    # Launcher 生命周期（由 launcher/game_launch.py 调用）
    # ------------------------------------------------------------------

    @classmethod
    def run_launcher_phase(cls, phase: str) -> None:
        """PHASE_RUNNING('start') / PHASE_EXIT('stop') 通用分发。

        按插件声明检查 enabled_key 与风险同意（consent）后调用 on_start/on_stop；
        未解锁（无插件注册）时安全跳过。
        """
        if not cls._plugins:
            return
        for plugin in cls._plugins:
            launcher = plugin.get("launcher")
            if not launcher:
                continue
            handler = launcher.get("on_start" if phase == "start" else "on_stop")
            if not handler:
                continue
            if phase == "start":
                if not ConfigManager().get(launcher.get("enabled_key"), False):
                    continue
                consent = launcher.get("consent")
                if consent and not ConfigManager().get(f"{consent}.disclaimer_accepted", False):
                    _log_manager.log(f"{plugin.get('name')}: 未同意风险须知，跳过注入")
                    continue
            try:
                getattr(cls._manager_module(plugin), handler)()
            except Exception as e:
                _log_manager.log_error(e)

    @classmethod
    def close_all(cls) -> None:
        """atexit 兜底：逐个调用插件 close（未解锁静默）。"""
        for plugin in cls._plugins:
            try:
                manager = cls._manager_class(plugin)
            except Exception:
                continue
            try:
                if hasattr(manager, "close"):
                    manager.close()
            except RuntimeError:
                pass
            except Exception as e:
                logger.warning("插件 close 异常: %s", e)
