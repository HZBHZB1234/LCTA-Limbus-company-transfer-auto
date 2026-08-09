"""
tests/test_steam_launcher.py
Steam 启动器设置模块单元测试。

覆盖：
- get_steam_path 注册表读取失败回退
- _normalize_path 路径分隔符归一化
- resolve_localconfig_path 路径自动生成（MostRecent / 回退扫描 / 多账号 appid 优先）
- set_steam_launch_options 写盘 / 备份 / 覆盖自定义值 / 中间节点创建 / BOM 保留
- clear_steam_launch_options 清除 / 保留其他字段 / 幂等 / 错误路径
- read_current_launch_options 读取
- is_lcta_launch_options 判定
- get_steam_launcher_status 状态组装（state: missing/unconfigured/lcta_current/lcta_stale/lcta/other；is_current_lcta）
"""

import sys
from pathlib import Path

import pytest

from webutils.function_steam_launcher import (
    GAME_ID,
    _normalize_path,
    clear_steam_launch_options,
    get_steam_launcher_status,
    is_lcta_launch_options,
    read_current_launch_options,
    resolve_localconfig_path,
    set_steam_launch_options,
)


def _dump_vdf(data, path, bom=False):
    import vdf
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig' if bom else 'utf-8') as f:
        vdf.dump(data, f)


def _make_steam_root(tmp_path, most_recent='1536544116', app_launch_options=None):
    """构造 Steam 根目录：loginusers.vdf + 账号 userdata 下的 localconfig.vdf。"""
    steam_root = tmp_path / 'Steam'
    (steam_root / 'config').mkdir(parents=True, exist_ok=True)
    loginusers = {
        'users': {
            '11111111': {'AccountName': 'old', 'MostRecent': '0'},
            most_recent: {'AccountName': 'main', 'MostRecent': '1'},
        }
    }
    _dump_vdf(loginusers, steam_root / 'config' / 'loginusers.vdf')

    # Steam 使用小写 apps 键
    apps = {} if app_launch_options is None else {GAME_ID: {'LaunchOptions': app_launch_options}}
    localconfig = {'UserLocalConfigStore': {'Software': {'Valve': {'Steam': {'apps': apps}}}}}
    lc_path = steam_root / 'userdata' / most_recent / 'config' / 'localconfig.vdf'
    _dump_vdf(localconfig, lc_path)
    return steam_root, most_recent, lc_path


@pytest.fixture(autouse=True)
def _patch_steam_running(monkeypatch):
    import webutils.function_steam_launcher as fsl
    monkeypatch.setattr(fsl, 'is_steam_running', lambda: False)


@pytest.fixture
def no_steam(monkeypatch):
    import webutils.function_steam_launcher as fsl
    monkeypatch.setattr(fsl, 'get_steam_path', lambda: None)


@pytest.fixture
def steam_root_path(monkeypatch):
    import webutils.function_steam_launcher as fsl

    def _patch(root):
        monkeypatch.setattr(fsl, 'get_steam_path', lambda: str(root))
    return _patch


class TestNormalizePath:
    def test_forward_slashes_to_backslashes(self):
        assert _normalize_path('C:/Program Files (x86)/Steam') == r'C:\Program Files (x86)\Steam'

    def test_keeps_backslashes(self):
        assert _normalize_path(r'D:\Steam') == r'D:\Steam'

    def test_empty_returns_empty(self):
        assert _normalize_path('') == ''


class TestIsLcta:
    def test_lcta_packaged(self):
        assert is_lcta_launch_options(r'"C:\LCTA.exe" -launcher %command%') is True

    def test_lcta_dev(self):
        assert is_lcta_launch_options(r'"C:\python.exe" "C:\start_webui.py" -launcher %command%') is True

    def test_other_value(self):
        assert is_lcta_launch_options('-novid') is False

    def test_empty(self):
        assert is_lcta_launch_options('') is False
        assert is_lcta_launch_options(None) is False


