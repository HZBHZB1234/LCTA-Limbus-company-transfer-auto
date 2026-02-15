import shutil
import sys
import os
import subprocess
from pathlib import Path
from typing import Tuple
import json

from .functions import *

def check_lang_enabled(game_path:str) -> bool:
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
    if lang_path.exists():
        return True
    lang_path = Path(game_path) / 'LimbusCompany_Data' / '_lang'
    if not lang_path.exists():
        lang_path.mkdir()
    return False

def find_installed_packages(config) -> Tuple[list, str]:
    game_path = config.get('game_path', '')
    if not game_path:
        raise
    if not check_lang_enabled(game_path):
        return [], ''
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
    r = []
    for folder in lang_path.iterdir():
        if not folder.is_dir():
            continue
        if (folder / 'BattleAnnouncerDlg').exists() and (folder / 'Font').exists():
            r.append(folder.name)
    
    try:
        config_lang = json.loads((lang_path / 'config.json').read_text(encoding='utf-8'))
    except:
        config_lang = {}
    return r, config_lang.get('lang', '')

def use_translation_package(package_name: str, config):
    game_path = config.get('game_path', '')
    if not package_name or not game_path:
        raise
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
    if not (lang_path / package_name).exists():
        raise
    lang_config = lang_path / 'config.json'
    try:
        config_lang = json.loads(lang_config.read_text(encoding='utf-8'))
    except:
        config_lang = {}
    config_lang['lang'] = package_name
    lang_config.write_text(json.dumps(config_lang, indent=4, ensure_ascii=False))
    return True

def delete_installed_package(package_name: str, config):
    game_path = config.get('game_path', '')
    if not package_name or not game_path:
        raise
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
    if not (lang_path / package_name).exists():
        return {'success': False, "message": '当前汉化包不存在'}
    lang_config = lang_path / 'config.json'
    try:
        config_lang = json.loads(lang_config.read_text(encoding='utf-8'))
    except:
        config_lang = {}
    current_lang = config_lang.get('lang', '')
    if current_lang == package_name:
        return {'success': False, "message": '当前汉化包正在使用，无法删除'}
    shutil.rmtree(lang_path / package_name)
    return {'success': True, "message": '已删除'}

def toggle_install_package(config, enable):
    game_path = config.get('game_path', '')
    if not game_path:
        raise
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
    disable_path = Path(game_path) / 'LimbusCompany_Data' / '_lang'
    current = check_lang_enabled(game_path)
    if current == enable:
        return False
    else:
        if enable:
            shutil.move(disable_path, lang_path)
        else:
            shutil.move(lang_path, disable_path)
        return True

def get_default_mod_path():
    return Path.home() / 'AppData' /  'Roaming' / 'LimbusCompanyMods'

def get_mod_path(config):
    mod_path = config.get('ui_default').get('manage', {}).get('mod_path', '')
    if not mod_path:
        mod_path = get_default_mod_path()
    else:
        mod_path = Path(mod_path)
    return mod_path

def fing_mod(config):
    mod_path = get_mod_path(config)
    r = list(mod_path.glob('*.carra2'))
    r.extend(list(mod_path.glob('*.bank')))
    r.extend(list(mod_path.glob('*.lunartique')))
    rd = list(mod_path.glob('*.carra2_disable'))
    rd.extend(list(mod_path.glob('*.bank_disable')))
    rd.extend(list(mod_path.glob('*.lunartique_disable')))
    r = [i.name for i in r]
    rd = [(i.name).rstrip('_disable') for i in rd]
    return r, rd

def toggle_mod(config, mod_name: str, enable):
    mod_path = get_mod_path(config)
    mod = mod_path / (mod_name if not enable else f'{mod_name}_disable')
    if mod.exists():
        shutil.move(mod, mod_path / (mod_name if enable else f'{mod_name}_disable'))
        return True
    else:
        return False
    
def delete_mod(config, mod_name: str, enable):
    mod_path = get_mod_path(config)
    mod = mod_path / (mod_name if enable else f'{mod_name}_disable')
    if mod.exists():
        mod.unlink()
        return True
    else:
        return False

def open_mod_path(config):
    mod_path = get_mod_path(config)
    os.system(f'explorer {mod_path}')
    
LOCAL_BASE = Path.home() / 'AppData' / 'LocalLow'
UNITY = LOCAL_BASE / 'Unity'
PM = LOCAL_BASE / 'ProjectMoon'
    
def check_path(path: Path):
    if not path.exists():
        return {'status': 'not_exist', 'path': str(path)}
    if not path.is_symlink():
        return {'status': 'not_symlink', 'path': str(path)}
    return {'status': 'symlink', 'path': str(path), 'target': str(path.readlink())}
    
def check_symlink():
    return {
        'unity': check_path(UNITY),
        'PM': check_path(PM)
    }
    
def open_explorer(path):
    """打开资源管理器窗口"""
    if os.path.exists(str(path)):
        subprocess.Popen(['explorer', str(path)])
    else:raise

def create_symlink_for(folder: str, target_dir: str, logger_):
    """
    为 Unity 或 ProjectMoon 创建软链接指向 target_dir
    folder: 'unity' 或 'pm'
    """
    if folder.lower() not in ('unity', 'pm'):
        logger_.log(f"无效的文件夹名称: {folder}")
        return False

    target = Path(target_dir)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)

    # 原始目录
    if folder.lower() == 'unity':
        original = UNITY
    else:
        original = PM

    # 如果原始目录已存在且是符号链接，先移除（避免覆盖）
    if original.is_symlink() or original.exists():
        # 如果是普通目录，需要用户先移动内容，这里我们只移除链接，不处理内容
        if original.is_symlink():
            original.unlink()
        else:
            # 普通目录，不能直接覆盖，应提示用户
            logger_.log(f"错误：{original} 已存在且不是符号链接，请手动处理后再试")
            return False

    # 创建软链接
    try:
        if os.name == 'nt':  # Windows
            import ctypes
            kdll = ctypes.windll.LoadLibrary("kernel32.dll")
            ret = kdll.CreateSymbolicLinkW(str(original), str(target), 0x1)  # 0x1 表示目录链接
            if ret == 0:
                raise OSError(f"创建符号链接失败，错误码: {ctypes.GetLastError()}")
        else:
            original.symlink_to(target, target_is_directory=True)
        logger_.log(f"已创建软链接 {original} -> {target}")
        return True
    except Exception as e:
        logger_.log(f"创建软链接失败: {e}")
        return False

def remove_symlink_for(folder: str, logger_):
    """移除 Unity 或 ProjectMoon 的软链接，恢复为普通目录（如果目标存在则重命名）"""
    if folder.lower() not in ('unity', 'pm'):
        logger_.log(f"无效的文件夹名称: {folder}")
        return False

    original = UNITY if folder.lower() == 'unity' else PM

    if not original.exists():
        logger_.log(f"{original} 不存在")
        return False

    if not original.is_symlink():
        logger_.log(f"{original} 不是符号链接")
        return False

    # 获取链接指向的目标
    target = original.resolve()
    original.unlink()  # 删除链接

    # 如果目标目录存在且不为空，可以保留，也可以移动回来？这里只移除链接，不自动移动数据
    logger_.log(f"已移除软链接 {original}")
    # 可选：将目标目录重命名为原始名称？但可能造成数据丢失，不自动处理
    return True