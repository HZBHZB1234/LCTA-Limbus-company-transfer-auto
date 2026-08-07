"""
tests/test_cdn_hosts.py
CDN hosts 写入/提权回归测试。

覆盖：
- hosts.py: 标记块追加/替换/移除、编码与 BOM 保留、只读属性处理、
  raise_on_permission_error 语义、_format_hosts_error 文案区分
- elevate.py: 管理员直写、非管理员可写直写、权限失败才触发 UAC 提权、
  非权限失败不提权、UAC 取消文案、提权子进程结果文件
"""
import json
import os
import stat
import sys

import pytest

import webutils.cdn.elevate as elevate_mod
import webutils.cdn.hosts as hosts_mod
from webutils.cdn.constants import (
    CFA_END_MARKER,
    CFA_START_MARKER,
    CF_END_MARKER,
    CF_START_MARKER,
)


# ========== hosts.py: write_hosts 基础行为 ==========

def test_write_hosts_appends_managed_blocks(tmp_path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")

    success, err = hosts_mod.write_hosts(
        cf_ip="1.2.3.4",
        cloudfront_mappings={"www.limbuscompanyapi.com": "5.6.7.8"},
        hosts_path=str(hosts),
    )

    assert success is True
    assert err is None
    content = hosts.read_text(encoding="utf-8")
    assert "127.0.0.1 localhost" in content  # 原内容保留
    assert CF_START_MARKER in content
    assert "1.2.3.4\tdownload.limbuscompanycdn.org" in content
    assert CF_END_MARKER in content
    assert CFA_START_MARKER in content
    assert "5.6.7.8\twww.limbuscompanyapi.com" in content
    assert CFA_END_MARKER in content


def test_write_hosts_replaces_existing_block(tmp_path):
    hosts = tmp_path / "hosts"
    hosts.write_text(
        f"127.0.0.1 localhost\n{CF_START_MARKER}\n9.9.9.9\tdownload.limbuscompanycdn.org\n{CF_END_MARKER}\n",
        encoding="utf-8",
    )

    success, _ = hosts_mod.write_hosts(cf_ip="1.2.3.4", hosts_path=str(hosts))

    assert success is True
    content = hosts.read_text(encoding="utf-8")
    assert "9.9.9.9" not in content  # 旧 IP 被替换
    assert content.count(CF_START_MARKER) == 1  # 不产生重复块
    assert "1.2.3.4\tdownload.limbuscompanycdn.org" in content


def test_write_hosts_removes_block_when_empty(tmp_path):
    hosts = tmp_path / "hosts"
    hosts.write_text(
        f"{CF_START_MARKER}\n9.9.9.9\tdownload.limbuscompanycdn.org\n{CF_END_MARKER}\n",
        encoding="utf-8",
    )

    success, _ = hosts_mod.write_hosts(cf_ip=None, hosts_path=str(hosts))

    assert success is True
    content = hosts.read_text(encoding="utf-8")
    assert CF_START_MARKER not in content


def test_write_hosts_preserves_utf8_bom(tmp_path):
    hosts = tmp_path / "hosts"
    hosts.write_bytes(b"\xef\xbb\xbf" + b"127.0.0.1 localhost\r\n")

    success, _ = hosts_mod.write_hosts(cf_ip="1.2.3.4", hosts_path=str(hosts))

    assert success is True
    raw = hosts.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM 保留
    assert b"1.2.3.4\tdownload.limbuscompanycdn.org" in raw


def test_write_hosts_clears_readonly_before_replace(tmp_path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    os.chmod(str(hosts), stat.S_IREAD)  # 设置只读属性

    success, err = hosts_mod.write_hosts(cf_ip="1.2.3.4", hosts_path=str(hosts))

    assert success is True
    assert err is None
    attrs = os.stat(str(hosts)).st_file_attributes
    assert attrs & stat.FILE_ATTRIBUTE_READONLY == 0  # 只读属性已被清除


def test_write_hosts_permission_error_returns_formatted_by_default(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(hosts_mod, "REPLACE_RETRY_DELAY", 0)

    def fake_replace(src, dst):
        raise PermissionError(13, "拒绝访问", dst)

    monkeypatch.setattr(os, "replace", fake_replace)

    success, err = hosts_mod.write_hosts(cf_ip="1.2.3.4", hosts_path=str(hosts))

    assert success is False
    assert "权限不足" in err
    assert "UAC" in err  # 未提权场景引导 UAC 重试


def test_write_hosts_permission_error_raises_when_requested(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(hosts_mod, "REPLACE_RETRY_DELAY", 0)

    def fake_replace(src, dst):
        raise PermissionError(13, "拒绝访问", dst)

    monkeypatch.setattr(os, "replace", fake_replace)

    with pytest.raises(PermissionError):
        hosts_mod.write_hosts(
            cf_ip="1.2.3.4",
            hosts_path=str(hosts),
            raise_on_permission_error=True,
        )


def test_write_hosts_lock_error_still_formatted_when_requested(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(hosts_mod, "REPLACE_RETRY_DELAY", 0)

    def fake_replace(src, dst):
        raise OSError(32, "另一个程序正在使用此文件", dst)

    monkeypatch.setattr(os, "replace", fake_replace)

    success, err = hosts_mod.write_hosts(
        cf_ip="1.2.3.4",
        hosts_path=str(hosts),
        raise_on_permission_error=True,
    )

    assert success is False
    assert "被其他程序锁定" in err  # 非权限类错误不重抛


def test_format_hosts_error_elevated_wording():
    exc = PermissionError(5, "拒绝访问", "hosts")
    msg = hosts_mod._format_hosts_error(exc, elevated=True)
    assert "已以管理员权限运行" in msg
    assert "只读" in msg
    assert "占用" in msg  # 文案覆盖"被其他程序占用"场景


def test_write_hosts_retries_then_succeeds(tmp_path, monkeypatch):
    """权限类失败一次后重试成功，且最终结果正确。"""
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    monkeypatch.setattr(hosts_mod, "REPLACE_RETRY_DELAY", 0)

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(5, "拒绝访问", dst)
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky_replace)

    success, err = hosts_mod.write_hosts(cf_ip="1.2.3.4", hosts_path=str(hosts))

    assert success is True
    assert err is None
    assert calls["n"] == 2
    assert "1.2.3.4" in hosts.read_text(encoding="utf-8")


def test_write_hosts_retries_exhausted_appends_occupancy_detail(tmp_path, monkeypatch):
    """三次均失败后，附加占用进程的 PID 与路径到错误文案。"""
    hosts = tmp_path / "hosts"
    hosts.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(hosts_mod, "REPLACE_RETRY_DELAY", 0)
    monkeypatch.setattr(
        hosts_mod,
        "_find_locking_processes",
        lambda path: [{"pid": 1234, "name": r"C:\fake\guard.exe"}],
    )

    def fake_replace(src, dst):
        raise OSError(32, "另一个程序正在使用此文件", dst)

    monkeypatch.setattr(os, "replace", fake_replace)

    success, err = hosts_mod.write_hosts(cf_ip="1.2.3.4", hosts_path=str(hosts))

    assert success is False
    assert "被其他程序锁定" in err
    assert "1234" in err
    assert "C:\\fake\\guard.exe" in err


def test_write_hosts_retries_exhausted_no_occupancy_message(tmp_path, monkeypatch):
    """三次均失败且查不到占用进程时，给出兜底提示。"""
    hosts = tmp_path / "hosts"
    hosts.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(hosts_mod, "REPLACE_RETRY_DELAY", 0)
    monkeypatch.setattr(hosts_mod, "_find_locking_processes", lambda path: [])

    def fake_replace(src, dst):
        raise PermissionError(5, "拒绝访问", dst)

    monkeypatch.setattr(os, "replace", fake_replace)

    success, err = hosts_mod.write_hosts(cf_ip="1.2.3.4", hosts_path=str(hosts))

    assert success is False
    assert "未能检测到占用 hosts 文件的进程" in err


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows 支持 Restart Manager")
def test_find_locking_processes_detects_self(tmp_path):
    """Restart Manager 能检测到持有文件句柄的进程（自身），并返回 PID 与路径。"""
    held = tmp_path / "held.txt"
    with held.open("w", encoding="utf-8") as f:
        f.write("hold")
        with held.open("r", encoding="utf-8") as f2:
            procs = hosts_mod._find_locking_processes(str(held))

    assert procs, "应检测到持有句柄的进程"
    assert os.getpid() in {p["pid"] for p in procs}
    assert any("python" in p["name"].lower() for p in procs)


def test_read_current_hosts_mappings(tmp_path):
    hosts = tmp_path / "hosts"
    hosts.write_text(
        f"{CF_START_MARKER}\n1.2.3.4\tdownload.limbuscompanycdn.org\n{CF_END_MARKER}\n"
        f"{CFA_START_MARKER}\n5.6.7.8\twww.limbuscompanyapi.com\n{CFA_END_MARKER}\n",
        encoding="utf-8",
    )

    result = hosts_mod.read_current_hosts_mappings(str(hosts))

    assert result["cf_ip"] == "1.2.3.4"
    assert result["cloudfront"] == {"www.limbuscompanyapi.com": "5.6.7.8"}


# ========== elevate.py: 提权策略 ==========

class _LogStub:
    def __init__(self):
        self.lines = []

    def __call__(self, msg):
        self.lines.append(msg)


def _fake_run_as_admin_writes_result(success=True, message="hosts 写入成功"):
    """模拟提权子进程：调用 _run_as_admin 时同步写入 .result 文件。"""

    def fake(script_path, args):
        assert "--cdn-write-hosts" in args
        request_path = args[1]
        result_path = request_path + ".result"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({"success": success, "message": message}, f)
        return 0

    return fake


def test_elevate_write_admin_direct_no_shell(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    monkeypatch.setattr(elevate_mod, "_is_admin", lambda: True)

    def boom(*a, **k):
        raise AssertionError("管理员直写不应触发 ShellExecuteW")

    monkeypatch.setattr(elevate_mod, "_run_as_admin", boom)

    success, err = elevate_mod.elevate_write_hosts(
        cf_ip="1.2.3.4", hosts_path=str(hosts)
    )

    assert success is True
    assert err is None
    assert "1.2.3.4" in hosts.read_text(encoding="utf-8")


def test_elevate_write_non_admin_writable_direct(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    monkeypatch.setattr(elevate_mod, "_is_admin", lambda: False)

    def boom(*a, **k):
        raise AssertionError("可直写时不应触发 ShellExecuteW")

    monkeypatch.setattr(elevate_mod, "_run_as_admin", boom)

    success, err = elevate_mod.elevate_write_hosts(
        cf_ip="1.2.3.4", hosts_path=str(hosts)
    )

    assert success is True
    assert err is None
    assert "1.2.3.4" in hosts.read_text(encoding="utf-8")


def test_elevate_write_permission_failure_triggers_uac(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(elevate_mod, "_is_admin", lambda: False)
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))  # 请求文件落在 tmp_path 内

    def raise_perm(*a, **k):
        raise PermissionError(13, "拒绝访问", str(hosts))

    monkeypatch.setattr(elevate_mod, "write_hosts", raise_perm)
    monkeypatch.setattr(
        elevate_mod, "_run_as_admin", _fake_run_as_admin_writes_result()
    )
    log = _LogStub()

    success, err = elevate_mod.elevate_write_hosts(
        cf_ip="1.2.3.4", hosts_path=str(hosts), log_cb=log
    )

    assert success is True
    assert err is None
    assert any("请求管理员权限" in line for line in log.lines)
    # 请求/结果临时文件已清理
    assert not [p for p in os.listdir(str(tmp_path)) if p.startswith("lcta_cdn_")]


def test_elevate_write_non_permission_failure_no_uac(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(elevate_mod, "_is_admin", lambda: False)

    def return_locked(*a, **k):
        return False, "hosts 文件被其他程序锁定。\n\n原因：杀毒软件正在保护 hosts 文件。"

    monkeypatch.setattr(elevate_mod, "write_hosts", return_locked)

    def boom(*a, **k):
        raise AssertionError("非权限类失败不应触发 UAC")

    monkeypatch.setattr(elevate_mod, "_run_as_admin", boom)

    success, err = elevate_mod.elevate_write_hosts(
        cf_ip="1.2.3.4", hosts_path=str(hosts)
    )

    assert success is False
    assert "被其他程序锁定" in err


def test_elevate_write_uac_cancelled_message(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(elevate_mod, "_is_admin", lambda: False)

    def raise_perm(*a, **k):
        raise PermissionError(13, "拒绝访问", str(hosts))

    monkeypatch.setattr(elevate_mod, "write_hosts", raise_perm)

    def raise_cancel(*a, **k):
        raise OSError("提权失败（用户可能取消了 UAC 弹窗）：ShellExecuteW 返回错误码：1223")

    monkeypatch.setattr(elevate_mod, "_run_as_admin", raise_cancel)
    log = _LogStub()

    success, err = elevate_mod.elevate_write_hosts(
        cf_ip="1.2.3.4", hosts_path=str(hosts), log_cb=log
    )

    assert success is False
    assert "UAC" in err
    assert "取消" in err


def test_elevate_remove_permission_failure_triggers_uac(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text(
        f"{CF_START_MARKER}\n1.2.3.4\tdownload.limbuscompanycdn.org\n{CF_END_MARKER}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(elevate_mod, "_is_admin", lambda: False)

    def raise_perm(*a, **k):
        raise PermissionError(13, "拒绝访问", str(hosts))

    monkeypatch.setattr(elevate_mod, "remove_hosts_block", raise_perm)
    monkeypatch.setattr(
        elevate_mod, "_run_as_admin",
        _fake_run_as_admin_writes_result(success=True, message="cf hosts 移除成功"),
    )

    success, err = elevate_mod.elevate_remove_hosts("cf", hosts_path=str(hosts))

    assert success is True
    assert err is None


def test_helper_invocation_writes_result_file(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    request_path = tmp_path / "lcta_cdn_request.json"
    with open(request_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "action": "write_hosts",
                "cf_ip": "1.2.3.4",
                "cloudfront_mappings": {},
                "hosts_path": str(hosts),
            },
            f,
        )

    monkeypatch.setattr(
        sys, "argv", ["elevate.py", "--cdn-write-hosts", str(request_path)]
    )

    with pytest.raises(SystemExit):
        elevate_mod._handle_helper_invocation()

    result_path = str(request_path) + ".result"
    with open(result_path, "r", encoding="utf-8") as f:
        result = json.load(f)
    assert result["success"] is True
    assert "1.2.3.4" in hosts.read_text(encoding="utf-8")
