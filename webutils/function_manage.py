import shutil
import sys
import os
from pathlib import Path
from typing import Tuple
import json

from .functions import *

def check_lang_enabled(game_path:str) -> str:
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
    if lang_path.exists():
        return "able"
    lang_path = Path(game_path) / 'LimbusCompany_Data' / '_lang'
    if lang_path.exists():
        return "disable"
    return 'not_exist'

def find_installed_packages(config) -> Tuple[list, str]:
    game_path = config.get('game_path', '')
    if not game_path:
        raise
    if not check_lang_enabled(game_path)=='able':
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
    if (current=='able') == enable:
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