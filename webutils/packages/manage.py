from __future__ import annotations

import shutil
import sys
import os
import subprocess
from pathlib import Path
from typing import Tuple
import json

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager
from globalManagers.exceptions import CancelRunning

_log_manager = LogManager()


def safe_join_path(base_path, name):
    """校验目录/包名安全性并返回 base 目录下的目标路径

    拒绝绝对路径、包含 `..` 段、包含盘符的非法名称；
    解析后的目标路径必须位于 base 目录解析后的子树内，否则抛出 ValueError。
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("无效的名称")
    if os.path.isabs(name) or ':' in name:
        raise ValueError(f"不允许使用绝对路径或盘符: {name}")
    parts = Path(name).parts
    if '..' in parts:
        raise ValueError(f"路径不能包含 '..' 段: {name}")
    base = Path(base_path).resolve()
    target = (base / name).resolve()
    if target == base or base not in target.parents:
        raise ValueError(f"目标路径超出允许范围: {name}")
    return target

def check_lang_enabled(game_path:str) -> bool:
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
    if lang_path.exists():
        return True
    lang_path = Path(game_path) / 'LimbusCompany_Data' / '_lang'
    if not lang_path.exists():
        lang_path.mkdir()
    return False

def get_active_lang_path(game_path: str) -> Path:
    """当前启用的汉化目录路径（禁用态为 _lang）"""
    if check_lang_enabled(game_path):
        return Path(game_path) / 'LimbusCompany_Data' / 'lang'
    return Path(game_path) / 'LimbusCompany_Data' / '_lang'

def find_installed_packages() -> Tuple[list, str]:
    game_path = ConfigManager().get('game_path', '')
    if not game_path:
        raise ValueError("未设置游戏路径")
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

def use_translation_package(package_name: str, modal_id: str = "false"):
    game_path = ConfigManager().get('game_path', '')
    if not package_name or not game_path:
        raise ValueError("未选择汉化包或未设置游戏路径")
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
    if not (lang_path / package_name).exists():
        raise FileNotFoundError(f"汉化包不存在: {package_name}")
    lang_config = lang_path / 'config.json'
    _log_manager.check_running(modal_id)
    try:
        config_lang = json.loads(lang_config.read_text(encoding='utf-8'))
    except:
        config_lang = {}
    _log_manager.check_running(modal_id)
    config_lang['lang'] = package_name
    lang_config.write_text(json.dumps(config_lang, indent=4, ensure_ascii=False))
    return True

def delete_installed_package(package_name: str):
    game_path = ConfigManager().get('game_path', '')
    if not package_name or not game_path:
        raise ValueError("未选择汉化包或未设置游戏路径")
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
    # 校验名称安全并解析目标路径，防止路径穿越
    package_path = safe_join_path(lang_path, package_name)
    if not package_path.exists():
        return {'success': False, "message": '当前汉化包不存在'}
    lang_config = lang_path / 'config.json'
    try:
        config_lang = json.loads(lang_config.read_text(encoding='utf-8'))
    except:
        config_lang = {}
    current_lang = config_lang.get('lang', '')
    if current_lang == package_name:
        return {'success': False, "message": '当前汉化包正在使用，无法删除'}
    shutil.rmtree(package_path)
    return {'success': True, "message": '已删除'}

def toggle_install_package(enable):
    game_path = ConfigManager().get('game_path', '')
    if not game_path:
        raise ValueError("未设置游戏路径")
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
    disable_path = Path(game_path) / 'LimbusCompany_Data' / '_lang'
    current = check_lang_enabled(game_path)
    if current == enable:
        return False
    else:
        if enable:
            # 目标已存在（双目录状态）时先移除旧目标，避免嵌套移动
            if lang_path.exists():
                shutil.rmtree(lang_path)
            shutil.move(disable_path, lang_path)
        else:
            if disable_path.exists():
                shutil.rmtree(disable_path)
            shutil.move(lang_path, disable_path)
        return True

def get_default_mod_path():
    return Path.home() / 'AppData' /  'Roaming' / 'LimbusCompanyMods'

def get_mod_path():
    mod_path = ConfigManager().get('ui_default.manage.mod_path', '')
    if not mod_path:
        mod_path = get_default_mod_path()
    else:
        mod_path = Path(mod_path)
    return mod_path

def fing_mod():
    mod_path = get_mod_path()
    r = list(mod_path.glob('*.carra2'))
    r.extend(list(mod_path.glob('*.bank')))
    r.extend(list(mod_path.glob('*.rebank')))
    r.extend(list(mod_path.glob('*.zip')))
    r.extend(list(mod_path.glob('*.json')))
    r.extend([i for i in mod_path.glob('*') if i.is_dir() and not i.name.endswith('_disable')])
    rd = list(mod_path.glob('*.carra2_disable'))
    rd.extend(list(mod_path.glob('*.bank_disable')))
    rd.extend(list(mod_path.glob('*.rebank_disable')))
    rd.extend(list(mod_path.glob('*.zip_disable')))
    rd.extend(list(mod_path.glob('*.json_disable')))
    rd.extend([i for i in mod_path.glob('*') if i.is_dir() and i.name.endswith('_disable')])
    r = [i.name for i in r]
    rd = [(i.name).rstrip('_disable') for i in rd]
    return r, rd

def toggle_mod(mod_name: str, enable):
    mod_path = get_mod_path()
    # 校验 mod 名称安全，防止路径穿越
    safe_join_path(mod_path, mod_name)
    mod = mod_path / (mod_name if not enable else f'{mod_name}_disable')
    if mod.exists():
        shutil.move(mod, mod_path / (mod_name if enable else f'{mod_name}_disable'))
        return True
    else:
        return False
    
def delete_mod(mod_name: str, enable):
    mod_path = get_mod_path()
    # 校验 mod 名称安全，防止路径穿越
    safe_join_path(mod_path, mod_name)
    mod = mod_path / (mod_name if enable else f'{mod_name}_disable')
    if mod.exists():
        if mod.is_dir():
            shutil.rmtree(mod)
            return True
        mod.unlink()
        return True
    else:
        return False

def open_mod_path():
    mod_path = get_mod_path()
    # 使用 subprocess 列表参数而非 os.system 拼接命令，避免路径含空格时被截断
    subprocess.Popen(['explorer', str(mod_path)])
    
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
    else:
        raise FileNotFoundError(f"路径不存在: {path}")

def create_symlink_for(from_dir: str, target_dir: str):
    Path(target_dir).symlink_to(from_dir, target_is_directory=True)

def remove_symlink_for(folder: str):
    _folder = Path(folder)
    try:
        if _folder.is_symlink():
            _folder.unlink()
        elif _folder.exists():
            _folder.rmdir()
        else:
            return False
        return True
    except OSError as e:
        _log_manager.log(f"删除软链接失败: {e}")
        _log_manager.log_error(e)
        return False

def evaluate_path(path: str):
    _path = Path(path)
    if not _path.exists():
        _path.mkdir(exist_ok=True)
    return bool(list(_path.iterdir()))
