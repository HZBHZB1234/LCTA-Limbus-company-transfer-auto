# -*- coding: utf-8 -*-
"""订阅工具桥：状态查询 / 登录 / 安装管理（原「工具箱」，2026-10-30 更名）。

## 一键安装契约（2026-10-30，manifest-driven）

订阅工具（季目录内已发布版本）**必须**提供签名安装清单 —— 站点 publish
强制签名（`manifest_unsigned` 拒绝发布），因此客户端只信清单：

- 无签名 / 验签失败 / 清单无文件 / 未知 ``install_kind`` → **一律拒绝安装**；
- 安装过程完全清单驱动：逐文件取短期票据下载并校验 sha256（不接受网页传
  URL/路径），再按 ``install_kind`` 分发 —— ``bepinex_plugin_dll`` 走
  ``install_plugin``（事务 journal/备份/启停保持），``runtime_zip_root`` 走
  ``install_runtime``，``game_relative_files`` 走 ``install_package``
  （逐文件写入清单声明的 ``target_dir``），``game_relative_zip`` 走
  ``install_package_zip``（**客户端解压**：清单只给一个 .zip，下载校验后
  解压到同一 ``target_dir``，落盘路径与逐文件包共享 ``_apply_package``）；
- 本地管理（列出/启停/卸载/回滚/完整性）**不需要**在线资格：过季后用户
  仍必须能停用与卸载，只有「新下载/安装」需要在线资格。

## 状态查询拆两段（2026-11-01 重构）

旧版 `toolbox_status` 一次串行抓 season/access/catalog/afdian，单请求超时
20s，首屏最坏要等 60–80 秒。现在拆成：

- ``toolbox_status_local()``：纯本地快照（毫秒级，断网可用）；
- ``toolbox_status_online()``：在线分片，逐片上报 ``errors``；
- ``toolbox_status()``：两者组合，保留旧字段以兼容既有调用方与镜像站桥。

⚠️ 在线分片的**顺序**是契约：``access`` 必须在 ``catalog`` 之前调用。
服务端 ``/toolbox/catalog`` 用 ``get_optional_user``（过期 token 降级为游客
视图，``downloadable`` 全 False 且不触发刷新），而 ``/toolbox/access`` 用
``get_current_user``（401 会触发单飞刷新）。顺序反了会出现「已登录却整页
显示需要订阅」的假象。

## 安全边界（plan 12.3）

- JS **只**传 ``tool_id`` / ``release_id`` / ``action`` 与用户确认信息；
  **不接受**任意 URL、磁盘目标或脚本 —— 描述符、清单、票据一律由 Python
  自己从可信 API 获取；
- 即使网页被改成直接调用 ``toolbox_install``，也必须经过本层的权限、
  签名、哈希与路径校验；
- ``game_root`` 只接受**用户已配置的**游戏路径，不由 JS 指定任意目录；
- ``toolbox_open_site`` 只接受**固定白名单**的站点路径，不接受任意 URL。
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from globalManagers.ConfigManager import ConfigManager

logger = logging.getLogger(__name__)

CONFIG_KEY = "ui_default.toolbox"
# 桥协议版本（2026-11-02：4）
# 4 = 支持清单 v2（version_sort / min_client_protocol / main_dll）、
#     依赖门禁与缺口上报、底座卸载/回滚、启动器更新报告。
# 服务端 min_client_protocol 会与本值比较，低于要求的版本必须拒绝安装。
BRIDGE_PROTOCOL_VERSION = 4
# 本客户端能解析的最高清单 schema（未知更高版本一律拒绝，避免误装）
SUPPORTED_MANIFEST_SCHEMA = 2

# 在线快照的短缓存：同一轮刷新里 status 与 catalog 都取时避免重复打服务端。
ONLINE_CACHE_TTL = 5.0

# 允许经系统浏览器打开的站点页面（**白名单**，不是任意 URL 拼接）
SITE_PATHS = frozenset({
    "/",
    "/login",
    "/register",
    "/forgot-password",
    "/toolbox",
    "/me",
})

# 官方资源站签名清单公钥（公开信息，非密钥）。写入代码而不是只放
# config_default.json：已有用户的 config.json 不会自动合并新增默认项，
# 仅靠默认文件会让老用户安装时因「缺公钥」被 fail-closed 拒绝。
DEFAULT_MANIFEST_PUBLIC_KEY = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MCowBQYDK2VwAyEAwR/+IVWZvbqixhs8A+y+QCzEQzKf4bsxz8UKdL1imIk=\n"
    "-----END PUBLIC KEY-----"
)

# 一键安装契约（站点 install_kind 白名单，与站点 services/tool_releases.py 同源）
INSTALL_KIND_PLUGIN = "bepinex_plugin_dll"
INSTALL_KIND_RUNTIME = "runtime_zip_root"
INSTALL_KIND_PACKAGE = "game_relative_files"
INSTALL_KIND_PACKAGE_ZIP = "game_relative_zip"
INSTALL_KIND_DOWNLOAD = "download_only"
INSTALL_KINDS = frozenset({
    INSTALL_KIND_PLUGIN,
    INSTALL_KIND_RUNTIME,
    INSTALL_KIND_PACKAGE,
    INSTALL_KIND_PACKAGE_ZIP,
    INSTALL_KIND_DOWNLOAD,
})
# 需要 target_dir 的安装类型（写进游戏目录内某个相对目录）
TARGET_DIR_KINDS = frozenset({INSTALL_KIND_PACKAGE, INSTALL_KIND_PACKAGE_ZIP})

# 同一时刻只允许一个安装/更新任务（并发安装会互相覆盖文件）
_task_lock = threading.Lock()


def _now_iso() -> str:
    """UTC ISO 时间戳（与本地 manifest 的时间口径一致）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_bool(value) -> bool:
    """JS 布尔值宽容解析（pywebview 偶尔把 ``"false"`` 当字符串传过来）。"""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


# 「本机密钥已被其他账号占用」的识别词（2026-11-05）。
# 服务端 code 没有稳定契约（不同版本可能是 device_conflict / already_exists /
# in_use…），只按 code 分支必然漏判，所以同时看 code 片段与中文文案。
_DEVICE_CONFLICT_CODE_PARTS = ("conflict", "already", "in_use", "occupied", "bound")
_DEVICE_CONFLICT_MESSAGE_HINTS = (
    "取消授权", "另一账号", "另一个账号", "其它账号", "其他账号",
    "已被授权", "已被绑定", "已绑定", "已被占用", "密钥冲突",
)


def _is_device_conflict(exc: BaseException) -> bool:
    """注册设备失败是否属于「本机密钥属于另一个账号」。"""
    code = str(getattr(exc, "code", "") or "").lower()
    if any(part in code for part in _DEVICE_CONFLICT_CODE_PARTS):
        return True
    message = str(getattr(exc, "message", "") or exc or "")
    return any(hint in message for hint in _DEVICE_CONFLICT_MESSAGE_HINTS)


