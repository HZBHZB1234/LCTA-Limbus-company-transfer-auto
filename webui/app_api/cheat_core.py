# -*- coding: utf-8 -*-
"""LCTA_API CheatCore 密钥门 + 插件宿主：状态查询 / 解锁 / 锁定 / 插件列表 / 通用分发。

另含通用插件独立窗口入口（pw_open）：按注册表 PLUGIN["windows"][] 元数据创建
pywebview 窗口（壳 webui/plugin-window.html，桥 webui/plugin_window_api.py），
工具语义全部留在解密功能脚本内，本层不感知任何具体工具。
"""

from globalManagers.ConfigManager import ConfigManager


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
                "blob_corrupt": "工具箱数据损坏，请重新安装后重试",
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

    # ------------------------------------------------------------------
    # 通用插件独立窗口（壳 + 桥均工具无关，窗口元数据来自插件注册表）
    # ------------------------------------------------------------------

    def pw_open(self, window_id):
        """按 id 打开注册表声明的插件独立窗口。

        流程：解锁校验 → 注册表查窗口描述符 → 风险同意门控 → 创建窗口
        （壳 plugin-window.html + 通用桥 PluginWindowAPI）→ 主题注入与跟踪。
        """
        try:
            import os
            import webview
            from webutils import cheat_core
            from webutils.cheat_plugins import CheatPluginHost
            from webui.plugin_window_api import PluginWindowAPI

            result = cheat_core.ensure_unlocked()
            if not result.get("success"):
                return {"success": False, "reason": result.get("reason", "need_key"),
                        "message": "作弊工具箱未解锁，请先在作弊工具箱页解锁"}

            desc = CheatPluginHost.find_window(str(window_id or ""))

            consent = desc.get("consent")
            if consent and not ConfigManager().get(f"{consent}.disclaimer_accepted", False):
                return {"success": False, "reason": "consent_required",
                        "message": "请先在作弊工具箱页阅读并同意风险须知"}

            html_path = os.path.join(os.getenv("path_") or "", "webui", "plugin-window.html")
            if not os.path.isfile(html_path):
                return {"success": False, "message": f"缺少插件窗口壳: {html_path}"}

            bridge = PluginWindowAPI(str(window_id))
            window = webview.create_window(
                desc.get("title") or "LCTA - 插件窗口", url=html_path,
                width=int(desc.get("width", 1280)), height=int(desc.get("height", 860)),
                resizable=True, text_select=True, js_api=bridge,
            )
            bridge._window = window  # 文件对话框需要窗口句柄

            # 窗口创建后立即注入主题（同 open_rule_editor；bootstrap 就绪后会再次对齐）
            try:
                current_theme = ConfigManager().get('theme', 'light')
                window.evaluate_js(f"""
                    (function() {{
                        if (document.body) {{
                            document.body.className = 'theme-{current_theme}';
                        }}
                    }})();
                """)
            except Exception as e:
                # 主题预注入失败不阻断开窗（bootstrap 就绪后仍会应用主题）
                try:
                    self.log_error(e)
                except Exception:
                    pass

            if not hasattr(self, '_plugin_windows'):
                self._plugin_windows = []
            entry = {"id": str(window_id), "window": window}
            self._plugin_windows.append(entry)

            def remove_window(*_args):
                if getattr(self, '_plugin_windows', None) and entry in self._plugin_windows:
                    try:
                        self._plugin_windows.remove(entry)
                    except ValueError:
                        pass

            window.events.closed += remove_window
            return {"success": True}
        except RuntimeError as e:
            from webutils.cheat_plugins import CheatPluginHost
            reason = "locked" if CheatPluginHost.is_empty() else "unknown_window"
            return {"success": False, "reason": reason, "message": str(e)}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"打开插件窗口失败: {e}"}

    def sync_theme_to_plugin_windows(self, theme):
        """推送主题变更到所有打开的插件窗口。"""
        for entry in list(getattr(self, '_plugin_windows', []) or []):
            try:
                entry["window"].evaluate_js(f"""
                    if (typeof applyTheme === 'function') {{
                        applyTheme('{theme}');
                    }}
                """)
            except Exception:
                pass
