# -*- coding: utf-8 -*-
"""订阅工具桥：状态查询 / 登录 / 安装管理（原「工具箱」，2026-10-30 更名）。

## 一键安装契约（2026-10-30，manifest-driven）

订阅工具（季目录内已发布版本）**必须**提供签名安装清单 —— 站点 publish
强制签名（`manifest_unsigned` 拒绝发布），因此客户端只信清单：

- 无签名 / 验签失败 / 清单无文件 / 未知 ``install_kind`` → **一律拒绝安装**；
- 安装过程完全清单驱动：逐文件取短期票据下载并校验 sha256（不接受网页传
  URL/路径），再按 ``install_kind`` 分发 —— ``bepinex_plugin_dll`` 走
  ``install_plugin``（事务 journal/备份/启停保持），``runtime_zip_root`` 走
  ``install_runtime``；
- 本地管理（列出/启停/卸载/回滚/完整性）**不需要**在线资格：过季后用户
  仍必须能停用与卸载，只有「新下载/安装」需要在线资格。

## 安全边界（plan 12.3）

- JS **只**传 ``tool_id`` / ``release_id`` / ``action`` 与用户确认信息；
  **不接受**任意 URL、磁盘目标或脚本 —— 描述符、清单、票据一律由 Python
  自己从可信 API 获取；
- 即使网页被改成直接调用 ``toolbox_install``，也必须经过本层的权限、
  签名、哈希与路径校验；
- ``game_root`` 只接受**用户已配置的**游戏路径，不由 JS 指定任意目录。
"""
from __future__ import annotations

import logging
import threading

from globalManagers.ConfigManager import ConfigManager

logger = logging.getLogger(__name__)

CONFIG_KEY = "ui_default.toolbox"
BRIDGE_PROTOCOL_VERSION = 2

