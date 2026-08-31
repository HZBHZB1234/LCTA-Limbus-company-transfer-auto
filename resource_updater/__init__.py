"""Limbus Company 官方资源预下载与本地化更新。"""

# 注意：不要在此包顶层导入会反向依赖 webutils 的模块（如 webutils.process_job），
# 否则独立入口（`python -c "from resource_updater import ..."`）会因循环导入失败
# （详见 core.py 中 ChildProcessJob 的延迟导入说明）。
# 需要符号时请直接 `from resource_updater.<模块> import ...`。

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
