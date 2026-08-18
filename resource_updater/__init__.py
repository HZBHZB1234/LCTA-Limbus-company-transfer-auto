"""Limbus Company 官方资源预下载、本地化更新与官服/lethe 资源切换。"""

# 注意：不要在此处导入 server_sync 子模块 —— `python -m resource_updater.server_sync`
# （桌面快捷方式启动脚本）会因 runpy 在包 __init__ 已导入子模块时报 RuntimeWarning。
# 需要 server_sync 符号时请直接 `from resource_updater.server_sync import ...`。

from .core import (
    DownloadCancelled,
    GameInfo,
    ResourceUpdater,
    UpdateError,
    build_game_fingerprint,
)
from .service import run_launcher_resource_update

__all__ = [
    "DownloadCancelled",
    "GameInfo",
    "ResourceUpdater",
    "UpdateError",
    "build_game_fingerprint",
    "run_launcher_resource_update",
]
