"""webutils/drop/ 包的类型识别与安装逻辑测试

覆盖：
- evalZip / evalFolder / eval7zip 对单根目录包裹（LimbusLocalize_xxx/StoryData/...）的识别
- evalFiles 的 full 7z 分支：包裹剥开、多顶层条目逐项安装
- FLmod / jsononly 预删除与实际解压目标对齐
- update 分支 zip 成员名安全校验（路径穿越防护）
"""
import sys
import types
import zipfile
from pathlib import Path

import pytest


if "openspeedy" not in sys.modules:
    openspeedy = types.ModuleType("openspeedy")
    openspeedy.SpeedController = type("SpeedController", (), {})  # type: ignore[attr-defined]
    openspeedy.ProcessInfo = type("ProcessInfo", (), {})  # type: ignore[attr-defined]
    for exception_name in (
        "OpenSpeedyError",
        "PlatformNotSupportedError",
        "DLLNotFoundError",
        "ProcessAccessDeniedError",
        "ProcessNotFoundError",
        "ProcessArchitectureMismatch",
        "InjectionError",
        "EjectionError",
        "SpeedRangeError",
        "SpeedControlError",
    ):
        setattr(openspeedy, exception_name, type(exception_name, (Exception,), {}))
    sys.modules["openspeedy"] = openspeedy

from webutils.drop import detect, eval_files, handlers, inspect


FOLDERLIST_DIRS = [
    'BattleAnnouncerDlg',
    'BgmLyrics',
    'EGOVoiceDig',
    'PersonalityVoiceDlg',
    'StoryData',
]


def _make_zip(path, members):
    with zipfile.ZipFile(path, 'w') as zf:
        for member in members:
            zf.writestr(member, 'x')
    return path


def _make_full_zip(path, wrapper=None, font=True, loose=None):
    """构造达到 full/nofont 判定阈值的汉化包 zip（>1500 条目）"""
    root = f"{wrapper}/" if wrapper else ""
    members = []
    for folder in FOLDERLIST_DIRS:
        members.append(f"{root}{folder}/")
        members.append(f"{root}{folder}/dummy.bin")
    if font:
        members.append(f"{root}Font/")
        members.append(f"{root}Font/dummy.ttf")
    members.extend(f"{root}StoryData/k{i}.txt" for i in range(1600))
    if loose:
        members.append(loose)
    return _make_zip(path, members)


def _make_full_folder(base, wrapper=None, font=True, loose=None):
    """构造目录形式的汉化包（对应 evalFolder 输入）"""
    root = base / wrapper if wrapper else base
    root.mkdir(parents=True)
    for folder in FOLDERLIST_DIRS:
        (root / folder).mkdir()
        (root / folder / 'dummy.bin').write_bytes(b'x')
    if font:
        (root / 'Font').mkdir()
        (root / 'Font' / 'dummy.ttf').write_bytes(b'x')
    if loose:
        (base / loose).write_bytes(b'x')
    return base


class TestRegistryOrder:
    def test_update_zip_takes_priority_over_jsononly(self):
        names = ('update_pkg/app.py', 'update_pkg/requirements.txt',
                 'update_pkg/start_webui.py', 'update_pkg/readme.md')
        inspection = inspect.ZipFormatInspection(
            names=names,
            non_json_names=tuple(n for n in names if '.json' not in n),
        )
        assert handlers.REGISTRY.detect('zip', inspection) == 'update'

    def test_every_refer_type_has_handler(self):
        for file_type in (
            'full', 'nofont', 'FLmod', 'jsononly', 'update',
            'invalid', 'carra', 'bank', 'textFile', 'LCTAchange',
            'FLchange', 'busimport', 'font',
        ):
            assert handlers.REGISTRY.handler_for(file_type) is not None


# ========== evalZip：单根目录包裹识别 ==========

