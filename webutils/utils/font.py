"""字体缓存工具函数。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager

from .net import download_with_github
from .io import decompress_7z

_log_manager = LogManager()


# ============================================================
# 字体缓存
# ============================================================

def save_cache_font(font_path: str) -> str:
    """复制本地字体文件到缓存路径，替换缓存字体 ChineseFont.ttf，返回目标路径。"""
    cache_dir = Path(ConfigManager().get('cache_path', 'tmp'))
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / 'ChineseFont.ttf'
    shutil.copy2(font_path, target)
    if not ConfigManager().get('enable_cache', True):
        _log_manager.log("警告: 资源缓存未启用，上传的字体不会被使用")
    return str(target)


def get_cache_font() -> str:
    """获取缓存中的中文字体路径。

    缓存约定为扁平的 ``cache_path/ChineseFont.ttf``。当缓存缺失且启用缓存时，
    自动下载官方字体包（``LLCCN-Font.7z``，包内为嵌套目录
    ``LimbusCompany_Data/Lang/LLC_zh-CN/Font/Context/ChineseFont.ttf``）并解包，
    将定位到的字体文件落盘为扁平的缓存文件后再返回。
    """
    game_path = ConfigManager().get('game_path', '')
    cache_normal = os.path.join(game_path, 'LimbusCompany_Data', 'lang', 'LLC_zh-CN', 'Font', 'Context', 'ChineseFont.ttf')
    if ConfigManager().get('enable_cache', False):
        cache_font = Path(ConfigManager().get('cache_path', '')) / 'ChineseFont.ttf'
        if cache_font.exists():
            return str(cache_font)
        if Path(cache_normal).exists():
            return str(cache_normal)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                from ..function_llc import font_assets_seven
                font_7z = Path(temp_dir) / 'LLCCN-Font.7z'
                # 解到临时目录（避免把嵌套结构污染进缓存目录），再定位字体文件
                if not download_with_github(
                    font_assets_seven, font_7z, chunk_size=1024 * 100
                ):
                    raise RuntimeError("字体包下载失败")
                if not decompress_7z(font_7z, temp_dir):
                    raise RuntimeError("字体包解压失败")
                # LLCCN-Font.7z 内部为嵌套目录，需在解压结果中查找字体文件
                resolved = None
                for root, _, files in os.walk(temp_dir):
                    for name in files:
                        if name.lower().endswith(('.ttf', '.otf')):
                            resolved = os.path.join(root, name)
                            break
                    if resolved:
                        break
                if not resolved:
                    raise RuntimeError("字体包内未找到字体文件")
                Path(ConfigManager().get('cache_path', '')).mkdir(parents=True, exist_ok=True)
                shutil.copy2(resolved, cache_font)
            return get_cache_font()
        except Exception as e:
            _log_manager.log_error(e)
            return cache_normal

    cache_path = Path(cache_normal)
    if cache_path.exists():
        return str(cache_path)
    else:
        return ''
