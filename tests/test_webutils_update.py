"""
tests/test_webutils_update.py
webutils.update 修复回归测试。
覆盖：
- compare_versions 逐段整数比较（不再拼接整数），跨大版本与小版本号段位差正确判定
- v 前缀与非数字段容错
- install_requirements 按包名比对：涉及移除/版本变动 → 整个依赖修改延迟到下次启动
  （写入 pending，本次不执行任何 pip 操作）；仅全新依赖 → 立即安装，失败跳过继续
- pending 持久化与 apply_pending_pip_ops 启动钩子（先卸载后安装、成功清空、失败保留）
- check_and_update 缓存迁移到应用目录外的临时目录并在 finally 中清理
"""
import json
import subprocess
import sys
import zipfile

import pytest

import webutils.update as update_mod
from webutils.update import Updater


class _LogStub:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


@pytest.fixture
def updater(monkeypatch):
    monkeypatch.setattr(update_mod, "_log_manager", _LogStub())
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
           pending_path, delete_old_files=True):
    _write_req(app_dir / "requirements.txt", old_req)
    _write_req(source_dir / "requirements.txt", new_req)
    updater.delete_old_files = delete_old_files
    calls = []
    monkeypatch.setattr(subprocess, "check_call", lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(update_mod, "_pending_ops_default_path",
                        lambda: pending_path)
    return calls


def test_install_requirements_defers_removal_to_next_start(
        monkeypatch, updater, tmp_path, pending_path):
    # 涉及移除依赖：整个依赖修改（卸载+安装）进 pending，本次无任何 pip 操作
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir, "olddep==1.0\nkeep==2.0\n",
                   source_dir, "keep==2.0\nfresh==3.0\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result is True
    assert calls == []
    ops = json.loads(pending_path.read_text(encoding="utf-8"))
    assert sorted(ops["uninstall"]) == ["olddep"]
    assert sorted(ops["install"]) == ["fresh==3.0"]


def test_install_requirements_defers_version_bump_to_next_start(
        monkeypatch, updater, tmp_path, pending_path):
    # 版本 pin 变更（升级）：同样延迟到下次启动，本次无 pip 操作
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir, "pywebview==6.2.1\n",
                   source_dir, "pywebview==6.3.0\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result is True
    assert calls == []
    ops = json.loads(pending_path.read_text(encoding="utf-8"))
    assert ops["uninstall"] == []
    assert ops["install"] == ["pywebview==6.3.0"]


def test_install_requirements_comment_change_is_not_a_bump(
        monkeypatch, updater, tmp_path, pending_path):
    # 行内注释差异在去除注释后不构成 spec 变化 → 不触发延迟、无 pip 操作
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir,
                   "etcpak==0.9.8 # old comment\n",
                   source_dir, "etcpak==0.9.8 # new comment\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result is True
    assert calls == []
    assert not pending_path.exists()


def test_install_requirements_no_diff_returns_true(monkeypatch, updater, tmp_path, pending_path):
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir, "keep==2.0\n",
                   source_dir, "keep==2.0\n", pending_path)

    result = updater.install_requirements(source_dir)

    assert result is True
    assert calls == []
    assert not pending_path.exists()


def test_install_requirements_keep_old_files_skips_uninstall(
        monkeypatch, updater, tmp_path, pending_path):
    # delete_old_files=False：移除项不卸载、不触发延迟；全新依赖立即安装
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = _setup(monkeypatch, updater, app_dir, "old==1.0\n",
                   source_dir, "new==1.0\n", pending_path,
                   delete_old_files=False)

    result = updater.install_requirements(source_dir)

    assert result is True
    assert calls == [[sys.executable, "-m", "pip", "install", "new==1.0"]]
    assert not pending_path.exists()


def test_install_requirements_missing_file_returns_false(updater, tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    _write_req(app_dir / "requirements.txt", "keep==2.0\n")
    source_dir = tmp_path / "empty"
    source_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)

    assert updater.install_requirements(source_dir) is False


def test_install_requirements_fresh_install_failure_skips_and_continues(
        monkeypatch, updater, tmp_path, pending_path):
    # 仅全新依赖：立即安装；失败仅记日志，跳过该依赖继续，不中断更新
    app_dir = tmp_path / "app"
    source_dir = tmp_path / "src"
    calls = []

    def fake_check_call(cmd, **kw):
        calls.append(cmd)
        raise subprocess.CalledProcessError(1, cmd)

    _write_req(app_dir / "requirements.txt", "keep==2.0\n")
    _write_req(source_dir / "requirements.txt", "keep==2.0\nfresh==3.0\n")
    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", app_dir)
    monkeypatch.setattr(update_mod, "_pending_ops_default_path",
                        lambda: pending_path)

    result = updater.install_requirements(source_dir)

    assert result is True
    assert calls == [[sys.executable, "-m", "pip", "install", "fresh==3.0"]]
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
    assert ops == {"uninstall": ["b", "a"], "install": ["x", "y"]}


def test_load_pending_ops_missing_file_returns_empty(tmp_path):
    assert update_mod.load_pending_ops(
        tmp_path / "nope.json") == {"uninstall": [], "install": []}


def test_apply_pending_pip_ops_uninstall_then_install(monkeypatch, tmp_path, pending_path):
    ops = {"uninstall": ["olddep"], "install": ["fresh==3.0"]}
    update_mod.save_pending_ops(ops, pending_path)
    calls = []
    monkeypatch.setattr(subprocess, "check_call", lambda cmd, **kw: calls.append(cmd))

    result = update_mod.apply_pending_pip_ops(pending_path)

    assert result is True
    assert not pending_path.exists()
    assert calls == [
        [sys.executable, "-m", "pip", "uninstall", "olddep", "-y"],
        [sys.executable, "-m", "pip", "install", "fresh==3.0"],
    ]


def test_apply_pending_pip_ops_keeps_remaining_on_failure(
        monkeypatch, tmp_path, pending_path):
    ops = {"uninstall": ["a", "b"], "install": ["c"]}
    update_mod.save_pending_ops(ops, pending_path)
    calls = []

    def fake_check_call(cmd, **kw):
        calls.append(cmd)
        if cmd[4] == "b":
            raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    result = update_mod.apply_pending_pip_ops(pending_path)

    assert result is False
    remaining = json.loads(pending_path.read_text(encoding="utf-8"))
    assert sorted(remaining["uninstall"]) == ["b"]
    assert remaining["install"] == []
    # a 已成功卸载、c 已成功安装，不得再次执行
    assert calls == [
        [sys.executable, "-m", "pip", "uninstall", "a", "-y"],
        [sys.executable, "-m", "pip", "uninstall", "b", "-y"],
        [sys.executable, "-m", "pip", "install", "c"],
    ]


def test_apply_pending_pip_ops_empty_pending_is_noop(monkeypatch, tmp_path, pending_path):
    calls = []
    monkeypatch.setattr(subprocess, "check_call", lambda cmd, **kw: calls.append(cmd))
    assert update_mod.apply_pending_pip_ops(pending_path) is True
    assert calls == []


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

