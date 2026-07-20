import winreg
import json
import os
import zipfile
from shutil import rmtree, copytree,copyfile
import time
import sys
from typing import Dict, List, Tuple, Union, Any, Optional

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
_log_manager = LogManager()


def find_lcb() -> Optional[str]:
    """查找游戏安装路径"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Valve\Steam')
        value, value_type = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        
        with open(value + '\\steamapps\\libraryfolders.vdf', 'r') as f:
            game_path_file = f.read()
            applist=[i.split('\"')[3].replace('\\\\','\\') for i in game_path_file.split('\n') if 'path' in i]
        
        for i in applist:
            game_path = i + '\\steamapps\\common\\Limbus Company\\'
            if check_game_path(game_path):
                return game_path
                
        return None
    except Exception as e:
        _log_manager.log(f"查找游戏路径时出错: {str(e)}")
        _log_manager.log_error(e)
        return None

def load_config_types() -> Dict[str, Any]:
    """
    加载配置类型定义
    """
    config_types_path = os.getenv('path_') + "\\config_check.json"
    with open(config_types_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def validate_config_value(value: Any, expected_type: Union[str, List[Any]]) -> bool:
    """
    验证单个配置值的类型
    
    Args:
        value: 实际值
        expected_type: 期望的类型字符串 ("str", "int", "bool", "null", "dict")
    
    Returns:
        bool: 类型是否匹配
    """
    if expected_type == "null":
        return value is None
    elif expected_type == "str":
        return isinstance(value, str)
    elif expected_type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    elif expected_type == "bool":
        return isinstance(value, bool)
    elif expected_type == "dict":
        return isinstance(value, dict)
    elif isinstance(expected_type, list):
        return value in expected_type
    return False

def validate_config(config: Dict[str, Any] = None, config_types: Optional[Dict[str, Any]]=None) -> Tuple[bool, List[str]]:
    """验证配置对象是否符合类型定义（委托给 ConfigManager）"""
    return ConfigManager().validate()

def check_config_type(key_path: str, value: Any) -> Tuple[bool, Union[str, Dict[str, Any]], str]:
    """
    检查特定配置项的类型
    
    Args:
        key_path (str): 配置项路径，如 "ui_default.proper.max_length"
        value: 要检查的值
    
    Returns:
        tuple: (is_valid, expected_type, actual_type)
    """
    config_types = load_config_types()
    
    # 根据路径查找期望的类型
    keys = key_path.split('.')
    current = config_types
    
    try:
        for key in keys:
            current = current[key]
        expected_type = current
        is_valid = validate_config_value(value, expected_type)
        return is_valid, expected_type, type(value).__name__
    except KeyError:
        return False, "unknown", type(value).__name__

def load_config() -> Optional[Dict[str, Any]]:
    try:
        return ConfigManager().raw
    except Exception as e:
        _log_manager.log_error(e)
        return None

def load_config_default() -> Optional[Dict[str, Any]]:
    try:
        with open( os.getenv('path_') + '\\config_default.json','r',encoding='utf-8') as f:
            config = json.load(f)
            return config
    except FileNotFoundError:
        return None
    
def check_game_path(game_path: str) -> bool:
    return os.path.exists(game_path + 'LimbusCompany.exe')

def fix_config(config: Dict[str, Any] = None, config_default: Optional[Dict[str, Any]]=None, config_check: Optional[Dict[str, Any]]=None) -> Dict[str, Any]:
    """修复配置文件中的错误（委托给 ConfigManager）"""
    ConfigManager().fix()
    return json.loads(json.dumps(ConfigManager().raw))