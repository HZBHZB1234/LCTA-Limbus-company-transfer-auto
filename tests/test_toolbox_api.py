# -*- coding: utf-8 -*-
"""P6 API 客户端与下载测试（plan 16.4）。

用本地 HTTP 服务器模拟后端，**不连真实站点**：
验证字段契约（identifier / 无 invite_code / 422 数组解析）、
401 单飞刷新、下载哈希校验、缓存复用与污染检测、拒绝不安全 URL。
"""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from webutils.toolbox import api as api_mod
from webutils.toolbox import download as dl


# ---------------------------------------------------------------------------
# 假后端
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    routes = {}
    calls = []

    def log_message(self, *args):
        pass

    def _handle(self, method):
        _Handler.calls.append((method, self.path, self.headers.get("Authorization")))
        route = _Handler.routes.get((method, self.path.split("?")[0]))
        if route is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"detail":"not found"}')
            return
        status, payload = route(self)
        body = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self._body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        self._handle("POST")


@pytest.fixture()
def server():
    _Handler.routes = {}
    _Handler.calls = []
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture()
def store(tmp_path):
    from webutils.toolbox import session as session_mod

    return session_mod.CredentialStore(tmp_path / "cred.bin")


@pytest.fixture()
def client(server, store):
    return api_mod.ToolboxApi(server, store=store)


# ---------------------------------------------------------------------------
# 契约
# ---------------------------------------------------------------------------


class TestLoginContract:
    def test_login_sends_identifier(self, client):
        """登录必须发 identifier（服务端禁止 username，会 422）。"""
        def route(h):
            body = json.loads(json.dumps(h._body))
            assert "identifier" in body and "username" not in body
            return 200, {"access_token": "a", "refresh_token": "r", "user": {"id": 1}}

        _Handler.routes[("POST", "/api/auth/client/login")] = route
        data = client.login("alice", "pw")
        assert data["access_token"] == "a"
        assert client.current_user()["id"] == 1

    def test_register_sends_no_invite_code(self, client):
        """注册**不能**发 invite_code（服务端 extra=forbid → 422）。"""
        def route(h):
            assert "invite_code" not in h._body
            assert set(h._body) == {"username", "password", "email", "challenge_id", "code"}
            return 201, {"access_token": "a", "refresh_token": "r", "user": {"id": 2}}

        _Handler.routes[("POST", "/api/client/register")] = route
        _Handler.routes[("POST", "/api/auth/client/register")] = route
        client.register("bob", "pw12345678", "b@x.test", "c" * 16, "123456")

    def test_422_array_detail_is_surfaced(self, client):
        """422 的 detail 是**数组**；必须解析成可读文案而不是「点了没反应」。"""
        def route(h):
            return 422, {"detail": [
                {"loc": ["body", "identifier"], "msg": "Field required", "type": "missing"},
            ]}

        _Handler.routes[("POST", "/api/auth/client/login")] = route
        with pytest.raises(api_mod.ApiError) as ei:
            client.login("x", "y")
        assert "identifier" in ei.value.message
        assert ei.value.code == "invalid_request"

    def test_dict_detail_code_and_message(self, client):
        def route(h):
            return 400, {"detail": {"code": "PUZZLE_BAD_ANSWER", "message": "答案不正确"}}

        _Handler.routes[("POST", "/api/toolbox/puzzle/solve")] = route
        client.save_auth({"access_token": "t", "refresh_token": "r"})
        with pytest.raises(api_mod.ApiError) as ei:
            client.solve("c" * 16, "deadbeef")
        assert ei.value.code == "PUZZLE_BAD_ANSWER"
        assert ei.value.message == "答案不正确"

    def test_string_detail(self, client):
        def route(h):
            return 403, {"detail": "账号已被禁用"}

        _Handler.routes[("GET", "/api/toolbox/access")] = route
        client.save_auth({"access_token": "t", "refresh_token": "r"})
        with pytest.raises(api_mod.ApiError) as ei:
            client.access()
        assert ei.value.message == "账号已被禁用"


