import base64
from pathlib import Path

import pytest

import webutils.function_aria2_downloader as dl_module
from resource_updater.core import Aria2Error
from webutils.function_aria2_downloader import (
    Aria2DownloaderManager,
    TERMINAL_STATES,
    derive_display_name,
)


class FakeClient:
    """伪造 aria2 JSON-RPC 客户端：记录调用并返回可编程状态。"""

    def __init__(self):
        self.calls = []
        self.gids = {}
        self.active = []
        self.pause_error_for = set()
        self.remove_error_for = set()
        self.endpoint = "http://127.0.0.1:9999/jsonrpc"

    def _new_gid(self):
        gid = "g{:04x}".format(len(self.calls))
        self.gids[gid] = {
            "status": "active",
            "totalLength": "1000",
            "completedLength": "0",
            "downloadSpeed": "0",
            "errorCode": "0",
            "errorMessage": "",
            "dir": "",
            "files": [],
            "bittorrent": None,
        }
        return gid

    def add_uri(self, url, save_dir, out):
        self.calls.append(("add_uri", url, str(save_dir), out))
        return self._new_gid()

    def add_torrent(self, torrent_b64, save_dir):
        self.calls.append(("add_torrent", torrent_b64, str(save_dir)))
        return self._new_gid()

    def status(self, gid):
        return dict(self.gids[gid])

    def tell_active(self):
        return list(self.active)

    def pause(self, gid):
        self.calls.append(("pause", gid))
        if gid in self.pause_error_for:
            raise Aria2Error("无法暂停")

    def force_pause(self, gid):
        self.calls.append(("force_pause", gid))

    def unpause(self, gid):
        self.calls.append(("unpause", gid))

    def remove(self, gid):
        self.calls.append(("remove", gid))
        if gid in self.remove_error_for:
            raise Aria2Error("无法移除")

    def force_remove(self, gid):
        self.calls.append(("force_remove", gid))

    def remove_result(self, gid):
        self.calls.append(("remove_result", gid))

    def pause_all(self):
        self.calls.append(("pause_all",))

    def unpause_all(self):
        self.calls.append(("unpause_all",))

    def purge_results(self):
        self.calls.append(("purge_results",))


def make_manager(fake=None):
    mgr = Aria2DownloaderManager()
    mgr._client = fake or FakeClient()
    return mgr


# ---- URL 解析 ----

def test_derive_display_name_strips_query_and_quotes():
    assert derive_display_name("https://a.com/b/file.zip?v=1") == "file.zip"
    assert derive_display_name("https://a.com/b/%E6%B5%8B%E8%AF%95.json") == "测试.json"
    assert derive_display_name("https://a.com/") is None
    assert derive_display_name("https://a.com/..") is None


# ---- add_urls ----

def test_add_urls_validates_schemes_and_dedups(tmp_path):
    fake = FakeClient()
    mgr = make_manager(fake)
    save_dir = tmp_path / "dl"
    save_dir.mkdir()

    result = mgr.add_urls([
        "  https://a.com/x.zip  ",
        "http://b.com/y",
        "ftp://c.com/z",
        "magnet:?xt=urn:btih:aaaa",
        "not-a-url",
        "javascript:alert(1)",
        "https://a.com/x.zip",
        "",
    ], str(save_dir))

    assert result["success"] is True
    assert len(result["added"]) == 4
    kinds = {item["url"]: item["kind"] for item in result["added"]}
    assert kinds["magnet:?xt=urn:btih:aaaa"] == "magnet"
    assert kinds["https://a.com/x.zip"] == "http"
    assert len(result["errors"]) == 2
    assert result["errors"][0]["url"] == "not-a-url"
    # 去重 + 空白行过滤：提交 4 次
    assert len([c for c in fake.calls if c[0] == "add_uri"]) == 4
    # 不再强制 out：http 与 magnet 均由 aria2 原生命名（Content-Disposition 优先）
    for call in fake.calls:
        if call[0] == "add_uri":
            assert call[3] is None


def test_add_urls_rejects_missing_save_dir(tmp_path):
    fake = FakeClient()
    mgr = make_manager(fake)

    result = mgr.add_urls(["https://a.com/x.zip"], str(tmp_path / "dl"))

    assert result["success"] is False
    assert "保存目录不存在" in result["message"]
    assert fake.calls == []
    assert mgr._tasks == {}


def test_add_urls_requires_started_server(tmp_path):
    mgr = Aria2DownloaderManager()
    with pytest.raises(Aria2Error):
        mgr.add_urls(["https://a.com/x"], str(tmp_path))


