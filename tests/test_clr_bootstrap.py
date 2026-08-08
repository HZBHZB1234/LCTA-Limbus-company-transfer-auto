"""webutils/clr_bootstrap.py 引导逻辑测试

覆盖：
- 成功路径：强制 netfx、返回 clr 模块、不调用探针
- Python.Runtime.dll 缺失/为空时给出修复指引
- import clr 失败时错误信息包含探针输出与修复指引
- clr_loader 版本过旧 / .NET Framework 缺失时给出环境警告
- 版本元组解析
"""
import importlib.util
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