class TestResolvePath:
    def test_most_recent_account(self, tmp_path):
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path)
        assert resolve_localconfig_path(str(steam_root)) == (expected_id, str(lc_path))

    def test_missing_loginusers_falls_back_to_scan(self, tmp_path):
        steam_root = tmp_path / 'Steam'
        (steam_root / 'userdata' / '22222222' / 'config').mkdir(parents=True, exist_ok=True)
        lc = steam_root / 'userdata' / '22222222' / 'config' / 'localconfig.vdf'
        _dump_vdf({'UserLocalConfigStore': {}}, lc)
        assert resolve_localconfig_path(str(steam_root)) == ('22222222', str(lc))

    def test_scan_prefers_account_with_app(self, tmp_path):
        steam_root = tmp_path / 'Steam'
        # 账号 999 无 app 条目，账号 777 含 app 条目；均无 loginusers.vdf
        empty = steam_root / 'userdata' / '99999999' / 'config' / 'localconfig.vdf'
        _dump_vdf({'UserLocalConfigStore': {}}, empty)
        with_app = steam_root / 'userdata' / '77777777' / 'config' / 'localconfig.vdf'
        _dump_vdf({'UserLocalConfigStore': {'Software': {'Valve': {'Steam': {'apps': {GAME_ID: {}}}}}}}, with_app)
        assert resolve_localconfig_path(str(steam_root)) == ('77777777', str(with_app))

    def test_no_steam_path_returns_none(self, no_steam):
        assert resolve_localconfig_path(None) is None

    def test_no_localconfig_returns_none(self, tmp_path):
        steam_root = tmp_path / 'Steam'
        (steam_root / 'config').mkdir(parents=True, exist_ok=True)
        _dump_vdf({'users': {'12345678': {'MostRecent': '1'}}}, steam_root / 'config' / 'loginusers.vdf')
        assert resolve_localconfig_path(str(steam_root)) is None


class TestSetLaunchOptions:
    def test_writes_and_backs_up(self, tmp_path, steam_root_path):
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path)
        steam_root_path(steam_root)
        cmd = '"D:\\LCTA.exe" -launcher %command%'
        result = set_steam_launch_options(cmd)
        assert result['success'] is True
        assert result['localconfig_path'] == str(lc_path)
        assert read_current_launch_options(str(lc_path)) == cmd
        backup = Path(str(lc_path) + '.lcta.bak')
        assert backup.exists()

    def test_overwrites_existing_custom_value(self, tmp_path, steam_root_path):
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path, app_launch_options='-novid')
        steam_root_path(steam_root)
        cmd = '"D:\\LCTA.exe" -launcher %command%'
        result = set_steam_launch_options(cmd)
        assert result['success'] is True
        assert result['old'] == '-novid'
        assert result['new'] == cmd
        assert read_current_launch_options(str(lc_path)) == cmd
        # 备份保留旧值
        backup = Path(str(lc_path) + '.lcta.bak')
        assert read_current_launch_options(str(backup)) == '-novid'

    def test_creates_intermediate_nodes(self, tmp_path, steam_root_path):
        steam_root = tmp_path / 'Steam'
        (steam_root / 'userdata' / '88888888' / 'config').mkdir(parents=True, exist_ok=True)
        lc_path = steam_root / 'userdata' / '88888888' / 'config' / 'localconfig.vdf'
        _dump_vdf({}, lc_path)
        steam_root_path(steam_root)
        result = set_steam_launch_options('"x" -launcher %command%')
        assert result['success'] is True
        assert read_current_launch_options(str(lc_path)) == '"x" -launcher %command%'

    def test_preserves_bom(self, tmp_path, steam_root_path):
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path)
        steam_root_path(steam_root)
        # 带 BOM 重写一遍
        with open(lc_path, 'rb') as f:
            content = f.read()
        with open(lc_path, 'wb') as f:
            f.write(b'\xef\xbb\xbf' + content)
        assert set_steam_launch_options('"x" -launcher %command%')['success'] is True
        with open(lc_path, 'rb') as f:
            assert f.read().startswith(b'\xef\xbb\xbf')

    def test_missing_file_returns_error(self, tmp_path, steam_root_path):
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path)
        steam_root_path(steam_root)
        lc_path.unlink()
        result = set_steam_launch_options('"x" -launcher %command%')
        assert result['success'] is False

    def test_missing_steam_returns_error(self, no_steam):
        assert set_steam_launch_options('"x" -launcher %command%')['success'] is False