def test_add_urls_error_reported_per_line(tmp_path):
    fake = FakeClient()

    class FlakyClient(FakeClient):
        def add_uri(self, url, save_dir, out):
            if "bad" in url:
                raise Aria2Error("服务器拒绝")
            return super().add_uri(url, save_dir, out)

    mgr = make_manager(FlakyClient())
    save_dir = tmp_path / "dl"
    save_dir.mkdir()
    result = mgr.add_urls(["https://a.com/ok.zip", "https://a.com/bad.zip"], str(save_dir))

    assert len(result["added"]) == 1
    assert result["errors"] == [{
        "url": "https://a.com/bad.zip",
        "error": "提交失败: 服务器拒绝",
    }]


# ---- add_torrent ----

def test_add_torrent_requires_existing_torrent_file(tmp_path):
    mgr = make_manager()
    assert mgr.add_torrent(str(tmp_path / "missing.torrent"), str(tmp_path))["success"] is False
    txt = tmp_path / "not-a-torrent.txt"
    txt.write_text("x")
    result = mgr.add_torrent(str(txt), str(tmp_path))
    assert result["success"] is False
    assert "仅支持 .torrent" in result["message"]


def test_add_torrent_sends_base64_content(tmp_path):
    fake = FakeClient()
    mgr = make_manager(fake)
    torrent = tmp_path / "test.torrent"
    payload = b"\xd1\x00\x00\x00torrent-bytes"
    torrent.write_bytes(payload)
    save_dir = tmp_path / "dl"
    save_dir.mkdir()

    result = mgr.add_torrent(str(torrent), str(save_dir))

    assert result["success"] is True
    call = [c for c in fake.calls if c[0] == "add_torrent"][0]
    assert base64.b64decode(call[1]) == payload
    assert call[2] == str(save_dir)
    task = mgr._tasks[result["gid"]]
    assert task["kind"] == "torrent"


def test_add_torrent_rejects_missing_save_dir(tmp_path):
    fake = FakeClient()
    mgr = make_manager(fake)
    torrent = tmp_path / "test.torrent"
    torrent.write_bytes(b"torrent")

    result = mgr.add_torrent(str(torrent), str(tmp_path / "dl"))

    assert result["success"] is False
    assert "保存目录不存在" in result["message"]
    assert mgr._tasks == {}


# ---- pause / resume / remove ----

def test_pause_falls_back_to_force_pause():
    fake = FakeClient()
    mgr = make_manager(fake)
    gid = mgr.add_urls(["https://a.com/x.zip"], str(Path(".").resolve()))["added"][0]["gid"]
    fake.pause_error_for.add(gid)

    result = mgr.pause(gid)

    assert result["success"] is True
    assert ("pause", gid) in fake.calls
    assert ("force_pause", gid) in fake.calls


def test_resume_calls_unpause():
    fake = FakeClient()
    mgr = make_manager(fake)
    gid = mgr.add_urls(["https://a.com/x.zip"], str(Path(".").resolve()))["added"][0]["gid"]

    result = mgr.resume(gid)

    assert result["success"] is True
    assert ("unpause", gid) in fake.calls


def test_remove_falls_back_through_force_remove_and_result():
    fake = FakeClient()
    mgr = make_manager(fake)
    gid = mgr.add_urls(["https://a.com/x.zip"], str(Path(".").resolve()))["added"][0]["gid"]
    fake.remove_error_for.add(gid)
    # force_remove 也失败 → 走 removeDownloadResult
    def failing_force_remove(g):
        fake.calls.append(("force_remove", g))
        raise Aria2Error("无法强制移除")

    fake.force_remove = failing_force_remove

    result = mgr.remove(gid)

    assert result["success"] is True
    assert gid not in mgr._tasks
    assert ("remove", gid) in fake.calls
    assert ("force_remove", gid) in fake.calls
    assert ("remove_result", gid) in fake.calls


def test_remove_unknown_task_returns_error():
    mgr = make_manager()
    result = mgr.remove("nope")
    assert result["success"] is False
    assert "任务不存在" in result["message"]


# ---- purge ----

def test_purge_completed_removes_terminal_tasks(tmp_path):
    fake = FakeClient()
    mgr = make_manager(fake)
    save_dir = tmp_path / "dl"
    save_dir.mkdir()
    result = mgr.add_urls(["https://a.com/one.zip", "https://a.com/two.zip"], str(save_dir))
    gid_ok, gid_waiting = [item["gid"] for item in result["added"]]
    fake.gids[gid_ok]["status"] = "complete"
    fake.gids[gid_waiting]["status"] = "active"
    mgr.snapshot()  # 轮询同步任务状态（真实流程由后台线程完成）

    mgr.purge_completed()

    assert gid_ok not in mgr._tasks
    assert gid_waiting in mgr._tasks
    assert ("remove_result", gid_ok) in fake.calls
    assert ("purge_results",) in fake.calls


# ---- snapshot ----

