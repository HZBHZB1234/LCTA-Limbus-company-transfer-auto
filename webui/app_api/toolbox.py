# -*- coding: utf-8 -*-
"""LCTA_API 工具箱桥：状态查询 / 登录 / 解锁 / 安装管理。

## 安全边界（plan 12.3）

- JS **只**传 ``tool_id`` / ``release_id`` / ``action`` 与用户确认信息；
  **不接受**任意 URL、磁盘目标或脚本 —— 描述符、清单、票据一律由 Python
  自己从可信 API 获取；
- 即使网页被改成直接调用 ``toolbox_install``，也必须经过本层的权限、
  签名、哈希与路径校验；
- ``game_root`` 只接受**用户已配置的**游戏路径，不由 JS 指定任意目录。

## 与旧解密门的关系

本地管理（列出/启停/卸载/回滚）**不依赖**旧 blob 解锁，也不依赖在线资格：
过季后用户仍必须能停用与卸载。只有「新下载/安装」需要在线资格。
"""
from __future__ import annotations

import logging
import threading

from globalManagers.ConfigManager import ConfigManager

logger = logging.getLogger(__name__)

CONFIG_KEY = "ui_default.toolbox"
BRIDGE_PROTOCOL_VERSION = 2

# 同一时刻只允许一个安装/更新任务（并发安装会互相覆盖文件）
_task_lock = threading.Lock()


