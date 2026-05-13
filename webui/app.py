"""LCTA 应用程序框架 —— 轻量 API 层，零业务逻辑。

提供:
- 装饰器: api_expose / modal_handler / require_config / on_startup
- PluginManager: 插件发现、加载、生命周期管理
- LCTAAppFramework: 持有 window、配置、插件管理器，暴露 JS 可调用方法

所有业务逻辑位于 plugins/ 目录下各自插件中。
"""

from __future__ import annotations

import json
import os
import sys
import importlib.util
from functools import wraps
from pathlib import Path
from typing import Callable, Any, Optional

import webview

from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from globalManagers.pathManager import pathManager


# ═══════════════════════════════════════════════════════════════════════════════
# 全局注册表
# ═══════════════════════════════════════════════════════════════════════════════

_api_registry: dict[str, Callable] = {}
_config_schema: dict[str, dict] = {}
_plugin_manifests: dict[str, dict] = {}
_startup_hooks: list[Callable] = []


class CancelRunning(Exception):
    """用户取消当前操作的信号异常。"""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# 装饰器
# ═══════════════════════════════════════════════════════════════════════════════

def api_expose(func=None, *, name: str = None):
    """将函数注册为 JS 可调用 API。

    用法:
        @api_expose
        def my_func(framework, *args, **kwargs): ...

        @api_expose(name="custom_name")
        def my_func(framework, *args, **kwargs): ...
    """
    def decorator(fn):
        api_name = name or fn.__name__
        _api_registry[api_name] = fn
        return fn
    return decorator(func) if func else decorator


def modal_handler(process_name: str = None):
    """装饰器：自动包裹 modal 生命周期（日志→进度→取消检查→异常处理）。

    被装饰函数签名为 (self, modal_id, ...) → dict {success, message}
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, modal_id: str = None, *args, **kwargs):
            label = process_name or func.__name__
            logManager.ModalLog(f"开始{label}", modal_id)
            try:
                result = func(self, modal_id, *args, **kwargs)
                logManager.ModalLog("执行完毕", modal_id)
                return {"success": True, "message": f"{label}完成"}
            except CancelRunning:
                logManager.info("用户已取消流程")
                return {"success": False, "message": "已取消"}
            except Exception as e:
                logManager.exception(e)
                return {"success": False, "message": str(e)}
        return wrapper
    return decorator


def require_config(*keys: str):
    """前置配置校验。空字符串表示 game_path。

    用法:
        @require_config("game_path", "ui_default.translator.translator")
        def my_func(self, ...): ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            for key in keys:
                value = configManager.get(key) if key else configManager.get("game_path")
                if not value:
                    label = key or "game_path"
                    return {"success": False, "message": f"请先设置: {label}"}
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


def on_startup(func):
    """注册窗口就绪回调。func(framework) 在窗口创建且插件发现完成后调用。"""
    _startup_hooks.append(func)
    return func


# ═══════════════════════════════════════════════════════════════════════════════
# PluginManager
# ═══════════════════════════════════════════════════════════════════════════════

