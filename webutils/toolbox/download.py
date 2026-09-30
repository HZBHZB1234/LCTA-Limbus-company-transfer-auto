# -*- coding: utf-8 -*-
"""工具箱下载：票据换取 + 哈希校验 + 暂存。

## 与普通 Mod 下载的区别（plan 10.2）

复用网络能力，但**不复用**普通 Mod 的「永远下 ZIP → 解到 mod 目录」策略：
这里只负责「把已授权的文件下到暂存并校验哈希」，安装由 ``install`` 决定落点。

## 安全要点

1. 下载地址来自**服务端签发的票据**（``download_url``），不接受网页传来的
   任意 URL —— 否则等于开放任意下载/SSRF；
2. 下载完成**必须**校验 SHA256（缓存命中也校验）：
   CDN 缓存污染或中间人都会在这里被拦下；
3. 限制单文件大小，避免磁盘被写满；
4. 缓存按内容哈希命名，manifest 里不含任何凭据。
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 单文件上限：底座包通常几十 MB，1 GiB 足够且能防写满磁盘
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
CHUNK = 1024 * 1024


class DownloadError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def cache_root() -> Path:
    """下载缓存根目录（大文件放 LOCALAPPDATA，不塞游戏目录）。"""
    local = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    root = local / "LCTA" / "toolbox" / "cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def sha256_file(path: os.PathLike | str) -> str:
    h = hashlib.sha256()
    with open(str(path), "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_safe_download_url(url: str) -> bool:
    """只接受 https，且不带凭据。

    服务端票据 URL 形如 ``https://<cdn>/restricted/...?ticket=...``。
    拒绝 http（明文传输票据）与含 userinfo 的 URL。
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    if parsed.username or parsed.password:
        return False
    return bool(parsed.netloc)


def download_verified(
    url: str,
    dest: Path,
    *,
    expected_sha256: str,
    expected_size: Optional[int] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Path:
    """下载到 ``dest`` 并校验 SHA256。

    校验失败时**删除**已下载文件并报错 —— 留下一个哈希不符的文件，
    后续步骤可能误用它。
    """
    if not _is_safe_download_url(url):
        raise DownloadError("INVALID_URL", "下载地址不是可信的 HTTPS 地址")

    dest.parent.mkdir(parents=True, exist_ok=True)
    expected_sha256 = (expected_sha256 or "").lower()
    if not expected_sha256:
        raise DownloadError("HASH_MISSING", "缺少预期哈希，拒绝下载（无法校验完整性）")

    request = urllib.request.Request(url, headers={"Accept": "*/*"})
    fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".part", dir=str(dest.parent))
    os.close(fd)
    tmp = Path(tmp_name)

    total = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            declared = resp.headers.get("Content-Length")
            total_expected = int(declared) if declared and declared.isdigit() else 0
            with open(str(tmp), "wb") as out:
                while True:
                    if should_cancel and should_cancel():
                        raise DownloadError("CANCELLED", "下载已取消")
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise DownloadError(
                            "TOO_LARGE",
                            f"文件超过上限 {MAX_DOWNLOAD_BYTES // 1024 // 1024} MiB",
                        )
                    out.write(chunk)
                    if progress:
                        progress(total, total_expected)
    except urllib.error.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        # 403/401 = 票据无效/过期；404 = 对象不存在或未授权
        code = {
            401: "TICKET_INVALID",
            403: "TICKET_INVALID",
            404: "NOT_FOUND",
        }.get(exc.code, "HTTP_ERROR")
        raise DownloadError(code, f"下载失败（HTTP {exc.code}）") from exc
    except urllib.error.URLError as exc:
        tmp.unlink(missing_ok=True)
        raise DownloadError("NETWORK_ERROR", "下载中断，请检查网络后重试") from exc
    except DownloadError:
        tmp.unlink(missing_ok=True)
        raise
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise DownloadError("IO_ERROR", f"写入失败：{exc}") from exc

    # 校验：缓存命中也必须核对内容（plan 10.3 第 3 条）
    actual = sha256_file(tmp)
    if actual != expected_sha256:
        tmp.unlink(missing_ok=True)
        raise DownloadError(
            "HASH_MISMATCH",
            f"下载内容哈希不符（期望 {expected_sha256[:12]}…，实际 {actual[:12]}…），已丢弃",
        )
    if expected_size is not None and total != int(expected_size):
        tmp.unlink(missing_ok=True)
        raise DownloadError(
            "SIZE_MISMATCH", f"文件大小不符（期望 {expected_size}，实际 {total}）"
        )

    os.replace(str(tmp), str(dest))
    return dest


def cached_path(sha256: str) -> Path:
    """按内容哈希定位缓存文件。"""
    h = (sha256 or "").lower()
    return cache_root() / h[:2] / h


def fetch_or_reuse(
    url: str,
    sha256: str,
    *,
    expected_size: Optional[int] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Path:
    """优先复用缓存（**仍校验哈希**），否则下载。

    缓存文件被改过（用户手改/杀毒改动）时会重新下载，
    而不是盲信旧的「已缓存」标记。
    """
    target = cached_path(sha256)
    if target.exists():
        if sha256_file(target) == (sha256 or "").lower():
            logger.debug("缓存命中且哈希一致：%s", target)
            return target
        logger.warning("缓存文件哈希不符，丢弃并重新下载：%s", target)
        target.unlink(missing_ok=True)

    return download_verified(
        url,
        target,
        expected_sha256=sha256,
        expected_size=expected_size,
        progress=progress,
        should_cancel=should_cancel,
    )


def clear_cache(keep_sha256: Optional[set] = None) -> int:
    """清理缓存；``keep_sha256`` 中的哈希保留（如仍安装的版本）。"""
    root = cache_root()
    removed = 0
    keep = {s.lower() for s in (keep_sha256 or set())}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.lower() in keep:
            continue
        try:
            p.unlink()
            removed += 1
        except OSError:
            logger.debug("删除缓存文件失败：%s", p, exc_info=True)
    return removed


def verify_manifest_hash(manifest: dict, file_name: str) -> Optional[str]:
    """从签名清单里取某个文件的声明哈希。

    取不到就返回 None —— 调用方必须拒绝下载，不能「猜一个哈希」。
    """
    for entry in manifest.get("files") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        if Path(path.replace("\\", "/")).name == Path(str(file_name)).name:
            sha = str(entry.get("sha256") or "").lower()
            if len(sha) == 64:
                return sha
    return None