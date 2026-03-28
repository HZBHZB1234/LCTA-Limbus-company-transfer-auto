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
    r.extend(list(mod_path.glob('*.zip')))
    r.extend(list(mod_path.glob('*.json')))
    r.extend([i for i in mod_path.glob('*') if i.is_dir() and not i.name.endswith('_disable')])
    rd = list(mod_path.glob('*.carra2_disable'))
    rd.extend(list(mod_path.glob('*.bank_disable')))
    rd.extend(list(mod_path.glob('*.zip_disable')))
    rd.extend(list(mod_path.glob('*.json_disable')))
    rd.extend([i for i in mod_path.glob('*') if i.is_dir() and i.name.endswith('_disable')])
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
        if mod.is_dir():
            shutil.rmtree(mod)
            return True
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
        'Unity': check_path(UNITY),
        'ProjectMoon': check_path(PM)
    }
    
def open_explorer(path):
    """打开资源管理器窗口"""
    if os.path.exists(str(path)):
        subprocess.Popen(['explorer', str(path)])
    else:raise

def create_symlink_for(from_dir: str, target_dir: str):
    Path(target_dir).symlink_to(from_dir, target_is_directory=True)

def remove_symlink_for(folder: str):
    _folder = Path(folder)
    if _folder.is_symlink():
        _folder.unlink()
    else:
        _folder.rmdir()

def evaluate_path(path: str):
    _path = Path(path)
    if not _path.exists():
        _path.mkdir(exist_ok=True)
    return bool(list(_path.iterdir()))