class PluginManager:
    """插件发现、加载、生命周期管理。"""

    def __init__(self, plugins_dir: Path):
        self.plugins_dir = plugins_dir
        self.loaded: set[str] = set()
        self.active_page: Optional[str] = None

    # ── 发现 ──

    def discover_all(self) -> list[dict]:
        """扫描 plugins/ 目录，返回所有有效 manifest 列表。"""
        manifests = []
        if not self.plugins_dir.exists():
            logManager.warn(f"插件目录不存在: {self.plugins_dir}")
            return manifests

        for plugin_dir in sorted(self.plugins_dir.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith('_'):
                continue
            manifest_path = plugin_dir / 'manifest.json'
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError as e:
                logManager.warn(f"插件 {plugin_dir.name} 的 manifest.json 解析失败: {e}")
                continue
            manifest['_dir'] = str(plugin_dir)
            _plugin_manifests[manifest['name']] = manifest
            manifests.append(manifest)

            # 注册配置 schema
            for cfg in manifest.get('config_keys', []):
                _config_schema[cfg['path']] = {
                    'type': cfg.get('type', 'string'),
                    'default': cfg.get('default'),
                    'label': cfg.get('label', ''),
                    'options': cfg.get('options'),
                    'description': cfg.get('description', ''),
                }

            # startup 插件立即加载
            if manifest.get('load_timing') == 'startup':
                self._load_plugin(manifest)

        manifests.sort(key=lambda m: m.get('nav_button', {}).get('order', 999))
        logManager.info(f"发现 {len(manifests)} 个插件")
        return manifests

    # ── 加载 ──

    def _load_plugin(self, manifest: dict):
        """导入插件的 Python 模块并调用 register() 钩子。"""
        plugin_id = manifest['name']
        if plugin_id in self.loaded:
            return
        plugin_dir = Path(manifest['_dir'])

        # 导入 api.py（其中的 @api_expose 装饰器会在导入时自动注册）
        api_path = plugin_dir / 'api.py'
        if api_path.exists():
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_id}.api", api_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

        # 调用 register() 钩子
        init_path = plugin_dir / '__init__.py'
        if init_path.exists():
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_id}", init_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, 'register'):
                module.register()

        self.loaded.add(plugin_id)
        logManager.info(f"插件已加载: {plugin_id}")

    # ── 页面激活 ──

    def activate_page(self, plugin_id: str) -> dict:
        """激活指定插件的页面，返回 HTML + JS + CSS。"""
        manifest = _plugin_manifests.get(plugin_id)
        if not manifest:
            return {"success": False, "message": f"插件不存在: {plugin_id}"}

        # lazy 加载：首次激活时才导入 Python 模块
        if manifest.get('load_timing') == 'lazy':
            self._load_plugin(manifest)

        self.active_page = plugin_id
        plugin_dir = Path(manifest['_dir'])

        result = {"success": True, "plugin_id": plugin_id}

        html_path = plugin_dir / 'page.html'
        if html_path.exists():
            result['html'] = html_path.read_text(encoding='utf-8')

        js_modules = manifest.get('js_modules', [])
        if js_modules:
            result['js'] = {}
            for js_file in js_modules:
                js_path = plugin_dir / js_file
                if js_path.exists():
                    result['js'][js_file] = js_path.read_text(encoding='utf-8')

        css_modules = manifest.get('css_modules', [])
        if css_modules:
            result['css'] = {}
            for css_file in css_modules:
                css_path = plugin_dir / css_file
                if css_path.exists():
                    result['css'][css_file] = css_path.read_text(encoding='utf-8')

        return result

    # ── 导航 ──

    def get_nav_config(self) -> list[dict]:
        """返回前端导航按钮配置列表。"""
        nav = []
        for manifest in _plugin_manifests.values():
            btn = manifest.get('nav_button', {})
            if btn.get('show', False):
                nav.append({
                    'id': btn.get('id', f"plugin-{manifest['name']}-btn"),
                    'plugin_id': manifest['name'],
                    'icon': btn.get('icon', 'fas fa-puzzle-piece'),
                    'label': btn.get('label', manifest.get('display_name', manifest['name'])),
                    'order': btn.get('order', 999),
                    'visible_when': btn.get('visible_when'),
                })
        nav.sort(key=lambda x: x['order'])
        return nav


# ═══════════════════════════════════════════════════════════════════════════════
# LCTAAppFramework
# ═══════════════════════════════════════════════════════════════════════════════