class TestEvalZipWrapped:
    def test_wrapped_full(self, tmp_path):
        z = _make_full_zip(tmp_path / 'pkg.zip', wrapper='LimbusLocalize_w')
        assert detect.evalZip(str(z)) == 'full'

    def test_wrapped_nofont(self, tmp_path):
        z = _make_full_zip(tmp_path / 'pkg.zip', wrapper='LimbusLocalize_w', font=False)
        assert detect.evalZip(str(z)) == 'nofont'

    def test_wrapped_with_loose_file(self, tmp_path):
        z = _make_full_zip(tmp_path / 'pkg.zip', wrapper='LimbusLocalize_w', loose='说明.txt')
        assert detect.evalZip(str(z)) == 'full'

    def test_unwrapped_full(self, tmp_path):
        z = _make_full_zip(tmp_path / 'pkg.zip')
        assert detect.evalZip(str(z)) == 'full'

    def test_unwrapped_nofont(self, tmp_path):
        z = _make_full_zip(tmp_path / 'pkg.zip', font=False)
        assert detect.evalZip(str(z)) == 'nofont'

    def test_wrapped_small_package_still_invalid(self, tmp_path):
        z = _make_zip(tmp_path / 'small.zip', ['LimbusLocalize_w/StoryData/a.txt'])
        assert detect.evalZip(str(z)) == 'invalid'

    def test_flmod_unaffected(self, tmp_path):
        z = _make_zip(tmp_path / 'mod.zip', ['MyMod/mod_info.json', 'MyMod/data.json'])
        assert detect.evalZip(str(z)) == 'FLmod'

    def test_jsononly_unaffected(self, tmp_path):
        z = _make_zip(tmp_path / 'j.zip', ['a.txt', 'b.txt', 'c.txt'])
        assert detect.evalZip(str(z)) == 'jsononly'


# ========== evalFolder：单根目录包裹识别 ==========

class TestEvalFolderWrapped:
    def test_wrapped_full(self, tmp_path):
        base = _make_full_folder(tmp_path, wrapper='LimbusLocalize_w')
        assert detect.evalFolder(str(base)) == 'full'

    def test_wrapped_nofont(self, tmp_path):
        base = _make_full_folder(tmp_path, wrapper='LimbusLocalize_w', font=False)
        assert detect.evalFolder(str(base)) == 'nofont'

    def test_wrapped_with_loose_file(self, tmp_path):
        base = _make_full_folder(tmp_path, wrapper='LimbusLocalize_w', loose='说明.txt')
        assert detect.evalFolder(str(base)) == 'full'

    def test_unwrapped_full(self, tmp_path):
        base = _make_full_folder(tmp_path / 'unwrapped')
        assert detect.evalFolder(str(base)) == 'full'

    def test_flmod_unaffected(self, tmp_path):
        mod = tmp_path / 'MyMod'
        mod.mkdir()
        (mod / 'mod_info.json').write_text('{}', encoding='utf-8')
        assert detect.evalFolder(str(mod)) == 'FLmod'

    def test_jsononly_unaffected(self, tmp_path):
        for i in range(3):
            (tmp_path / f'f{i}.txt').write_bytes(b'x')
        assert detect.evalFolder(str(tmp_path)) == 'jsononly'

    def test_invalid(self, tmp_path):
        (tmp_path / 'a.txt').write_bytes(b'x')
        assert detect.evalFolder(str(tmp_path)) == 'invalid'


# ========== eval7zip：单根目录包裹识别 ==========

class TestEval7zipWrapped:
    @staticmethod
    def _fake_decompress(src, dst):
        pkg = Path(dst) / 'LimbusLocalize_wrapped'
        for folder in FOLDERLIST_DIRS + ['Font']:
            (pkg / folder).mkdir(parents=True)
        return True

    def test_wrapped_full(self, tmp_path, monkeypatch):
        monkeypatch.setattr(detect, 'decompress_7z', self._fake_decompress)
        sevenz = tmp_path / 'pkg.7z'
        sevenz.write_bytes(b'fake')
        assert detect.eval7zip(str(sevenz)) == 'full'

    def test_decompress_failure_returns_invalid(self, tmp_path, monkeypatch):
        monkeypatch.setattr(detect, 'decompress_7z', lambda src, dst: False)
        sevenz = tmp_path / 'pkg.7z'
        sevenz.write_bytes(b'fake')
        assert detect.eval7zip(str(sevenz)) == 'invalid'


# ========== _zip_extract_root：预删除目标判定 ==========

class TestZipExtractRoot:
    def test_single_root_dir(self, tmp_path):
        z = _make_zip(tmp_path / 'm.zip', ['MyMod/mod_info.json', 'MyMod/data.json'])
        assert handlers.FLMOD._zip_extract_root(str(z)) == 'MyMod'

    def test_multi_root_returns_stem(self, tmp_path):
        z = _make_zip(tmp_path / 'm.zip', ['A/mod_info.json', 'B/x.json'])
        assert handlers.FLMOD._zip_extract_root(str(z)) == 'm'

    def test_rejects_dotdot_member(self, tmp_path):
        z = _make_zip(tmp_path / 'evil.zip', ['../evil/mod_info.json'])
        with pytest.raises(ValueError):
            handlers.FLMOD._zip_extract_root(str(z))

    def test_rejects_absolute_member(self, tmp_path):
        z = _make_zip(tmp_path / 'evil.zip', ['/etc/passwd'])
        with pytest.raises(ValueError):
            handlers.FLMOD._zip_extract_root(str(z))

    def test_rejects_drive_member(self, tmp_path):
        z = _make_zip(tmp_path / 'evil.zip', ['C:/secret.txt'])
        with pytest.raises(ValueError):
            handlers.FLMOD._zip_extract_root(str(z))