class ToolboxMixin:
    """工具箱桥方法集合（由 API 组装处混入）。"""

    # -- 基础 --------------------------------------------------------------

    def _toolbox_api(self):
        from webutils.toolbox import api as toolbox_api

        return toolbox_api.ToolboxApi()

    def _toolbox_game_root(self):
        """用户配置的游戏目录；未配置则报错，**不**猜测。"""
        cfg = ConfigManager().get(CONFIG_KEY, {}) or {}
        root = (cfg.get("game_root") if isinstance(cfg, dict) else "") or ""
        if not root:
            raise ValueError("尚未配置游戏目录，请先在设置中选择 Limbus Company 安装目录")
        return root

    # -- 状态 --------------------------------------------------------------

    def toolbox_status(self):
        """本地状态 + 在线资格（两者分开返回）。

        ⚠️ 网络不可达时**不能**让本地状态也消失：用户过季或断网仍要能
        停用/卸载。因此在线部分失败只标 ``online_error``，本地照常返回。
        """
        try:
            from webutils.toolbox import install, runtime, state

            data = {
                "protocol_version": BRIDGE_PROTOCOL_VERSION,
                "logged_in": False,
                "online": None,
                "online_error": None,
                "local": None,
                "game_running": None,
                "recovered": None,
            }

            try:
                root = self._toolbox_game_root()
            except ValueError as exc:
                data["local_error"] = str(exc)
                return {"success": True, "data": data}

            # 启动时先恢复未完成事务（崩溃可恢复）
            try:
                recovered = state.recover_if_needed(root)
                if recovered:
                    data["recovered"] = recovered
            except Exception as exc:  # noqa: BLE001
                self.log_error(exc)
                data["online_error"] = None

            try:
                data["game_running"] = runtime.is_game_running(root)
            except Exception:  # noqa: BLE001
                data["game_running"] = None

            try:
                data["local"] = install.list_installed(root)
            except Exception as exc:  # noqa: BLE001
                self.log_error(exc)
                data["local_error"] = str(exc)

            api = self._toolbox_api()
            data["logged_in"] = api.is_logged_in()
            try:
                data["online"] = api.access()
            except Exception as exc:  # noqa: BLE001
                # 在线失败不影响本地管理能力
                data["online_error"] = str(exc)

            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    # -- 登录 --------------------------------------------------------------

    def toolbox_login(self, identifier, password):
        """账号密码登录（identifier 含 @ 按邮箱、否则按用户名）。"""
        try:
            api = self._toolbox_api()
            api.login(str(identifier or ""), str(password or ""))
            self.log_ui("工具箱：已登录资源站")
            return {"success": True, "message": "登录成功"}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_logout(self):
        try:
            self._toolbox_api().logout()
            self.log_ui("工具箱：已登出（服务端会话已撤销）")
            return {"success": True}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_current_user(self):
        try:
            return {"success": True, "data": self._toolbox_api().current_user()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    # -- 解锁（赛季资格）---------------------------------------------------

    def toolbox_season(self):
        """当前赛季公开信息（无需登录）。"""
        try:
            return {"success": True, "data": self._toolbox_api().season()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_new_challenge(self):
        """获取个人当季谜题（响应**不含答案**，需用户自己解出）。"""
        try:
            return {"success": True, "data": self._toolbox_api().new_challenge()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_solve(self, challenge_id, answer):
        try:
            data = self._toolbox_api().solve(str(challenge_id or ""), str(answer or ""))
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_afdian_status(self):
        try:
            return {"success": True, "data": self._toolbox_api().afdian_status()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_afdian_bind_url(self):
        """取爱发电授权地址（redirect_uri 只来自服务端配置）。"""
        try:
            api = self._toolbox_api()
            data = api._request("POST", "/api/integrations/afdian/bind/start", auth=True)
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_verify_order(self, order_no):
        try:
            data = self._toolbox_api().verify_order(str(order_no or ""))
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_catalog(self):
        """当前季可获取内容（需已解锁）。"""
        try:
            return {"success": True, "data": self._toolbox_api().catalog()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    # -- 安装管理 ----------------------------------------------------------

    def toolbox_list_installed(self):
        """列出本地受管状态（离线可用）。"""
        try:
            from webutils.toolbox import install

            return {"success": True, "data": install.list_installed(self._toolbox_game_root())}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_set_enabled(self, tool_id, enabled):
        """启用/停用（本地操作，**不需要**在线资格）。"""
        try:
            from webutils.toolbox import install

            data = install.set_enabled(self._toolbox_game_root(), str(tool_id or ""), bool(enabled))
            self.log_ui(f"工具箱：{'启用' if enabled else '停用'} {tool_id}")
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_uninstall(self, tool_id, remove_config=False):
        """卸载受管插件（本地操作，离线可用）。"""
        try:
            from webutils.toolbox import install

            data = install.uninstall_plugin(
                self._toolbox_game_root(), str(tool_id or ""), remove_config=bool(remove_config)
            )
            self.log_ui(f"工具箱：已卸载 {tool_id}")
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_rollback(self, tool_id):
        """回滚到本地备份（离线可用）。"""
        try:
            from webutils.toolbox import install

            data = install.rollback_plugin(self._toolbox_game_root(), str(tool_id or ""))
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_verify_integrity(self, tool_id):
        try:
            from webutils.toolbox import install

            return {
                "success": True,
                "data": install.verify_integrity(self._toolbox_game_root(), str(tool_id or "")),
            }
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_open_folder(self, tool_id=""):
        """在资源管理器中打开受管目录（只打开受管区，不接受任意路径）。"""
        try:
            import os
            import subprocess

            from webutils.toolbox import paths

            root = self._toolbox_game_root()
            target = paths.plugin_dir(root, tool_id) if tool_id else paths.toolbox_dir(root)
            target.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                subprocess.Popen(["explorer", str(target)])
            return {"success": True, "data": {"path": str(target)}}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_install(self, tool_id, release_id):
        """安装/更新一个插件（**需要**在线资格）。

        清单与票据由 Python 自己取；网页无法指定 URL 或目标路径。
        """
        if not _task_lock.acquire(blocking=False):
            return {"success": False, "message": "已有安装任务在进行中，请稍候"}
        try:
            from webutils.toolbox import download, ed25519, install

            root = self._toolbox_game_root()
            api = self._toolbox_api()

            manifest_out = api.manifest(int(tool_id), str(release_id))
            manifest = manifest_out.get("manifest") or {}
            signature = manifest_out.get("signature")

            # 签名校验：未签名或验签失败一律拒绝安装（plan 16.3）
            if not signature:
                raise ValueError("该版本没有签名清单，拒绝安装")
            pub = self._manifest_public_key()
            if not pub or not ed25519.verify_from_der_public_key(
                pub, self._b64(signature), ed25519.canonical_bytes(manifest)
            ):
                raise ValueError("清单签名校验失败，拒绝安装")

            files = manifest.get("files") or []
            if not files:
                raise ValueError("清单没有文件，拒绝安装")

            main_name = str(files[0].get("path") or "")
            sha = str(files[0].get("sha256") or "").lower()
            size = files[0].get("size")

            ticket = api.download_ticket(int(tool_id), str(release_id), main_name, sha)
            url = ticket.get("download_url")
            if not url:
                raise ValueError("服务端未返回下载地址")

            stub = download.fetch_or_reuse(url, sha, expected_size=size)

            plan = install.InstallPlan(
                kind="plugin",
                release_id=str(release_id),
                version=str(manifest.get("version") or ""),
                tool_id=str(tool_id),
                guid=manifest.get("guid"),
                main_dll=main_name,
                requires_runtime=True,
                stub_path=stub,
            )
            data = install.install_plugin(root, plan)
            self.log_ui(f"工具箱：已安装 {tool_id}/{release_id}")
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}
        finally:
            _task_lock.release()

    # -- 辅助 --------------------------------------------------------------

    @staticmethod
    def _b64(value: str) -> bytes:
        import base64

        return base64.b64decode(value)

    @staticmethod
    def _manifest_public_key():
        """清单验签公钥（本地配置）。

        未配置时返回 None → 调用方拒绝安装（fail-closed）。
        """
        cfg = ConfigManager().get(CONFIG_KEY, {}) or {}
        pem = (cfg.get("manifest_public_key") if isinstance(cfg, dict) else "") or ""
        return pem.encode("utf-8") if pem else None

    def toolbox_set_game_root(self, path):
        """设置游戏目录（会做校验，拒绝盘符根/不可写/不存在）。"""
        try:
            from webutils.toolbox import paths

            resolved = paths.validate_game_root(str(path or ""))
            cfg = ConfigManager().get(CONFIG_KEY, {}) or {}
            if not isinstance(cfg, dict):
                cfg = {}
            cfg["game_root"] = str(resolved)
            ConfigManager().set(CONFIG_KEY, cfg)
            return {"success": True, "data": {"game_root": str(resolved)}}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}