def _login_identity(online: dict) -> str:
    """在线快照的「登录身份」指纹，用来识别登录态**迁移**（换账号/登出/失效）。

    只在身份变化时推送刷新事件（见 ``ToolboxMixin._toolbox_notify_auth_changed``）：
    定时查询每次返回同样的身份值不会误触发；一旦变了，主窗口页面就必须立刻
    重拉，否则会停在「已经登录/已经登出，页面还显示旧状态」。
    """
    if online.get("session_expired"):
        return "expired"
    if not online.get("logged_in"):
        return "guest"
    user = online.get("user") or {}
    ident = user.get("id") or user.get("username") or user.get("email") or ""
    return f"user:{ident}"


class ToolboxBridgeError(RuntimeError):
    """带机器可读 ``code`` 的桥接层错误。

    ``message`` 是可直接展示的中文文案（历史文案保持不变：现有测试与用户
    认知都依赖它）；``code`` 供前端分支（重试 / 引导登录 / 打开设置）。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _error_payload(exc: BaseException) -> dict:
    """把任意异常收敛成 ``{success, code, message, data?}``。

    API 客户端（``ApiError``）与下载层（``DownloadError``）自带 ``code``，
    直接小写沿用；其余异常回落为 ``error``。

    依赖门禁（``DependencyError``）会带结构化缺口（``data``），前端要逐条
    显示"缺哪个工具/什么版本"，所以 ``data`` 一并透出。
    """
    raw = str(getattr(exc, "code", "") or "").strip()
    code = raw.lower().replace(" ", "_") or "error"
    # 登录失效统一成 ``auth_required``：服务端 detail 的 code 五花八门
    # （error / invalid_token / expired），前端按 code 分支就永远匹配不上，
    # 用户只在诊断里看到一行小字。``auth`` 标记来自 api.AuthRequiredError。
    if getattr(exc, "auth", False):
        code = "auth_required"
    message = str(getattr(exc, "message", "") or exc or "未知错误")
    payload = {"success": False, "code": code, "message": message}
    data = getattr(exc, "data", None)
    if isinstance(data, dict) and data:
        payload["data"] = data
    return payload


class _ToolboxTaskRegistry:
    """安装/下载任务记录（任务坞）。

    安装与下载在桥接层同步执行（JS 侧 await），所以任务记录不是用来「继续
    或取消」任务的，而是让用户切到别的页面、再回到订阅工具页时仍能看到
    刚才发生了什么（前端规范 §7.3：正交状态，不堆一条超长状态机）。
    """

    def __init__(self, limit: int = 5) -> None:
        self._lock = threading.Lock()
        self._seq = 0
        self._limit = limit
        self._current: dict | None = None
        self._history: list[dict] = []

    def start(self, kind: str, tool_id, release_id, label: str) -> dict:
        with self._lock:
            self._seq += 1
            task = {
                "task_id": f"t{self._seq}",
                "kind": str(kind),
                "tool_id": str(tool_id or ""),
                "release_id": str(release_id or ""),
                "label": str(label or ""),
                "status": "running",
                "percent": 0,
                "text": "准备中…",
                "started_at": _now_iso(),
                "finished_at": None,
                "message": None,
            }
            self._current = task
            return dict(task)

    def progress(self, percent, text: str = "") -> None:
        with self._lock:
            if self._current is None:
                return
            try:
                self._current["percent"] = max(0, min(100, int(percent)))
            except (TypeError, ValueError):
                pass
            if text:
                self._current["text"] = str(text)

    def finish(self, ok: bool, message: str = "") -> dict | None:
        with self._lock:
            task = self._current
            if task is None:
                return None
            task["status"] = "done" if ok else "failed"
            if ok:
                task["percent"] = 100
            if message:
                task["text"] = str(message)
                task["message"] = str(message)
            task["finished_at"] = _now_iso()
            self._history.append(task)
            if len(self._history) > self._limit:
                self._history = self._history[-self._limit:]
            self._current = None
            return dict(task)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self._current is not None,
                "current": dict(self._current) if self._current else None,
                "history": [dict(t) for t in self._history],
            }


class ToolboxMixin:
    """工具箱桥方法集合（由 API 组装处混入）。"""

    # -- 基础 --------------------------------------------------------------

    def _toolbox_api(self):
        from webutils.toolbox import api as toolbox_api

        return toolbox_api.ToolboxApi()

    def _toolbox_game_root(self):
        """用户配置的游戏目录；未配置则报错，**不**猜测。

        与设置页共用 ``game_path`` 这一个键（见 ``webutils/toolbox/config.py``）：
        历史上有两份独立配置，导致「设置里改好了，订阅工具仍说没配置」。
        """
        from webutils.toolbox import config as toolbox_config

        root = toolbox_config.get_game_path()
        if not root:
            raise ToolboxBridgeError(
                "no_game_root",
                "尚未配置游戏目录：请在「设置」页填写 Limbus Company 安装目录"
                "（订阅工具与本软件共用同一份游戏路径）",
            )
        return root

    def _toolbox_task_registry(self) -> _ToolboxTaskRegistry:
        reg = getattr(self, "_toolbox_task_reg", None)
        if reg is None:
            reg = _ToolboxTaskRegistry()
            self._toolbox_task_reg = reg
        return reg

    # -- 登录失效标记 -------------------------------------------------------

    def _toolbox_mark_session_expired(self, expired: bool = True) -> None:
        """记住「登录已失效」直到用户重新登录。

        为什么需要这个标记：``api._refresh_once`` 刷新失败时会**清空本地凭据**
        （DPAPI 存储里的 refresh token 被撤销，留着也没用），于是下一次
        ``is_logged_in()`` 变成 False —— 只靠当次 401 判断的话，失效提示只闪
        一次，之后用户看到的是普通的「未登录」，不知道刚才发生了什么。
        """
        self._toolbox_session_expired = bool(expired)

    def _toolbox_session_was_expired(self) -> bool:
        return bool(getattr(self, "_toolbox_session_expired", False))

    def _toolbox_track_login_identity(self, online: dict) -> None:
        """登录身份变化时通知页面立即刷新（首次观测只记基线，不通知）。

        只认**迁移**：定时刷新/重复查询拿到同一身份不推事件，避免「刷新→查询→
        再刷新」的自激回环。真正变化的三类都在这里覆盖：登录（guest→user）、
        登出（user→guest）、失效（user→expired）。
        """
        ident = _login_identity(online)
        previous = getattr(self, "_toolbox_last_login_identity", None)
        self._toolbox_last_login_identity = ident
        if previous is None or previous == ident:
            return
        self._toolbox_notify_auth_changed(f"{previous}->{ident}")

    def _toolbox_notify_auth_changed(self, reason: str = "") -> None:
        """把「登录态变了」推给主窗口页面，让它**立即**刷新。

        为什么必须有这条通道：登录/登出/镜像站同步登录都可能发生在**别的
        窗口**（Mod 镜像站独立窗口直接调 LCTA_API），主窗口的订阅工具页收不到
        任何通知，只能等用户手动点刷新 —— 表现成「已经登录了，状态条还写着
        未登录」。这里派发 ``lcta-toolbox-auth-changed`` CustomEvent，
        ``toolboxManager.onAuthChanged()`` 收到即强制重拉在线状态。

        只在**状态迁移**时调用（见 ``toolbox_status_online``），否则前端刷新又
        触发状态查询、状态查询又发事件，会形成回环。
        """
        window = getattr(self, "_window", None)
        if window is None:
            return
        import json

        detail = json.dumps({"reason": str(reason or "")}, ensure_ascii=False)
        js = (
            "window.dispatchEvent(new CustomEvent("
            f"'lcta-toolbox-auth-changed', {{detail: {detail}}}));"
        )
        for name in ("evaluate_js", "run_js"):
            fn = getattr(window, name, None)
            if not callable(fn):
                continue
            try:
                fn(js)
                return
            except Exception:  # noqa: BLE001 - 窗口/页面未就绪不应让登录失败
                logger.debug("派发登录态变更事件失败（%s）", name, exc_info=True)

    # -- 状态：本地快照（离线可用）------------------------------------------

    def toolbox_status_local(self):
        """纯本地快照：毫秒级返回，断网/过季都能用。

        只读本地 manifest 与进程列表，**不**访问网络 —— 首屏先渲染这一份，
        在线部分再异步补齐（旧实现是等 4 个网络请求跑完才出第一屏）。
        """
        data = {
            "protocol_version": BRIDGE_PROTOCOL_VERSION,
            "game_root": None,
            "game_running": None,
            "local": None,
            "local_error": None,
            "recovered": None,
            "mirror_auth_available": False,
            # 上次「启动前自动更新」的结果（启动器写盘，这里只读）
            "last_update": None,
        }
        try:
            from webutils.function_mod_mirror import mod_mirror_get_auth

            data["mirror_auth_available"] = bool(mod_mirror_get_auth())
        except Exception:  # noqa: BLE001 — 镜像站不可用不应影响本地状态
            pass

        try:
            from launcher.toolbox_update import read_last_report

            report = read_last_report()
            data["last_update"] = report or None
        except Exception:  # noqa: BLE001 - 启动器模块不可用时不影响本地状态
            pass

        try:
            root = self._toolbox_game_root()
        except Exception as exc:  # noqa: BLE001
            data["local_error"] = str(exc)
            return {"success": True, "data": data}

        data["game_root"] = root

        try:
            from webutils.toolbox import state

            recovered = state.recover_if_needed(root)
            if recovered:
                data["recovered"] = recovered
        except Exception as exc:  # noqa: BLE001
            self.log_error(exc)

        try:
            from webutils.toolbox import runtime

            data["game_running"] = runtime.is_game_running(root)
        except Exception:  # noqa: BLE001
            data["game_running"] = None

        try:
            from webutils.toolbox import install

            data["local"] = install.list_installed(root)
        except Exception as exc:  # noqa: BLE001
            self.log_error(exc)
            data["local_error"] = str(exc)

        return {"success": True, "data": data}

    # -- 状态：在线分片 -----------------------------------------------------

    def toolbox_status_online(self, force=False):
        """在线分片：season / access / catalog / afdian，逐片上报失败。

        任何一片失败都只记进 ``errors[part]``，不影响其它片 —— 断网时用户
        仍然能看到本地状态与上一次的目录（JS 侧保留旧快照）。
        """
        cache = getattr(self, "_toolbox_online_cache", None)
        if not force and cache and (time.monotonic() - cache[0]) < ONLINE_CACHE_TTL:
            return {"success": True, "data": cache[1]}

        data = {
            "protocol_version": BRIDGE_PROTOCOL_VERSION,
            "logged_in": False,
            # 登录态失效（令牌过期/在别处登出/refresh 被撤销）：前端据此**要求**
            # 重新登录，而不是只在诊断里显示一行小字（2026-11-04）
            "session_expired": False,
            "base_url": "",
            "user": None,
            "season": None,
            "access": None,
            "catalog": None,
            "afdian": None,
            "errors": {},
            "generation": None,
            "fetched_at": _now_iso(),
        }
        errors = data["errors"]

        try:
            api = self._toolbox_api()
        except Exception as exc:  # noqa: BLE001
            errors["api"] = _error_payload(exc)
            return {"success": True, "data": data}

        data["base_url"] = getattr(api, "base_url", "") or ""
        try:
            data["logged_in"] = bool(api.is_logged_in())
        except Exception:  # noqa: BLE001
            data["logged_in"] = False

        try:
            data["season"] = api.season()
        except Exception as exc:  # noqa: BLE001
            logger.info("订阅工具：赛季公开信息获取失败 %s", exc)
            errors["season"] = _error_payload(exc)

        # 本地还留着 refresh token ⇒ is_logged_in() 为 True，但服务端已判失效
        # （令牌过期、在别处登出、refresh 被撤销）。这时必须把「已登录」改回
        # False 并置 session_expired，否则状态条仍显示"已登录"，用户以为一切正常。
        session_expired = False
        if data["logged_in"]:
            # ⚠️ access 必须先于 catalog：见模块 docstring 的刷新顺序说明。
            try:
                data["access"] = api.access()
            except Exception as exc:  # noqa: BLE001
                errors["access"] = _error_payload(exc)
                session_expired = errors["access"].get("code") == "auth_required"

        try:
            # 名单公开（2026-10-30）：未登录也能看，逐条 downloadable 决定可否安装
            data["catalog"] = api.catalog()
        except Exception as exc:  # noqa: BLE001
            errors["catalog"] = _error_payload(exc)

        if session_expired:
            data["logged_in"] = False
            data["session_expired"] = True
            data["user"] = None
            self._toolbox_mark_session_expired(True)
        elif data["logged_in"]:
            # 服务端认账了：之前记下的「已失效」应当撤掉
            self._toolbox_mark_session_expired(False)
            try:
                data["user"] = api.current_user()
            except Exception:  # noqa: BLE001
                data["user"] = None
            try:
                data["afdian"] = api.afdian_status()
            except Exception:  # noqa: BLE001
                data["afdian"] = None
        elif self._toolbox_session_was_expired():
            # 凭据已被刷新失败清空（见 _toolbox_mark_session_expired）：
            # 仍要让用户知道「需要重新登录」，而不是无声无息变成未登录。
            data["session_expired"] = True

        access = data["access"] if isinstance(data["access"], dict) else {}
        catalog = data["catalog"] if isinstance(data["catalog"], dict) else {}
        generation = access.get("generation")
        if generation is None:
            generation = catalog.get("generation")
        data["generation"] = generation

        self._toolbox_online_cache = (time.monotonic(), data)
        self._toolbox_track_login_identity(data)
        return {"success": True, "data": data}

    def toolbox_status(self):
        """本地快照 + 在线分片的组合（保留旧字段，兼容既有调用方）。

        旧字段映射：``online``←access、``online_error``←access 错误、
        ``catalog_error``←catalog 错误。新调用方应改用
        ``toolbox_status_local`` / ``toolbox_status_online`` 两段式。
        """
        try:
            local = self.toolbox_status_local()
            data = dict(local.get("data") or {})
            online_res = self.toolbox_status_online()
            online = online_res.get("data") or {}
            errors = online.get("errors") or {}
            data.update({
                "logged_in": online.get("logged_in", False),
                "session_expired": online.get("session_expired", False),
                "base_url": online.get("base_url", ""),
                "season": online.get("season"),
                "online": online.get("access"),
                "catalog": online.get("catalog"),
                "user": online.get("user"),
                "afdian": online.get("afdian"),
                "online_error": (errors.get("access") or {}).get("message"),
                "catalog_error": (errors.get("catalog") or {}).get("message"),
                "errors": errors,
                "generation": online.get("generation"),
                "fetched_at": online.get("fetched_at"),
            })
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    # -- 任务坞 -------------------------------------------------------------

    def toolbox_task_status(self):
        """安装/下载任务快照（切页、重开页面后仍可恢复展示）。"""
        try:
            return {"success": True, "data": self._toolbox_task_registry().snapshot()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    # -- 登录 --------------------------------------------------------------

    def toolbox_login(self, identifier, password):
        """账号密码登录（identifier 含 @ 按邮箱、否则按用户名）。"""
        try:
            api = self._toolbox_api()
            api.login(str(identifier or ""), str(password or ""))
            self.log_ui("订阅工具：已登录资源站")
            self._toolbox_online_cache = None
            self._toolbox_mark_session_expired(False)
            # 登录态变了：立即让页面重拉（含「别的窗口登录、本页未知」的情形）
            self._toolbox_last_login_identity = None
            self._toolbox_notify_auth_changed("login")
            return {"success": True, "message": "登录成功"}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_logout(self):
        try:
            self._toolbox_api().logout()
            self.log_ui("订阅工具：已登出（服务端会话已撤销）")
            self._toolbox_online_cache = None
            # 主动登出不是「失效」：不该再显示「请重新登录」
            self._toolbox_mark_session_expired(False)
            self._toolbox_last_login_identity = None
            self._toolbox_notify_auth_changed("logout")
            return {"success": True}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_current_user(self):
        try:
            return {"success": True, "data": self._toolbox_api().current_user()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    # -- 站点跳转（注册 / 找回密码走系统浏览器）-----------------------------

    def toolbox_open_site(self, path="/"):
        """用系统浏览器打开资源站页面（只接受白名单路径）。

        注册与找回密码**不在客户端内嵌**（2026-11-01 决策）：它们涉及邮件
        往返，交给站点页面更直接。``redirect_uri`` 与域名都来自本地配置，
        不接受调用方传入主机 —— 与「JS 不传 URL」的边界一致。
        """
        try:
            target = str(path or "/").strip() or "/"
            if target not in SITE_PATHS:
                return {
                    "success": False,
                    "code": "invalid_target",
                    "message": "只支持打开资源站的内置页面",
                }
            base = str(getattr(self._toolbox_api(), "base_url", "") or "").rstrip("/")
            if not base.startswith(("https://", "http://")):
                return {
                    "success": False,
                    "code": "invalid_target",
                    "message": "资源站地址无效，请检查配置",
                }
            url = base + ("" if target == "/" else target)
            import webbrowser

            webbrowser.open(url)
            return {"success": True, "data": {"url": url}}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    # -- 解锁（赛季资格）---------------------------------------------------

    def toolbox_season(self):
        """当前赛季公开信息（无需登录）。"""
        try:
            return {"success": True, "data": self._toolbox_api().season()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_new_challenge(self):
        """获取个人当季谜题（响应**不含答案**，需用户自己解出）。"""
        try:
            return {"success": True, "data": self._toolbox_api().new_challenge()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_solve(self, challenge_id, answer):
        try:
            data = self._toolbox_api().solve(str(challenge_id or ""), str(answer or ""))
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_afdian_status(self):
        try:
            return {"success": True, "data": self._toolbox_api().afdian_status()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

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
            return _error_payload(e)

    def toolbox_afdian_refresh(self):
        """刷新订阅状态：服务端重新拉取该赞助者全部订单并自动核验（幂等）。"""
        try:
            data = self._toolbox_api().afdian_refresh()
            self._toolbox_online_cache = None
            self.log_ui(
                "订阅工具：订阅状态已刷新（扫描 {scanned}，核验 {verified}）".format(
                    scanned=data.get("scanned", 0), verified=data.get("verified", 0)
                )
            )
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_verify_order(self, order_no):
        try:
            data = self._toolbox_api().verify_order(str(order_no or ""))
            self._toolbox_online_cache = None
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_catalog(self):
        """当前季可获取内容（游客可浏览；逐条 downloadable 决定可否安装）。"""
        try:
            return {"success": True, "data": self._toolbox_api().catalog()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

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
            return _error_payload(e)

    def toolbox_authz_enable(self, display_name="", overwrite=False):
        """启用本机（生成/复用 TPM 密钥并注册）。

        成功后 Zylarnex 可脱离启动器自行运行：doorstop 原生层会读本地
        凭据换票据，决定是否加载 BepInEx。

        ``overwrite``：覆盖本机密钥。用于「本机密钥已被另一个账号授权」的死局 ——
        密钥名曾经是固定常量，同一台机器上任何账号导出的都是同一个公钥，服务端
        只会认定它属于上一个账号，于是当前账号永远授权不上（报「请先在另一账号
        取消授权」），而那个账号往往已经登录不上。覆盖会删掉旧 TPM 密钥、生成
        新密钥与新 ``device_id``，等于换一个全新设备身份。

        冲突时**不直接失败**，而是回一个 ``code = "device_key_conflict"`` +
        ``data.need_overwrite = True``，让前端弹窗询问是否覆盖 —— 后端不替用户
        做「销毁旧身份」这个不可逆的决定。
        """
        overwrite = _as_bool(overwrite)
        try:
            data = self._toolbox_api().enable_device(str(display_name or ""), overwrite=overwrite)
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            if not overwrite and _is_device_conflict(e):
                self.log_ui("订阅工具：本机密钥已被其他账号授权，等待用户确认是否覆盖")
                return {
                    "success": False,
                    "code": "device_key_conflict",
                    "message": str(getattr(e, "message", "") or e
                                   or "本机密钥已被另一个账号授权"),
                    "data": {"need_overwrite": True, "overwrite_hint": "overwrite"},
                }
            self.log_error(e)
            return _error_payload(e)

    def toolbox_authz_disable(self):
        """撤销本机授权并清除本地凭据。"""
        try:
            return {"success": True, "data": self._toolbox_api().disable_device()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_authz_revoke(self, device_id):
        """撤销指定设备（管理另一台机器时用）。"""
        try:
            return {"success": True,
                    "data": self._toolbox_api().revoke_device(str(device_id or ""))}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    # -- 安装管理 ----------------------------------------------------------

    def toolbox_list_installed(self):
        """列出本地受管状态（离线可用）。"""
        try:
            from webutils.toolbox import install

            return {"success": True, "data": install.list_installed(self._toolbox_game_root())}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_set_enabled(self, tool_id, enabled):
        """启用/停用（本地操作，**不需要**在线资格）。"""
        try:
            from webutils.toolbox import install

            data = install.set_enabled(self._toolbox_game_root(), str(tool_id or ""), bool(enabled))
            self.log_ui(f"订阅工具：{'启用' if enabled else '停用'} {tool_id}")
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_uninstall(self, tool_id, remove_config=False):
        """卸载受管插件/文件包/底座（本地操作，离线可用）。

        ``remove_config``：插件卸载后是否一并清理其 BepInEx 配置（默认保留）。

        ``tool_id`` 传空字符串或 ``"runtime"`` 表示卸载**底座**：底座是插件的
        前置，历史版本只有安装没有卸载入口，装上就回不到裸跑。卸载只动底座
        清单登记过且哈希仍匹配的文件，``BepInEx/plugins`` 里的用户插件保留。
        """
        try:
            from webutils.toolbox import deps, install, state

            root = self._toolbox_game_root()
            tool_id = str(tool_id or "")
            manifest = state.Manifest.load(root)
            # 反向依赖只警告、不阻止（用户已确认的行为）：卸载后依赖方会加载
            # 失败，先把受影响工具列出来，让人有心理准备。
            warnings = [] if tool_id in ("", "runtime") else deps.uninstall_warnings(
                manifest, tool_id
            )
            if tool_id in ("", "runtime"):
                data = install.uninstall_runtime(root)
                self.log_ui("订阅工具：已卸载底座（用户插件保留）")
                return {"success": True, "data": data, "warnings": []}
            if tool_id in manifest.packages:
                data = install.uninstall_package(root, tool_id)
            elif tool_id in manifest.plugins:
                data = install.uninstall_plugin(root, tool_id, remove_config=bool(remove_config))
            else:
                raise ToolboxBridgeError("not_managed", f"{tool_id} 不在本机受管清单内")
            if warnings:
                self.log_ui(f"订阅工具：{'；'.join(warnings)}")
            self.log_ui(f"订阅工具：已卸载 {tool_id}")
            return {"success": True, "data": data, "warnings": warnings}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_rollback(self, tool_id):
        """回滚到本地备份（离线可用）。

        ``tool_id`` 传空字符串或 ``"runtime"`` 表示回滚底座文件。
        """
        try:
            from webutils.toolbox import install, state

            root = self._toolbox_game_root()
            tool_id = str(tool_id or "")
            manifest = state.Manifest.load(root)
            if tool_id in ("", "runtime"):
                data = install.rollback_runtime(root)
                self.log_ui("订阅工具：已还原底座文件到安装前")
                return {"success": True, "data": data}
            if tool_id in manifest.packages:
                data = install.rollback_package(root, tool_id)
            elif tool_id in manifest.plugins:
                data = install.rollback_plugin(root, tool_id)
            else:
                raise ToolboxBridgeError("not_managed", f"{tool_id} 不在本机受管清单内")
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_update_report(self):
        """上次「启动前自动更新」的结果（订阅工具页展示用）。

        自动更新跑在启动器进程（游戏启动前），结果落在
        ``<游戏目录>/.lcta-toolbox/last-update.json`` —— WebUI 只读文件，
        不重复发请求。读不到（没开过启动器/没更新过）返回空对象。
        """
        try:
            from launcher.toolbox_update import read_last_report

            return {"success": True, "data": read_last_report()}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_verify_integrity(self, tool_id):
        try:
            from webutils.toolbox import install, state

            root = self._toolbox_game_root()
            tool_id = str(tool_id or "")
            manifest = state.Manifest.load(root)
            if tool_id in manifest.packages:
                data = install.verify_integrity_package(root, tool_id)
            else:
                data = install.verify_integrity(root, tool_id)
            return {"success": True, "data": data}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_open_folder(self, tool_id=""):
        """在资源管理器中打开受管目录（只打开受管区，不接受任意路径）。"""
        try:
            import os
            import subprocess

            from webutils.toolbox import paths, state

            root = self._toolbox_game_root()
            tool_id = str(tool_id or "")
            if tool_id:
                manifest = state.Manifest.load(root)
                pkg = manifest.packages.get(tool_id)
                if pkg is not None:
                    target = paths.package_dir(root, pkg.target_dir)
                else:
                    target = paths.plugin_dir(root, tool_id)
            else:
                target = paths.toolbox_dir(root)
            target.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                subprocess.Popen(["explorer", str(target)])
            return {"success": True, "data": {"path": str(target)}}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_open_downloads(self):
        """打开系统「下载」目录（仅下载类工具的落点）。"""
        try:
            import os
            import subprocess

            from webutils.utils.shell import get_downloads_dir

            target = get_downloads_dir()
            os.makedirs(target, exist_ok=True)
            if os.name == "nt":
                subprocess.Popen(["explorer", target])
            return {"success": True, "data": {"path": target}}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_sync_mirror_login(self, force=False):
        """把 Mod 镜像站当前保存的登录态同步为 LCTA 订阅工具会话。

        只导入 ``access_token``（30 分钟有效）与用户信息，**不导入 refresh
        token**：镜像站和客户端各自刷新 refresh token 会互相判重放并撤销整个
        会话。客户端已有会话时默认不覆盖；``force=True`` 用于显式点击
        「同步登录」时刷新 access token（保留客户端自己的 refresh token）。
        """
        try:
            import json

            from webutils.function_mod_mirror import mod_mirror_get_auth

            data = mod_mirror_get_auth() or {}
            token = str(data.get("access_token") or "")
            if not token:
                return {"success": False, "code": "not_logged_in", "message": "镜像站尚未登录，无法同步"}
            api = self._toolbox_api()
            if api.is_logged_in() and not force:
                return {"success": True, "data": {"synced": False, "message": "客户端已有登录会话"}}
            user = data.get("user")
            if isinstance(user, str):
                try:
                    user = json.loads(user)
                except (ValueError, TypeError):
                    user = None
            api.save_auth({"access_token": token, "user": user if isinstance(user, dict) else None})
            self._toolbox_online_cache = None
            self._toolbox_mark_session_expired(False)
            self.log_ui("订阅工具：已从 Mod 镜像站同步登录态（仅 access token）")
            # 同步登录发生在**镜像站窗口**里：主窗口订阅工具页必须立刻刷新，
            # 否则用户已经登录了，页面还停在「未登录 + 登录表单」。
            self._toolbox_last_login_identity = None
            self._toolbox_notify_auth_changed("sync-mirror")
            return {"success": True, "data": {"synced": True}}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            return _error_payload(e)

    def toolbox_install(self, tool_id, release_id, confirm_foreign=False, modal_id="false"):
        """一键安装/更新插件、文件包或仅下载（清单驱动，需要下载资格）。"""
        return self._toolbox_install_guarded(
            tool_id, release_id,
            allowed_kinds={INSTALL_KIND_PLUGIN, INSTALL_KIND_PACKAGE, INSTALL_KIND_DOWNLOAD},
            confirm_foreign=confirm_foreign, modal_id=modal_id,
        )

    def toolbox_install_any(self, tool_id, release_id, confirm_foreign=False, modal_id="false"):
        """按签名清单的 ``install_kind`` 自动分发安装（供镜像站/统一入口使用）。"""
        return self._toolbox_install_guarded(
            tool_id, release_id, allowed_kinds=INSTALL_KINDS,
            confirm_foreign=confirm_foreign, modal_id=modal_id,
        )

    def toolbox_install_runtime(self, tool_id, release_id, confirm_foreign=False, modal_id="false"):
        """一键安装/更新订阅工具底座（``runtime_zip_root``，清单驱动）。

        ``confirm_foreign``：检测到非 LCTA 管理的 BepInEx 时必须由用户
        明确确认（网页侧 confirm 对话框），否则拒绝覆盖。
        """
        return self._toolbox_install_guarded(
            tool_id, release_id, allowed_kinds={INSTALL_KIND_RUNTIME},
            confirm_foreign=confirm_foreign, modal_id=modal_id,
        )

    def toolbox_download_file(self, tool_id, release_id, file_name, sha256, modal_id="false"):
        """下载清单内的单个文件到系统「下载」目录（镜像站嵌入模式用）。"""
        if not _task_lock.acquire(blocking=False):
            return {"success": False, "code": "in_progress", "message": "已有下载/安装任务在进行中，请稍候"}
        task = self._toolbox_task_registry().start(
            "download", tool_id, release_id, f"下载文件 {file_name}"
        )
        try:
            from webutils.toolbox import download

            api = self._toolbox_api()
            manifest, _kind, files = self._toolbox_fetch_verified_manifest(api, tool_id, release_id)
            name = str(file_name or "")
            sha = str(sha256 or "").lower()
            meta = next(
                (f for f in files
                 if str(f.get("path") or "") == name
                 and str(f.get("sha256") or "").lower() == sha),
                None,
            )
            if meta is None:
                raise ToolboxBridgeError("file_not_in_manifest", "该文件不在当前版本的签名清单内")
            ticket = api.download_ticket(int(tool_id), str(release_id), name, sha)
            url = ticket.get("download_url")
            if not url:
                raise ToolboxBridgeError("ticket_no_url", "服务端未返回下载地址")
            self._toolbox_progress(modal_id, 10, f"下载 {name}…")
            stub = download.fetch_or_reuse(url, sha, expected_size=meta.get("size"))
            folder = str(manifest.get("tool_dir") or tool_id)
            saved = download.save_to_downloads([(name, stub)], folder)
            self._toolbox_progress(modal_id, 100, "下载完成")
            self._toolbox_task_registry().finish(True, "下载完成")
            return {"success": True, "data": {"save_paths": [str(p) for p in saved]}}
        except Exception as e:  # noqa: BLE001
            self._toolbox_task_registry().finish(False, str(getattr(e, "message", "") or e))
            self.log_error(e)
            return _error_payload(e)
        finally:
            _task_lock.release()

    def _toolbox_install_guarded(self, tool_id, release_id, *, allowed_kinds,
                                 confirm_foreign=False, modal_id="false"):
        if not _task_lock.acquire(blocking=False):
            return {"success": False, "code": "in_progress", "message": "已有安装任务在进行中，请稍候"}
        task = self._toolbox_task_registry().start(
            "install", tool_id, release_id, f"安装 {tool_id}"
        )
        try:
            result = self._toolbox_install_impl(
                tool_id, release_id,
                allowed_kinds=allowed_kinds,
                confirm_foreign=confirm_foreign,
                modal_id=modal_id,
            )
            ok = bool(result.get("success"))
            self._toolbox_task_registry().finish(
                ok, str(result.get("message") or ("安装完成" if ok else "安装失败"))
            )
            return result
        except Exception as e:  # noqa: BLE001
            self._toolbox_task_registry().finish(
                False, str(getattr(e, "message", "") or e)
            )
            self.log_error(e)
            return _error_payload(e)
        finally:
            _task_lock.release()

    def _toolbox_install_impl(self, tool_id, release_id, *, allowed_kinds,
                              confirm_foreign=False, modal_id="false"):
        from webutils.toolbox import install  # noqa: F401 — 保持导入失败可被上层捕获

        api = self._toolbox_api()
        manifest, kind, files = self._toolbox_fetch_verified_manifest(api, tool_id, release_id)
        if kind not in allowed_kinds:
            label = {
                INSTALL_KIND_RUNTIME: "底座",
                INSTALL_KIND_PLUGIN: "插件",
                INSTALL_KIND_PACKAGE: "文件包",
                INSTALL_KIND_PACKAGE_ZIP: "解压包",
                INSTALL_KIND_DOWNLOAD: "仅下载",
            }.get(kind, kind)
            raise ToolboxBridgeError(
                "install_kind_mismatch",
                f"该版本是{label}（install_kind={kind}），请使用对应入口",
            )

        if kind == INSTALL_KIND_DOWNLOAD:
            return self._toolbox_install_download_impl(
                api, tool_id, release_id, manifest, files, modal_id
            )

        root = self._toolbox_game_root()
        # 依赖门禁：写任何文件之前判定（2026-11-02）
        self._toolbox_assert_dependencies(api, root, tool_id)
        if kind == INSTALL_KIND_RUNTIME:
            return self._toolbox_install_runtime_impl(
                api, root, tool_id, release_id, manifest, files, confirm_foreign, modal_id
            )
        if kind == INSTALL_KIND_PACKAGE:
            return self._toolbox_install_package_impl(
                api, root, tool_id, release_id, manifest, files, modal_id
            )
        if kind == INSTALL_KIND_PACKAGE_ZIP:
            return self._toolbox_install_package_zip_impl(
                api, root, tool_id, release_id, manifest, files, modal_id
            )
        return self._toolbox_install_plugin_impl(
            api, root, tool_id, release_id, manifest, files, modal_id
        )

    def _toolbox_catalog_items(self, api):
        """目录条目（优先复用在线快照缓存，避免安装前多打一次站点）。"""
        cache = getattr(self, "_toolbox_online_cache", None)
        if cache and (time.monotonic() - cache[0]) < ONLINE_CACHE_TTL:
            catalog = (cache[1] or {}).get("catalog") or {}
            items = catalog.get("items")
            if isinstance(items, list):
                return items
        try:
            catalog = api.catalog() or {}
        except Exception:  # noqa: BLE001 - 目录不可用不应阻止安装（服务端仍会判权限）
            logger.info("订阅工具：依赖门禁取目录失败，跳过本地预检", exc_info=True)
            return []
        items = catalog.get("items")
        return items if isinstance(items, list) else []

    def _toolbox_assert_dependencies(self, api, root, tool_id):
        """依赖不满足时抛 ``ToolboxBridgeError``（携带结构化缺口）。

        服务端已保证"发布时依赖齐备、无环"，这里再判一次是因为**本地磁盘**
        才决定依赖是否真的可用（没装/版本旧/被停用/换机）。写文件前拦住，
        避免装到一半才发现缺依赖。
        """
        from webutils.toolbox import deps, state

        manifest = state.Manifest.load(root)
        items = self._toolbox_catalog_items(api)
        try:
            return deps.assert_ready(manifest, items, tool_id)
        except deps.DependencyError as exc:
            error = ToolboxBridgeError(exc.code, exc.message)
            error.data = getattr(exc, "data", {}) or {}
            raise error from exc

    def _toolbox_install_plugin_impl(self, api, root, tool_id, release_id, manifest, files, modal_id):
        from webutils.toolbox import install

        stubs = self._toolbox_download_all_files(api, tool_id, release_id, files, modal_id)
        stub = self._toolbox_pack_plugin_stub(stubs, files)
        self._toolbox_progress(modal_id, 90, "安装插件…")
        # 主 DLL 以签名清单为准：多文件工具用 files[0] 猜会让"发布方调顺序"
        # 变成"所有客户端装错文件"。清单没有 main_dll（早期发布）才回退。
        main_dll = str(manifest.get("main_dll") or (files[0].get("path") if files else ""))
        plan = install.InstallPlan(
            kind="plugin",
            release_id=str(release_id),
            version=str(manifest.get("version") or ""),
            version_sort=str(manifest.get("version_sort") or ""),
            dependencies=tuple(manifest.get("dependencies") or ()),
            tool_id=str(tool_id),
            guid=manifest.get("guid"),
            main_dll=main_dll,
            requires_runtime=True,
            stub_path=stub,
        )
        data = install.install_plugin(root, plan)
        self._toolbox_progress(modal_id, 100, "安装完成")
        self.log_ui(f"订阅工具：已安装 {tool_id}/{release_id}（{len(files)} 个文件）")
        return {"success": True, "data": data}

    def _toolbox_install_runtime_impl(self, api, root, tool_id, release_id, manifest, files,
                                      confirm_foreign, modal_id):
        from webutils.toolbox import install

        stubs = self._toolbox_download_all_files(api, tool_id, release_id, files, modal_id)
        if len(stubs) != 1:
            raise ToolboxBridgeError("manifest_bad_runtime", "底座清单必须恰好声明一个整包文件")
        self._toolbox_progress(modal_id, 90, "安装底座…")
        plan = install.InstallPlan(
            kind="runtime",
            release_id=str(release_id),
            version=str(manifest.get("version") or ""),
            version_sort=str(manifest.get("version_sort") or ""),
            tool_id=str(tool_id),
            requires_runtime=False,
            stub_path=stubs[0],
        )
        data = install.install_runtime(root, plan, confirm_foreign=bool(confirm_foreign))
        self._toolbox_progress(modal_id, 100, "安装完成")
        self.log_ui(f"订阅工具：已安装底座 {tool_id}/{release_id}")
        return {"success": True, "data": data}

    def _toolbox_install_package_impl(self, api, root, tool_id, release_id, manifest, files, modal_id):
        from webutils.toolbox import install

        target_dir = str(manifest.get("target_dir") or "")
        if not target_dir:
            raise ToolboxBridgeError("manifest_bad_target", "文件包清单缺少 target_dir，拒绝安装")
        stubs = self._toolbox_download_all_files(api, tool_id, release_id, files, modal_id)
        sources = [
            (str(meta.get("path") or ""), stub)
            for meta, stub in zip(files, stubs)
        ]
        self._toolbox_progress(modal_id, 90, f"安装到 {target_dir} …")
        plan = install.InstallPlan(
            kind="package",
            release_id=str(release_id),
            version=str(manifest.get("version") or ""),
            version_sort=str(manifest.get("version_sort") or ""),
            dependencies=tuple(manifest.get("dependencies") or ()),
            tool_id=str(tool_id),
            target_dir=target_dir,
            requires_runtime=bool(manifest.get("requires_runtime", False)),
            file_sources=sources,
        )
        data = install.install_package(root, plan)
        self._toolbox_progress(modal_id, 100, "安装完成")
        self.log_ui(f"订阅工具：已安装文件包 {tool_id}/{release_id} → {target_dir}")
        return {"success": True, "data": data}

    def _toolbox_install_package_zip_impl(self, api, root, tool_id, release_id, manifest, files, modal_id):
        """安装 ``game_relative_zip``：下一个 .zip，客户端解压到 ``target_dir``。

        与 ``_toolbox_install_package_impl`` 的差别只在交付形态 —— 清单恰好一个
        工件，下载校验后交给 ``install.install_package_zip`` 解压 + 事务化落盘。

        **解压后的成员名不由清单决定**，因此这里不做任何"按清单路径匹配"的
        校验：包内布局由 ``archive.extract_zip_safe`` 净化 + ``package_dir``
        收窄，落盘后每个文件的 sha256 由 journal 记录（用于完整性检查/卸载）。
        """
        from webutils.toolbox import install

        target_dir = str(manifest.get("target_dir") or "")
        if not target_dir:
            raise ToolboxBridgeError("manifest_bad_target", "解压包清单缺少 target_dir，拒绝安装")
        if len(files) != 1:
            raise ToolboxBridgeError(
                "manifest_bad_archive",
                f"解压包清单必须恰好声明一个 .zip 工件（当前 {len(files)} 个）",
            )
        if not str(files[0].get("path") or "").lower().endswith(".zip"):
            raise ToolboxBridgeError(
                "manifest_bad_archive",
                f"解压包清单的工件必须是 .zip：{files[0].get('path')}",
            )

        stubs = self._toolbox_download_all_files(api, tool_id, release_id, files, modal_id)
        self._toolbox_progress(modal_id, 85, f"解压并安装到 {target_dir} …")
        plan = install.InstallPlan(
            kind="package_zip",
            release_id=str(release_id),
            version=str(manifest.get("version") or ""),
            version_sort=str(manifest.get("version_sort") or ""),
            dependencies=tuple(manifest.get("dependencies") or ()),
            tool_id=str(tool_id),
            target_dir=target_dir,
            requires_runtime=bool(manifest.get("requires_runtime", False)),
            stub_path=stubs[0],
            archive_prefixes=tuple(manifest.get("archive_prefixes") or ()),
        )
        data = install.install_package_zip(root, plan)
        self._toolbox_progress(modal_id, 100, "安装完成")
        self.log_ui(
            f"订阅工具：已解压安装 {tool_id}/{release_id} → {target_dir}"
            f"（{data.get('files', 0)} 个文件）"
        )
        return {"success": True, "data": data}

    def _toolbox_install_download_impl(self, api, tool_id, release_id, manifest, files, modal_id):
        from webutils.toolbox import download

        stubs = self._toolbox_download_all_files(api, tool_id, release_id, files, modal_id)
        folder = str(manifest.get("tool_dir") or tool_id)
        self._toolbox_progress(modal_id, 90, "复制到下载目录…")
        saved = download.save_to_downloads(
            [(str(meta.get("path") or ""), stub) for meta, stub in zip(files, stubs)],
            folder,
            progress=lambda done, total: self._toolbox_progress(
                modal_id, 90 + int(10 * done / max(total, 1)), "复制到下载目录…"
            ),
        )
        self._toolbox_progress(modal_id, 100, "下载完成")
        self.log_ui(f"订阅工具：已下载 {tool_id}/{release_id} 到系统下载目录")
        return {
            "success": True,
            "data": {
                "kind": "download",
                "folder": folder,
                "save_paths": [str(p) for p in saved],
            },
        }

    # -- 一键安装契约的内部步骤 ---------------------------------------------

    def _toolbox_fetch_verified_manifest(self, api, tool_id, release_id):
        """取回并验签安装清单（契约第 1 步：**只信签名清单**）。"""
        from webutils.toolbox import ed25519

        manifest_out = api.manifest(int(tool_id), str(release_id))
        manifest = manifest_out.get("manifest") or {}
        signature = manifest_out.get("signature")

        if not signature:
            raise ToolboxBridgeError(
                "manifest_unsigned", "该版本没有签名清单，拒绝安装（一键安装契约）"
            )
        pub = self._manifest_public_key()
        if not pub or not ed25519.verify_from_der_public_key(
            pub, self._b64(signature), ed25519.canonical_bytes(manifest)
        ):
            raise ToolboxBridgeError("signature_invalid", "清单签名校验失败，拒绝安装")

        # 版本门禁（2026-11-02）：清单格式与客户端协议都必须够新。
        # 旧客户端遇到带新字段的清单会按老逻辑装错（例如不认 main_dll 的
        # 多文件工具），所以这里 fail-closed，而不是"尽力而为"。
        try:
            schema_version = int(manifest.get("schema_version") or 1)
        except (TypeError, ValueError):
            schema_version = 1
        if schema_version > SUPPORTED_MANIFEST_SCHEMA:
            raise ToolboxBridgeError(
                "client_outdated",
                f"该版本使用了更新的清单格式（schema {schema_version}），"
                f"当前客户端仅支持到 {SUPPORTED_MANIFEST_SCHEMA}；请先更新 LCTA",
            )
        try:
            required_protocol = int(manifest.get("min_client_protocol") or 1)
        except (TypeError, ValueError):
            required_protocol = 1
        if required_protocol > BRIDGE_PROTOCOL_VERSION:
            raise ToolboxBridgeError(
                "client_outdated",
                f"该版本要求客户端协议 {required_protocol}，"
                f"当前为 {BRIDGE_PROTOCOL_VERSION}；请先更新 LCTA",
            )

        kind = str(manifest.get("install_kind") or "")
        if kind not in INSTALL_KINDS:
            raise ToolboxBridgeError(
                "install_kind_unknown",
                f"未知的安装类型（install_kind={kind or '缺失'}），拒绝安装",
            )
        if kind in TARGET_DIR_KINDS:
            target_dir = str(manifest.get("target_dir") or "")
            if not target_dir:
                raise ToolboxBridgeError(
                    "manifest_bad_target", "文件包清单缺少 target_dir，拒绝安装"
                )
        if kind == INSTALL_KIND_PACKAGE_ZIP:
            # 解压型：清单必须恰好一个 .zip（服务端已校验，这里兜住旧站点/手改清单）
            if len(files := (manifest.get("files") or [])) != 1:
                raise ToolboxBridgeError(
                    "manifest_bad_archive",
                    f"解压包清单必须恰好声明一个 .zip 工件（当前 {len(files)} 个），拒绝安装",
                )
            if not str(files[0].get("path") or "").lower().endswith(".zip"):
                raise ToolboxBridgeError(
                    "manifest_bad_archive",
                    f"解压包清单的工件必须是 .zip：{files[0].get('path')}，拒绝安装",
                )
        if kind == INSTALL_KIND_DOWNLOAD and manifest.get("target_dir"):
            raise ToolboxBridgeError(
                "manifest_bad_target", "仅下载清单不应包含 target_dir，拒绝安装"
            )

        files = manifest.get("files") or []
        if not files:
            raise ToolboxBridgeError("manifest_no_files", "清单没有文件，拒绝安装")
        return manifest, kind, files

    def _toolbox_download_all_files(self, api, tool_id, release_id, files, modal_id="false"):
        """逐文件取票据下载并校验 sha256（契约第 2 步：清单外文件不可得）。"""
        from webutils.toolbox import download

        paths = []
        total = max(len(files), 1)
        for idx, f in enumerate(files):
            name = str(f.get("path") or "")
            sha = str(f.get("sha256") or "").lower()
            if not name or len(sha) != 64:
                raise ToolboxBridgeError(
                    "manifest_bad_file", f"清单文件项缺少 path/sha256：{name or '未知'}"
                )
            ticket = api.download_ticket(int(tool_id), str(release_id), name, sha)
            url = ticket.get("download_url")
            if not url:
                raise ToolboxBridgeError("ticket_no_url", f"服务端未返回下载地址：{name}")

            base_pct = 5 + int(80 * idx / total)

            def _on_bytes(done, total_bytes, _idx=idx, _name=name, _base=base_pct):
                if total_bytes:
                    pct = _base + int(80 / total * min(done / total_bytes, 1.0))
                    self._toolbox_progress(modal_id, pct, f"下载 {_name}…")

            self._toolbox_progress(modal_id, base_pct, f"下载 {name}（{idx + 1}/{total}）…")
            paths.append(download.fetch_or_reuse(
                url, sha, expected_size=f.get("size"), progress=_on_bytes
            ))
        return paths

    def _toolbox_progress(self, modal_id, percent, text):
        """更新任务坞与进度模态框；两者失败都只静默。"""
        try:
            self._toolbox_task_registry().progress(percent, text)
        except Exception:  # noqa: BLE001 - 任务记录失败不影响安装
            pass
        try:
            if modal_id and str(modal_id) != "false" and hasattr(self, "update_modal_progress"):
                self.update_modal_progress(percent, text, modal_id)
        except Exception:  # noqa: BLE001 - 进度展示失败不影响安装
            pass

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
        """清单验签公钥：本地配置优先，未配置时使用官方内置公钥。

        内置公钥解决「已有 config.json 不会合并 config_default 新增项」的
        老用户升级问题；两者都没有时才返回 None（调用方仍 fail-closed）。
        """
        cfg = ConfigManager().get(CONFIG_KEY, {}) or {}
        pem = (cfg.get("manifest_public_key") if isinstance(cfg, dict) else "") or ""
        pem = pem or DEFAULT_MANIFEST_PUBLIC_KEY
        return pem.encode("utf-8") if pem else None

    def toolbox_set_game_root(self, path):
        """设置游戏目录（会做校验，拒绝盘符根/不可写/不存在）。

        写入的是**共用**的 ``game_path``（设置页同一个键），订阅工具页不再
        维护第二份 ``ui_default.toolbox.game_root`` —— 两份配置是历史 bug 的
        来源：改一处另一处不生效，而两边都显示"保存成功"。
        """
        try:
            from webutils.toolbox import config as toolbox_config, paths

            resolved = paths.validate_game_root(str(path or ""))
            toolbox_config.set_game_path(str(resolved))
            return {"success": True, "data": {"game_root": str(resolved)}}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            payload = _error_payload(e)
            if payload["code"] == "error":
                payload["code"] = "invalid_game_root"
            return payload

    def toolbox_pick_game_root(self):
        """选择游戏目录（弹系统文件夹选择框），**只**返回校验过的路径。

        不落盘：与设置页的浏览按钮一致，用户点「保存」才写入配置。
        """
        try:
            from webutils.toolbox import paths

            window = getattr(self, "_window", None)
            if window is None:
                return {"success": False, "code": "window_missing", "message": "窗口尚未初始化"}
            import webview

            selected = window.create_file_dialog(webview.FileDialog.FOLDER)
            if not selected:
                return {"success": False, "code": "cancelled", "message": "已取消选择"}
            resolved = paths.validate_game_root(str(selected[0]))
            return {"success": True, "data": {"game_root": str(resolved)}}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            payload = _error_payload(e)
            if payload["code"] == "error":
                payload["code"] = "invalid_game_root"
            return payload

    def toolbox_validate_game_root(self, path):
        """只校验目录是否可用，**不**写入配置（设置页「检查目录」按钮）。

        与 ``toolbox_set_game_root`` 共用 ``paths.validate_game_root``
        这一条判定，避免「检查通过但保存失败」的两套口径。
        """
        try:
            from webutils.toolbox import paths

            resolved = paths.validate_game_root(str(path or ""))
            return {"success": True, "data": {"game_root": str(resolved)}}
        except Exception as e:  # noqa: BLE001
            self.log_error(e)
            payload = _error_payload(e)
            if payload["code"] == "error":
                payload["code"] = "invalid_game_root"
            return payload
