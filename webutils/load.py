import winreg
import json
import os
import zipfile
from shutil import rmtree, copytree,copyfile
import time
import sys

from webutils.log_h import *
def find_lcb():
    """查找游戏安装路径"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Valve\Steam')
        value, value_type = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        
        with open(value + '\\steamapps\\libraryfolders.vdf', 'r') as f:
            game_path_file = f.read()
            applist=[i.split('\"')[3] for i in game_path_file.split('\n') if 'path' in i]
        
        for i in applist:
            game_path = i + '\\steamapps\\common\\Limbus Company\\'
            if os.path.exists(game_path + 'LimbusCompany.exe'):
                return game_path
                
        return None
    except Exception as e:
        log(f"查找游戏路径时出错: {str(e)}")
        log_error(e)
        return None
