# -*- coding: utf-8 -*-
"""Mod 镜像站集成：aria2c 下载 + 校验 + 自动安装。

镜像站（默认 https://mods.lcta.top，国内友好 CDN）以独立 pywebview 窗口嵌入，
详情页下载请求经 pywebview 桥（webui/mod_mirror_api.py）到达本模块：
- kind=standard：aria2c 下载标准版包到 staging → size/sha256 校验 → 安全解压安装到 mod 目录
  （launcher 启动时 rglob 递归应用，下次启动游戏生效）。
- kind=file    ：aria2c 下载普通文件到系统「下载」目录（不安装）。

下载器优先随包 aria2c（多连接高速），缺失时降级 requests 流式下载。
登录态持久化（ui_default.mod_mirror.auth）亦由本模块承载。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path

import requests

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager
from globalManagers.exceptions import CancelRunning
from resource_updater.core import Aria2Error, resolve_aria2_binary
from webutils.function_aria2_downloader import Aria2DlClient
from webutils.packages.manage import get_mod_path
from webutils.utils.net import download_with
from webutils.utils.shell import get_downloads_dir

_log_manager = LogManager()

AUTH_KEY = "ui_default.mod_mirror.auth"
CONFIG_KEY = "ui_default.mod_mirror"
DEFAULT_BASE_URL = "https://mods.lcta.top"


# ============================================================
# 配置
# ============================================================

def _mirror_config() -> dict:
    cfg = ConfigManager().get(CONFIG_KEY, {})
    return cfg if isinstance(cfg, dict) else {}


def base_url() -> str:
    return str(_mirror_config().get("base_url") or DEFAULT_BASE_URL).rstrip("/")


def _staging_root() -> Path:
    local = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    root = local / "LCTA" / "mod-mirror"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ============================================================
# 登录态持久化（站点经 pywebview 桥读写）
# ============================================================

def mod_mirror_get_auth() -> dict | None:
    raw = ConfigManager().get(AUTH_KEY, "")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def mod_mirror_save_auth(data: dict | None) -> None:
    if not data:
        ConfigManager().set(AUTH_KEY, "")
    else:
        ConfigManager().set(AUTH_KEY, json.dumps(data, ensure_ascii=False))


# ============================================================
# 通用工具
# ============================================================

_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(name: str, fallback: str = "download") -> str:
    """清洗文件名：替换 Windows 非法字符、压缩空白、截断。"""
    s = _INVALID_FILENAME.sub("_", str(name or ""))
    s = re.sub(r"\s+", "_", s).strip("._")
    s = s[:120]
    return s or fallback


def _sanitize_member(name: str) -> str:
    """校验 zip 成员名安全性，拒绝路径穿越（与 packages/clean.py 同规则）。"""
    if not isinstance(name, str) or not name:
        raise ValueError(f"压缩包包含无效的文件名: {name!r}")
    name = name.replace("\\", "/")
    if name.startswith("/"):
        raise ValueError(f"压缩包包含绝对路径成员: {name}")
    if ":" in name:
        raise ValueError(f"压缩包包含盘符成员: {name}")
    if ".." in name.split("/"):
        raise ValueError(f"压缩包包含不安全的路径成员: {name}")
    return name


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_expected(path: Path, size: int, sha256: str) -> None:
    if size:
        actual = os.path.getsize(path)
        if actual != size:
            raise ValueError(f"文件大小校验失败: 期望 {size} 字节，实际 {actual} 字节")
    if sha256:
        actual = _sha256(path)
        if actual.lower() != str(sha256).lower():
            raise ValueError(f"SHA256 校验失败: 期望 {sha256}，实际 {actual}")


def _extract_zip_safe(zip_path: Path, dest_dir: Path, modal_id: str) -> None:
    """安全解压：testzip 完整性 + 成员名路径穿越校验 + 逐成员落盘（可取消）。"""
    try:
        z = zipfile.ZipFile(str(zip_path))
    except zipfile.BadZipFile as e:
        raise ValueError(f"压缩包损坏或格式错误: {e}") from e
    with z:
        bad = z.testzip()
        if bad:
            raise ValueError(f"压缩包完整性校验失败（损坏成员: {bad}）")
        dest_resolved = dest_dir.resolve()
        for info in z.infolist():
            _log_manager.check_running(modal_id, log=False)
            name = _sanitize_member(info.filename)
            target = (dest_dir / name).resolve()
            if not str(target).startswith(str(dest_resolved)):
                raise ValueError(f"压缩包包含不安全的路径成员: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


# ============================================================
# 下载（aria2c 优先，降级 requests 流式）
# ============================================================

def _resolve_direct_url(url: str) -> str:
    """站点 API 域（mods.lcta.top）会拦截 aria2c 的 TLS 指纹（403/连接重置），
    但 302 后的 CDN 直链域（dl.mods.lcta.top）不拦。先用 requests 解析 302
    拿到预签名直链再交给 aria2c，保持多连接高速下载。
    无重定向（如后端 proxy 模式直出）或解析失败时原样返回。"""
    try:
        r = requests.get(
            url, timeout=15, stream=True, allow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LCTA"},
        )
        loc = r.headers.get("Location")
        if r.status_code in (301, 302, 303, 307, 308) and loc:
            return requests.compat.urljoin(url, loc)
        return url
    except Exception:
        return url


def _download_aria2(url: str, dest: Path, modal_id: str, expected_size: int) -> bool:
    client: Aria2DlClient | None = None
    try:
        binary = resolve_aria2_binary()
        if binary is None:
            raise Aria2Error("未找到 aria2c")
        url = _resolve_direct_url(url)
        cfg = ConfigManager().get("ui_default.aria2_dl", {}) or {}
        client = Aria2DlClient(
            Path(binary),
            jobs=int(cfg.get("jobs") or 8),
            connection_limit=int(cfg.get("connection_limit") or 16),
        )
        client.start()
        gid = client.add_uri(url, dest.parent, dest.name)
        last_pct = -1
        while True:
            _log_manager.check_running(modal_id, log=False)
            st = client.status(gid)
            status = st.get("status")
            total = int(st.get("totalLength") or 0)
            done = int(st.get("completedLength") or 0)
            if status == "complete":
                _log_manager.log_modal_process("下载完成", modal_id)
                _log_manager.update_modal_progress(85, "下载完成，校验中...", modal_id)
                return True
            if status == "error":
                err = st.get("errorMessage") or st.get("errorCode") or "未知错误"
                _log_manager.log_modal_process(
                    f"aria2c 下载失败（{err}），降级为内置下载器", modal_id)
                return _download_fallback(url, dest, modal_id, expected_size)
            if status == "removed":
                raise CancelRunning()
            if total > 0:
                pct = int(done * 100 / total)
                if pct != last_pct:
                    last_pct = pct
                    speed = int(st.get("downloadSpeed") or 0)
                    _log_manager.update_modal_progress(
                        5 + int(pct * 80 / 100),
                        f"正在下载... {pct}%  速度 {speed / 1024 / 1024:.1f} MB/s",
                        modal_id,
                    )
            time.sleep(0.5)
    except CancelRunning:
        raise
    except Aria2Error as e:
        _log_manager.log_modal_process(f"aria2c 不可用（{e}），降级为内置下载器", modal_id)
        return _download_fallback(url, dest, modal_id, expected_size)
    finally:
        if client is not None:
            try:
                client.stop()
            except Exception:
                pass


def _download_fallback(url: str, dest: Path, modal_id: str, expected_size: int) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    return download_with(
        url, str(dest), size=expected_size,
        modal_id=modal_id, progress_=[5, 85],
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LCTA"},
    )


# ============================================================
# 安装
# ============================================================

def _install_standard(zip_path: Path, mod_name: str, modal_id: str) -> Path:
    mod_root = Path(get_mod_path())
    mod_root.mkdir(parents=True, exist_ok=True)
    target = mod_root / mod_name
    disable = mod_root / f"{mod_name}_disable"
    # 覆盖安装：先移除旧同名目录（含禁用态残留）
    for old in (disable, target):
        if old.exists():
            if old.is_dir():
                shutil.rmtree(old)
            else:
                old.unlink()
    _log_manager.update_modal_progress(92, "解压安装到模组目录...", modal_id)
    _extract_zip_safe(zip_path, target, modal_id)
    return target


# ============================================================
# 主流程
# ============================================================

def mod_mirror_request(payload: dict | None, modal_id: str = "false") -> dict:
    """下载镜像站 Mod 并安装（standard）或下载到「下载」目录（file）。

    payload = {target_type, target_id, kind, file_id?, name, size?, sha256?}
    进度：下载 5-85 → 校验 85-90 → 安装 90-100。
    """
    try:
        payload = payload or {}
        target_type = str(payload.get("target_type") or "nexus")
        target_id = str(payload.get("target_id") or "").strip()
        kind = payload.get("kind") or "standard"
        if not target_id or not target_id.isdigit():
            raise ValueError("无效的 Mod 标识")
        if kind not in ("standard", "file"):
            raise ValueError(f"不支持的下载类型: {kind}")

        fallback_name = f"mod_{target_id}"
        name = _safe_filename(payload.get("name") or fallback_name, fallback_name)
        expected_size = int(payload.get("size") or 0)
        expected_sha = str(payload.get("sha256") or "")

        if kind == "standard":
            save_dir = _staging_root() / f"{target_id}_standard"
            url = f"{base_url()}/api/mods/{target_type}/{target_id}/standard"
        else:
            save_dir = Path(get_downloads_dir())
            file_id = str(payload.get("file_id") or "0")
            url = f"{base_url()}/api/mods/{target_type}/{target_id}/download?file_id={file_id}"
        save_dir.mkdir(parents=True, exist_ok=True)
        dest = save_dir / f"{target_id}_{name}.zip"

        _log_manager.log_modal_process(
            f"开始下载：{name}（{'标准版' if kind == 'standard' else '文件'}）", modal_id)
        _log_manager.update_modal_progress(2, "准备下载环境...", modal_id)

        # 清理上次残留的续传状态，保证从零开始
        for leftover in (dest.with_name(dest.name + ".aria2"), dest):
            try:
                if leftover.exists():
                    leftover.unlink()
            except OSError:
                pass

        if not _download_aria2(url, dest, modal_id, expected_size):
            raise ValueError("下载失败")

        _log_manager.update_modal_progress(90, "校验文件完整性...", modal_id)
        _verify_expected(dest, expected_size, expected_sha)

        if kind == "standard":
            mod_dir = _install_standard(dest, name, modal_id)
            _log_manager.update_modal_progress(100, "安装完成", modal_id)
            return {
                "success": True,
                "message": "安装完成，下次启动游戏时生效",
                "mod_dir": str(mod_dir),
            }
        _log_manager.update_modal_progress(100, "下载完成", modal_id)
        return {"success": True, "message": "已下载到系统「下载」目录", "save_path": str(dest)}
    except CancelRunning:
        _log_manager.log_modal_process("任务已取消", modal_id)
        return {"success": False, "message": "已取消"}
    except Exception as e:
        _log_manager.log_error(e)
        _log_manager.log_modal_process(f"失败：{e}", modal_id)
        _log_manager.update_modal_progress(0, "失败", modal_id)
        return {"success": False, "message": str(e)}