class TestSessionHandling:
    def test_logout_clears_local_even_if_server_fails(self, client, store):
        client.save_auth({"access_token": "t", "refresh_token": "r"})
        _Handler.routes[("POST", "/api/auth/logout")] = lambda h: (500, {"detail": "boom"})
        client.logout()
        assert not store.has(api_mod.ACCESS_KEY)
        assert not store.has(api_mod.REFRESH_KEY)

    def test_logout_notifies_server(self, client):
        client.save_auth({"access_token": "t", "refresh_token": "r"})
        _Handler.routes[("POST", "/api/auth/logout")] = lambda h: (204, {})
        client.logout()
        assert any(c[1] == "/api/auth/logout" for c in _Handler.calls)

    def test_401_triggers_single_refresh(self, client):
        """401 → 刷新一次 → 重试成功。"""
        state = {"refreshed": 0}

        def protected(h):
            if h.headers.get("Authorization") == "Bearer new-token":
                return 200, {"unlocked": True}
            return 401, {"detail": "expired"}

        def refresh(h):
            state["refreshed"] += 1
            return 200, {"access_token": "new-token", "refresh_token": "new-refresh"}

        _Handler.routes[("GET", "/api/toolbox/access")] = protected
        _Handler.routes[("POST", "/api/auth/client/refresh")] = refresh
        client.save_auth({"access_token": "old", "refresh_token": "r"})

        assert client.access()["unlocked"] is True
        assert state["refreshed"] == 1

    def test_refresh_failure_raises_auth_required(self, client, store):
        _Handler.routes[("GET", "/api/toolbox/access")] = lambda h: (401, {"detail": "expired"})
        _Handler.routes[("POST", "/api/auth/client/refresh")] = lambda h: (401, {"detail": "bad"})
        client.save_auth({"access_token": "old", "refresh_token": "bad"})
        with pytest.raises(api_mod.AuthRequiredError):
            client.access()
        assert not store.has(api_mod.ACCESS_KEY), "刷新失败后应清空凭据"

    def test_no_refresh_loop(self, client):
        """刷新后仍 401 → 直接报错，**不能**无限刷新。"""
        count = {"n": 0}

        def protected(h):
            return 401, {"detail": "expired"}

        def refresh(h):
            count["n"] += 1
            return 200, {"access_token": "still-bad", "refresh_token": "r2"}

        _Handler.routes[("GET", "/api/toolbox/access")] = protected
        _Handler.routes[("POST", "/api/auth/client/refresh")] = refresh
        client.save_auth({"access_token": "old", "refresh_token": "r"})
        with pytest.raises(api_mod.AuthRequiredError):
            client.access()
        assert count["n"] == 1, "只应刷新一次"


class TestEndpointPaths:
    def test_manifest_and_ticket_paths(self, client):
        seen = {}

        def manifest(h):
            seen["m"] = h.path
            return 200, {"manifest": {"files": []}, "signature": "s"}

        def ticket(h):
            seen["t"] = h.path
            return 200, {"ticket": "tk", "download_url": "https://cdn/x"}

        _Handler.routes[("GET", "/api/toolbox/tools/7/releases/r1/manifest")] = manifest
        _Handler.routes[("POST", "/api/toolbox/tools/7/releases/r1/ticket")] = ticket
        client.save_auth({"access_token": "t", "refresh_token": "r"})

        client.manifest(7, "r1")
        client.download_ticket(7, "r1", "A.dll", "a" * 64)
        assert seen["m"] == "/api/toolbox/tools/7/releases/r1/manifest"
        assert "file_name=A.dll" in seen["t"] and "sha256=" in seen["t"]

    def test_season_is_public(self, client):
        _Handler.routes[("GET", "/api/toolbox/season")] = lambda h: (200, {"season_active": False})
        assert client.season()["season_active"] is False
        # 公开端点不应带 Authorization
        assert _Handler.calls[-1][2] is None


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------


