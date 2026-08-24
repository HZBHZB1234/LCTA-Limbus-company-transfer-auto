"""Limbus Company 官方资源预下载、本地化更新与官服/lethe 资源切换。"""

# 注意：不要在此处导入 server_sync 子模块 —— 桌面快捷方式启动脚本通过
# `python -c "from resource_updater import server_sync; server_sync.main()"` 运行，
# 若本包 __init__ 已导入 server_sync，会与 `webutils` 反向导入 `resource_updater.core`
# 形成循环依赖而失败（详见 core.py 中 ChildProcessJob 的延迟导入说明）。
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
