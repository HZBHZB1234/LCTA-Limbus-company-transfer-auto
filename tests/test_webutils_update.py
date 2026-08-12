"""
tests/test_webutils_update.py
webutils.update 修复回归测试。
覆盖：
- compare_versions 逐段整数比较（不再拼接整数），跨大版本与小版本号段位差正确判定
- v 前缀与非数字段容错
- install_requirements 按包名比对：废弃依赖永久保留；新增/升级依赖在 GUI 内先安装，
  默认源网络失败时切换清华源；仅非网络失败写入 pending
- spec 归一化比较：包名大小写等纯格式差异不误判为版本变动
- pending 持久化与 apply_pending_pip_ops 启动钩子（仅安装、成功清空、失败保留、
  pip 子进程 UTF-8 环境、stderr GBK 回退解码）
- globalManagers.pending_pip_ops 导入链纯标准库（不触发 webutils 等第三方导入）
- check_and_update 缓存迁移到应用目录外的临时目录并在 finally 中清理
- check_and_update 事务性：update_files 失败时还原 install_requirements 写入的 pending
"""
import json
import subprocess
import sys
import zipfile

import pytest

import webutils.update as update_mod
import globalManagers.pending_pip_ops as ppo
from webutils.update import Updater


class _LogStub:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def _repo_root():
    import pathlib
    return pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def updater(monkeypatch):
    monkeypatch.setattr(update_mod, "_log_manager", _LogStub())
    monkeypatch.setattr(ppo, "_log_manager", _LogStub())
    return Updater("owner", "repo")


@pytest.fixture
def pending_path(tmp_path):
    return tmp_path / "pending_pip_ops.json"


# ========== compare_versions ==========

def test_compare_same_version_no_update(updater):
    assert updater.compare_versions("5.0.0", "5.0.0") is False


def test_compare_newer_major_is_update(updater):
    # 旧实现拼接整数：600 < 5100 误判为无更新
    assert updater.compare_versions("5.10.0", "6.0.0") is True


def test_compare_newer_minor_is_update(updater):
    assert updater.compare_versions("5.9.0", "5.10.0") is True


def test_compare_older_no_update(updater):
    assert updater.compare_versions("6.0.0", "5.10.0") is False
    assert updater.compare_versions("5.10.0", "5.9.0") is False


def test_compare_v_prefix(updater):
    assert updater.compare_versions("5.10.0", "v6.0.0") is True
    assert updater.compare_versions("v5.10.0", "5.10.0") is False


def test_compare_non_numeric_suffix_tolerant(updater):
    # 带后缀的段取段首数字，不抛异常、不误判
    assert updater.compare_versions("6.0.0", "6.0.1-beta") is True
    assert updater.compare_versions("5.10.0", "6.0.0-beta") is True


def test_compare_segment_count_imbalance(updater):
    # 段位数不同时按 tuple 语义比较
    assert updater.compare_versions("5.0", "5.0.0") is True
    assert updater.compare_versions("5.0.0", "5.0") is False


def test_compare_malformed_lenient(updater):
    # 无法解析时保持宽容语义：视为有更新
    assert updater.compare_versions("", "1.0.0") is True
    assert updater.compare_versions("garbage", "1.0.0") is True


# ========== _parse_requirements ==========

def test_parse_requirements_handles_comments_and_blank_lines():
    text = (
        "requests\n"
        "pywebview==6.2.1\n"
        "etcpak==0.9.8 # 0.9.9 crashes when trying to import dll\n"
        "\n"
        "  pillow==10.4.0  \n"
        "-r other.txt\n"
        "-e .\n"
    )
    parsed = update_mod._parse_requirements(text)
    assert parsed == {
        "requests": "requests",
        "pywebview": "pywebview==6.2.1",
        "etcpak": "etcpak==0.9.8",
        "pillow": "pillow==10.4.0",
    }


def test_parse_requirements_normalizes_pkg_name():
    text = "Foo_Bar.1==2.0\n"
    parsed = update_mod._parse_requirements(text)
    assert "foo-bar-1" in parsed
    assert parsed["foo-bar-1"] == "Foo_Bar.1==2.0"