class LCTAAppFramework:
    """应用程序框架 —— 持有 window、配置、插件管理器。"""

    def __init__(self):
        self._window: Optional[webview.Window] = None
        self.plugin_manager: Optional[PluginManager] = None
        self.modal_list: list[dict] = []

    # ── 初始化 ──

    def init(self, window: webview.Window):
        """窗口创建后调用：初始化插件系统、执行 startup hooks、暴露 JS API。"""
        self._window = window

        # 初始化配置
        try:
            configManager.loadConfig()
        except Exception as e:
            logManager.exception(e)

        if configManager.config is None:
            try:
                configManager.load_config_default()
                configManager.config = configManager._default
                configManager._do_save()
                logManager.info("已生成默认配置文件")
            except Exception as e:
                logManager.error("生成默认配置文件时出现问题")
                logManager.exception(e)

        # 校验配置
        config_ok, config_error = configManager.validate_config()
        if not config_ok:
            logManager.warn("配置文件格式错误")
            logManager.warn("\n".join(config_error))

        # 初始化插件管理器
        plugins_dir = pathManager.plugins_path
        self.plugin_manager = PluginManager(plugins_dir)
        self.plugin_manager.discover_all()

        # 执行 startup hooks
        for hook in _startup_hooks:
            try:
                hook(self)
            except Exception as e:
                logManager.exception(e)

        # 暴露 JS 可调用方法
        self._window.expose(
            self.config_get_full_sync,
            self.config_set_batch,
            self.plugin_activate,
            self.plugin_get_nav,
            self.api_call,
        )

    # ── JS 可调用: 配置 ──

    def config_get_full_sync(self) -> dict:
        """一次性返回 config_schema + 当前值 + 导航配置。前端首次加载时调用。"""
        return {
            "schema": _config_schema,
            "values": {
                key: configManager.get(key)
                for key in _config_schema
            },
            "nav": self.plugin_manager.get_nav_config() if self.plugin_manager else [],
            "version": os.environ.get("__version__", "0.0.0"),
        }

    def config_set_batch(self, updates: dict[str, Any]) -> dict:
        """JS 批量更新配置: {key_path: value, ...}"""
        changed = configManager.set_batch(updates)
        return {"success": True, "updated": changed}

    # ── JS 可调用: 插件 ──

    def plugin_activate(self, plugin_id: str) -> dict:
        """JS 调用：激活插件页面，返回 HTML/JS/CSS。"""
        if not self.plugin_manager:
            return {"success": False, "message": "插件管理器未初始化"}
        return self.plugin_manager.activate_page(plugin_id)

    def plugin_get_nav(self) -> dict:
        """JS 调用：获取导航按钮配置。"""
        if not self.plugin_manager:
            return {"nav": []}
        return {"nav": self.plugin_manager.get_nav_config()}

    # ── JS 可调用: API 路由 ──

    def api_call(self, func_name: str, *args, **kwargs) -> Any:
        """统一 API 路由：根据注册表分发调用。"""
        func = _api_registry.get(func_name)
        if not func:
            return {"success": False, "message": f"未知 API: {func_name}"}
        try:
            return func(self, *args, **kwargs)
        except CancelRunning:
            return {"success": False, "message": "已取消"}
        except Exception as e:
            logManager.exception(e)
            return {"success": False, "message": str(e)}

    # ── Modal 管理 ──

    def add_modal_id(self, modal_id: str) -> bool:
        logManager.info(f"添加模态窗口ID: {modal_id}")
        self.modal_list.append({"modal_id": modal_id, "running": "running"})
        return True

    def _check_modal_running(self, modal_id: str) -> str:
        for m in self.modal_list:
            if m["modal_id"] == modal_id:
                return m["running"]
        return "running"

    def check_modal_running(self, modal_id: str):
        import time
        status = self._check_modal_running(modal_id)
        if status == "pause":
            while self._check_modal_running(modal_id) == "pause":
                time.sleep(1)
        elif status == "cancel":
            raise CancelRunning

    def set_modal_running(self, modal_id: str, types: str = "cancel"):
        logManager.info(f"设置模态窗口ID: {modal_id} 状态为 {types}")
        for m in self.modal_list:
            if m["modal_id"] == modal_id:
                m["running"] = str(types)
                break

    def del_modal_list(self, modal_id: str):
        logManager.info(f"删除模态窗口ID: {modal_id}")
        for idx, m in enumerate(self.modal_list):
            if m["modal_id"] == modal_id:
                del self.modal_list[idx]
                break

    # ── 向后兼容：未知方法自动路由到 api_call ──

    def __getattr__(self, name: str):
        """将未知属性访问路由到 api_call，保持旧 JS 调用兼容。"""
        if name.startswith('_'):
            raise AttributeError(name)
        func = _api_registry.get(name)
        if func:
            def wrapper(*args, **kwargs):
                return func(self, *args, **kwargs)
            return wrapper
        raise AttributeError(f"未知方法或 API: {name}")

    # ── 工具 ──

    def browse_file(self, input_id: str) -> Optional[str]:
        """打开文件浏览器，通过 input_id 回填前端输入框。"""
        file_path = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            save_filename='选择文件'
        )
        if file_path and len(file_path) > 0:
            selected = file_path[0]
            js = f"document.getElementById('{input_id}').value = '{selected.replace(os.sep, '/')}';"
            self._window.run_js(js)
            return selected
        return None

    def browse_folder(self, input_id: str) -> Optional[str]:
        """打开文件夹浏览器，通过 input_id 回填前端输入框。"""
        folder_path = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if folder_path and len(folder_path) > 0:
            selected = folder_path[0]
            js = f"document.getElementById('{input_id}').value = '{selected.replace(os.sep, '/')}';"
            self._window.run_js(js)
            return selected
        return None

    @property
    def window(self) -> Optional[webview.Window]:
        return self._window


# ═══════════════════════════════════════════════════════════════════════════════
# 框架单例
# ═══════════════════════════════════════════════════════════════════════════════

framework = LCTAAppFramework()
