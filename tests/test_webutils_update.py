"""
tests/test_webutils_update.py
webutils.update 修复回归测试。
覆盖：
- compare_versions 逐段整数比较（不再拼接整数），跨大版本与小版本号段位差正确判定
- v 前缀与非数字段容错
- install_requirements 卸载全部旧依赖后才返回 True（不再提前返回）
"""
import subprocess

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


# ========== install_requirements ==========

def _write_req(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _split_calls(calls):
    installs = [c[4] for c in calls if c[3] == "install"]
    uninstalls = [c[4] for c in calls if c[3] == "uninstall"]
    return installs, uninstalls


def test_install_requirements_uninstalls_all_old_deps(updater, tmp_path, monkeypatch):
    _write_req(tmp_path / "requirements.txt", "olddep==1.0\nkeep==2.0\n")
    source_dir = tmp_path / "src"
    _write_req(source_dir / "requirements.txt", "keep==2.0\nfresh==3.0\n")
    calls = []
    monkeypatch.setattr(subprocess, "check_call", lambda cmd: calls.append(cmd))
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", tmp_path)

    result = updater.install_requirements(source_dir)

    assert result is True
    installs, uninstalls = _split_calls(calls)
    assert installs == ["fresh==3.0"]
    # 卸载所有旧依赖，而非只卸载第一个
    assert sorted(uninstalls) == ["olddep==1.0"]


def test_install_requirements_no_diff_returns_true(updater, tmp_path, monkeypatch):
    _write_req(tmp_path / "requirements.txt", "keep==2.0\n")
    source_dir = tmp_path / "src"
    _write_req(source_dir / "requirements.txt", "keep==2.0\n")
    monkeypatch.setattr(subprocess, "check_call", lambda cmd: None)
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", tmp_path)

    assert updater.install_requirements(source_dir) is True


def test_install_requirements_keep_old_files_skips_uninstall(updater, tmp_path, monkeypatch):
    _write_req(tmp_path / "requirements.txt", "old==1.0\n")
    source_dir = tmp_path / "src"
    _write_req(source_dir / "requirements.txt", "new==1.0\n")
    calls = []
    monkeypatch.setattr(subprocess, "check_call", lambda cmd: calls.append(cmd))
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", tmp_path)
    updater.delete_old_files = False

    assert updater.install_requirements(source_dir) is True
    installs, uninstalls = _split_calls(calls)
    assert installs == ["new==1.0"]
    assert uninstalls == []


def test_install_requirements_missing_file_returns_false(updater, tmp_path, monkeypatch):
    _write_req(tmp_path / "requirements.txt", "keep==2.0\n")
    source_dir = tmp_path / "empty"
    source_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", tmp_path)

    assert updater.install_requirements(source_dir) is False


def test_install_requirements_returns_true_on_uninstall_error(updater, tmp_path, monkeypatch):
    _write_req(tmp_path / "requirements.txt", "old1==1.0\nold2==2.0\n")
    source_dir = tmp_path / "src"
    _write_req(source_dir / "requirements.txt", "fresh==3.0\n")
    calls = []

    def fake_check_call(cmd):
        calls.append(cmd)
        if cmd[3] == "uninstall":
            raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(update_mod, "APPLICATION_PATH", tmp_path)

    result = updater.install_requirements(source_dir)

    # 卸载出错仅记录日志，仍返回 True 并继续处理其余依赖
    assert result is True
    installs, uninstalls = _split_calls(calls)
    assert sorted(uninstalls) == ["old1==1.0", "old2==2.0"]
    assert installs == ["fresh==3.0"]
