# -*- coding: utf-8 -*-
"""通用插件窗口 js-API 桥接（公共仓库 · 工具无关）。

由 webui/app_api/cheat_core.py 的 pw_open() 在创建窗口时实例化并绑定。
职责：
    - pw_get_bootstrap(): 返回窗口元数据（标题/主题）与解密功能脚本内容
    - pw_invoke(): 按注册表白名单分发到插件管理器方法（与主窗口
      cheat_plugin_invoke 同一信任边界，统一 {success, data} 信封）
    - pw_get_config_value / pw_set_config_value: 窗口侧配置读取/写入
    - pw_browse_folder / pw_browse_file: 目录/文件选择对话框

本类不感知任何具体工具：window_id 只是注册表 PLUGIN["windows"][] 的键，
工具语义全部在私有仓库解密包内。
"""

import json

from globalManagers.ConfigManager import ConfigManager


class PluginWindowAPI:
    """通用插件窗口桥。pw_open() 创建窗口后回填 _window 供文件对话框使用。"""

    def __init__(self, window_id: str):
        self._window_id = str(window_id or "")
        self._window = None  # pw_open() 创建窗口后绑定

    # ------------------------------------------------------------------
    # 引导
    # ------------------------------------------------------------------

    def pw_get_bootstrap(self):
        """返回窗口标题/主题与解密功能脚本；未解锁等场景返回失败信封。"""
        try:
            from webutils.cheat_plugins import CheatPluginHost
            from webutils import cheat_core
            desc = CheatPluginHost.find_window(self._window_id)
            theme = ConfigManager().get("theme", "light")
            js_content = cheat_core._read_webui_file(f"webui/{desc['js']}")
            return {
                "success": True,
                "data": {
                    "title": desc.get("title") or "LCTA - 插件窗口",
                    "theme": theme,
                    "js": js_content,
                },
            }
        except RuntimeError as e:
            return {"success": False, "reason": "locked", "message": str(e)}
        except FileNotFoundError as e:
            return {"success": False, "reason": "missing", "message": f"功能文件缺失: {e}"}
        except Exception as e:
            try:
                from globalManagers.LogManager import LogManager
                LogManager().log_error(e)
            except Exception:
                pass
            return {"success": False, "message": f"窗口引导失败: {e}"}

    # ------------------------------------------------------------------
    # 白名单分发
    # ------------------------------------------------------------------

    def pw_invoke(self, action, args=None):
        """按注册表 api 白名单调用插件管理器方法，返回 {success, data} 信封。"""
        try:
            from webutils.cheat_plugins import CheatPluginHost
            return {"success": True, "data": CheatPluginHost.invoke(str(action or ""), args)}
        except RuntimeError as e:
            reason = "locked" if CheatPluginHost.is_empty() else "invalid_action"
            return {"success": False, "reason": reason, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": f"操作失败: {e}"}

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    def pw_get_config_value(self, key_path, default_value=None):
        """读取主应用配置（如主题、导出目录）；读取失败时返回默认值。"""
        try:
            return ConfigManager().get(str(key_path or ""), default_value)
        except Exception:
            return default_value

    def pw_set_config_value(self, key_path, value):
        """写入主应用配置并落盘。"""
        try:
            ConfigManager().set(str(key_path or ""), value)
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ------------------------------------------------------------------
    # 对话框
    # ------------------------------------------------------------------

    def pw_browse_folder(self):
        """选择文件夹，返回 {success, path|message}。"""
        import webview
        if self._window is None:
            return {"success": False, "message": "窗口未绑定"}
        folder_path = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if folder_path and len(folder_path) > 0:
            return {"success": True, "path": str(folder_path[0])}
        return {"success": False, "message": "已取消"}

    def pw_browse_file(self, title="选择文件", save=False):
        """选择文件，返回 {success, path|message}。save=True 时为保存对话框。"""
        import webview
        if self._window is None:
            return {"success": False, "message": "窗口未绑定"}
        if save:
            file_path = self._window.create_file_dialog(
                webview.FileDialog.SAVE, save_filename=str(title or "保存文件"))
            if isinstance(file_path, str) and file_path:
                return {"success": True, "path": file_path.replace("\\", "/")}
        else:
            file_path = self._window.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False)
            if file_path and len(file_path) > 0:
                return {"success": True, "path": str(file_path[0])}
        return {"success": False, "message": "已取消"}

    @staticmethod
    def _json_safe(obj):
        """pywebview 序列化兜底（当前无需转换，保留扩展点）。"""
        return json.loads(json.dumps(obj, ensure_ascii=False, default=str))
