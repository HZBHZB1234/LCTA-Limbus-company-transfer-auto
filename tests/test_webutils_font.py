"""
tests/test_webutils_font.py
webutils/utils/font.py 缓存字体工具测试。
覆盖：
- save_cache_font 复制本地字体替换缓存 ChineseFont.ttf（自动创建缓存目录）
- 重复替换覆盖旧内容
- enable_cache 关闭时仍执行复制（仅记警告）
"""
from pathlib import Path

import pytest

from webutils.utils.font import save_cache_font


class _FakeConfig:
    def __init__(self, values):
        self._values = values

    def get(self, key, default=''):
        return self._values.get(key, default)


def test_save_cache_font_creates_dir_and_replaces(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'webutils.utils.font.ConfigManager',
        lambda: _FakeConfig({
            'cache_path': str(tmp_path / 'cache'),
            'enable_cache': True,
        }),
    )
    font = tmp_path / 'myfont.ttf'
    font.write_bytes(b'font-data-v1')

    target = save_cache_font(str(font))
    assert target == str(tmp_path / 'cache' / 'ChineseFont.ttf')
    assert Path(target).read_bytes() == b'font-data-v1'

    font.write_bytes(b'font-data-v2')
    save_cache_font(str(font))
    assert Path(target).read_bytes() == b'font-data-v2'


def test_save_cache_font_works_when_cache_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'webutils.utils.font.ConfigManager',
        lambda: _FakeConfig({
            'cache_path': str(tmp_path / 'cache'),
            'enable_cache': False,
        }),
    )
    font = tmp_path / 'f.ttf'
    font.write_bytes(b'x')

    target = save_cache_font(str(font))
    assert Path(target).exists()
    assert Path(target).read_bytes() == b'x'


def test_save_cache_font_default_cache_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'webutils.utils.font.ConfigManager',
        lambda: _FakeConfig({'enable_cache': True}),
    )
    monkeypatch.chdir(tmp_path)
    font = tmp_path / 'f.otf'
    font.write_bytes(b'y')

    target = save_cache_font(str(font))
    assert Path(target).resolve() == (tmp_path / 'tmp' / 'ChineseFont.ttf').resolve()
    assert Path(target).read_bytes() == b'y'
