# -*- coding: utf-8 -*-
"""aria2c 孤儿进程修复验证：

- ChildProcessJob 在 Windows 上能把真实子进程加入 job（父进程退出即被内核杀死）
- Aria2Client / Aria2DlClient 在 start() 绑定 job、stop() 释放，且 stop() 能可靠终止子进程
"""
import subprocess
import sys

import pytest

from webutils.process_job import ChildProcessJob, attach_kill_on_parent_exit

IS_WINDOWS = sys.platform == "win32"


def _spawn_sleeper():
    """启动一个真实存活的 python 子进程，返回 Popen 对象。"""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_child_process_job_constructs_without_error():
    # 任何平台都不应抛异常；非 Windows 上 _handle 为 None
    job = ChildProcessJob()
    if IS_WINDOWS:
        assert job._handle is not None
    else:
        assert job._handle is None
    job.close()


def test_attach_kill_on_parent_exit_return_value():
    proc = _spawn_sleeper()
    try:
        job = attach_kill_on_parent_exit(proc)
        if IS_WINDOWS:
            assert job is not None
            assert job._handle is not None
        else:
            assert job is None
    finally:
        proc.kill()
        if IS_WINDOWS and "job" in dir() and job is not None:
            job.close()


@pytest.mark.skipif(not IS_WINDOWS, reason="Job Object 仅 Windows 可用")
def test_job_assign_and_release_real_child():
    proc = _spawn_sleeper()
    try:
        job = ChildProcessJob()
        # 绑定真实存活子进程应成功
        assert job.assign(proc.pid) is True
        assert proc.poll() is None  # 子进程仍存活
        # 关闭 job 句柄不影响已运行的子进程（父进程未退出）
        job.close()
        assert proc.poll() is None
    finally:
        proc.kill()


@pytest.mark.skipif(not IS_WINDOWS, reason="Job Object 仅 Windows 可用")
def test_job_kills_child_on_handle_close():
    """模拟父进程退出：关闭 job 句柄应导致子进程被内核杀死。"""
    proc = _spawn_sleeper()
    job = ChildProcessJob()
    assert job.assign(proc.pid) is True
    # 子进程此时存活
    assert proc.poll() is None
    # 关闭唯一 job 句柄（等价于父进程退出时内核关闭句柄）
    job.close()
    # 给内核一点时间回收
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("关闭 job 句柄后子进程未被内核杀死")


def test_aria2_client_binds_and_releases_job():
    from resource_updater.core import Aria2Client

    client = Aria2Client(__file__, jobs=1, connection_limit=1)
    proc = _spawn_sleeper()
    try:
        client.process = proc
        # 复刻 start() 中的绑定逻辑
        client._job = ChildProcessJob()
        client._job.assign(client.process.pid)
        if IS_WINDOWS:
            assert client._job._handle is not None
        # stop() 应终止子进程并释放 job
        client.stop()
        assert proc.poll() is not None
        assert client._job is None
    finally:
        if proc.poll() is None:
            proc.kill()


def test_aria2_dl_client_binds_and_releases_job():
    from webutils.function_aria2_downloader import Aria2DlClient

    client = Aria2DlClient(__file__, jobs=1, connection_limit=1)
    proc = _spawn_sleeper()
    try:
        client.process = proc
        client._job = ChildProcessJob()
        client._job.assign(client.process.pid)
        if IS_WINDOWS:
            assert client._job._handle is not None
        client.stop()
        assert proc.poll() is not None
        assert client._job is None
    finally:
        if proc.poll() is None:
            proc.kill()


def test_stop_is_idempotent_when_not_started():
    from resource_updater.core import Aria2Client

    client = Aria2Client(__file__, jobs=1, connection_limit=1)
    # 未启动（process 为 None）时 stop() 不得抛异常
    client.stop()
    assert client._job is None
