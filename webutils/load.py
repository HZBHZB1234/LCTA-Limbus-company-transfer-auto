import winreg
import json
import os
import zipfile
from shutil import rmtree, copytree,copyfile
import time
import sys

from .log_h import LogManager

log:LogManager = None

def set_logger(logger_instance : LogManager):
    """设置全局日志记录器实例"""
    global log
    log = logger_instance
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
    config_types_path = os.getenv('path_') + "\\config_check.json"
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

def load_config_default():
    try:
        with open( os.getenv('path_') + '\\config_default.json','r',encoding='utf-8') as f:
            config = json.load(f)
            return config
    except FileNotFoundError:
        return None
    
def check_game_path(game_path):
    return os.path.exists(game_path + 'LimbusCompany.exe')

def fix_config(config, config_default=None, config_check=None):
    """
    修复配置文件中的错误
    
    Args:
        config (dict): 当前配置
        config_default (dict): 默认配置，如果为None则自动加载
        config_check (dict): 配置类型定义，如果为None则自动加载
    
    Returns:
        dict: 修复后的配置
    """
    if config_default is None:
        config_default = load_config_default()
    
    if config_check is None:
        config_check = load_config_types()
    
    if config_default is None or config_check is None:
        # 如果无法加载默认配置或类型定义，则返回原配置
        log.log("警告: 无法加载默认配置或配置类型定义，跳过配置修复")
        return config
    
    def _fix_recursive(current_config, current_default, current_check, path=""):
        """
        递归修复配置
        """
        if not isinstance(current_check, dict):
            return
        
        for key, expected_type in current_check.items():
            current_path = f"{path}.{key}" if path else key
            
            # 如果键不存在于当前配置中，从默认配置复制
            if key not in current_config:
                if key in current_default:
                    current_config[key] = current_default[key]
                    log.log(f"修复配置: 添加缺失的键 '{current_path}' = {current_default[key]}")
                else:
                    # 默认配置中也没有此键，根据类型设置默认值
                    if expected_type == "null":
                        current_config[key] = None
                    elif expected_type == "str":
                        current_config[key] = ""
                    elif expected_type == "int":
                        current_config[key] = 0
                    elif expected_type == "bool":
                        current_config[key] = False
                    elif expected_type == "dict":
                        current_config[key] = {}
                    elif isinstance(expected_type, list):
                        current_config[key] = expected_type[0] if expected_type else None
                    log.log(f"修复配置: 添加缺失的键 '{current_path}' 并设置默认值")
                continue
                
            value = current_config[key]
            
            # 如果期望类型是字典但实际值是None，则用空字典替换
            if isinstance(expected_type, dict) and value is None:
                current_config[key] = {}
                value = current_config[key]
                log.log(f"修复配置: 将None值的键 '{current_path}' 修正为空字典")
            
            # 如果期望类型是字典且实际值也是字典，则递归检查
            if isinstance(expected_type, dict) and isinstance(value, dict):
                # 确保默认配置也有对应的键
                if key not in current_default or not isinstance(current_default[key], dict):
                    current_default[key] = {}
                _fix_recursive(value, current_default[key], expected_type, current_path)
            else:
                # 检查基本类型
                if not validate_config_value(value, expected_type):
                    # 类型不匹配，尝试从默认配置获取正确的值
                    if key in current_default and validate_config_value(current_default[key], expected_type):
                        current_config[key] = current_default[key]
                        log.log(f"修复配置: 修正键 '{current_path}' 的值为默认值 {current_default[key]}")
                    else:
                        # 默认配置中也没有有效值，根据类型设置默认值
                        if expected_type == "null":
                            current_config[key] = None
                        elif expected_type == "str":
                            current_config[key] = ""
                        elif expected_type == "int":
                            current_config[key] = 0
                        elif expected_type == "bool":
                            current_config[key] = False
                        elif expected_type == "dict":
                            current_config[key] = {}
                        elif isinstance(expected_type, list):
                            current_config[key] = expected_type[0] if expected_type else None
                        log.log(f"修复配置: 重置键 '{current_path}' 为类型相关的默认值")
    
    # 创建配置副本以避免修改原始配置
    fixed_config = json.loads(json.dumps(config))
    _fix_recursive(fixed_config, config_default, config_check)
    return fixed_config