"""webutils/utils/motw.py 「来自互联网」标记（MOTW）检测与清除测试

覆盖：
- has_zone_identifier：非 Windows 恒 False；无 ADS 时 False
- remove_zone_identifier：无标记返回 False 不抛错；Windows 下真实删除 ADS
- clear_motw：递归清除计数；非 Windows 恒 0；单文件路径
- 应用根目录解析：开发态 = code 目录；打包态 = launcher.exe 所在目录
- cleanup_app_on_startup：探针未标记走快路径（不遍历）；标记时整目录清除
- critical_assembly_paths：定位 venv 内 pythonnet / clr_loader 致命程序集
- cleanup_app_on_startup（venv 场景）：主程序探针干净但 venv 程序集被标记时
  定向清除这几个文件（不遍历目录）；失败原因经 on_error 回调上报
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


def test_cleanup_reports_error_via_callback(motw, tmp_path, monkeypatch):
    """清理失败原因经 on_error 回调上报（供调用方落盘），返回值仍为 0。"""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("path_", str(tmp_path))
    monkeypatch.setattr(motw, "_probe_file", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    errors = []
    assert motw.cleanup_app_on_startup(on_error=errors.append) == 0
    assert len(errors) == 1
    assert "boom" in str(errors[0])


def test_cleanup_on_error_swallows_callback_failure(motw, tmp_path, monkeypatch):
    """on_error 自身抛错也不能影响启动流程。"""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("path_", str(tmp_path))
    monkeypatch.setattr(motw, "_probe_file", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    def _bad(exc):
        raise RuntimeError("callback boom")

    assert motw.cleanup_app_on_startup(on_error=_bad) == 0


# ---------------------------------------------------------------
# critical_assembly_paths / venv 场景的定向清理
# ---------------------------------------------------------------

def _make_critical_assemblies(root: Path):
    """在 root 下构造标准 venv 布局的致命程序集，返回 (dll, native)。"""
    dll = root / "venv" / "Lib" / "site-packages" / "pythonnet" / "runtime" / "Python.Runtime.dll"
    native = root / "venv" / "Lib" / "site-packages" / "clr_loader" / "ffi" / "dlls" / "amd64" / "ClrLoader.dll"
    for path in (dll, native):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00" * 8)
    return dll, native


def test_critical_assembly_paths_empty_on_non_windows(motw, tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "linux")
    _make_critical_assemblies(tmp_path)
    assert motw.critical_assembly_paths(tmp_path) == []


def test_critical_assembly_paths_finds_pythonnet_and_clr_loader(motw, tmp_path, monkeypatch):
    """标准 venv 布局（含小写 lib）下的 pythonnet DLL 与 clr_loader 原生库都要命中。"""
    monkeypatch.setattr(os, "name", "nt")
    dll, native = _make_critical_assemblies(tmp_path)
    found = motw.critical_assembly_paths(tmp_path)
    assert dll in found
    assert native in found


def test_critical_assembly_paths_lowercase_lib_layout(motw, tmp_path, monkeypatch):
    """`venv/lib/...`（小写，非 Windows 原生 venv）同样要命中——面向 Linux 侧
    拷包后残留小写目录的真实故障形态。"""
    monkeypatch.setattr(os, "name", "nt")
    dll = tmp_path / "venv" / "lib" / "site-packages" / "pythonnet" / "runtime" / "Python.Runtime.dll"
    dll.parent.mkdir(parents=True)
    dll.write_bytes(b"\x00" * 8)
    assert dll in motw.critical_assembly_paths(tmp_path)


def test_critical_assembly_paths_skips_missing_venv(motw, tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    assert motw.critical_assembly_paths(tmp_path) == []


def test_cleanup_clears_only_critical_assemblies_when_probe_clean(motw, tmp_path, monkeypatch):
    """主程序探针干净、只有 venv 程序集被标记：定向清除，不遍历整个目录。

    回归点：此前探针只看 start_webui.py，venv 与主程序来源不同时永远不清理，
    带标记的 Python.Runtime.dll 让 CLR 每次都初始化失败。
    """
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("path_", str(tmp_path))
    (tmp_path / "start_webui.py").write_text("", encoding="utf-8")
    marked = tmp_path / "venv" / "lib" / "site-packages" / "pythonnet" / "runtime" / "Python.Runtime.dll"
    marked.parent.mkdir(parents=True)
    marked.write_bytes(b"\x00" * 8)

    monkeypatch.setattr(motw, "has_zone_identifier", lambda path: Path(path) == marked)
    removed = MagicMock(return_value=True)
    monkeypatch.setattr(motw, "remove_zone_identifier", removed)
    traversed = MagicMock(side_effect=AssertionError("只应定向清除，不应遍历目录"))
    monkeypatch.setattr(motw, "clear_motw", traversed)

    assert motw.cleanup_app_on_startup() == 1
    removed.assert_called_once_with(marked)
    traversed.assert_not_called()


def test_cleanup_critical_assembly_clears_real_ads(motw, tmp_path, monkeypatch):
    """真实 ADS：venv 内被标记的 pythonnet DLL 会被真正解锁。"""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("path_", str(tmp_path))
    (tmp_path / "start_webui.py").write_text("", encoding="utf-8")
    dll, native = _make_critical_assemblies(tmp_path)
    for path in (dll, native):
        with open(str(path) + ":Zone.Identifier", "w", encoding="utf-8") as fh:
            fh.write("[ZoneTransfer]\nZoneId=3\n")

    assert motw.cleanup_app_on_startup() == 2
    assert motw.has_zone_identifier(str(dll)) is False
    assert motw.has_zone_identifier(str(native)) is False

