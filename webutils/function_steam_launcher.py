# -*- coding: utf-8 -*-
"""Steam 启动器设置：通过 vdf 库自动编辑 userdata/<账号>/config/localconfig.vdf。

路径自动生成：Steam 安装目录取自注册表，账号从 loginusers.vdf 的 MostRecent 标记
（缺失时回退扫描 userdata 目录）。写入《Limbus Company》(1973530) 的 LaunchOptions。
"""

import io
import os
import sys
import shutil
import subprocess
from typing import Optional, Tuple

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager
from webutils.load import check_game_path
from webutils.utils.misc import get_steam_command

GAME_ID = '1973530'

_log_manager = LogManager()


# ============================================================
# 路径自动生成
# ============================================================

def _normalize_path(path: str) -> str:
    """统一路径分隔符为反斜杠（注册表 SteamPath 可能返回正斜杠）。"""
    if not path:
        return path
    return os.path.normpath(path.replace('/', os.sep))


def get_steam_path() -> Optional[str]:
    """从注册表读取 Steam 安装路径（HKCU\\SOFTWARE\\Valve\\Steam\\SteamPath）。"""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Valve\Steam')
        try:
            value, _ = winreg.QueryValueEx(key, 'SteamPath')
        finally:
            winreg.CloseKey(key)
        return _normalize_path(value) if value else None
    except OSError:
        return None


def _most_recent_account(steam_path: str) -> Optional[str]:
    """从 config/loginusers.vdf 解析 MostRecent 账号 ID。"""
    loginusers = os.path.join(steam_path, 'config', 'loginusers.vdf')
    if not os.path.exists(loginusers):
        return None
    try:
        import vdf
        with open(loginusers, 'rb') as f:
            data = vdf.loads(f.read().decode('utf-8-sig'))
        users = data.get('users', {}) if isinstance(data, dict) else {}
        for uid, info in users.items():
            if isinstance(info, dict) and str(info.get('MostRecent', 0)) == '1':
                return uid
        return next(iter(users), None)
    except Exception as e:
        _log_manager.log(f"解析 loginusers.vdf 失败: {e}")
        return None


def _localconfig_contains_app(path: str) -> bool:
    """粗略判断 localconfig.vdf 中是否含指定 appid（回退排序用，不完整解析）。"""
    try:
        with open(path, 'rb') as f:
            return ('"%s"' % GAME_ID).encode('utf-8') in f.read()
    except OSError:
        return False


def _scan_userdata_accounts(steam_path: str):
    """扫描 userdata\\*\\config\\localconfig.vdf，按（含 appid 优先、账号 ID 降序）排序。"""
    userdata = os.path.join(steam_path, 'userdata')
    if not os.path.isdir(userdata):
        return []
    found = []
    try:
        for entry in os.scandir(userdata):
            if not entry.is_dir():
                continue
            lc = os.path.join(entry.path, 'config', 'localconfig.vdf')
            if os.path.exists(lc):
                found.append((entry.name, lc))
    except OSError:
        return []
    found.sort(key=lambda x: (_localconfig_contains_app(x[1]), int(x[0]) if x[0].isdigit() else 0), reverse=True)
    return found


