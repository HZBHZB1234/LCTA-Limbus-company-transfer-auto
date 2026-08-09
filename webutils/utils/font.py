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
    """获取缓存中的中文字体路径。"""
    game_path = ConfigManager().get('game_path', '')
    cache_normal = os.path.join(game_path, 'LimbusCompany_Data', 'lang', 'LLC_zh-CN', 'Font', 'Context', 'ChineseFont.ttf')
    if ConfigManager().get('enable_cache', False):
        cache_path = Path(ConfigManager().get('cache_path', '')) / 'ChineseFont.ttf'
        if cache_path.exists():
            return str(cache_path)
        else:
            cache_path = Path(cache_normal)
            if cache_path.exists():
                return str(cache_path)
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    from ..function_llc import font_assets_seven
                    download_with_github(
                        font_assets_seven, Path(temp_dir) / 'font.7z',
                        chunk_size=1024 * 100
                    )
                    r = decompress_7z(Path(temp_dir) / 'font.7z',
                                      ConfigManager().get('cache_path', '.'))
                    if r:
                        return get_cache_font()
            except Exception as e:
                _log_manager.log_error(e)
                return cache_normal

    cache_path = Path(cache_normal)
    if cache_path.exists():
        return str(cache_path)
    else:
        return ''