class TestStatus:
    LCTA_CMD = r'"D:\LCTA.exe" -launcher %command%'

    @pytest.fixture
    def current_cmd(self, monkeypatch):
        import webutils.function_steam_launcher as fsl
        return lambda value: monkeypatch.setattr(fsl, 'get_current_launch_command', lambda: value)

    def test_status_fields(self, tmp_path, monkeypatch):
        import webutils.function_steam_launcher as fsl
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path, app_launch_options='-novid')
        monkeypatch.setattr(fsl, 'get_steam_path', lambda: str(steam_root))
        status = get_steam_launcher_status()
        assert status['localconfig_path'] == str(lc_path)
        assert status['account_id'] == expected_id
        assert status['game_id'] == GAME_ID
        assert status['exists'] is True
        assert status['current_launch_options'] == '-novid'
        assert status['steam_running'] is False

    def test_state_lcta_current(self, tmp_path, monkeypatch, current_cmd):
        import webutils.function_steam_launcher as fsl
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path, app_launch_options=self.LCTA_CMD)
        monkeypatch.setattr(fsl, 'get_steam_path', lambda: str(steam_root))
        current_cmd(self.LCTA_CMD)
        status = get_steam_launcher_status()
        assert status['state'] == 'lcta_current'
        assert status['is_current_lcta'] is True

    def test_state_lcta_stale(self, tmp_path, monkeypatch, current_cmd):
        import webutils.function_steam_launcher as fsl
        steam_root, expected_id, lc_path = _make_steam_root(
            tmp_path, app_launch_options=r'"D:\old\launcher.exe" -launcher %command%')
        monkeypatch.setattr(fsl, 'get_steam_path', lambda: str(steam_root))
        current_cmd(self.LCTA_CMD)
        status = get_steam_launcher_status()
        assert status['state'] == 'lcta_stale'
        assert status['is_current_lcta'] is False

    def test_state_lcta_fallback(self, tmp_path, monkeypatch, current_cmd):
        import webutils.function_steam_launcher as fsl
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path, app_launch_options=self.LCTA_CMD)
        monkeypatch.setattr(fsl, 'get_steam_path', lambda: str(steam_root))
        current_cmd(None)
        status = get_steam_launcher_status()
        assert status['state'] == 'lcta'
        assert status['is_current_lcta'] is None

    def test_state_other(self, tmp_path, monkeypatch, current_cmd):
        import webutils.function_steam_launcher as fsl
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path, app_launch_options='-novid')
        monkeypatch.setattr(fsl, 'get_steam_path', lambda: str(steam_root))
        current_cmd(self.LCTA_CMD)
        status = get_steam_launcher_status()
        assert status['state'] == 'other'
        assert status['is_current_lcta'] is False

    def test_state_unconfigured(self, tmp_path, monkeypatch, current_cmd):
        import webutils.function_steam_launcher as fsl
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path)
        monkeypatch.setattr(fsl, 'get_steam_path', lambda: str(steam_root))
        current_cmd(self.LCTA_CMD)
        status = get_steam_launcher_status()
        assert status['state'] == 'unconfigured'
        assert status['is_current_lcta'] is None

    def test_state_missing(self, no_steam):
        status = get_steam_launcher_status()
        assert status['state'] == 'missing'
        assert status['is_current_lcta'] is None

    def test_status_no_steam(self, no_steam):
        status = get_steam_launcher_status()
        assert status['localconfig_path'] == ''
        assert status['exists'] is False


class TestClearLaunchOptions:
    def test_clears_and_preserves_other_fields(self, tmp_path, steam_root_path):
        import webutils.function_steam_launcher as fsl
        steam_root = tmp_path / 'Steam'
        (steam_root / 'config').mkdir(parents=True, exist_ok=True)
        _dump_vdf({'users': {'1536544116': {'MostRecent': '1'}}}, steam_root / 'config' / 'loginusers.vdf')
        app = {GAME_ID: {'LastPlayed': '123', 'LaunchOptions': '"x" -launcher %command%'}}
        lc_path = steam_root / 'userdata' / '1536544116' / 'config' / 'localconfig.vdf'
        _dump_vdf({'UserLocalConfigStore': {'Software': {'Valve': {'Steam': {'apps': app}}}}}, lc_path)
        steam_root_path(steam_root)

        result = clear_steam_launch_options()
        assert result['success'] is True
        assert result['old'] == '"x" -launcher %command%'
        # LaunchOptions 已移除，LastPlayed 保留
        data, _ = fsl._load_vdf(str(lc_path))
        remaining = data['UserLocalConfigStore']['Software']['Valve']['Steam']['apps'][GAME_ID]
        assert 'LaunchOptions' not in remaining
        assert remaining['LastPlayed'] == '123'
        # 备份保留旧值
        backup = Path(str(lc_path) + '.lcta.bak')
        assert read_current_launch_options(str(backup)) == '"x" -launcher %command%'

    def test_idempotent_when_unconfigured(self, tmp_path, steam_root_path):
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path)
        steam_root_path(steam_root)
        result = clear_steam_launch_options()
        assert result['success'] is True
        assert read_current_launch_options(str(lc_path)) is None

    def test_missing_file_returns_error(self, tmp_path, steam_root_path):
        steam_root, expected_id, lc_path = _make_steam_root(tmp_path)
        steam_root_path(steam_root)
        lc_path.unlink()
        assert clear_steam_launch_options()['success'] is False

    def test_missing_steam_returns_error(self, no_steam):
        assert clear_steam_launch_options()['success'] is False
