"""删除/管理功能的路径安全校验测试"""
import json
import zipfile
from pathlib import Path

import pytest

import webutils.packages.clean as function_clean
import webutils.packages.install as function_install
import webutils.packages.manage as function_manage


class _FakeConfig:
    def __init__(self, values):
        self._values = values

    def get(self, key, default=''):
        return self._values.get(key, default)


def _make_zip(path, members):
    with zipfile.ZipFile(path, 'w') as zf:
        for member in members:
            zf.writestr(member, 'x')
    return path


class TestDeleteTranslationPackage:
    """webutils/packages/install.py::delete_translation_package"""

    def test_delete_folder_package(self, tmp_path):
        pkg = tmp_path / '汉化包A'
        pkg.mkdir()
        result = function_install.delete_translation_package('汉化包A', str(tmp_path))
        assert result['success'] is True
        assert not pkg.exists()

    def test_delete_file_package(self, tmp_path):
        pkg = tmp_path / '汉化包B.zip'
        pkg.write_bytes(b'x')
        result = function_install.delete_translation_package('汉化包B.zip', str(tmp_path))
        assert result['success'] is True
        assert not pkg.exists()

    def test_delete_nonexistent_returns_failure(self, tmp_path):
        result = function_install.delete_translation_package('不存在', str(tmp_path))
        assert result['success'] is False

    def test_reject_path_traversal(self, tmp_path):
        outside = tmp_path.parent / 'evil_delete_pkg'
        outside.mkdir(exist_ok=True)
        result = function_install.delete_translation_package('..\\evil_delete_pkg', str(tmp_path))
        assert result['success'] is False
        assert outside.exists()

    def test_reject_absolute_path(self, tmp_path):
        target = tmp_path / 'x'
        target.mkdir()
        result = function_install.delete_translation_package(str(target), str(tmp_path))
        assert result['success'] is False
        assert target.exists()

    def test_reject_drive_letter(self, tmp_path):
        result = function_install.delete_translation_package('C:evil', str(tmp_path))
        assert result['success'] is False


class TestDeleteInstalledPackage:
    """webutils/packages/manage.py::delete_installed_package"""

    @pytest.fixture
    def lang_path(self, tmp_path, monkeypatch):
        game = tmp_path / 'game'
        lang = game / 'LimbusCompany_Data' / 'lang'
        lang.mkdir(parents=True)
        monkeypatch.setattr(
            function_manage, 'ConfigManager',
            lambda: _FakeConfig({'game_path': str(game)}))
        return lang

    def test_delete_package(self, lang_path):
        (lang_path / '汉化包A').mkdir()
        result = function_manage.delete_installed_package('汉化包A')
        assert result['success'] is True
        assert not (lang_path / '汉化包A').exists()

    def test_delete_nonexistent(self, lang_path):
        result = function_manage.delete_installed_package('不存在')
        assert result['success'] is False

    def test_reject_path_traversal(self, lang_path, tmp_path):
        outside = tmp_path / 'evil_installed'
        outside.mkdir(exist_ok=True)
        with pytest.raises(ValueError):
            function_manage.delete_installed_package('..\\evil_installed')
        assert outside.exists()

    def test_reject_current_lang(self, lang_path):
        (lang_path / '汉化包A').mkdir()
        (lang_path / 'config.json').write_text(
            json.dumps({'lang': '汉化包A'}), encoding='utf-8')
        result = function_manage.delete_installed_package('汉化包A')
        assert result['success'] is False
        assert (lang_path / '汉化包A').exists()


class TestModManage:
    """webutils/packages/manage.py::toggle_mod / delete_mod / open_mod_path"""

    @pytest.fixture
    def mod_path(self, tmp_path, monkeypatch):
        mods = tmp_path / 'Mod Path'
        mods.mkdir()
        monkeypatch.setattr(
            function_manage, 'ConfigManager',
            lambda: _FakeConfig({'ui_default.manage.mod_path': str(mods)}))
        return mods

    def test_toggle_mod_enable(self, mod_path):
        (mod_path / 'm.carra2_disable').write_bytes(b'x')
        assert function_manage.toggle_mod('m.carra2', True) is True
        assert (mod_path / 'm.carra2').exists()
        assert not (mod_path / 'm.carra2_disable').exists()

    def test_toggle_mod_disable(self, mod_path):
        (mod_path / 'm.carra2').write_bytes(b'x')
        assert function_manage.toggle_mod('m.carra2', False) is True
        assert (mod_path / 'm.carra2_disable').exists()

    def test_toggle_mod_missing(self, mod_path):
        assert function_manage.toggle_mod('不存在', True) is False

    def test_toggle_mod_reject_traversal(self, mod_path, tmp_path):
        outside = tmp_path / 'evil_mod'
        outside.mkdir(exist_ok=True)
        with pytest.raises(ValueError):
            function_manage.toggle_mod('..\\evil_mod', True)
        assert outside.exists()

    def test_delete_mod_file(self, mod_path):
        (mod_path / 'm.bank').write_bytes(b'x')
        assert function_manage.delete_mod('m.bank', True) is True
        assert not (mod_path / 'm.bank').exists()

    def test_delete_mod_dir(self, mod_path):
        (mod_path / 'm_dir').mkdir()
        assert function_manage.delete_mod('m_dir', True) is True
        assert not (mod_path / 'm_dir').exists()

    def test_delete_mod_disable_variant(self, mod_path):
        (mod_path / 'm.json_disable').write_bytes(b'x')
        assert function_manage.delete_mod('m.json', False) is True
        assert not (mod_path / 'm.json_disable').exists()

    def test_delete_mod_reject_traversal(self, mod_path, tmp_path):
        outside = tmp_path / 'evil_mod2'
        outside.mkdir(exist_ok=True)
        with pytest.raises(ValueError):
            function_manage.delete_mod('..\\evil_mod2', True)
        assert outside.exists()

    def test_open_mod_path_uses_subprocess_list(self, mod_path, monkeypatch):
        calls = []

        def _fake_popen(args):
            calls.append(args)

        monkeypatch.setattr(function_manage.subprocess, 'Popen', _fake_popen)
        function_manage.open_mod_path()
        assert calls == [['explorer', str(mod_path)]]