def test_snapshot_aggregates_statuses_and_counts(tmp_path):
    fake = FakeClient()
    mgr = make_manager(fake)
    save_dir = tmp_path / "dl"
    save_dir.mkdir()
    result = mgr.add_urls(["https://a.com/one.zip", "https://a.com/two.zip"], str(save_dir))
    gids = [item["gid"] for item in result["added"]]
    fake.gids[gids[0]].update({
        "status": "active",
        "totalLength": "1000",
        "completedLength": "250",
        "downloadSpeed": "5000",
    })
    fake.gids[gids[1]].update({
        "status": "error",
        "totalLength": "0",
        "completedLength": "0",
        "downloadSpeed": "0",
        "errorCode": "22",
        "errorMessage": "HTTP 404",
    })
    fake.active = [{"gid": gids[0], "dir": str(save_dir), "status": "active"}]

    snapshot = mgr.snapshot()

    assert snapshot["available"] is True
    assert snapshot["server_running"] is True
    assert snapshot["counts"]["active"] == 1
    assert snapshot["counts"]["error"] == 1
    assert snapshot["counts"]["total"] == 2
    assert snapshot["total_speed"] == 5000
    by_gid = {t["gid"]: t for t in snapshot["tasks"]}
    assert by_gid[gids[0]]["pct"] == 25.0
    assert by_gid[gids[0]]["name"] == "one.zip"
    assert by_gid[gids[1]]["status"] == "error"
    assert by_gid[gids[1]]["error_message"] == "HTTP 404"


def test_snapshot_reports_server_stopped():
    mgr = Aria2DownloaderManager()
    mgr._client = FakeClient()
    mgr._client.endpoint = None
    snapshot = mgr.snapshot()
    assert snapshot["server_running"] is False


def test_http_task_display_name_from_resolved_path(tmp_path):
    fake = FakeClient()
    mgr = make_manager(fake)
    save_dir = tmp_path / "dl"
    save_dir.mkdir()
    result = mgr.add_urls(["https://objects.githubusercontent.com/uuid-segment"], str(save_dir))
    gid = result["added"][0]["gid"]
    # aria2 按 Content-Disposition 解析出的真实落盘名出现在 files[0].path
    fake.gids[gid].update({
        "status": "active",
        "files": [{"path": str(save_dir / "真实文件名.zip")}],
    })
    fake.active = [{"gid": gid, "dir": str(save_dir), "status": "active"}]

    snapshot = mgr.snapshot()

    assert snapshot["tasks"][0]["name"] == "真实文件名.zip"


# ---- magnet child adoption ----

def test_magnet_child_adoption(tmp_path):
    fake = FakeClient()
    mgr = make_manager(fake)
    save_dir = tmp_path / "dl"
    save_dir.mkdir()
    result = mgr.add_urls(["magnet:?xt=urn:btih:aaaa"], str(save_dir))
    parent_gid = result["added"][0]["gid"]
    fake.gids[parent_gid]["status"] = "complete"
    fake.active = [{
        "gid": "childgid",
        "dir": str(save_dir),
        "status": "active",
        "totalLength": "500",
        "completedLength": "100",
        "downloadSpeed": "1000",
    }]

    mgr.snapshot()

    assert parent_gid not in mgr._tasks
    child = mgr._tasks["childgid"]
    assert child["kind"] == "magnet"
    assert child["url"] == "magnet:?xt=urn:btih:aaaa"
    assert child["save_dir"] == str(save_dir)


# ---- server lifecycle ----

def test_start_server_reports_missing_binary(monkeypatch):
    monkeypatch.setattr(dl_module, "resolve_aria2_binary", lambda: None)
    mgr = Aria2DownloaderManager()
    result = mgr.start_server()
    assert result["success"] is False
    assert "aria2c" in result["message"]


def test_start_server_idempotent_when_running():
    fake = FakeClient()
    mgr = make_manager(fake)
    result = mgr.start_server()
    assert result["success"] is True


def test_stop_clears_tasks_and_client(tmp_path):
    fake = FakeClient()
    mgr = make_manager(fake)
    save_dir = tmp_path / "dl"
    save_dir.mkdir()
    mgr.add_urls(["https://a.com/x.zip"], str(save_dir))
    assert mgr._tasks

    mgr.stop()

    assert mgr._client is None
    assert mgr._tasks == {}
    assert mgr.is_running() is False


# ---- 默认下载目录解析 ----

def test_get_downloads_dir_falls_back_without_windows(monkeypatch):
    import types
    import webutils.utils.shell as shell_module
    monkeypatch.setattr(shell_module, "os", types.SimpleNamespace(name="posix"))
    result = shell_module.get_downloads_dir()
    assert result == str(Path.home() / "Downloads")