class TestDownload:
    def _serve(self, tmp_path, data: bytes):
        """起一个只提供该文件的假 CDN。"""
        sha = hashlib.sha256(data).hexdigest()

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        httpd = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{httpd.server_port}/f", sha, httpd

    def test_rejects_http_url(self, tmp_path):
        """http 明文会泄露票据，必须拒绝。"""
        with pytest.raises(dl.DownloadError) as ei:
            dl.download_verified("http://evil.test/x", tmp_path / "f", expected_sha256="a" * 64)
        assert ei.value.code == "INVALID_URL"

    def test_rejects_missing_hash(self, tmp_path):
        with pytest.raises(dl.DownloadError) as ei:
            dl.download_verified("https://cdn.test/x", tmp_path / "f", expected_sha256="")
        assert ei.value.code == "HASH_MISSING"

    def test_hash_mismatch_discards_file(self, tmp_path, monkeypatch):
        """哈希不符必须**删除**已下载文件，不能留下可疑内容。"""
        url, sha, httpd = self._serve(tmp_path, b"real-content")
        # 测试用 http（真实校验逻辑单独测），因此绕过 URL 检查
        monkeypatch.setattr(dl, "_is_safe_download_url", lambda u: True)
        dest = tmp_path / "out.bin"
        try:
            with pytest.raises(dl.DownloadError) as ei:
                dl.download_verified(url, dest, expected_sha256="b" * 64)
            assert ei.value.code == "HASH_MISMATCH"
            assert not dest.exists()
        finally:
            httpd.shutdown()

    def test_successful_download_verifies(self, tmp_path, monkeypatch):
        url, sha, httpd = self._serve(tmp_path, b"good-data")
        monkeypatch.setattr(dl, "_is_safe_download_url", lambda u: True)
        dest = tmp_path / "out.bin"
        try:
            dl.download_verified(url, dest, expected_sha256=sha)
            assert dest.read_bytes() == b"good-data"
            assert dl.sha256_file(dest) == sha
        finally:
            httpd.shutdown()

    def test_size_mismatch_rejected(self, tmp_path, monkeypatch):
        url, sha, httpd = self._serve(tmp_path, b"12345")
        monkeypatch.setattr(dl, "_is_safe_download_url", lambda u: True)
        try:
            with pytest.raises(dl.DownloadError) as ei:
                dl.download_verified(url, tmp_path / "o", expected_sha256=sha, expected_size=999)
            assert ei.value.code == "SIZE_MISMATCH"
        finally:
            httpd.shutdown()

    def test_cancel_aborts(self, tmp_path, monkeypatch):
        url, sha, httpd = self._serve(tmp_path, b"x" * 100000)
        monkeypatch.setattr(dl, "_is_safe_download_url", lambda u: True)
        try:
            with pytest.raises(dl.DownloadError) as ei:
                dl.download_verified(
                    url, tmp_path / "o", expected_sha256=sha, should_cancel=lambda: True
                )
            assert ei.value.code == "CANCELLED"
        finally:
            httpd.shutdown()


class TestCache:
    def test_reuses_valid_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "cache_root", lambda: tmp_path)
        data = b"cached"
        sha = hashlib.sha256(data).hexdigest()
        target = dl.cached_path(sha)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        def _boom(*a, **k):
            raise AssertionError("不应发起下载：缓存有效")

        monkeypatch.setattr(dl, "download_verified", _boom)
        assert dl.fetch_or_reuse("https://x/y", sha) == target

    def test_redownloads_when_cache_tampered(self, tmp_path, monkeypatch):
        """缓存被改过（用户手改/杀毒）→ 重新下载，不盲信缓存标记。"""
        monkeypatch.setattr(dl, "cache_root", lambda: tmp_path)
        data = b"good"
        sha = hashlib.sha256(data).hexdigest()
        target = dl.cached_path(sha)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"TAMPERED")

        called = {"n": 0}

        def _fake_download(url, dest, **kwargs):
            called["n"] += 1
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return dest

        monkeypatch.setattr(dl, "download_verified", _fake_download)
        dl.fetch_or_reuse("https://x/y", sha)
        assert called["n"] == 1

    def test_clear_cache_keeps_requested(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dl, "cache_root", lambda: tmp_path)
        keep_sha = "a" * 64
        (tmp_path / keep_sha[:2]).mkdir(parents=True, exist_ok=True)
        (tmp_path / keep_sha[:2] / keep_sha).write_bytes(b"k")
        other = "b" * 64
        (tmp_path / other[:2]).mkdir(parents=True, exist_ok=True)
        (tmp_path / other[:2] / other).write_bytes(b"o")

        removed = dl.clear_cache(keep_sha256={keep_sha})
        assert removed == 1
        assert (tmp_path / keep_sha[:2] / keep_sha).exists()


class TestManifestHashLookup:
    def test_finds_declared_hash(self):
        m = {"files": [{"path": "BepInEx/plugins/LCTA/tool-a/A.dll", "sha256": "c" * 64}]}
        assert dl.verify_manifest_hash(m, "A.dll") == "c" * 64

    def test_missing_returns_none(self):
        """清单里没有该文件 → 返回 None，调用方必须拒绝下载。"""
        assert dl.verify_manifest_hash({"files": []}, "A.dll") is None
        assert dl.verify_manifest_hash({"files": [{"path": "B.dll", "sha256": "d" * 64}]}, "A.dll") is None

    def test_short_hash_rejected(self):
        m = {"files": [{"path": "A.dll", "sha256": "abc"}]}
        assert dl.verify_manifest_hash(m, "A.dll") is None