class TestCleanByMod:
    """webutils/packages/clean.py::check_by_mod / clear_by_mod"""

    @pytest.fixture
    def unity_dir(self, tmp_path, monkeypatch):
        local_low = tmp_path / 'LocalLow'
        monkeypatch.setenv('APPDATA', str(tmp_path / 'Roaming'))
        unity = local_low / 'Unity' / 'ProjectMoon_LimbusCompany'
        unity.mkdir(parents=True)
        return unity

    def test_check_by_mod_returns_installation_items(self, tmp_path):
        mod = tmp_path / 'm.zip'
        _make_zip(mod, ['ModFolder/Assets/Installation/Text/foo.txt'])
        result = function_clean.check_by_mod(str(mod))
        assert result == ['ModFolder/Assets/Installation/Text/']

    def test_check_by_mod_rejects_dotdot_member(self, tmp_path):
        mod = tmp_path / 'evil1.zip'
        _make_zip(mod, ['../secret.txt'])
        with pytest.raises(ValueError):
            function_clean.check_by_mod(str(mod))

    def test_check_by_mod_rejects_absolute_member(self, tmp_path):
        mod = tmp_path / 'evil2.zip'
        _make_zip(mod, ['/etc/passwd'])
        with pytest.raises(ValueError):
            function_clean.check_by_mod(str(mod))

    def test_check_by_mod_rejects_drive_member(self, tmp_path):
        mod = tmp_path / 'evil3.zip'
        _make_zip(mod, ['C:/secret.txt'])
        with pytest.raises(ValueError):
            function_clean.check_by_mod(str(mod))

    def test_clear_installation_items(self, unity_dir, tmp_path):
        (unity_dir / 'Text').mkdir()
        (unity_dir / 'Text' / 'x.txt').write_bytes(b'x')
        mod = tmp_path / 'm.zip'
        _make_zip(mod, ['ModFolder/Assets/Installation/Text/foo.txt'])
        count = function_clean.clear_by_mod(str(mod), 'modal')
        assert count == 1
        assert not (unity_dir / 'Text').exists()

    def test_clear_non_installation_assets(self, unity_dir, tmp_path):
        (unity_dir / 'Assets').mkdir()
        (unity_dir / 'Assets' / 'x.txt').write_bytes(b'x')
        mod = tmp_path / 'm.zip'
        _make_zip(mod, ['Assets/foo.txt'])
        count = function_clean.clear_by_mod(str(mod), 'modal')
        assert count == 1
        assert not (unity_dir / 'Assets').exists()

    def test_installation_dir_itself_filtered(self, unity_dir, tmp_path):
        (unity_dir / 'Installation').mkdir()
        (unity_dir / 'Installation' / 'x.txt').write_bytes(b'x')
        mod = tmp_path / 'm.zip'
        _make_zip(mod, ['Assets/Installation/Installation/'])
        count = function_clean.clear_by_mod(str(mod), 'modal')
        assert count == 0
        assert (unity_dir / 'Installation').exists()

    def test_dotdot_member_does_not_delete_parent(self, unity_dir, tmp_path):
        parent = unity_dir.parent
        mod = tmp_path / 'evil.zip'
        _make_zip(mod, ['../secret.txt'])
        count = function_clean.clear_by_mod(str(mod), 'modal')
        assert count == 0
        assert parent.exists()

    def test_missing_mod_returns_zero(self, unity_dir, tmp_path):
        count = function_clean.clear_by_mod(str(tmp_path / 'none.zip'), 'modal')
        assert count == 0
