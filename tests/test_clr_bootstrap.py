"""webutils/clr_bootstrap.py 引导逻辑测试

覆盖：
- 成功路径：强制 netfx、返回 clr 模块、不调用探针
- Python.Runtime.dll 缺失/为空时给出修复指引
- import clr 失败时错误信息包含探针输出与修复指引
- clr_loader 版本过旧 / .NET Framework 缺失时给出环境警告
- 版本元组解析
- MOTW（「来自互联网」标记）自愈：预自愈先清一次、失败后清一次并重试一次、
  pythonnet 与 clr_loader 原生库都清、清完仍失败时错误信息注明已清理文件
"""
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = _PROJECT_ROOT / "webutils" / "clr_bootstrap.py"


def _load_module():
    """直接加载 clr_bootstrap,避免 webutils/__init__.py 的重型导入。"""
    spec = importlib.util.spec_from_file_location("clr_bootstrap", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["clr_bootstrap"] = mod
    return mod


@pytest.fixture()
def cb():
    return _load_module()


@pytest.fixture()
def fake_site_packages(cb, tmp_path):
    """把 site-packages 指到临时目录并创建 Python.Runtime.dll。"""
    dll_dir = tmp_path / "pythonnet" / "runtime"
    dll_dir.mkdir(parents=True)
    dll = dll_dir / "Python.Runtime.dll"
    dll.write_bytes(b"\x00" * 16)

    def _sp():
        yield tmp_path

    with patch("clr_bootstrap._site_packages", side_effect=_sp):
        yield SimpleNamespace(dll=dll, root=tmp_path)


def test_ensure_clr_success_forces_netfx(cb, fake_site_packages):
    """成功路径：设置 PYTHONNET_RUNTIME=netfx 并返回 clr 模块"""
    fake_clr = SimpleNamespace(__file__="fake_clr")
    with patch("clr_bootstrap._import_clr", return_value=fake_clr) as imp, \
         patch("clr_bootstrap._clr_loader_version", return_value="0.2.10"), \
         patch("clr_bootstrap._check_dotnet_framework", return_value=""), \
         patch("clr_bootstrap.get_real_exception") as probe:
        result = cb.ensure_clr()
    assert result is fake_clr
    assert imp.call_count == 1
    probe.assert_not_called()
    assert sys.modules["os"].environ["PYTHONNET_RUNTIME"] == "netfx"


def test_ensure_clr_missing_dll_raises_with_hint(cb, tmp_path):
    """Python.Runtime.dll 缺失：抛出带修复指引的错误"""
    def _sp():
        yield tmp_path

    with patch("clr_bootstrap._site_packages", side_effect=_sp):
        with pytest.raises(RuntimeError) as exc:
            cb.ensure_clr()
    assert "Python.Runtime.dll" in str(exc.value)
    assert "修复指引" in str(exc.value)


def test_ensure_clr_empty_dll_raises_with_hint(cb, tmp_path):
    """Python.Runtime.dll 为空文件：同样按损坏处理"""
    dll = tmp_path / "pythonnet" / "runtime" / "Python.Runtime.dll"
    dll.parent.mkdir(parents=True)
    dll.write_bytes(b"")

    def _sp():
        yield tmp_path

    with patch("clr_bootstrap._site_packages", side_effect=_sp):
        with pytest.raises(RuntimeError) as exc:
            cb.ensure_clr()
    assert "修复指引" in str(exc.value)


def test_ensure_clr_import_failure_includes_probe(cb, fake_site_packages):
    """import clr 失败：错误信息包含探针输出与修复指引"""
    with patch("clr_bootstrap._import_clr",
               side_effect=RuntimeError("Failed to resolve ...")), \
         patch("clr_bootstrap.get_real_exception",
               return_value="!! GetAssemblyName 失败: FileNotFoundException xxx"), \
         patch("clr_bootstrap._clr_loader_version", return_value="0.2.10"), \
         patch("clr_bootstrap._check_dotnet_framework", return_value=""):
        with pytest.raises(RuntimeError) as exc:
            cb.ensure_clr()
    msg = str(exc.value)
    assert "初始化失败" in msg
    assert "FileNotFoundException" in msg
    assert "修复指引" in msg
    assert sys.modules["os"].environ["PYTHONNET_RUNTIME"] == "netfx"


def test_ensure_clr_warns_old_clr_loader(cb, fake_site_packages):
    """clr_loader < 0.2.8：错误信息包含版本警告"""
    with patch("clr_bootstrap._import_clr", side_effect=RuntimeError("load failed")), \
         patch("clr_bootstrap.get_real_exception", return_value=""), \
         patch("clr_bootstrap._clr_loader_version", return_value="0.2.7"), \
         patch("clr_bootstrap._check_dotnet_framework", return_value=""):
        with pytest.raises(RuntimeError) as exc:
            cb.ensure_clr()
    assert "clr_loader 版本过旧 (0.2.7 < 0.2.8)" in str(exc.value)


def test_ensure_clr_warns_dotnet_framework(cb, fake_site_packages):
    """.NET Framework 缺失：错误信息包含环境警告"""
    with patch("clr_bootstrap._import_clr", side_effect=RuntimeError("load failed")), \
         patch("clr_bootstrap.get_real_exception", return_value=""), \
         patch("clr_bootstrap._clr_loader_version", return_value="0.2.10"), \
         patch("clr_bootstrap._check_dotnet_framework",
               return_value="未检测到 .NET Framework 4.x"):
        with pytest.raises(RuntimeError) as exc:
            cb.ensure_clr()
    assert "未检测到 .NET Framework" in str(exc.value)


def test_version_tuple_parses(cb):
    assert cb._version_tuple("0.2.10") == (0, 2, 10)
    assert cb._version_tuple("0.2.7") == (0, 2, 7)
    assert cb._version_tuple("0.2.7.post0") == (0, 2, 7)
    assert (cb._version_tuple("0.2.10") < (0, 2, 8)) is False
    assert (cb._version_tuple("0.2.7") < (0, 2, 8)) is True


# ---------------------------------------------------------------
# MOTW（「来自互联网」标记）自愈
#
# 回归点：带 Zone.Identifier(ZoneId=3) 的 Python.Runtime.dll 会被 .NET
# 拒绝 LoadFrom（0x80131515「不支持操作」），clr_loader 只报
# "Failed to resolve Python.Runtime.Loader.Initialize"。改配置无效
# （clr_loader 自建 AppDomain、不读进程 app.config），只能清文件标记。
# ---------------------------------------------------------------

_WIN_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="ADS 仅存在于 Windows")