def test_parse_requirements_skips_url_only_lines():
    parsed = update_mod._parse_requirements("https://example.com/pkg.whl\n")
    assert parsed == {}


# ========== install_requirements：延迟判定 ==========

def _write_req(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup(monkeypatch, updater, app_dir, old_req, source_dir, new_req,
           pending_path):
    _write_req(app_dir / "requirements.txt", old_req)
    _write_req(source_dir / "requirements.txt", new_req)
    calls = []
    monkeypatch.setattr(subprocess, "check_call", lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(update_mod, "_pending_ops_default_path",
                        lambda: pending_path)
    return calls


def test_install_requirements_keeps_removed_dependency_and_installs_new_one(
        monkeypatch, updater, tmp_path, pending_path):
    # requirements 中删除的依赖永久保留，只安装新增项。
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir, "olddep==1.0\nkeep==2.0\n",
                   source_dir, "keep==2.0\nfresh==3.0\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result.success is True
    assert calls == [[sys.executable, "-m", "pip", "install", "fresh==3.0"]]
    assert not pending_path.exists()


def test_install_requirements_installs_version_bump_in_gui(
        monkeypatch, updater, tmp_path, pending_path):
    # 版本 pin 变更先在当前 GUI 更新流程中安装。
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir, "pywebview==6.2.1\n",
                   source_dir, "pywebview==6.3.0\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result.success is True
    assert calls == [[sys.executable, "-m", "pip", "install", "pywebview==6.3.0"]]
    assert not pending_path.exists()


def test_install_requirements_comment_change_is_not_a_bump(
        monkeypatch, updater, tmp_path, pending_path):
    # 行内注释差异在去除注释后不构成 spec 变化 → 不触发延迟、无 pip 操作
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir,
                   "etcpak==0.9.8 # old comment\n",
                   source_dir, "etcpak==0.9.8 # new comment\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result.success is True
    assert calls == []
    assert not pending_path.exists()


def test_install_requirements_no_diff_returns_true(monkeypatch, updater, tmp_path, pending_path):
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir, "keep==2.0\n",
                   source_dir, "keep==2.0\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result.success is True
    assert calls == []
    assert not pending_path.exists()


def test_install_requirements_always_skips_uninstall(
        monkeypatch, updater, tmp_path, pending_path):
    # 不再提供删除旧依赖的配置，移除项始终保留。
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir, "old==1.0\n",
                   source_dir, "new==1.0\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result.success is True
    assert calls == [[sys.executable, "-m", "pip", "install", "new==1.0"]]
    assert not pending_path.exists()


def test_install_requirements_missing_file_returns_false(updater, tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    _write_req(app_dir / "requirements.txt", "keep==2.0\n")
    source_dir = tmp_path / "empty"
    source_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)

    assert not updater.install_requirements(source_dir)


def test_install_requirements_non_network_failure_moves_only_item_to_pending(
        monkeypatch, updater, tmp_path, pending_path):
    # 文件占用、权限或构建失败等非网络错误才允许进入 pending。
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = []

    def fake_check_call(cmd, **kw):
        calls.append(cmd)
        raise subprocess.CalledProcessError(
            1, cmd, stderr=b"Permission denied while replacing extension.pyd")

    _write_req(app_dir / "requirements.txt", "keep==2.0\n")
    _write_req(source_dir / "requirements.txt", "keep==2.0\nfresh==3.0\n")
    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(update_mod, "_pending_ops_default_path",
                        lambda: pending_path)

    updater.modal_id = "modal-test"
    result = updater.install_requirements(source_dir)

    assert result.success is True
    assert result.pending_specs == ["fresh==3.0"]
    assert calls == [[sys.executable, "-m", "pip", "install", "fresh==3.0"]]
    assert json.loads(pending_path.read_text(encoding="utf-8")) == {
        "uninstall": [],
        "install": ["fresh==3.0"],
    }


def test_install_requirements_non_gui_failure_never_creates_pending(
        monkeypatch, updater, tmp_path, pending_path):
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    _write_req(app_dir / "requirements.txt", "keep==2.0\n")
    _write_req(source_dir / "requirements.txt", "keep==2.0\nfresh==3.0\n")

    def fake_check_call(cmd, **kw):
        raise subprocess.CalledProcessError(
            1, cmd, stderr=b"Permission denied while replacing extension.pyd")

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(update_mod, "_pending_ops_default_path",
                        lambda: pending_path)

    result = updater.install_requirements(source_dir)

    assert result.success is False
    assert "不在 GUI 更新流程" in result.message
    assert not pending_path.exists()


def test_install_requirements_network_failure_retries_tsinghua(
        monkeypatch, updater, tmp_path, pending_path):
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    _write_req(app_dir / "requirements.txt", "keep==2.0\n")
    _write_req(source_dir / "requirements.txt", "keep==2.0\nfresh==3.0\n")
    calls = []

    def fake_check_call(cmd, **kw):
        calls.append(cmd)
        if "--index-url" not in cmd:
            raise subprocess.CalledProcessError(
                1, cmd, stderr=b"ProxyError: Cannot connect to proxy")

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(update_mod, "_pending_ops_default_path",
                        lambda: pending_path)

    result = updater.install_requirements(source_dir)

    assert result.success is True
    assert calls == [
        [sys.executable, "-m", "pip", "install", "fresh==3.0"],
        [
            sys.executable, "-m", "pip", "install", "--index-url",
            ppo._TSINGHUA_PYPI_INDEX, "fresh==3.0",
        ],
    ]
    assert not pending_path.exists()


def test_install_requirements_double_source_failure_stops_without_pending(
        monkeypatch, updater, tmp_path, pending_path):
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    _write_req(app_dir / "requirements.txt", "keep==2.0\n")
    _write_req(source_dir / "requirements.txt", "keep==2.0\nfresh==3.0\n")
    calls = []

    def fake_check_call(cmd, **kw):
        calls.append(cmd)
        raise subprocess.CalledProcessError(
            1, cmd, stderr=b"ProxyError: Cannot connect to proxy")

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(update_mod, "_pending_ops_default_path",
                        lambda: pending_path)

    result = updater.install_requirements(source_dir)

    assert result.success is False
    assert result.network_blocked is True
    assert "关闭系统代理" in result.message
    assert len(calls) == 2
    assert not pending_path.exists()


# ========== pending 持久化与启动钩子 ==========

def test_save_pending_ops_removes_file_when_empty(tmp_path):
    path = tmp_path / "ops.json"
    update_mod.save_pending_ops({"uninstall": ["a"], "install": ["b"]}, path)
    assert path.exists()
    assert update_mod.save_pending_ops(
        {"uninstall": [], "install": []}, path) is True
    assert not path.exists()


def test_save_pending_ops_dedups_and_keeps_order(tmp_path):
    path = tmp_path / "ops.json"
    update_mod.save_pending_ops(
        {"uninstall": ["b", "a", "b"], "install": ["x", "y", "x"]}, path)
    ops = json.loads(path.read_text(encoding="utf-8"))
    assert ops == {"uninstall": [], "install": ["x", "y"]}


def test_load_pending_ops_missing_file_returns_empty(tmp_path):
    assert update_mod.load_pending_ops(
        tmp_path / "nope.json") == {"uninstall": [], "install": []}


def test_apply_pending_pip_ops_ignores_legacy_uninstall(monkeypatch, tmp_path, pending_path):
    pending_path.write_text(json.dumps({
        "uninstall": ["olddep"],
        "install": ["fresh==3.0"],
    }), encoding="utf-8")
    calls = []
    monkeypatch.setattr(subprocess, "check_call", lambda cmd, **kw: calls.append(cmd))

    result = update_mod.apply_pending_pip_ops(pending_path)

    assert result is True
    assert not pending_path.exists()
    assert calls == [[sys.executable, "-m", "pip", "install", "fresh==3.0"]]


def test_apply_pending_pip_ops_keeps_remaining_on_failure(
        monkeypatch, tmp_path, pending_path):
    ops = {"uninstall": ["a", "b"], "install": ["c", "d"]}
    update_mod.save_pending_ops(ops, pending_path)
    calls = []

    def fake_check_call(cmd, **kw):
        calls.append(cmd)
        if cmd[-1] == "c":
            raise subprocess.CalledProcessError(
                1, cmd, stderr=b"Permission denied")

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    result = update_mod.apply_pending_pip_ops(pending_path)

    assert result is False
    remaining = json.loads(pending_path.read_text(encoding="utf-8"))
    assert remaining["uninstall"] == []
    assert remaining["install"] == ["c"]
    # 历史卸载项被忽略，d 已成功安装，不得再次执行。
    assert calls == [
        [sys.executable, "-m", "pip", "install", "c"],
        [sys.executable, "-m", "pip", "install", "d"],
    ]


def test_apply_pending_pip_ops_empty_pending_is_noop(monkeypatch, tmp_path, pending_path):
    calls = []
    monkeypatch.setattr(subprocess, "check_call", lambda cmd, **kw: calls.append(cmd))
    assert update_mod.apply_pending_pip_ops(pending_path) is True
    assert calls == []


def test_install_requirements_spec_case_only_diff_is_not_a_bump(
        monkeypatch, updater, tmp_path, pending_path):
    # spec 行仅包名大小写差异（PEP 503 等价）不构成版本变动 → 不触发延迟、
    # 无 pip 操作（避免仅格式差异误入 pending）
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir, "Foo_Bar.1==2.0\n",
                   source_dir, "foo-bar-1==2.0\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result.success is True
    assert calls == []
    assert not pending_path.exists()


def test_install_requirements_spec_whitespace_diff_is_not_a_bump(
        monkeypatch, updater, tmp_path, pending_path):
    # 行首尾空白差异不构成版本变动（解析阶段已 strip，此处兜底）
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir, "  pillow==10.4.0\n",
                   source_dir, "pillow==10.4.0\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result.success is True
    assert calls == []
    assert not pending_path.exists()


# ========== spec 归一化辅助 ==========

def test_normalize_spec_normalizes_name_case():
    assert ppo._normalize_spec("Foo_Bar.1==2.0") == "foo-bar-1==2.0"
    assert ppo._normalize_spec("  PyWebView==6.2.1  ") == "pywebview==6.2.1"
    assert ppo._normalize_spec("requests") == "requests"
    # 版本约束与其余字符保持原样
    assert ppo._normalize_spec("pywebview==6.2.1") == "pywebview==6.2.1"


# ========== pip 子进程健壮性 ==========

def test_run_pip_utf8_env_and_gbk_stderr_fallback(monkeypatch):
    # pip 子进程应注入 PYTHONIOENCODING=utf-8；GBK 编码的 stderr
    # 应回退解码成功，不产生异常、不抛出 UnicodeDecodeError
    calls = []

    def fake_check_call(cmd, **kw):
        calls.append((cmd, kw.get("env", {})))
        err = "错误：找不到包".encode("gbk")
        raise subprocess.CalledProcessError(1, cmd, stderr=err)

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(ppo, "_log_manager", _LogStub())

    result = ppo._run_pip(["install", "nope"])
    assert not result
    assert result.network_error is False
    cmd, env = calls[0]
    assert cmd[:3] == [sys.executable, "-m", "pip"]
    assert env.get("PYTHONIOENCODING") == "utf-8"


def test_run_pip_utf8_stderr_passthrough(monkeypatch):
    # UTF-8 stderr 按原样解码，不回退到 GBK 导致二次乱码
    messages = []

    class _Log:
        def log(self, msg):
            messages.append(msg)

    def fake_check_call(cmd, **kw):
        raise subprocess.CalledProcessError(
            1, cmd, stderr="distutils 被移除".encode("utf-8"))

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(ppo, "_log_manager", _Log())

    result = ppo._run_pip(["install", "x"])
    assert not result
    assert result.network_error is False
    assert any("distutils 被移除" in m for m in messages)


def test_run_pip_classifies_proxy_failure_as_network(monkeypatch):
    def fake_check_call(cmd, **kw):
        raise subprocess.CalledProcessError(
            1, cmd, stderr=b"ProxyError: Cannot connect to proxy")

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(ppo, "_log_manager", _LogStub())

    result = ppo._run_pip(["install", "x"])

    assert result.success is False
    assert result.network_error is True


# ========== 启动钩子导入链纯标准库 ==========

def test_pending_pip_ops_import_chain_is_stdlib_only():
    # start_webui.py init_env() 在加载任何第三方库之前导入本模块执行 pending；
    # 一旦导入链引入第三方包（或 webutils 包），"库缺失"状态会阻断执行
    code = (
        "import globalManagers.pending_pip_ops\n"
        "import sys\n"
        "banned = {'requests', 'UnityPy', 'pywebview', 'openspeedy', "
        "'translatekit', 'webutils', 'webui', 'webFunc'}\n"
        "tops = {m.split('.')[0] for m in sys.modules}\n"
        "assert not (tops & banned), sorted(tops & banned)\n"
    )
    root = _repo_root()
    subprocess.check_call([sys.executable, "-c", code], cwd=str(root))


def test_update_module_re_exports_pending_api():
    # webutils.update 迁移后 re-export 同名符号，保持既有调用方/测试兼容
    from webutils.update import (
        apply_pending_pip_ops,
        load_pending_ops,
        save_pending_ops,
        _pending_ops_default_path,
        _parse_requirements,
    )
    assert callable(apply_pending_pip_ops)
    assert callable(load_pending_ops)
    assert callable(save_pending_ops)
    assert callable(_parse_requirements)


# ========== check_and_update：缓存目录迁移 ==========

class _StubAsset:
    download_url = "https://example.com/LCTA-update.zip"
    size = 42


class _StubRelease:
    tag_name = "9.9.9"
    name = "v9.9.9"
    body = "release body"
    prerelease = False
    draft = False
    assets = [_StubAsset()]

    def get_asset_by_name(self, name):
        return self.assets[0]


class _StubRequester:
    @classmethod
    def update_config(cls, use_proxy):
        return None

    @classmethod
    def get_latest_release(cls, owner, repo):
        return _StubRelease()


def test_check_and_update_uses_external_cache_dir(monkeypatch, tmp_path, updater):
    # 缓存位于应用目录外的临时目录：update_files 清空应用目录后复制不受影响，
    # 且流程结束（成功/失败）后缓存目录被清理
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    _write_req(app_dir / "requirements.txt", "requests\n")
    (app_dir / "oldfile.txt").write_text("old", encoding="utf-8")

    src_dir = tmp_path / "pkg"
    src_dir.mkdir()
    _write_req(src_dir / "requirements.txt", "requests\n")
    (src_dir / "newfile.txt").write_text("new", encoding="utf-8")

    zip_path = tmp_path / "LCTA-update.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src_dir.iterdir():
            zf.write(f, f.name)

    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(update_mod.tempfile, "mkdtemp", lambda **kw: str(cache_dir))
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(
        update_mod.GithubDownload, "GithubRequester", _StubRequester)
    monkeypatch.setattr(updater, "download_latest_release",
                        lambda cache_dir_, release_info: str(zip_path))
    monkeypatch.setattr(updater, "install_requirements", lambda source_dir: True)

    result = updater.check_and_update("1.0.0")

    assert result is True
    assert (app_dir / "newfile.txt").read_text(encoding="utf-8") == "new"
    assert not (app_dir / "oldfile.txt").exists()
    assert not cache_dir.exists(), "缓存目录应在流程结束后被清理"


def test_check_and_update_cleans_cache_on_failure(monkeypatch, tmp_path, updater):
    # 更新文件失败时缓存目录同样被 finally 清理
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    _write_req(app_dir / "requirements.txt", "requests\n")

    src_dir = tmp_path / "pkg"
    src_dir.mkdir()
    _write_req(src_dir / "requirements.txt", "requests\n")

    zip_path = tmp_path / "LCTA-update.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src_dir.iterdir():
            zf.write(f, f.name)

    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(update_mod.tempfile, "mkdtemp", lambda **kw: str(cache_dir))
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(
        update_mod.GithubDownload, "GithubRequester", _StubRequester)
    monkeypatch.setattr(updater, "download_latest_release",
                        lambda cache_dir_, release_info: str(zip_path))
    monkeypatch.setattr(updater, "install_requirements", lambda source_dir: True)
    monkeypatch.setattr(updater, "update_files", lambda source_dir: False)

    result = updater.check_and_update("1.0.0")

    assert result is False
    assert not cache_dir.exists(), "失败路径也应清理缓存目录"


def test_check_and_update_keeps_custom_cache_dir(monkeypatch, tmp_path, updater):
    # F-9.3：调用方传入的自定义缓存目录不得被 finally 删除，仅清理内部自建目录
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    _write_req(app_dir / "requirements.txt", "requests\n")

    src_dir = tmp_path / "pkg"
    src_dir.mkdir()
    _write_req(src_dir / "requirements.txt", "requests\n")
    (src_dir / "newfile.txt").write_text("new", encoding="utf-8")

    zip_path = tmp_path / "LCTA-update.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src_dir.iterdir():
            zf.write(f, f.name)

    custom_cache = tmp_path / "my-cache"
    custom_cache.mkdir()
    (custom_cache / "keep.txt").write_text("keep", encoding="utf-8")

    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(
        update_mod.GithubDownload, "GithubRequester", _StubRequester)
    monkeypatch.setattr(updater, "download_latest_release",
                        lambda cache_dir_, release_info: str(zip_path))
    monkeypatch.setattr(updater, "install_requirements", lambda source_dir: True)

    result = updater.check_and_update("1.0.0", str(custom_cache))

    assert result is True
    assert (custom_cache / "keep.txt").exists(), "自定义缓存目录不应被删除"


def test_check_and_update_restores_pending_when_update_files_fails(
        monkeypatch, tmp_path, updater, pending_path):
    # install_requirements 写入非网络失败安装项后，文件替换失败必须还原 pending。
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    _write_req(app_dir / "requirements.txt", "olddep==1.0\n")

    src_dir = tmp_path / "pkg"
    src_dir.mkdir()
    _write_req(src_dir / "requirements.txt", "newdep==1.0\n")

    zip_path = tmp_path / "LCTA-update.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src_dir.iterdir():
            zf.write(f, f.name)

    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(update_mod.tempfile, "mkdtemp", lambda **kw: str(cache_dir))
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(update_mod, "_pending_ops_default_path",
                        lambda: pending_path)
    monkeypatch.setattr(
        update_mod.GithubDownload, "GithubRequester", _StubRequester)
    monkeypatch.setattr(updater, "download_latest_release",
                        lambda cache_dir_, release_info: str(zip_path))
    monkeypatch.setattr(updater, "update_files", lambda source_dir: False)
    updater.modal_id = "modal-test"

    def fail_non_network(cmd, **kw):
        raise subprocess.CalledProcessError(
            1, cmd, stderr=b"Permission denied while replacing extension.pyd")

    monkeypatch.setattr(subprocess, "check_call", fail_non_network)

    result = updater.check_and_update("1.0.0")

    assert result is False
    assert not pending_path.exists(), "更新失败后 pending 不得保留"
    assert not cache_dir.exists()


def test_check_and_update_keeps_pending_when_update_succeeds(
        monkeypatch, tmp_path, updater, pending_path):
    # 对照：更新成功后 pending 保留，供下次启动执行
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    _write_req(app_dir / "requirements.txt", "olddep==1.0\n")

    src_dir = tmp_path / "pkg"
    src_dir.mkdir()
    _write_req(src_dir / "requirements.txt", "newdep==1.0\n")
    (src_dir / "newfile.txt").write_text("new", encoding="utf-8")

    zip_path = tmp_path / "LCTA-update.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src_dir.iterdir():
            zf.write(f, f.name)

    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(update_mod.tempfile, "mkdtemp", lambda **kw: str(cache_dir))
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(update_mod, "_pending_ops_default_path",
                        lambda: pending_path)
    monkeypatch.setattr(
        update_mod.GithubDownload, "GithubRequester", _StubRequester)
    monkeypatch.setattr(updater, "download_latest_release",
                        lambda cache_dir_, release_info: str(zip_path))
    updater.modal_id = "modal-test"

    def fail_non_network(cmd, **kw):
        raise subprocess.CalledProcessError(
            1, cmd, stderr=b"Permission denied while replacing extension.pyd")

    monkeypatch.setattr(subprocess, "check_call", fail_non_network)

    result = updater.check_and_update("1.0.0")

    assert result is True
    ops = json.loads(pending_path.read_text(encoding="utf-8"))
    assert ops["uninstall"] == []
    assert ops["install"] == ["newdep==1.0"]
    assert not cache_dir.exists()