# ========== evalFiles：full 7z 分支 ==========

class TestEvalFilesFull7z:
    @pytest.fixture
    def fake_config(self, tmp_path, monkeypatch):
        class _FakeConfig:
            def __init__(self, values):
                self._values = values

            def get(self, key, default=''):
                return self._values.get(key, default)

        monkeypatch.setattr(
            eval_files, 'ConfigManager',
            lambda: _FakeConfig({'game_path': str(tmp_path / 'game')}))
        return _FakeConfig

    def test_wrapped_single_install_call(self, tmp_path, monkeypatch, fake_config):
        calls = []
        monkeypatch.setattr(
            handlers.translation, 'install_translation_package',
            lambda pkg, game, modal_id=None: calls.append(str(pkg)))

        def _fake_decompress(src, dst):
            pkg = Path(dst) / 'LimbusLocalize_wrapped'
            for folder in FOLDERLIST_DIRS + ['Font']:
                (pkg / folder).mkdir(parents=True)
            return True

        monkeypatch.setattr(handlers.translation, 'decompress_7z', _fake_decompress)
        sevenz = tmp_path / 'pkg.7z'
        sevenz.write_bytes(b'fake')

        result = eval_files.evalFiles({str(sevenz): 'full'}, 'modal')
        assert result['success'] is True
        assert result['installed'] == 1
        assert len(calls) == 1
        assert Path(calls[0]).name == 'LimbusLocalize_wrapped'

    def test_multi_top_entries_install_each_dir(self, tmp_path, monkeypatch, fake_config):
        calls = []
        monkeypatch.setattr(
            handlers.translation, 'install_translation_package',
            lambda pkg, game, modal_id=None: calls.append(str(pkg)))

        def _fake_decompress(src, dst):
            (Path(dst) / 'StoryData').mkdir()
            (Path(dst) / 'Font').mkdir()
            (Path(dst) / '说明.txt').write_bytes(b'x')
            return True

        monkeypatch.setattr(handlers.translation, 'decompress_7z', _fake_decompress)
        sevenz = tmp_path / 'pkg.7z'
        sevenz.write_bytes(b'fake')

        result = eval_files.evalFiles({str(sevenz): 'nofont'}, 'modal')
        assert result['success'] is True
        assert len(calls) == 2
        assert sorted(Path(c).name for c in calls) == ['Font', 'StoryData']

    def test_no_package_dirs_raises_error(self, tmp_path, monkeypatch, fake_config):
        def _fake_decompress(src, dst):
            (Path(dst) / '说明.txt').write_bytes(b'x')
            return True

        monkeypatch.setattr(handlers.translation, 'decompress_7z', _fake_decompress)
        sevenz = tmp_path / 'pkg.7z'
        sevenz.write_bytes(b'fake')

        result = eval_files.evalFiles({str(sevenz): 'full'}, 'modal')
        assert result['success'] is False
        assert result['errors'] == 1


# ========== evalFiles：FLmod / jsononly 预删除对齐 ==========

class TestEvalFilesPreDelete:
    @pytest.fixture
    def mod_path(self, tmp_path, monkeypatch):
        mods = tmp_path / 'Mod Path'
        mods.mkdir()
        monkeypatch.setattr(eval_files, 'get_mod_path', lambda: str(mods))
        return mods

    def test_flmod_single_root_deletes_actual_target(self, tmp_path, mod_path, monkeypatch):
        monkeypatch.setattr(handlers.archive_mod, 'extract_zip_smartly', lambda src, dst: None)
        mod_zip = tmp_path / 'myflmod.zip'
        _make_zip(mod_zip, ['MyMod/mod_info.json', 'MyMod/data.json'])

        actual = mod_path / 'MyMod'
        actual.mkdir()
        (actual / 'old.txt').write_bytes(b'x')
        stem_dir = mod_path / 'myflmod'
        stem_dir.mkdir()

        result = eval_files.evalFiles({str(mod_zip): 'FLmod'}, 'modal')
        assert result['success'] is True
        assert not actual.exists()
        assert stem_dir.exists()

    def test_flmod_multi_root_deletes_stem_dir(self, tmp_path, mod_path, monkeypatch):
        monkeypatch.setattr(handlers.archive_mod, 'extract_zip_smartly', lambda src, dst: None)
        mod_zip = tmp_path / 'multi.zip'
        _make_zip(mod_zip, ['A/mod_info.json', 'B/x.json'])

        target = mod_path / 'multi'
        target.mkdir()
        (target / 'old.txt').write_bytes(b'x')

        result = eval_files.evalFiles({str(mod_zip): 'FLmod'}, 'modal')
        assert result['success'] is True
        assert not target.exists()

    def test_flmod_rejects_unsafe_member(self, tmp_path, mod_path):
        mod_zip = tmp_path / 'evil.zip'
        _make_zip(mod_zip, ['../evil/mod_info.json'])
        result = eval_files.evalFiles({str(mod_zip): 'FLmod'}, 'modal')
        assert result['errors'] == 1
        assert result['success'] is False

    def test_jsononly_single_root_deletes_actual_target(self, tmp_path, mod_path, monkeypatch):
        monkeypatch.setattr(handlers.archive_mod, 'extract_zip_smartly', lambda src, dst: None)
        json_zip = tmp_path / 'textpack.zip'
        _make_zip(json_zip, ['TextPack/a.json', 'TextPack/b.json'])

        actual = mod_path / 'TextPack'
        actual.mkdir()
        (actual / 'old.json').write_bytes(b'x')

        result = eval_files.evalFiles({str(json_zip): 'jsononly'}, 'modal')
        assert result['success'] is True
        assert not actual.exists()


