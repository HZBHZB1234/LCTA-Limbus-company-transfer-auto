"""下载工具函数。"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import requests

from globalManagers.LogManager import LogManager

if TYPE_CHECKING:
    from webFunc.GithubDownload import ReleaseAsset

_log_manager = LogManager()


# ============================================================
# 下载
# ============================================================

def _iter_with_timeout(chunks, timeout=60):
    """对响应分块迭代加超时保护：单个分块等待超过 timeout 秒视为下载停滞。"""
    deadline = time.time() + timeout
    for chunk in chunks:
        if time.time() > deadline:
            raise TimeoutError(f"下载数据超时（超过 {timeout} 秒未收到数据）")
        deadline = time.time() + timeout
        yield chunk


def download_with(url, save_path, size=0, chunk_size=1024 * 100,
                  modal_id=None, progress_=[0, 100], headers={}, validate=True):
    """从指定 URL 下载文件，支持进度回调。

    verify 固定开启 TLS 证书验证；validate 仅控制下载后的大小校验，两者互不影响。
    """
    try:
        with requests.get(url, stream=True, headers=headers,
                          timeout=(10, 60), verify=True) as r:
            r.raise_for_status()

            if size == 0:
                total_size = int(r.headers.get('Content-Length', 0))
            else:
                total_size = size
            chunk_len = total_size // chunk_size + 1
            downloaded_chunk = 0

            _log_manager.log(f"开始下载文件，总大小: {total_size // 1024} KB")

            with open(save_path, 'wb') as f:
                for chunk in _iter_with_timeout(r.iter_content(chunk_size=chunk_size)):
                    if modal_id:
                        _log_manager.check_running(modal_id, log=False)
                    f.write(chunk)

                    downloaded_chunk += 1
                    _log_manager.update_modal_progress(
                        progress_[0] + (progress_[1] - progress_[0]) * downloaded_chunk / chunk_len,
                        f"已下载 {downloaded_chunk * chunk_size // 1024} KB / {total_size // 1024} KB",
                        modal_id, log=True
                    )

            _log_manager.log("\n下载完成")

        if validate and size > 0:
            actual_size = os.path.getsize(save_path)
            if actual_size != size:
                _log_manager.log(
                    f"文件校验失败: 期望大小 {size} 字节，实际大小 {actual_size} 字节")
                return False
        return True
    except Exception as e:
        _log_manager.log(f"\n下载失败 ({url}): {e}")
        _log_manager.log_error(e)
        return False


def download_with_github(asset: 'ReleaseAsset', save_path, chunk_size=1024 * 100,
                         modal_id=None,
                         progress_=[0, 100], use_proxy=True):
    """下载 ReleaseAsset 中的文件，支持代理轮换重试。"""
    if not asset:
        _log_manager.log("ReleaseAsset 为空，无法下载")
        return False

    # 确保保存目录存在
    save_dir = os.path.dirname(save_path)
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)

    if not use_proxy or not hasattr(asset, 'proxys') or not asset.proxys:
        _log_manager.log(f"不使用代理，直接下载: {asset.name}")
        return download_with(
            asset.download_url, save_path,
            size=asset.size, chunk_size=chunk_size,
            modal_id=modal_id,
            progress_=progress_
        )

    proxy_manager = asset.proxys

    def _build_url(proxy_url: str):
        if not proxy_url:
            return asset.download_url
        return proxy_url.rstrip('/') + '/' + asset.download_url.lstrip('/')

    _log_manager.log(f"开始下载 {asset.name} (大小: {asset.size} bytes)")

    len_proxies = len(proxy_manager.proxies)
    for i, proxy in enumerate(proxy_manager.get_proxies()):
        try:
            url = _build_url(proxy)
            _log_manager.log(f"尝试下载 (代理 {i + 1}/{len_proxies}): {url}")

            success = download_with(
                url, save_path,
                size=asset.size, chunk_size=chunk_size,
                modal_id=modal_id,
                progress_=progress_,
                headers={
                    'Accept': 'application/octet-stream',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )

            if success:
                if os.path.exists(save_path):
                    actual_size = os.path.getsize(save_path)
                    if asset.size > 0 and actual_size != asset.size:
                        _log_manager.log(f"警告: 文件大小不匹配。期望: {asset.size}, 实际: {actual_size}")
                        continue

                    _log_manager.log(f"下载成功! 使用链接 {url}")
                    proxy_manager.set_proxy_by_url(proxy)
                    return True
                else:
                    _log_manager.log(f"文件未创建: {save_path}")
                    raise FileNotFoundError(f"文件未创建: {save_path}")
            else:
                _log_manager.log(f"下载失败 (URL {i + 1}/{len_proxies})")

        except Exception as e:
            _log_manager.log(f"下载失败 (URL {i + 1}/{len_proxies}): {e}")
            _log_manager.log_error(e)
            time.sleep(0.1)

    _log_manager.log(f"所有下载尝试都失败: {asset.name}")
    return False
