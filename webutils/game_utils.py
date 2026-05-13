"""游戏路径工具 —— Steam 注册表查找与路径验证。"""

import winreg
from pathlib import Path
from typing import Optional

from globalManagers.logManager import logManager


def check_game_path(game_path: str) -> bool:
    """验证目录是否包含 LimbusCompany.exe。"""
    return Path(game_path, 'LimbusCompany.exe').exists()


def find_lcb() -> Optional[str]:
    """通过 Steam 注册表查找边狱公司安装路径。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Valve\Steam')
        steam_path, _ = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)

        library_folders = Path(steam_path, 'steamapps', 'libraryfolders.vdf')
        if not library_folders.exists():
            logManager.warn("未找到 Steam 库文件夹配置文件")
            return None

        content = library_folders.read_text(encoding='utf-8')
        applist = [
            line.split('"')[3].replace('\\\\', '\\')
            for line in content.split('\n')
            if 'path' in line
        ]

        for lib_path in applist:
            game_path = Path(lib_path, 'steamapps', 'common', 'Limbus Company')
            if check_game_path(str(game_path)):
                return str(game_path)

        return None
    except Exception as e:
        logManager.info(f"查找游戏路径时出错: {e}")
        return None