def resolve_localconfig_path(steam_path: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """自动定位 localconfig.vdf，返回 (account_id, path)；找不到返回 None。"""
    if steam_path is None:
        steam_path = get_steam_path()
    if not steam_path:
        return None

    account_id = _most_recent_account(steam_path)
    if account_id:
        candidate = os.path.join(steam_path, 'userdata', str(account_id), 'config', 'localconfig.vdf')
        if os.path.exists(candidate):
            return str(account_id), candidate

    for account_id, lc in _scan_userdata_accounts(steam_path):
        return account_id, lc

    return None


# ============================================================
# 读取 / 写入
# ============================================================

def _restore_vdf_quotes(node):
    """把值中的 \\" 还原为 "。

    Steam 写出的 VDF 只把引号转义为 \\"，反斜杠路径原样保留；vdf 库默认的
    escaped=True 会把 \\temp 类路径误解码为 TAB/换行，故解析需用 escaped=False。
    """
    for key, value in list(node.items()):
        if isinstance(value, dict):
            _restore_vdf_quotes(value)
        elif isinstance(value, str):
            node[key] = value.replace('\\"', '"')


def _escape_vdf_quotes(node):
    """按 Steam 约定把值中的 " 转义为 \\"（反斜杠路径保持原样）。"""
    for key, value in list(node.items()):
        if isinstance(value, dict):
            _escape_vdf_quotes(value)
        elif isinstance(value, str):
            node[key] = value.replace('"', '\\"')


def _load_vdf(path: str):
    """读取 VDF 文本，返回 (data, has_bom)。"""
    import vdf
    with open(path, 'rb') as f:
        raw = f.read()
    data = vdf.loads(raw.decode('utf-8-sig'), escaped=False)
    _restore_vdf_quotes(data)
    return data, raw.startswith(b'\xef\xbb\xbf')


def _save_vdf(path: str, data, has_bom: bool) -> None:
    """按原 BOM 状态写回 VDF。"""
    import vdf
    _escape_vdf_quotes(data)
    buf = io.StringIO()
    vdf.dump(data, buf, escaped=False)
    with open(path, 'w', encoding='utf-8-sig' if has_bom else 'utf-8') as f:
        f.write(buf.getvalue())


def read_current_launch_options(localconfig_path: str) -> Optional[str]:
    """读取当前游戏的 LaunchOptions；文件缺失/解析失败返回 None。"""
    if not os.path.exists(localconfig_path):
        return None
    try:
        data, _ = _load_vdf(localconfig_path)
        return (data.get('UserLocalConfigStore', {})
                .get('Software', {})
                .get('Valve', {})
                .get('Steam', {})
                .get('apps', {})
                .get(GAME_ID, {})
                .get('LaunchOptions'))
    except Exception as e:
        _log_manager.log(f"读取 localconfig.vdf 失败: {e}")
        return None


def is_steam_running() -> bool:
    """检测 steam.exe 是否在运行。"""
    try:
        out = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq steam.exe', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return 'steam.exe' in out.stdout.lower()
    except Exception:
        return False


def is_lcta_launch_options(launch_options: Optional[str]) -> bool:
    """判断启动项是否为 LCTA 启动器命令（打包与开发模式命令均以 -launcher %command% 结尾）。"""
    return bool(launch_options) and ' -launcher %command%' in launch_options


def get_current_launch_command() -> Optional[str]:
    """生成当前 LCTA 启动命令；无法生成（如开发环境缺少 launcher.exe）返回 None。"""
    from webutils.utils.misc import get_steam_command
    try:
        return get_steam_command()
    except Exception as e:
        _log_manager.log(f"获取当前 LCTA 启动命令失败: {e}")
        return None


def get_steam_launcher_status() -> dict:
    """返回 Steam 启动器设置状态，供前端展示。

    state: missing=未定位到 Steam / unconfigured=未配置 /
           lcta_current=当前 LCTA 启动项 / lcta_stale=旧版 LCTA 启动项 /
           lcta=LCTA 启动项（当前命令不可比较）/ other=已配置非LCTA
    is_current_lcta: True/False/None（当前命令无法生成时为 None）
    """
    result = {
        'steam_path': get_steam_path() or '',
        'account_id': '',
        'localconfig_path': '',
        'game_id': GAME_ID,
        'current_launch_options': '',
        'exists': False,
        'steam_running': is_steam_running(),
        'is_current_lcta': None,
        'state': 'missing',
    }
    resolved = resolve_localconfig_path()
    if not resolved:
        return result
    result['account_id'], result['localconfig_path'] = resolved
    if not os.path.exists(result['localconfig_path']):
        result['state'] = 'missing'
        return result
    result['exists'] = True
    current = read_current_launch_options(result['localconfig_path'])
    result['current_launch_options'] = current or ''
    if not current:
        result['state'] = 'unconfigured'
        return result

    current_command = get_current_launch_command()
    if is_lcta_launch_options(current):
        if current_command is None:
            result['state'] = 'lcta'
        elif current.strip() == current_command.strip():
            result['state'] = 'lcta_current'
            result['is_current_lcta'] = True
        else:
            result['state'] = 'lcta_stale'
            result['is_current_lcta'] = False
    else:
        result['state'] = 'other'
        result['is_current_lcta'] = False
    return result


def set_steam_launch_options(command: Optional[str] = None) -> dict:
    """将 LCTA 启动命令写入 Steam 启动选项，返回结果 dict。"""
    resolved = resolve_localconfig_path()
    if not resolved:
        return {'success': False, 'message': '无法定位 Steam 安装目录或 localconfig.vdf，请确认已安装 Steam 并登录过账号。'}
    account_id, localconfig_path = resolved
    if not os.path.exists(localconfig_path):
        return {'success': False, 'message': f'localconfig.vdf 不存在：{localconfig_path}'}

    if command is None:
        from webutils.utils.misc import get_steam_command
        try:
            command = get_steam_command()
        except Exception as e:
            return {'success': False, 'message': f'获取 LCTA 启动命令失败：{e}'}

    try:
        data, has_bom = _load_vdf(localconfig_path)
    except Exception as e:
        return {'success': False, 'message': f'解析 localconfig.vdf 失败：{e}'}

    store = data.setdefault('UserLocalConfigStore', {})
    software = store.setdefault('Software', {})
    valve = software.setdefault('Valve', {})
    steam = valve.setdefault('Steam', {})
    # Steam 在 localconfig.vdf 中使用小写 apps 键（apps 大写会被忽略）
    apps = steam.setdefault('apps', {})
    app = apps.setdefault(GAME_ID, {})
    old = app.get('LaunchOptions', '')

    app['LaunchOptions'] = command

    try:
        backup_path = localconfig_path + '.lcta.bak'
        shutil.copy2(localconfig_path, backup_path)
        _save_vdf(localconfig_path, data, has_bom)
    except Exception as e:
        return {'success': False, 'message': f'写入 localconfig.vdf 失败：{e}'}

    _log_manager.log(f"Steam 启动选项已写入 {localconfig_path}（账号 {account_id}）: {command}")
    return {
        'success': True,
        'message': f'已写入 Steam 启动选项（账号 {account_id}）。原文件已备份为 localconfig.vdf.lcta.bak。',
        'localconfig_path': localconfig_path,
        'account_id': account_id,
        'old': old,
        'new': command,
    }


def clear_steam_launch_options() -> dict:
    """清除 Steam 启动选项（仅移除 LaunchOptions，保留该游戏的其他字段），返回结果 dict。"""
    resolved = resolve_localconfig_path()
    if not resolved:
        return {'success': False, 'message': '无法定位 Steam 安装目录或 localconfig.vdf，请确认已安装 Steam 并登录过账号。'}
    account_id, localconfig_path = resolved
    if not os.path.exists(localconfig_path):
        return {'success': False, 'message': f'localconfig.vdf 不存在：{localconfig_path}'}

    try:
        data, has_bom = _load_vdf(localconfig_path)
    except Exception as e:
        return {'success': False, 'message': f'解析 localconfig.vdf 失败：{e}'}

    app = (data.get('UserLocalConfigStore', {})
           .get('Software', {})
           .get('Valve', {})
           .get('Steam', {})
           .get('apps', {})
           .get(GAME_ID))
    if not isinstance(app, dict) or 'LaunchOptions' not in app:
        _log_manager.log(f"Steam 启动选项未配置，无需清除（{localconfig_path}）")
        return {'success': True, 'message': '当前未配置 Steam 启动选项，无需清除。', 'account_id': account_id}

    old = app.pop('LaunchOptions')

    try:
        backup_path = localconfig_path + '.lcta.bak'
        shutil.copy2(localconfig_path, backup_path)
        _save_vdf(localconfig_path, data, has_bom)
    except Exception as e:
        return {'success': False, 'message': f'写入 localconfig.vdf 失败：{e}'}

    _log_manager.log(f"Steam 启动选项已清除 {localconfig_path}（账号 {account_id}），原值: {old}")
    return {
        'success': True,
        'message': f'已清除 Steam 启动选项（账号 {account_id}）。原文件已备份为 localconfig.vdf.lcta.bak。',
        'localconfig_path': localconfig_path,
        'account_id': account_id,
        'old': old,
    }


def start_game() -> dict:
    """通过 LCTA Launcher 全流程启动游戏（自动更新汉化、CDN 优选、模组准备后拉起游戏）。

    复用 Steam 启动命令模板构造 launcher 进程参数，经子进程独立拉起 Launcher 全流程，
    返回 {'success': bool, 'message': str}。
    """
    game_path = ConfigManager().get('game_path', '')
    if not game_path:
        return {'success': False, 'message': '未配置游戏路径，请先在「设置」页填写游戏路径。'}
    if not check_game_path(game_path):
        return {'success': False, 'message': f'游戏路径无效，未在 {game_path} 下找到 LimbusCompany.exe。'}

    game_exe = os.path.join(game_path, 'LimbusCompany.exe')

    # 复用 Steam 启动命令模板（已覆盖打包 / 调试 / 开发三种环境）：
    # 将 %command% 占位符替换为实际游戏 exe 路径后，以子进程方式拉起 Launcher 全流程。
    try:
        template = get_steam_command()
    except Exception as e:
        # 开发环境未编译 launcher.exe 时的回退：直接用当前 python 走启动器流程
        template = f'"{sys.executable}" "{os.path.join(os.getcwd(), "start_webui.py")}" -launcher %command%'
        _log_manager.log(f"get_steam_command 失败，回退开发模式命令: {e}")

    command = template.replace('%command%', f'"{game_exe}"')

    try:
        subprocess.Popen(command, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        return {'success': False, 'message': f'启动游戏失败：{e}'}

    return {'success': True, 'message': '已通过 LCTA Launcher 启动游戏，请稍候 Launcher 进度窗…'}
