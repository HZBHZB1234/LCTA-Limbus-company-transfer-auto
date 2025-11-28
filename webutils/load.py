import winreg
import json
import os
import zipfile
from shutil import rmtree, copytree,copyfile
import time
import sys

from . import log_manager as log
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
            if check_game_path(game_path):
                return game_path
                
        return None
    except Exception as e:
        log.log(f"查找游戏路径时出错: {str(e)}")
        log.log_error(e)
        return None

def load_config_types():
    """
    加载配置类型定义
    """
    config_types_path = os.path.join(os.path.dirname(__file__), '..', 'config_check.json')
    with open(config_types_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def validate_config_value(value, expected_type):
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

def validate_config(config, config_types=None):
    """
    验证配置对象是否符合类型定义
    
    Args:
        config (dict): 实际配置
        config_types (dict): 配置类型定义，如果为None则自动加载
    
    Returns:
        tuple: (is_valid, errors) 其中is_valid是布尔值，errors是错误列表
    """
    if config_types is None:
        config_types = load_config_types()
    
    errors = []
    
    def _validate_recursive(current_config, current_types, path=""):
        if not isinstance(current_types, dict):
            return
            
        for key, expected_type in current_types.items():
            current_path = f"{path}.{key}" if path else key
            
            # 检查键是否存在
            if key not in current_config:
                errors.append(f"Missing key: {current_path}")
                continue
                
            value = current_config[key]
            
            # 如果期望类型是字典且实际值也是字典，则递归检查
            if isinstance(expected_type, dict) and isinstance(value, dict):
                _validate_recursive(value, expected_type, current_path)
            else:
                # 检查基本类型
                if not validate_config_value(value, expected_type):
                    errors.append(
                        f"Type mismatch for key '{current_path}': "
                        f"expected {expected_type}, got {type(value).__name__} "
                        f"(value: {value})"
                    )
    
    _validate_recursive(config, config_types)
    return len(errors) == 0, errors

def check_config_type(key_path, value):
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

def load_config():
    try:
        with open('config.json','r',encoding='utf-8') as f:
            config = json.load(f)
            return config
    except FileNotFoundError:
        return None

def check_game_path(game_path):
    return os.path.exists(game_path + 'LimbusCompany.exe')