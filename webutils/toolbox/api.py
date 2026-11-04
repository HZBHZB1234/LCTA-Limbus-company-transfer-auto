# -*- coding: utf-8 -*-
"""工具箱后端 API 客户端（客户端侧）。

## 安全边界（plan 12.3）

- 客户端**只**提交 ``tool_id`` / ``release_id`` / ``action`` 与用户确认信息；
  绝不接受网页传来的任意 URL、磁盘目标或脚本；
- 所有描述符、清单、票据都**由 Python 自己**从可信 API 获取 ——
  网页即使被改成直接调用 install，也必须经过本层的权限与签名校验；
- ``base_url`` 只来自本地配置，不接受调用方传入的任意主机。

## 会话

access/refresh token 走 DPAPI 加密存储（``session.CredentialStore``）。
401 时**单飞**刷新：并发 401 各自刷新会让服务端把第二个请求判定为
refresh 重放并撤销整个会话（服务端是原子旋转）。
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import session as session_mod
from .constants import USER_AGENT

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://mods.lcta.top"
REQUEST_TIMEOUT = 20
# 版本号：桥协议变更时递增，便于两侧拒绝不匹配的调用（plan 12.3）
BRIDGE_PROTOCOL_VERSION = 2

ACCESS_KEY = "toolbox.access_token"
REFRESH_KEY = "toolbox.refresh_token"
USER_KEY = "toolbox.user"


class ApiError(RuntimeError):
    """后端返回的可解释错误。``code`` 用于界面分支，``message`` 直接可展示。"""

    def __init__(self, code: str, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class AuthRequiredError(ApiError):
    """未登录/登录已失效（界面应引导登录，而不是显示「操作失败」）。

    ``auth = True`` 是**机器可读标记**：``code`` 保留服务端原文（便于排查，
    也避免把「密码错误」这类 401 说成「会话过期」），而桥接层/前端统一用
    这个标记判断「需要重新登录」。只看 ``code`` 是历史 bug 的根源 ——
    服务端 detail 里的 code 五花八门（``error``/``invalid_token``/``expired``），
    前端按 ``code == "auth_required"`` 分支就永远匹配不上，用户只在设置页
    诊断里看到一行小字，没有任何重新登录的引导。
    """

    auth = True


def _detail_message(detail: Any, fallback: str) -> Tuple[str, str]:
    """把后端 ``detail`` 解析成 ``(code, message)``。

    后端有三种真实形态（与服务端 ``schemas`` 一致）：
    字符串 / ``{code, message}`` / **422 数组**。
    数组形态最容易漏 —— 漏了就会变成「点了没反应」。
    """
    if isinstance(detail, str):
        return ("error", detail)
    if isinstance(detail, dict):
        return (str(detail.get("code") or "error"), str(detail.get("message") or fallback))
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict):
                loc = ".".join(str(x) for x in (item.get("loc") or []) if x != "body")
                msg = str(item.get("msg") or "")
                parts.append(f"{loc}: {msg}" if loc else msg)
        return ("invalid_request", "；".join(parts) or fallback)
    return ("error", fallback)


class ToolboxApi:
    """工具箱 API 客户端。

    ``base_url`` 默认取本地配置，可在测试中注入。
    """

    def __init__(
        self,
        base_url: str = "",
        *,
        store: Optional[session_mod.CredentialStore] = None,
    ) -> None:
        self.base_url = (base_url or self._config_base_url()).rstrip("/")
        self._store = store or session_mod.CredentialStore()
        self._refresh_lock = threading.Lock()

    @staticmethod
    def _config_base_url() -> str:
        try:
            from globalManagers.ConfigManager import ConfigManager

            cfg = ConfigManager().get("ui_default.toolbox", {}) or {}
            if isinstance(cfg, dict) and cfg.get("base_url"):
                return str(cfg["base_url"])
        except Exception:  # noqa: BLE001 — 配置不可用不应让模块导入失败
            logger.debug("读取工具箱 base_url 配置失败，使用默认值", exc_info=True)
        return DEFAULT_BASE_URL

    # -- 会话 ---------------------------------------------------------------

    @property
    def access_token(self) -> Optional[str]:
        return self._store.get(ACCESS_KEY)

    @property
    def refresh_token(self) -> Optional[str]:
        return self._store.get(REFRESH_KEY)

    def is_logged_in(self) -> bool:
        return bool(self.refresh_token or self.access_token)

    def save_auth(self, data: Dict[str, Any]) -> None:
        """保存登录结果（access/refresh/user）。"""
        if data.get("access_token"):
            self._store.set(ACCESS_KEY, str(data["access_token"]))
        if data.get("refresh_token"):
            self._store.set(REFRESH_KEY, str(data["refresh_token"]))
        user = data.get("user")
        if user:
            self._store.set(USER_KEY, json.dumps(user, ensure_ascii=False))

    def current_user(self) -> Optional[Dict[str, Any]]:
        raw = self._store.get(USER_KEY)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def logout(self) -> None:
        """登出：先通知服务端撤销会话，再清本地。

        只清本地会让 DB 里的会话与 refresh 凭据继续有效 —— 重放 refresh
        即可拿回登录态，等于「登出无效」。服务端 logout 幂等，
        失败也必须完成本地清理。
        """
        try:
            if self.access_token:
                self._request("POST", "/api/auth/logout", auth=True, allow_fail=True)
        except Exception:  # noqa: BLE001
            logger.debug("通知服务端登出失败（继续清理本地）", exc_info=True)
        self._store.clear()

    # -- 登录 ---------------------------------------------------------------

    def login(self, identifier: str, password: str) -> Dict[str, Any]:
        """登录。``identifier`` 含 @ 按邮箱、否则按用户名（服务端契约）。"""
        data = self._request(
            "POST",
            "/api/auth/client/login",
            body={"identifier": identifier, "password": password},
        )
        self.save_auth(data)
        return data

    def register(
        self, username: str, password: str, email: str, challenge_id: str, code: str
    ) -> Dict[str, Any]:
        """邮箱验证码注册（**无** invite_code：服务端 extra=forbid 会 422）。"""
        data = self._request(
            "POST",
            "/api/auth/client/register",
            body={
                "username": username,
                "password": password,
                "email": email,
                "challenge_id": challenge_id,
                "code": code,
            },
        )
        self.save_auth(data)
        return data

    def request_email_code(self, email: str, purpose: str) -> Dict[str, Any]:
        """发起邮箱验证码。响应刻意统一（防枚举），不代表「邮箱未注册」。"""
        return self._request(
            "POST", "/api/auth/email/request", body={"email": email, "purpose": purpose}
        )

    # -- 工具箱 -------------------------------------------------------------

    def season(self) -> Dict[str, Any]:
        """当前赛季公开信息（无需登录）。"""
        return self._request("GET", "/api/toolbox/season")

    def access(self) -> Dict[str, Any]:
        """本人当季资格摘要（需登录）。"""
        return self._request("GET", "/api/toolbox/access", auth=True)

    def new_challenge(self) -> Dict[str, Any]:
        """获取个人当季谜题（**不含答案** —— 答案由用户自己解出来）。"""
        return self._request("POST", "/api/toolbox/puzzle/challenges", auth=True)

    def solve(self, challenge_id: str, answer: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/toolbox/puzzle/solve",
            body={"challenge_id": challenge_id, "answer": answer},
            auth=True,
        )

    def afdian_status(self) -> Dict[str, Any]:
        return self._request("GET", "/api/integrations/afdian/status", auth=True)

    def afdian_refresh(self) -> Dict[str, Any]:
        """刷新订阅状态：服务端重新拉取该赞助者全部订单并自动核验（幂等）。

        2026-10-30 起站点语义：绑定后订单自动核验，之后每月续费也只需点一次
        本接口（服务端按赞助者全量扫描，无需传订单号）。
        """
        return self._request("POST", "/api/integrations/afdian/refresh", auth=True)

    def verify_order(self, order_no: str) -> Dict[str, Any]:
        """核验赞助订单（服务端主动查询官方 API，客户端只给订单号）。"""
        return self._request(
            "POST", "/api/toolbox/afdian/verify-order", body={"order_no": order_no}, auth=True
        )

    def catalog(self) -> Dict[str, Any]:
        """当前季可获取的底座与插件目录。

        2026-10-30 起站点名单对游客可见：条目带 ``access_kind``（原创/转载）、
        ``downloadable`` 与 ``files``；未登录时服务端返回未下载态名单，
        ``downloadable`` 一律为 False。
        """
        return self._request("GET", "/api/toolbox/catalog", auth=True)

    # -- 启动鉴权：设备授权（TPM，2026-10-27）---------------------------------

    def list_devices(self) -> Dict[str, Any]:
        """本人已授权设备（最多 2 台）。"""
        return self._request("GET", "/api/toolbox/authz/devices", auth=True)

    def register_device(self, device_id: str, public_key_b64: str,
                        display_name: str = "",
                        machine_hint: Optional[str] = None) -> Dict[str, Any]:
        """注册本机为授权设备。

        ``public_key_b64`` 是 TPM 内不可导出私钥对应的**公钥**（DER 的 base64）。
        私钥永不出芯片。
        """
        body: Dict[str, Any] = {
            "device_id": device_id,
            "public_key": public_key_b64,
            "display_name": display_name or "",
        }
        if machine_hint:
            body["machine_hint"] = machine_hint
        return self._request("POST", "/api/toolbox/authz/devices", body=body, auth=True)

    def revoke_device(self, device_id: str) -> Dict[str, Any]:
        """撤销某台设备。"""
        return self._request(
            "DELETE",
            f"/api/toolbox/authz/devices/{urllib.parse.quote(str(device_id), safe='')}",
            auth=True,
        )

    def authz_public_key(self) -> Dict[str, Any]:
        """票据验签公钥（部署时内嵌进 doorstop）。"""
        return self._request("GET", "/api/toolbox/authz/public-key")

    def enable_device(self, display_name: str = "") -> Dict[str, Any]:
        """**一键启用本机**：生成/复用 TPM 密钥 → 注册设备 → 写本地凭据。

        这是用户在工具箱里点的那个按钮。成功后 Zylarnex 可脱离启动器自行运行。
        """
        from . import authz_tpm

        if not authz_tpm.tpm_available():
            raise ApiError("tpm_unavailable", "本机没有可用的 TPM，无法启用订阅工具")

        key_name = authz_tpm.DEFAULT_KEY_NAME
        public_key_b64 = authz_tpm.export_public_key_der(key_name)

        existing = authz_tpm.load_device()
        device_id = existing.get("device_id") if existing else None
        if not device_id:
            device_id = authz_tpm.new_device_id()

        result = self.register_device(device_id, public_key_b64, display_name)
        authz_tpm.save_device(device_id, api_base=self.base_url, key_name=key_name)
        return result

    def disable_device(self) -> Dict[str, Any]:
        """撤销本机设备并清除本地凭据。"""
        from . import authz_tpm

        existing = authz_tpm.load_device()
        if existing and existing.get("device_id"):
            try:
                self.revoke_device(existing["device_id"])
            except ApiError:
                logger.warning("撤销设备失败（继续清理本地）", exc_info=True)
        authz_tpm.clear_device()
        return {"ok": True}

    def manifest(self, tool_id: int, release_id: str) -> Dict[str, Any]:
        """签名安装清单。"""
        return self._request(
            "GET",
            f"/api/toolbox/tools/{int(tool_id)}/releases/{urllib.parse.quote(str(release_id))}/manifest",
            auth=True,
        )

    def download_ticket(
        self, tool_id: int, release_id: str, file_name: str, sha256: str
    ) -> Dict[str, Any]:
        """签发短期下载票据。

        ``file_name`` 与 ``sha256`` 必须与发布清单一致：
        服务端会校验它们确实属于该版本，因此「拿到 A 的授权去下 B」不可行。
        """
        query = urllib.parse.urlencode({"file_name": file_name, "sha256": sha256})
        return self._request(
            "POST",
            f"/api/toolbox/tools/{int(tool_id)}/releases/{urllib.parse.quote(str(release_id))}/ticket?{query}",
            auth=True,
        )

    # -- HTTP ---------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        auth: bool = False,
        allow_fail: bool = False,
        _retried: bool = False,
    ) -> Dict[str, Any]:
        url = self.base_url + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        # 必须显式带 User-Agent：urllib 默认的 Python-urllib/x.y 会被站点
        # Cloudflare WAF 判定为脚本签名并 403（error 1010）。见 constants.py。
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if auth:
            token = self.access_token
            if token:
                headers["Authorization"] = f"Bearer {token}"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            payload = self._safe_json(exc)
            detail = (payload or {}).get("detail")
            code, message = _detail_message(detail, f"请求失败（HTTP {exc.code}）")

            if exc.code == 401 and auth and not _retried and self.refresh_token:
                # 单飞刷新：并发 401 各自刷新会被服务端判为重放并撤销会话
                if self._refresh_once():
                    return self._request(
                        method, path, body=body, auth=auth, allow_fail=allow_fail, _retried=True
                    )
                raise AuthRequiredError(code, "登录已失效，请重新登录", exc.code) from exc

            if allow_fail:
                return {"ok": False, "code": code, "message": message}
            if exc.code == 401:
                raise AuthRequiredError(code, message or "请先登录", exc.code) from exc
            raise ApiError(code, message, exc.code) from exc
        except urllib.error.URLError as exc:
            raise ApiError("network_error", "无法连接资源站，请检查网络或稍后重试") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError("bad_response", "资源站返回内容无法解析") from exc

    def _refresh_once(self) -> bool:
        """用 refresh token 换新令牌；全局只允许一个刷新在飞。"""
        with self._refresh_lock:
            refresh = self.refresh_token
            if not refresh:
                return False
            try:
                data = self._request(
                    "POST", "/api/auth/client/refresh", body={"refresh_token": refresh}
                )
            except ApiError:
                self._store.clear()
                return False
            if not data.get("access_token"):
                return False
            self.save_auth(data)
            return True

    @staticmethod
    def _safe_json(exc: urllib.error.HTTPError) -> Optional[Dict[str, Any]]:
        try:
            raw = exc.read()
            return json.loads(raw.decode("utf-8")) if raw else None
        except Exception:  # noqa: BLE001
            return None