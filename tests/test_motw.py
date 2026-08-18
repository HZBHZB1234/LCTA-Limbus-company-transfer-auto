"""webutils/utils/motw.py 「来自互联网」标记（MOTW）检测与清除测试

覆盖：
- has_zone_identifier：非 Windows 恒 False；无 ADS 时 False
- remove_zone_identifier：无标记返回 False 不抛错；Windows 下真实删除 ADS
- clear_motw：递归清除计数；非 Windows 恒 0；单文件路径
- 应用根目录解析：开发态 = code 目录；打包态 = launcher.exe 所在目录
- cleanup_app_on_startup：探针未标记走快路径（不遍历）；标记时整目录清除
"""
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = _PROJECT_ROOT / "webutils" / "utils" / "motw.py"

_WIN_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="ADS 仅存在于 Windows")


def _load_module():
    """直接加载 motw,避免 webutils/__init__.py 的重型导入。"""
    spec = importlib.util.spec_from_file_location("_lcta_motw", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["_lcta_motw"] = mod
    return mod


@pytest.fixture()
def motw():
    return _load_module()


# ---------------------------------------------------------------
# has_zone_identifier
# ---------------------------------------------------------------

def test_has_zone_identifier_false_on_non_windows(motw, monkeypatch):
    monkeypatch.setattr(os, "name", "linux")
    assert motw.has_zone_identifier("C:\\any\\file.exe") is False


def test_has_zone_identifier_false_without_ads(motw, tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    f = tmp_path / "plain.txt"
    f.write_text("hello", encoding="utf-8")
    assert motw.has_zone_identifier(str(f)) is False


@_WIN_ONLY
def test_has_zone_identifier_true_with_ads(motw, tmp_path):
    f = tmp_path / "marked.txt"
    f.write_text("hello", encoding="utf-8")
    ads = str(f) + ":Zone.Identifier"
    with open(ads, "w", encoding="utf-8") as fh:
        fh.write("[ZoneTransfer]\nZoneId=3\n")
    assert motw.has_zone_identifier(str(f)) is True


# ---------------------------------------------------------------
# remove_zone_identifier
# ---------------------------------------------------------------

def test_remove_zone_identifier_without_ads_returns_false(motw, tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    f = tmp_path / "plain.txt"
    f.write_text("hello", encoding="utf-8")
    assert motw.remove_zone_identifier(str(f)) is False


@_WIN_ONLY
def test_remove_zone_identifier_removes_ads(motw, tmp_path):
    f = tmp_path / "marked.txt"
    f.write_text("hello", encoding="utf-8")
    ads = str(f) + ":Zone.Identifier"
    with open(ads, "w", encoding="utf-8") as fh:
        fh.write("[ZoneTransfer]\nZoneId=3\n")
    assert motw.remove_zone_identifier(str(f)) is True
    assert motw.has_zone_identifier(str(f)) is False
    # 再次删除应返回 False 且不抛错
    assert motw.remove_zone_identifier(str(f)) is False


# ---------------------------------------------------------------
# clear_motw
# ---------------------------------------------------------------

def test_clear_motw_zero_on_non_windows(motw, tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "linux")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("b", encoding="utf-8")
    assert motw.clear_motw(str(tmp_path)) == 0


@_WIN_ONLY
def test_clear_motw_recursive_counts(motw, tmp_path):
    files = [tmp_path / "a.txt", tmp_path / "sub" / "b.txt", tmp_path / "sub" / "c.dll"]
    files[1].parent.mkdir()
    for f in files:
        f.write_bytes(b"x")
        with open(str(f) + ":Zone.Identifier", "w", encoding="utf-8") as fh:
            fh.write("[ZoneTransfer]\nZoneId=3\n")
    assert motw.clear_motw(str(tmp_path)) == len(files)
    for f in files:
        assert motw.has_zone_identifier(str(f)) is False


@_WIN_ONLY
def test_clear_motw_single_file(motw, tmp_path):
    f = tmp_path / "single.exe"
    f.write_bytes(b"MZ")
    with open(str(f) + ":Zone.Identifier", "w", encoding="utf-8") as fh:
        fh.write("[ZoneTransfer]\nZoneId=3\n")
    assert motw.clear_motw(str(f)) == 1
    assert motw.has_zone_identifier(str(f)) is False


# ---------------------------------------------------------------
# 应用根目录解析
# ---------------------------------------------------------------

def test_app_root_dev(motw, tmp_path, monkeypatch):
    monkeypatch.setattr(motw, "_app_code_root", lambda: tmp_path)
    assert motw._app_root() == tmp_path


def test_app_root_packaged(motw, tmp_path, monkeypatch):
    code = tmp_path / "code"
    code.mkdir()
    (tmp_path / "launcher.exe").write_bytes(b"MZ")
    monkeypatch.setattr(motw, "_app_code_root", lambda: code)
    assert motw._app_root() == tmp_path


def test_probe_file_prefers_start_webui(motw, tmp_path):
    (tmp_path / "start_webui.py").write_text("", encoding="utf-8")
    assert motw._probe_file(tmp_path) == tmp_path / "start_webui.py"


def test_probe_file_falls_back_to_module(motw, tmp_path):
    probe = motw._probe_file(tmp_path)
    assert probe == Path(motw.__file__).resolve()


# ---------------------------------------------------------------
# cleanup_app_on_startup
# ---------------------------------------------------------------

def test_cleanup_non_windows_returns_zero(motw, monkeypatch):
    monkeypatch.setattr(os, "name", "linux")
    assert motw.cleanup_app_on_startup() == 0


def test_cleanup_fast_path_when_probe_clean(motw, tmp_path, monkeypatch):
    """探针未标记：返回 0 且不调用 clear_motw（不做目录遍历）。"""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("path_", str(tmp_path))
    (tmp_path / "start_webui.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(motw, "has_zone_identifier", lambda path: False)
    called = MagicMock(side_effect=AssertionError("快路径不应遍历目录"))
    monkeypatch.setattr(motw, "clear_motw", called)
    assert motw.cleanup_app_on_startup() == 0
    called.assert_not_called()


def test_cleanup_clears_app_root_when_probe_marked(motw, tmp_path, monkeypatch):
    """探针被标记：对整个应用根目录递归清除并返回清理数。"""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("path_", str(tmp_path))
    (tmp_path / "start_webui.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(motw, "has_zone_identifier", lambda path: True)
    cleared = MagicMock(return_value=7)
    monkeypatch.setattr(motw, "clear_motw", cleared)
    assert motw.cleanup_app_on_startup() == 7
    cleared.assert_called_once_with(tmp_path, recursive=True)


def test_cleanup_packaged_clears_parent_with_launcher_exe(motw, tmp_path, monkeypatch):
    """打包态：探针在 code/ 下，清除范围扩展到 launcher.exe 所在的应用根。"""
    monkeypatch.setattr(os, "name", "nt")
    code = tmp_path / "code"
    code.mkdir()
    (tmp_path / "launcher.exe").write_bytes(b"MZ")
    monkeypatch.setenv("path_", str(code))
    (code / "start_webui.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(motw, "has_zone_identifier", lambda path: True)
    cleared = MagicMock(return_value=12)
    monkeypatch.setattr(motw, "clear_motw", cleared)
    assert motw.cleanup_app_on_startup() == 12
    cleared.assert_called_once_with(tmp_path, recursive=True)


def test_cleanup_exception_safe(motw, tmp_path, monkeypatch):
    """内部异常被吞掉，启动不受影响。"""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("path_", str(tmp_path))
    monkeypatch.setattr(motw, "_probe_file", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert motw.cleanup_app_on_startup() == 0