# 一键安装契约（站点 install_kind 白名单，与站点 services/tool_releases.py 同源）
INSTALL_KIND_PLUGIN = "bepinex_plugin_dll"
INSTALL_KIND_RUNTIME = "runtime_zip_root"

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
        """本地状态 + 在线资格 + 赛季/目录（三部分分开返回，互不拖垮）。

        ⚠️ 网络不可达时**不能**让本地状态也消失：用户过季或断网仍要能
        停用/卸载。因此在线部分失败只标 ``online_error``，本地照常返回。
        ``season``（公开信息）与 ``catalog``（2026-10-30 起名单对游客可见）
        独立获取 —— 之前目录数据从未被填充，页面永远显示「暂无可获取内容」。
        """
        try:
            from webutils.toolbox import install, runtime, state

            data = {
                "protocol_version": BRIDGE_PROTOCOL_VERSION,
                "logged_in": False,
                "online": None,
                "online_error": None,
                "season": None,
                "catalog": None,
                "catalog_error": None,
                "user": None,
                "afdian": None,
                "local": None,
                "game_running": None,
                "recovered": None,
            }

            try:
                root = self._toolbox_game_root()
            except ValueError as exc:
                data["local_error"] = str(exc)
                self._toolbox_fill_online(data)
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

            self._toolbox_fill_online(data)

            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def _toolbox_fill_online(self, data):
        """填充在线部分（season/access/catalog）：任何一项失败不影响其它。"""
        try:
            api = self._toolbox_api()
        except Exception as exc:  # noqa: BLE001
            data["online_error"] = str(exc)
            return
        data["logged_in"] = api.is_logged_in()
        data["base_url"] = getattr(api, "base_url", "") or ""
        try:
            data["season"] = api.season()
        except Exception as exc:  # noqa: BLE001
            logger.info("订阅工具：赛季公开信息获取失败 %s", exc)
        try:
            data["online"] = api.access() if api.is_logged_in() else None
        except Exception as exc:  # noqa: BLE001
            # 在线失败不影响本地管理能力
            data["online_error"] = str(exc)
        try:
            # 名单公开（2026-10-30）：未登录也能看，逐条 downloadable 决定可否安装
            data["catalog"] = api.catalog()
        except Exception as exc:  # noqa: BLE001
            data["catalog_error"] = str(exc)
        if api.is_logged_in():
            try:
                data["user"] = api.current_user()
            except Exception:  # noqa: BLE001
                data["user"] = None
            try:
                data["afdian"] = api.afdian_status()
            except Exception:  # noqa: BLE001
                data["afdian"] = None

    # -- 登录 --------------------------------------------------------------

    def toolbox_login(self, identifier, password):
        """账号密码登录（identifier 含 @ 按邮箱、否则按用户名）。"""
        try:
            api = self._toolbox_api()
            api.login(str(identifier or ""), str(password or ""))
            self.log_ui("订阅工具：已登录资源站")
            return {"success": True, "message": "登录成功"}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_logout(self):
        try:
            self._toolbox_api().logout()
            self.log_ui("订阅工具：已登出（服务端会话已撤销）")
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
        """取爱发电授权地址并用**系统浏览器**打开（redirect_uri 只来自服务端配置）。

        OAuth 回调落在站点域名上 —— 在 pywebview 内打开会 404，因此交给
        系统浏览器；用户在浏览器完成授权后回到本页点「刷新订阅状态」。
        """
        try:
            import webbrowser

            data = self._toolbox_api()._request(
                "POST", "/api/integrations/afdian/bind/start", auth=True
            )
            url = str((data or {}).get("authorize_url") or "")
            if url:
                webbrowser.open(url)
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_afdian_refresh(self):
        """刷新订阅状态：服务端重新拉取该赞助者全部订单并自动核验（幂等）。"""
        try:
            data = self._toolbox_api().afdian_refresh()
            self.log_ui(
                "订阅工具：订阅状态已刷新（扫描 {scanned}，核验 {verified}）".format(
                    scanned=data.get("scanned", 0), verified=data.get("verified", 0)
                )
            )
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

    # -- 启动鉴权：设备授权（TPM，2026-10-27）--------------------------------

    def toolbox_authz_devices(self):
        """已授权设备列表 + 本机凭据/TPM 状态。"""
        try:
            api = self._toolbox_api()
            data = api.list_devices()
            try:
                from webutils.toolbox import authz_tpm

                local = authz_tpm.load_device()
                data["local_device_id"] = local.get("device_id") if local else None
                data["tpm_available"] = authz_tpm.tpm_available()
            except Exception:  # noqa: BLE001
                data["local_device_id"] = None
                data["tpm_available"] = False
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_authz_enable(self, display_name=""):
        """启用本机（生成/复用 TPM 密钥并注册）。

        成功后 Zylarnex 可脱离启动器自行运行：doorstop 原生层会读本地
        凭据换票据，决定是否加载 BepInEx。
        """
        try:
            data = self._toolbox_api().enable_device(str(display_name or ""))
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_authz_disable(self):
        """撤销本机授权并清除本地凭据。"""
        try:
            return {"success": True, "data": self._toolbox_api().disable_device()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def toolbox_authz_revoke(self, device_id):
        """撤销指定设备（管理另一台机器时用）。"""
        try:
            return {"success": True,
                    "data": self._toolbox_api().revoke_device(str(device_id or ""))}
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
            self.log_ui(f"订阅工具：{'启用' if enabled else '停用'} {tool_id}")
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
            self.log_ui(f"订阅工具：已卸载 {tool_id}")
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

    def toolbox_install(self, tool_id, release_id, confirm_foreign=False):
        """一键安装/更新一个订阅工具（**清单驱动**，需要相应下载资格）。

        契约：只信签名清单 —— 验签 → 逐文件取票据下载并校验 sha256 →
        ``bepinex_plugin_dll`` 打包成事务化 zip 走 ``install_plugin``。
        网页无法指定 URL 或目标路径；未签名/未知 install_kind 一律拒绝。
        """
        if not _task_lock.acquire(blocking=False):
            return {"success": False, "message": "已有安装任务在进行中，请稍候"}
        try:
            from webutils.toolbox import ed25519, install

            root = self._toolbox_game_root()
            api = self._toolbox_api()
            manifest, kind, files = self._toolbox_fetch_verified_manifest(api, tool_id, release_id)
            if kind != INSTALL_KIND_PLUGIN:
                return {
                    "success": False,
                    "message": f"该版本是底座（install_kind={kind}），请使用「安装底座」入口",
                }
            stubs = self._toolbox_download_all_files(api, tool_id, release_id, files)
            stub = self._toolbox_pack_plugin_stub(stubs, files)

            plan = install.InstallPlan(
                kind="plugin",
                release_id=str(release_id),
                version=str(manifest.get("version") or ""),
                tool_id=str(tool_id),
                guid=manifest.get("guid"),
                main_dll=str(files[0].get("path") or ""),
                requires_runtime=True,
                stub_path=stub,
            )
            data = install.install_plugin(root, plan)
            self.log_ui(f"订阅工具：已安装 {tool_id}/{release_id}（{len(files)} 个文件）")
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}
        finally:
            _task_lock.release()

    def toolbox_install_runtime(self, tool_id, release_id, confirm_foreign=False):
        """一键安装/更新订阅工具底座（``runtime_zip_root``，清单驱动）。

        ``confirm_foreign``：检测到非 LCTA 管理的 BepInEx 时必须由用户
        明确确认（网页侧 confirm 对话框），否则拒绝覆盖。
        """
        if not _task_lock.acquire(blocking=False):
            return {"success": False, "message": "已有安装任务在进行中，请稍候"}
        try:
            from webutils.toolbox import ed25519, install

            root = self._toolbox_game_root()
            api = self._toolbox_api()
            manifest, kind, files = self._toolbox_fetch_verified_manifest(api, tool_id, release_id)
            if kind != INSTALL_KIND_RUNTIME:
                return {
                    "success": False,
                    "message": f"该版本是插件（install_kind={kind}），请使用「安装/更新」入口",
                }
            stubs = self._toolbox_download_all_files(api, tool_id, release_id, files)
            if len(stubs) != 1:
                raise ValueError("底座清单必须恰好声明一个整包文件")
            plan = install.InstallPlan(
                kind="runtime",
                release_id=str(release_id),
                version=str(manifest.get("version") or ""),
                tool_id=str(tool_id),
                requires_runtime=False,
                stub_path=stubs[0],
            )
            data = install.install_runtime(root, plan, confirm_foreign=bool(confirm_foreign))
            self.log_ui(f"订阅工具：已安装底座 {tool_id}/{release_id}")
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return {"success": False, "message": str(e)}
        finally:
            _task_lock.release()

    # -- 一键安装契约的内部步骤 ---------------------------------------------

    def _toolbox_fetch_verified_manifest(self, api, tool_id, release_id):
        """取回并验签安装清单（契约第 1 步：**只信签名清单**）。"""
        from webutils.toolbox import ed25519

        manifest_out = api.manifest(int(tool_id), str(release_id))
        manifest = manifest_out.get("manifest") or {}
        signature = manifest_out.get("signature")

        if not signature:
            raise ValueError("该版本没有签名清单，拒绝安装（一键安装契约）")
        pub = self._manifest_public_key()
        if not pub or not ed25519.verify_from_der_public_key(
            pub, self._b64(signature), ed25519.canonical_bytes(manifest)
        ):
            raise ValueError("清单签名校验失败，拒绝安装")

        kind = str(manifest.get("install_kind") or "")
        if kind not in (INSTALL_KIND_PLUGIN, INSTALL_KIND_RUNTIME):
            raise ValueError(f"未知的安装类型（install_kind={kind or '缺失'}），拒绝安装")

        files = manifest.get("files") or []
        if not files:
            raise ValueError("清单没有文件，拒绝安装")
        return manifest, kind, files

    def _toolbox_download_all_files(self, api, tool_id, release_id, files):
        """逐文件取短期票据下载并校验 sha256（契约第 2 步：清单外文件不可得）。"""
        from webutils.toolbox import download

        paths = []
        for f in files:
            name = str(f.get("path") or "")
            sha = str(f.get("sha256") or "").lower()
            if not name or len(sha) != 64:
                raise ValueError(f"清单文件项缺少 path/sha256：{name or '未知'}")
            ticket = api.download_ticket(int(tool_id), str(release_id), name, sha)
            url = ticket.get("download_url")
            if not url:
                raise ValueError(f"服务端未返回下载地址：{name}")
            paths.append(download.fetch_or_reuse(url, sha, expected_size=f.get("size")))
        return paths

    @staticmethod
    def _toolbox_pack_plugin_stub(stub_paths, manifest_files):
        """把清单文件组装成 install_plugin 可事务化解压的 zip stub。

        - 恰好一个 .zip 工件 → 直接复用（与旧单包行为一致）；
        - 其余情况（裸 DLL / 多文件）→ 按清单 path 打包成临时 zip，
          ``install_plugin`` 的 journal/备份/启停保持逻辑原样复用。
        """
        import os
        import tempfile
        import zipfile

        if len(stub_paths) == 1 and str(manifest_files[0].get("path", "")).lower().endswith(".zip"):
            return stub_paths[0]

        fd, zip_path = tempfile.mkstemp(prefix="toolbox-plugin-", suffix=".zip")
        os.close(fd)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for src, meta in zip(stub_paths, manifest_files):
                zf.write(str(src), str(meta.get("path")))
        return zip_path

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