def test_clear_zone_identifier_no_ads(cb, tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules["os"], "name", "nt")
    plain = tmp_path / "plain.dll"
    plain.write_bytes(b"\x00")
    assert cb._clear_zone_identifier(plain) is False


def test_clear_zone_identifier_non_windows(cb, tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules["os"], "name", "linux")
    plain = tmp_path / "plain.dll"
    plain.write_bytes(b"\x00")
    assert cb._clear_zone_identifier(plain) is False


@_WIN_ONLY
def test_clear_zone_identifier_removes_ads(cb, tmp_path):
    dll = tmp_path / "Python.Runtime.dll"
    dll.write_bytes(b"\x00")
    ads = str(dll) + ":Zone.Identifier"
    with open(ads, "w", encoding="utf-8") as fh:
        fh.write("[ZoneTransfer]\nZoneId=3\n")
    assert cb._clear_zone_identifier(dll) is True
    assert not os.path.exists(ads)
    # 第二次没有标记可删
    assert cb._clear_zone_identifier(dll) is False


@_WIN_ONLY
def test_clear_assembly_motw_clears_pythonnet_and_clr_loader(cb, tmp_path):
    dll = tmp_path / "pythonnet" / "runtime" / "Python.Runtime.dll"
    native = tmp_path / "clr_loader" / "ffi" / "dlls" / "amd64" / "ClrLoader.dll"
    for path in (dll, native):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00")
        with open(str(path) + ":Zone.Identifier", "w", encoding="utf-8") as fh:
            fh.write("[ZoneTransfer]\nZoneId=3\n")

    cleared = cb._clear_assembly_motw(dll)

    assert set(cleared) == {dll, native}
    for path in (dll, native):
        assert not os.path.exists(str(path) + ":Zone.Identifier")