# ========== evalFiles：update 分支安全校验 ==========

class TestEvalFilesUpdate:
    @pytest.fixture
    def fake_config(self, tmp_path, monkeypatch):
        class _FakeConfig:
            def get(self, key, default=''):
                return default

        monkeypatch.setattr(handlers.update, 'ConfigManager', _FakeConfig)
        return _FakeConfig

    def test_rejects_unsafe_member(self, tmp_path, fake_config):
        up_zip = tmp_path / 'update.zip'
        _make_zip(up_zip, ['../evil/requirements.txt', '../evil/start_webui.py'])
        result = eval_files.evalFiles({str(up_zip): 'update'}, 'modal')
        assert result['errors'] == 1
        assert result['success'] is False

    def test_safe_update_succeeds(self, tmp_path, fake_config, monkeypatch):
        class _FakeUpdater:
            def __init__(self, *args, **kwargs):
                pass

            def install_requirements(self, path):
                pass

            def update_files(self, path):
                return True

        monkeypatch.setattr(handlers.update, 'Updater', _FakeUpdater)
        up_zip = tmp_path / 'update.zip'
        _make_zip(up_zip, [
            'update_pkg/requirements.txt',
            'update_pkg/start_webui.py',
            'update_pkg/app.py',
        ])
        result = eval_files.evalFiles({str(up_zip): 'update'}, 'modal')
        assert result['updated'] == 1
        assert result['success'] is True


# ========== evalFile / evalFiles：缓存字体替换 ==========

class TestCacheFontHandler:
    def test_eval_file_ttf_detects_font(self, tmp_path):
        f = tmp_path / 'myfont.ttf'
        f.write_bytes(b'x')
        assert detect.evalFile(str(f)) == 'font'

    def test_eval_file_otf_detects_font(self, tmp_path):
        f = tmp_path / 'myfont.otf'
        f.write_bytes(b'x')
        assert detect.evalFile(str(f)) == 'font'

    def test_eval_file_uppercase_suffix_detects_font(self, tmp_path):
        f = tmp_path / 'MYFONT.TTF'
        f.write_bytes(b'x')
        assert detect.evalFile(str(f)) == 'font'

    def test_eval_file_other_suffix_invalid(self, tmp_path):
        f = tmp_path / 'myfont.txt'
        f.write_bytes(b'x')
        assert detect.evalFile(str(f)) == 'invalid'

    def test_eval_files_replaces_cache_font(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / 'cache'
        saved = {}

        def _fake_save(font_path):
            cache_dir.mkdir(parents=True, exist_ok=True)
            target = cache_dir / 'ChineseFont.ttf'
            target.write_bytes(Path(font_path).read_bytes())
            saved['target'] = str(target)
            return str(target)

        monkeypatch.setattr(handlers.font, 'save_cache_font', _fake_save)
        monkeypatch.setattr(eval_files, 'get_mod_path', lambda: str(tmp_path / 'mods'))

        font_file = tmp_path / 'myfont.ttf'
        font_file.write_bytes(b'fontdata')
        result = eval_files.evalFiles({str(font_file): 'font'}, 'modal')
        assert result['success'] is True
        assert result['fonts'] == 1
        assert result['errors'] == 0
        assert Path(saved['target']).name == 'ChineseFont.ttf'
        assert Path(saved['target']).read_bytes() == b'fontdata'

