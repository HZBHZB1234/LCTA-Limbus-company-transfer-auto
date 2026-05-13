"""路径管理器 —— 单例，统一管理项目中所有常用路径。

使用方式:
    from globalManagers.pathManager import pathManager
    config_json = pathManager.config_path  # Path('.../config.json')
    log_dir = pathManager.logs_path        # Path('.../logs')
"""

from __future__ import annotations

import os
from pathlib import Path


class PathManager:
    """单例路径管理器。"""

    def __init__(self):
        self.work_path: Path = Path(os.getcwd())
        self.code_path: Path = Path(__file__).parent.parent
        self.game_path: Path | None = None

    @property
    def config_path(self) -> Path:
        """config.json 完整路径。"""
        return self.work_path / 'config.json'

    @property
    def config_default_path(self) -> Path:
        """config_default.json 完整路径。"""
        return self.code_path / 'config_default.json'

    @property
    def config_check_path(self) -> Path:
        """config_check.json 完整路径。"""
        return self.code_path / 'config_check.json'

    @property
    def logs_path(self) -> Path:
        """日志目录。"""
        return self.work_path / 'logs'

    @property
    def plugins_path(self) -> Path:
        """插件目录。"""
        return self.code_path / 'plugins'

    @property
    def webui_path(self) -> Path:
        """WebUI 目录。"""
        return self.code_path / 'webui'

    @property
    def assets_path(self) -> Path:
        """静态资源目录。"""
        return self.webui_path / 'assets'

    @property
    def translateFunc_path(self) -> Path:
        """翻译引擎目录。"""
        return self.code_path / 'translateFunc'

    @property
    def webutils_path(self) -> Path:
        """Web 工具目录。"""
        return self.code_path / 'webutils'

    @property
    def launcher_path(self) -> Path:
        """启动器目录。"""
        return self.code_path / 'launcher'

    @property
    def webFunc_path(self) -> Path:
        """Web 功能目录。"""
        return self.code_path / 'webFunc'

    @property
    def is_frozen(self) -> bool:
        """是否为 PyInstaller 打包环境。"""
        return os.getenv('is_frozen', 'false').lower() == 'true'

    @property
    def is_debug(self) -> bool:
        """是否为调试模式。"""
        return os.getenv('debug', 'false').lower() == 'true'

    @property
    def app_version(self) -> str:
        """应用版本号。"""
        return os.environ.get('__version__', '0.0.0')

    @property
    def resource_path(self) -> Path:
        """资源文件根路径（兼容 PyInstaller 打包）。"""
        try:
            import sys
            return Path(sys._MEIPASS)
        except Exception:
            return self.code_path

    def resolve(self, relative_path: str | Path) -> Path:
        """将相对路径解析为相对于工作目录的绝对路径。"""
        p = Path(relative_path)
        if p.is_absolute():
            return p
        return self.work_path / p


pathManager = PathManager()
