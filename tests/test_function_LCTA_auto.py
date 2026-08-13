"""
tests/test_function_LCTA_auto.py
webutils/function_LCTA_auto.py 字体注入逻辑测试。
覆盖：
- _inject_font_into_zip 在单根目录汉化包中注入 Font/Context/ChineseFont.ttf 且保留原包结构
- _resolve_font_path 优先使用缓存字体
- _resolve_font_path 缓存缺失时回退下载 LLC 字体包
"""
import sys
import types
import zipfile
from pathlib import Path

from webutils import function_LCTA_auto as mod


def _make_lcta_zip(zip_path, root='LLc-CN-LCTA'):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f'{root}/BattleAnnouncerDlg/Announcer.json', '{}')
        zf.writestr(f'{root}/Info/version.json', '{"version": "1"}')
        zf.writestr(f'{root}/MainUIText.json', '{}')


def test_inject_font_into_zip_single_root(tmp_path):
    zip_path = tmp_path / 'LLc-CN-LCTA-2026081301.zip'
    font_path = tmp_path / 'ChineseFont.ttf'
    font_path.write_bytes(b'font-bytes')
    _make_lcta_zip(str(zip_path))

    assert mod._inject_font_into_zip(str(zip_path), str(font_path), None) is True

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert 'LLc-CN-LCTA/Font/Context/ChineseFont.ttf' in names
        assert zf.read('LLc-CN-LCTA/Font/Context/ChineseFont.ttf') == b'font-bytes'
        assert 'LLc-CN-LCTA/BattleAnnouncerDlg/Announcer.json' in names
        assert 'LLc-CN-LCTA/Info/version.json' in names
        assert 'LLc-CN-LCTA/MainUIText.json' in names


def test_inject_font_into_zip_multiple_roots(tmp_path):
    zip_path = tmp_path / 'LCTA_auto.zip'
    font_path = tmp_path / 'f.ttf'
    font_path.write_bytes(b'x')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('LLc-CN-LCTA/BattleAnnouncerDlg/Announcer.json', '{}')
        zf.writestr('extra.json', '{}')

    assert mod._inject_font_into_zip(str(zip_path), str(font_path), None) is True

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert 'LCTA_auto/LLc-CN-LCTA/Font/Context/ChineseFont.ttf' in names
        assert 'LCTA_auto/LLc-CN-LCTA/BattleAnnouncerDlg/Announcer.json' in names


def test_resolve_font_path_uses_cache(monkeypatch, tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    cached = tmp_path / 'cached.ttf'
    cached.write_bytes(b'cached')
    monkeypatch.setattr(mod, 'get_cache_font', lambda: str(cached))

    result = mod._resolve_font_path(None, str(work))
    assert result == str(cached)


def test_resolve_font_path_downloads_when_no_cache(monkeypatch, tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    font_bytes = b'font-data'

    def fake_download(asset, save_path, **kwargs):
        Path(save_path).write_bytes(b'fake-7z')
        return True

    def fake_decompress(file_path, output_dir='.'):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        target = out / 'Font' / 'Context' / 'LLCCN-Font.ttf'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(font_bytes)
        return True

    fake_llc = types.ModuleType('webutils.function_llc')
    fake_llc.font_assets_seven = object()
    monkeypatch.setitem(sys.modules, 'webutils.function_llc', fake_llc)
    monkeypatch.setattr(mod, 'get_cache_font', lambda: '')
    monkeypatch.setattr(mod, 'download_with_github', fake_download)
    monkeypatch.setattr('webutils.utils.io.decompress_by_extension', fake_decompress)

    result = mod._resolve_font_path(None, str(work))
    assert result
    assert Path(result).read_bytes() == font_bytes