def test_clear_assembly_motw_without_venv_siblings(cb, fake_site_packages):
    """没有任何标记时返回空列表（预自愈走快路径）。"""
    assert cb._clear_assembly_motw(fake_site_packages.dll) == []


def test_ensure_clr_self_heals_motw_and_retries(cb, fake_site_packages):
    """导入失败后清标记并重试一次：成功则不报错、不跑探针。"""
    fake_clr = SimpleNamespace(__file__="fake_clr")
    calls = {"import": 0, "clear": 0}

    def _import():
        calls["import"] += 1
        if calls["import"] == 1:
            raise RuntimeError("Failed to resolve Python.Runtime.Loader.Initialize")
        return fake_clr

    def _clear(dll_path):
        calls["clear"] += 1
        # 第 1 次是预自愈（无标记），第 2 次是在失败后（命中标记）
        return [] if calls["clear"] == 1 else [fake_site_packages.dll]

    with patch("clr_bootstrap._import_clr", side_effect=_import), \
         patch("clr_bootstrap._clear_assembly_motw", side_effect=_clear), \
         patch("clr_bootstrap.get_real_exception") as probe, \
         patch("clr_bootstrap._clr_loader_version", return_value="0.2.10"), \
         patch("clr_bootstrap._check_dotnet_framework", return_value=""):
        result = cb.ensure_clr()

    assert result is fake_clr
    assert calls["import"] == 2
    probe.assert_not_called()


def test_ensure_clr_clears_motw_before_first_import(cb, fake_site_packages):
    """预自愈：正常路径也先清一次（成本极低，避免注定失败的加载）。"""
    fake_clr = SimpleNamespace(__file__="fake_clr")
    with patch("clr_bootstrap._import_clr", return_value=fake_clr), \
         patch("clr_bootstrap._clear_assembly_motw", return_value=[]) as clear, \
         patch("clr_bootstrap._clr_loader_version", return_value="0.2.10"), \
         patch("clr_bootstrap._check_dotnet_framework", return_value=""):
        cb.ensure_clr()
    clear.assert_called_once_with(fake_site_packages.dll)


def test_ensure_clr_reports_cleared_paths_when_still_failing(cb, fake_site_packages):
    """清标记后依旧失败：错误信息注明已清理的文件，便于区分「不是 MOTW 问题」。"""
    calls = {"clear": 0}

    def _clear(dll_path):
        calls["clear"] += 1
        return [] if calls["clear"] == 1 else [fake_site_packages.dll]

    with patch("clr_bootstrap._import_clr",
               side_effect=RuntimeError("Failed to resolve ...")), \
         patch("clr_bootstrap._clear_assembly_motw", side_effect=_clear), \
         patch("clr_bootstrap.get_real_exception", return_value=""), \
         patch("clr_bootstrap._clr_loader_version", return_value="0.2.10"), \
         patch("clr_bootstrap._check_dotnet_framework", return_value=""):
        with pytest.raises(RuntimeError) as exc:
            cb.ensure_clr()
    msg = str(exc.value)
    assert "已清除「来自互联网」标记后重试" in msg
    assert "Python.Runtime.dll" in msg


def test_fix_hint_mentions_unblock_file(cb):
    """修复指引第一条必须给出 MOTW 自查/清除办法（0x80131515 的高频成因）。"""
    assert "Unblock-File" in cb._FIX_HINT
    assert "0x80131515" in cb._FIX_HINT

