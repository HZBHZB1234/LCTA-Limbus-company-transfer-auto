"""
路径管理器（单例模式）
统一管理项目内所有路径，消除散乱的 os.getenv('path_') 和 Path(os.getcwd()) 调用
自动处理打包/非打包环境差异
"""

import os
import sys
import threading
import winreg
from pathlib import Path
from typing import Optional, Dict, Any


class PathManager:
    """
    路径管理器单例

    统一管理：
    - 项目根目录（打包/非打包环境自适应）
    - 游戏路径及子路径（lang、Assets等）
    - 缓存、日志、临时目录
    """

    _instance: Optional['PathManager'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'PathManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 确定项目根目录
        self._project_root = self._resolve_project_root()
        self._is_frozen = os.getenv('is_frozen', 'false').lower() == 'true'

    def _resolve_project_root(self) -> Path:
        """解析项目根目录（打包/非打包环境自适应）"""
        # pywebview 打包环境下由环境变量指定
        env_path = os.getenv('path_')
        if env_path:
            return Path(env_path)

        # 从 __main__ 模块推导
        try:
            import __main__
            if hasattr(__main__, '__file__'):
                return Path(__main__.__file__).parent
        except Exception:
            pass

        # 从当前工作目录推导
        return Path(os.getcwd())

    # ========== 基础路径属性 ==========

    @property
    def project_root(self) -> Path:
        """项目根目录"""
        return self._project_root

    @property
    def is_frozen(self) -> bool:
        """是否为打包环境"""
        return self._is_frozen

    @property
    def config_path(self) -> Path:
        """配置文件路径"""
        return self._project_root / "config.json"

    @property
    def log_dir(self) -> Path:
        """日志目录"""
        return self._project_root / "logs"

    @property
    def cache_dir(self) -> Path:
        """缓存目录"""
        from globalManagers import get_config
        cache_path = get_config().get('cache_path', '')
        if cache_path:
            return Path(cache_path)
        return self._project_root / "cache"

    @property
    def tmp_dir(self) -> Path:
        """临时文件目录"""
        return self._project_root / "tmp"

    # ========== 游戏路径 ==========

    @property
    def game_root(self) -> Optional[Path]:
        """游戏根目录"""
        from globalManagers import get_config
        game_path = get_config().get('game_path', '')
        if not game_path:
            return None
        return Path(game_path)

    @property
    def game_lang_dir(self) -> Optional[Path]:
        """游戏语言文件目录 (LimbusCompany_Data/lang)"""
        game = self.game_root
        if not game:
            return None
        return game / "LimbusCompany_Data" / "lang"

    @property
    def game_localize_dir(self) -> Optional[Path]:
        """游戏本地化资源目录 (Assets/Resources_moved/Localize)"""
        game = self.game_root
        if not game:
            return None
        return game / "LimbusCompany_Data" / "Assets" / "Resources_moved" / "Localize"

    @property
    def game_exe_path(self) -> Optional[Path]:
        """游戏可执行文件路径"""
        game = self.game_root
        if not game:
            return None
        return game / "LimbusCompany.exe"

    @property
    def game_config_path(self) -> Optional[Path]:
        """游戏内部配置路径 (lang/config.json)"""
        lang = self.game_lang_dir
        if not lang:
            return None
        return lang / "config.json"

    # ========== 资源路径 ==========

    @property
    def webui_dir(self) -> Path:
        """WebUI 目录"""
        return self._project_root / "webui"

    @property
    def html_path(self) -> Path:
        """主页面 HTML 路径"""
        return self.webui_dir / "index.html"

    @property
    def assets_dir(self) -> Path:
        """前端资源目录"""
        return self.webui_dir / "assets"

    # ========== 工具方法 ==========

    def resolve(self, relative_path: str) -> Path:
        """将相对路径解析为绝对路径"""
        p = Path(relative_path)
        if p.is_absolute():
            return p
        return self._project_root / p

    def locate_game(self) -> Optional[str]:
        """
        自动查找游戏安装路径（通过Steam）
        迁移自 webutils/load.py 的 find_lcb()
        """
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Valve\Steam')
            value, _ = winreg.QueryValueEx(key, 'SteamPath')
            winreg.CloseKey(key)

            library_folders_path = value + '\\steamapps\\libraryfolders.vdf'
            with open(library_folders_path, 'r') as f:
                content = f.read()
                applist = [
                    i.split('\"')[3].replace('\\\\', '\\')
                    for i in content.split('\n') if 'path' in i
                ]

            for lib_path in applist:
                game_path = lib_path + '\\steamapps\\common\\Limbus Company\\'
                if self._check_game_path(game_path):
                    return game_path

            return None
        except Exception:
            return None

    def _check_game_path(self, game_path: str) -> bool:
        """检查游戏目录是否有效（存在 LimbusCompany.exe）"""
        return os.path.exists(game_path + 'LimbusCompany.exe')

    def ensure_dir(self, path: Path) -> Path:
        """确保目录存在，返回路径"""
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_kr_path(self, use_custom: bool = False) -> Optional[Path]:
        """获取韩文原文路径"""
        from globalManagers import get_config
        config = get_config()
        custom_path = config.get('ui_default.translator.kr_path', '')
        if use_custom and custom_path:
            return Path(custom_path)
        localize = self.game_localize_dir
        if not localize:
            return None
        return localize / "kr"

    def get_jp_path(self, use_custom: bool = False) -> Optional[Path]:
        """获取日文原文路径"""
        from globalManagers import get_config
        config = get_config()
        custom_path = config.get('ui_default.translator.jp_path', '')
        if use_custom and custom_path:
            return Path(custom_path)
        localize = self.game_localize_dir
        if not localize:
            return None
        return localize / "jp"

    def get_en_path(self, use_custom: bool = False) -> Optional[Path]:
        """获取英文原文路径"""
        from globalManagers import get_config
        config = get_config()
        custom_path = config.get('ui_default.translator.en_path', '')
        if use_custom and custom_path:
            return Path(custom_path)
        localize = self.game_localize_dir
        if not localize:
            return None
        return localize / "en"

    def get_llc_path(self, use_custom: bool = False) -> Optional[Path]:
        """获取零协汉化路径"""
        from globalManagers import get_config
        config = get_config()
        custom_path = config.get('ui_default.translator.llc_path', '')
        if use_custom and custom_path:
            return Path(custom_path)
        lang = self.game_lang_dir
        if not lang:
            return None
        return lang / "LLC_zh-CN"
