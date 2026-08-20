"""Mod 镜像站集成测试：文件名清洗 / zip 安全解压 / 校验 / 主流程（mock 下载层）。"""
import json
import zipfile
from pathlib import Path

import pytest

import webutils.function_mod_mirror as mm


@pytest.fixture(autouse=True)
def isolate_dirs(tmp_path, monkeypatch):
    """隔离 staging 与 mod 目录到临时目录，避免污染用户环境。"""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    fake_mod_root = tmp_path / "Mods"
    fake_mod_root.mkdir()
    monkeypatch.setattr(mm, "get_mod_path", lambda: fake_mod_root)
    return {"mod_root": fake_mod_root}


class FakeConfig:
    def __init__(self, data):
        self._data = data

    def get(self, key_path, default=None):
        cur = self._data
        for part in key_path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def set(self, key_path, value, auto_save=True):
        parts = key_path.split(".")
        cur = self._data
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = value


@pytest.fixture(autouse=True)
def fake_config(monkeypatch):
    data = {
        "ui_default": {
            "mod_mirror": {"base_url": "https://mods.lcta.top", "auth": ""},
            "aria2_dl": {"jobs": 4, "connection_limit": 8},
        }
    }
    monkeypatch.setattr(mm.ConfigManager, "get", FakeConfig(data).get)
    monkeypatch.setattr(mm.ConfigManager, "set", FakeConfig(data).set)
    return data


@pytest.fixture(autouse=True)
def reset_aria2_pool():
    """重置 aria2 单例池状态，避免测试间互相污染。"""
    mm.stop_mod_mirror_aria2()
    mm._aria2_reaper_thread = None
    yield
    mm.stop_mod_mirror_aria2()
    mm._aria2_reaper_thread = None


# ==================== 文件名清洗 ====================

def test_safe_filename_cleans_windows_invalid_chars():
    assert mm._safe_filename('a:b\\c|d?e*f<g>h"i') == "a_b_c_d_e_f_g_h_i"
    assert mm._safe_filename("  多 个 空格  ") == "多_个_空格"
    assert mm._safe_filename("") == "download"
    assert mm._safe_filename(None) == "download"
    assert mm._safe_filename(".") == "download"
    assert len(mm._safe_filename("x" * 500)) <= 120


# ==================== zip 成员名安全 ====================

def test_sanitize_member_rejects_traversal():
    with pytest.raises(ValueError):
        mm._sanitize_member("../evil.txt")
    with pytest.raises(ValueError):
        mm._sanitize_member("a/../../evil.txt")
    with pytest.raises(ValueError):
        mm._sanitize_member("C:/evil.txt")
    with pytest.raises(ValueError):
        mm._sanitize_member("/abs/evil.txt")
    with pytest.raises(ValueError):
        mm._sanitize_member("")
    assert mm._sanitize_member("data/rebank.json") == "data/rebank.json"
    assert mm._sanitize_member("a\\b.rebank") == "a/b.rebank"


def test_extract_zip_safe_rejects_traversal_member(tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../escape.txt", "bad")
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(ValueError):
        mm._extract_zip_safe(evil, dest, "false")
    assert not (tmp_path / "escape.txt").exists()


def test_extract_zip_safe_rejects_corrupt(tmp_path):
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("a.txt", "hello")
    corrupt = tmp_path / "corrupt.zip"
    corrupt.write_bytes(good.read_bytes()[:-2])
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(ValueError):
        mm._extract_zip_safe(corrupt, dest, "false")


def test_extract_zip_safe_extracts_nested(tmp_path):
    src = tmp_path / "pkg.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("mod.json", "{}")
        z.writestr("data/1.carra2", "x" * 10)
    dest = tmp_path / "out"
    dest.mkdir()
    mm._extract_zip_safe(src, dest, "false")
    assert (dest / "mod.json").read_bytes() == b"{}"
    assert (dest / "data" / "1.carra2").read_bytes() == b"x" * 10


# ==================== 校验 ====================

def test_verify_expected_ok(tmp_path):
    f = tmp_path / "f.zip"
    f.write_bytes(b"abc")
    mm._verify_expected(f, 3, mm._sha256(f))


def test_verify_expected_size_mismatch(tmp_path):
    f = tmp_path / "f.zip"
    f.write_bytes(b"abc")
    with pytest.raises(ValueError, match="大小"):
        mm._verify_expected(f, 4, "")


def test_verify_expected_hash_mismatch(tmp_path):
    f = tmp_path / "f.zip"
    f.write_bytes(b"abc")
    with pytest.raises(ValueError, match="SHA256"):
        mm._verify_expected(f, 0, "0" * 64)


# ==================== 登录态持久化 ====================

def test_auth_roundtrip(fake_config):
    assert mm.mod_mirror_get_auth() is None
    mm.mod_mirror_save_auth({"access_token": "tok", "refresh_token": "ref", "user": '{"id":1}'})
    assert mm.mod_mirror_get_auth() == {"access_token": "tok", "refresh_token": "ref", "user": '{"id":1}'}
    mm.mod_mirror_save_auth(None)
    assert mm.mod_mirror_get_auth() is None
    assert fake_config["ui_default"]["mod_mirror"]["auth"] == ""


# ==================== 主流程 ====================

def test_standard_flow_installs(monkeypatch, tmp_path, fake_config, isolate_dirs):
    """标准版：aria2 下载成功 → 校验 → 解压安装到 mod 目录。"""
    fake_zip = tmp_path / "fake.zip"
    with zipfile.ZipFile(fake_zip, "w") as z:
        z.writestr("mod.json", "{}")
        z.writestr("sound/1.rebank", "rebank-data")

    def fake_download(url, dest, modal_id, expected_size):
        dest.write_bytes(fake_zip.read_bytes())
        return True

    monkeypatch.setattr(mm, "_download_aria2", fake_download)

    result = mm.mod_mirror_request({
        "target_type": "nexus", "target_id": "1234", "kind": "standard",
        "name": "My Mod", "size": fake_zip.stat().st_size,
        "sha256": mm._sha256(fake_zip),
    }, "false")

    assert result["success"] is True
    mod_dir = Path(result["mod_dir"])
    assert (mod_dir / "mod.json").read_bytes() == b"{}"
    assert (mod_dir / "sound" / "1.rebank").read_bytes() == b"rebank-data"


def test_standard_flow_overwrites_existing(monkeypatch, tmp_path, isolate_dirs):
    """标准版重复安装：覆盖旧同名目录。"""
    old = isolate_dirs["mod_root"] / "My_Mod"
    old.mkdir()
    (old / "stale.txt").write_text("old")
    fake_zip = tmp_path / "fake.zip"
    with zipfile.ZipFile(fake_zip, "w") as z:
        z.writestr("mod.json", "{}")

    def fake_download(url, dest, modal_id, expected_size):
        dest.write_bytes(fake_zip.read_bytes())
        return True

    monkeypatch.setattr(mm, "_download_aria2", fake_download)

    result = mm.mod_mirror_request({
        "target_type": "nexus", "target_id": "7", "kind": "standard",
        "name": "My Mod", "size": fake_zip.stat().st_size,
    }, "false")
    assert result["success"] is True
    new_dir = isolate_dirs["mod_root"] / "My_Mod"
    assert (new_dir / "mod.json").exists()
    assert not (new_dir / "stale.txt").exists()


def test_flow_hash_mismatch_fails(monkeypatch, tmp_path, isolate_dirs):
    """SHA256 校验失败 → 安装不执行、返回失败。"""
    fake_zip = tmp_path / "fake.zip"
    with zipfile.ZipFile(fake_zip, "w") as z:
        z.writestr("mod.json", "{}")

    monkeypatch.setattr(mm, "_download_aria2", lambda url, dest, modal_id, expected_size: (
        dest.write_bytes(fake_zip.read_bytes())) or True)

    result = mm.mod_mirror_request({
        "target_type": "nexus", "target_id": "9", "kind": "standard",
        "name": "M", "size": fake_zip.stat().st_size, "sha256": "f" * 64,
    }, "false")
    assert result["success"] is False
    assert "SHA256" in result["message"]
    assert not (isolate_dirs["mod_root"] / "M").exists()


def test_file_flow_downloads_only(monkeypatch, tmp_path, fake_config, isolate_dirs):
    """普通文件：下载到「下载」目录，不安装。"""
    fake_zip = tmp_path / "fake.zip"
    fake_zip.write_bytes(b"file-content")
    dl_dir = tmp_path / "Downloads"
    dl_dir.mkdir()
    monkeypatch.setattr(mm, "get_downloads_dir", lambda: str(dl_dir))

    def fake_download(url, dest, modal_id, expected_size):
        assert "download?file_id=55" in url
        dest.write_bytes(fake_zip.read_bytes())
        return True

    monkeypatch.setattr(mm, "_download_aria2", fake_download)

    result = mm.mod_mirror_request({
        "target_type": "nexus", "target_id": "12", "kind": "file", "file_id": 55,
        "name": "file.bank", "size": 12, "sha256": mm._sha256(fake_zip),
    }, "false")
    assert result["success"] is True
    saved = Path(result["save_path"])
    assert saved.parent == dl_dir
    assert saved.read_bytes() == b"file-content"
    assert not (isolate_dirs["mod_root"] / "file.bank").exists()


def test_invalid_payload_rejected(isolate_dirs):
    result = mm.mod_mirror_request({"target_id": "abc"}, "false")
    assert result["success"] is False
    result = mm.mod_mirror_request({"target_id": "1", "kind": "torrent"}, "false")
    assert result["success"] is False


def test_aria2_unavailable_falls_back(monkeypatch, tmp_path, isolate_dirs):
    """aria2c 不可用（Aria2Error）→ 降级内置下载器。"""
    fake_zip = tmp_path / "fake.zip"
    with zipfile.ZipFile(fake_zip, "w") as z:
        z.writestr("mod.json", "{}")

    def boom(*a, **k):
        raise mm.Aria2Error("aria2c 不可用")

    monkeypatch.setattr(mm, "resolve_aria2_binary", lambda: None)

    def fake_fallback(url, dest, modal_id, expected_size):
        dest.write_bytes(fake_zip.read_bytes())
        return True

    monkeypatch.setattr(mm, "_download_fallback", fake_fallback)

    result = mm.mod_mirror_request({
        "target_type": "nexus", "target_id": "3", "kind": "standard",
        "name": "M", "size": fake_zip.stat().st_size,
    }, "false")
    assert result["success"] is True
    assert (isolate_dirs["mod_root"] / "M" / "mod.json").exists()


def test_download_failure_reported(monkeypatch, tmp_path, isolate_dirs):
    def fake_download(url, dest, modal_id, expected_size):
        raise ValueError("下载失败（404）")

    monkeypatch.setattr(mm, "_download_aria2", fake_download)
    result = mm.mod_mirror_request({
        "target_type": "nexus", "target_id": "5", "kind": "standard", "name": "M",
    }, "false")
    assert result["success"] is False
    assert "404" in result["message"]


def test_base_url_from_config(fake_config):
    assert mm.base_url() == "https://mods.lcta.top"
    fake_config["ui_default"]["mod_mirror"]["base_url"] = "http://127.0.0.1:1146"
    assert mm.base_url() == "http://127.0.0.1:1146"


# ==================== 302 直链解析（aria2c 走 CDN 域） ====================

def test_resolve_direct_url_follows_302(monkeypatch):
    calls = {}

    def fake_get(url, **kw):
        calls["url"] = url
        calls["allow_redirects"] = kw.get("allow_redirects")
        return type("R", (), {
            "status_code": 302,
            "headers": {"Location": "https://dl.mods.lcta.top/nexus/139/abc.zip?X-Amz-Sig=x%2B1"},
        })()

    monkeypatch.setattr(mm.requests, "get", fake_get)
    out = mm._resolve_direct_url("https://mods.lcta.top/api/mods/nexus/139/standard")
    assert out == "https://dl.mods.lcta.top/nexus/139/abc.zip?X-Amz-Sig=x%2B1"
    assert calls["allow_redirects"] is False


def test_resolve_direct_url_no_redirect_keeps_url(monkeypatch):
    def fake_get(url, **kw):
        return type("R", (), {"status_code": 200, "headers": {}})()

    monkeypatch.setattr(mm.requests, "get", fake_get)
    url = "https://mods.lcta.top/api/mods/nexus/139/standard"
    assert mm._resolve_direct_url(url) == url


def test_resolve_direct_url_failure_keeps_url(monkeypatch):
    def fake_get(url, **kw):
        raise ConnectionError("down")

    monkeypatch.setattr(mm.requests, "get", fake_get)
    url = "https://mods.lcta.top/api/mods/nexus/139/standard"
    assert mm._resolve_direct_url(url) == url


def test_download_aria2_uses_direct_url(monkeypatch, tmp_path):
    """集成：aria2c 收到的 add_uri 应为 302 解析后的 CDN 直链而非 API 地址。"""
    seen = []

    class FakeClient:
        def __init__(self, *a, **k):
            self.gid = "g1"

        def start(self):
            pass

        def add_uri(self, url, save_dir, out):
            seen.append(url)
            return self.gid

        def status(self, gid):
            return {"status": "complete", "totalLength": "10", "completedLength": "10",
                    "downloadSpeed": "0"}

        def stop(self):
            pass

    monkeypatch.setattr(mm, "resolve_aria2_binary", lambda: "aria2c.exe")
    monkeypatch.setattr(mm, "_resolve_direct_url", lambda url: "https://dl.mods.lcta.top/nexus/139/abc.zip")
    monkeypatch.setattr(mm, "Aria2DlClient", FakeClient)

    dest = tmp_path / "out" / "139_x.zip"
    ok = mm._download_aria2("https://mods.lcta.top/api/mods/nexus/139/standard",
                            dest, "false", 0)
    assert ok is True
    assert seen == ["https://dl.mods.lcta.top/nexus/139/abc.zip"]


def test_download_aria2_error_falls_back(monkeypatch, tmp_path):
    """aria2 任务 status=error（如 CDN 403）→ 自动降级内置下载器。"""
    class FakeClient:
        def __init__(self, *a, **k):
            self.gid = "g1"

        def start(self):
            pass

        def add_uri(self, url, save_dir, out):
            return self.gid

        def status(self, gid):
            return {"status": "error", "errorMessage": "The response status is not successful. status=403"}

        def stop(self):
            pass

    monkeypatch.setattr(mm, "resolve_aria2_binary", lambda: "aria2c.exe")
    monkeypatch.setattr(mm, "_resolve_direct_url", lambda url: url)
    monkeypatch.setattr(mm, "Aria2DlClient", FakeClient)

    dest = tmp_path / "out" / "139_x.zip"
    fallback = {"called": False}

    def fake_fallback(url, dest_, modal_id, expected_size):
        fallback["called"] = True
        dest_.parent.mkdir(parents=True, exist_ok=True)
        dest_.write_bytes(b"ok")
        return True

    monkeypatch.setattr(mm, "_download_fallback", fake_fallback)
    assert mm._download_aria2("https://mods.lcta.top/api/mods/nexus/139/standard",
                              dest, "false", 0) is True
    assert fallback["called"] is True


# ==================== staging 复用 / 单根展开 / 包内容摘要 ====================

def test_standard_flow_reuses_existing_staging(monkeypatch, tmp_path, isolate_dirs):
    """已存在同内容（sha256 一致）的 staging 包 → 跳过下载直接安装。"""
    fake_zip = tmp_path / "fake.zip"
    with zipfile.ZipFile(fake_zip, "w") as z:
        z.writestr("mod.json", "{}")

    dest = tmp_path / "localappdata" / "LCTA" / "mod-mirror" / "42_standard" / "42_My_Mod.zip"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(fake_zip.read_bytes())

    calls = []
    monkeypatch.setattr(mm, "_download_aria2",
                        lambda url, d, m, s: calls.append(url) or True)

    result = mm.mod_mirror_request({
        "target_type": "nexus", "target_id": "42", "kind": "standard",
        "name": "My Mod", "size": fake_zip.stat().st_size,
        "sha256": mm._sha256(fake_zip),
    }, "false")
    assert result["success"] is True
    assert calls == []  # 未发起下载
    assert (isolate_dirs["mod_root"] / "My_Mod" / "mod.json").exists()


def test_standard_flow_redownloads_when_hash_differs(monkeypatch, tmp_path, isolate_dirs):
    """staging 内容与 sha256 不一致 → 重新下载覆盖。"""
    fake_zip = tmp_path / "fake.zip"
    with zipfile.ZipFile(fake_zip, "w") as z:
        z.writestr("mod.json", "{}")

    dest = tmp_path / "localappdata" / "LCTA" / "mod-mirror" / "43_standard" / "43_My_Mod.zip"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"stale-content")  # 旧版本

    monkeypatch.setattr(mm, "_download_aria2",
                        lambda url, d, m, s: d.write_bytes(fake_zip.read_bytes()) or True)

    result = mm.mod_mirror_request({
        "target_type": "nexus", "target_id": "43", "kind": "standard",
        "name": "My Mod", "size": fake_zip.stat().st_size,
        "sha256": mm._sha256(fake_zip),
    }, "false")
    assert result["success"] is True
    assert dest.read_bytes() == fake_zip.read_bytes()


def test_flatten_single_root_raises_contents(monkeypatch, tmp_path, isolate_dirs):
    """单根目录包安装后内容上提一层（对齐拖放行为）。"""
    fake_zip = tmp_path / "fake.zip"
    with zipfile.ZipFile(fake_zip, "w") as z:
        z.writestr("My_Mod/mod.json", "{}")
        z.writestr("My_Mod/sound/1.rebank", "rb")

    monkeypatch.setattr(mm, "_download_aria2",
                        lambda url, d, m, s: d.write_bytes(fake_zip.read_bytes()) or True)

    result = mm.mod_mirror_request({
        "target_type": "nexus", "target_id": "44", "kind": "standard",
        "name": "My Mod", "size": fake_zip.stat().st_size,
    }, "false")
    assert result["success"] is True
    mod_dir = Path(result["mod_dir"])
    assert (mod_dir / "mod.json").exists()
    assert (mod_dir / "sound" / "1.rebank").exists()
    assert not (mod_dir / "My_Mod").exists()


def test_summarize_package_counts_kinds(tmp_path):
    p = tmp_path / "pkg.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("a/1.carra2", "x")
        z.writestr("b/2.bank", "y")
        z.writestr("c/3.rebank", "z")
        z.writestr("d/mod.json", "{}")
    s = mm._summarize_package(p)
    assert "1 个 carra2" in s and "1 个 bank" in s and "1 个 rebank" in s and "1 个 json" in s


def test_summarize_package_warns_when_no_mod_content(tmp_path):
    p = tmp_path / "pkg.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("readme.txt", "hi")
    s = mm._summarize_package(p)
    assert "未识别到可加载的模组文件" in s


# ==================== aria2 单例池 ====================

def test_aria2_pool_reuses_client_across_downloads(monkeypatch, tmp_path):
    """并发下载复用同一 aria2c 实例（单例池），而非每次新建。"""
    created = []
    stopped = []

    class FakeClient:
        def __init__(self, *a, **k):
            created.append(self)
            self.gid = "g1"

        def start(self):
            pass

        def add_uri(self, url, save_dir, out):
            return self.gid

        def status(self, gid):
            return {"status": "complete", "totalLength": "1", "completedLength": "1",
                    "downloadSpeed": "0"}

        def stop(self):
            stopped.append(self)

    monkeypatch.setattr(mm, "resolve_aria2_binary", lambda: "aria2c.exe")
    monkeypatch.setattr(mm, "_resolve_direct_url", lambda url: url)
    monkeypatch.setattr(mm, "Aria2DlClient", FakeClient)

    dest1 = tmp_path / "out" / "a.zip"
    dest2 = tmp_path / "out" / "b.zip"
    assert mm._download_aria2("https://x/a", dest1, "false", 0) is True
    assert mm._download_aria2("https://x/b", dest2, "false", 0) is True
    assert len(created) == 1  # 只创建过一个实例

    # 手动触发空闲回收
    mm._aria2_idle_at = 0
    mm._aria2_reap_once()
    assert len(stopped) == 1


def test_aria2_pool_concurrent_downloads_share_client(monkeypatch, tmp_path):
    """两个线程并发下载共享同一实例，互不阻塞。"""
    import threading
    created = []
    lock = threading.Lock()
    active = 0
    max_active = 0
    barrier = threading.Barrier(2)

    class FakeClient:
        def __init__(self, *a, **k):
            created.append(self)
            self.gid = "g1"

        def start(self):
            pass

        def add_uri(self, url, save_dir, out):
            return self.gid

        def status(self, gid):
            return {"status": "complete", "totalLength": "1", "completedLength": "1",
                    "downloadSpeed": "0"}

        def stop(self):
            pass

    monkeypatch.setattr(mm, "resolve_aria2_binary", lambda: "aria2c.exe")
    monkeypatch.setattr(mm, "_resolve_direct_url", lambda url: url)
    monkeypatch.setattr(mm, "Aria2DlClient", FakeClient)

    def do_download(name):
        dest = tmp_path / "out" / name
        barrier.wait()
        assert mm._download_aria2("https://x/" + name, dest, "false", 0) is True

    threads = [threading.Thread(target=do_download, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(created) == 1  # 并发下载只创建一个实例


def test_aria2_reaper_does_not_stop_in_use_client(monkeypatch, tmp_path):
    """使用中的实例（引用计数 > 0）即使空闲超时也不回收（回归：锁间竞态）。"""
    created = []
    stopped = []

    class FakeClient:
        def __init__(self, *a, **k):
            created.append(self)
            self.gid = "g1"

        def start(self):
            pass

        def add_uri(self, url, save_dir, out):
            return self.gid

        def status(self, gid):
            return {"status": "complete", "totalLength": "1", "completedLength": "1",
                    "downloadSpeed": "0"}

        def stop(self):
            stopped.append(self)

    monkeypatch.setattr(mm, "resolve_aria2_binary", lambda: "aria2c.exe")
    monkeypatch.setattr(mm, "_resolve_direct_url", lambda url: url)
    monkeypatch.setattr(mm, "Aria2DlClient", FakeClient)

    client = mm._aria2_acquire()
    mm._aria2_idle_at = 0  # 模拟已空闲超时
    mm._aria2_reap_once()
    assert stopped == []  # 引用计数 > 0 → 不回收

    mm._aria2_release(client)
    mm._aria2_idle_at = 0
    mm._aria2_reap_once()
    assert len(stopped) == 1  # 释放后才回收

    # 回收后再获取 → 新建实例
    client2 = mm._aria2_acquire()
    assert client2 is not client
    assert len(created) == 2


def test_aria2_cancel_removes_task(monkeypatch, tmp_path):
    """取消下载时同步移除 aria2 任务，避免后台继续写目标文件（回归）。"""
    removed = []

    class FakeClient:
        def __init__(self, *a, **k):
            self.gid = "g1"

        def start(self):
            pass

        def add_uri(self, url, save_dir, out):
            return self.gid

        def status(self, gid):
            return {"status": "active", "totalLength": "100", "completedLength": "10",
                    "downloadSpeed": "5"}

        def remove(self, gid):
            removed.append(gid)

        def stop(self):
            pass

    monkeypatch.setattr(mm, "resolve_aria2_binary", lambda: "aria2c.exe")
    monkeypatch.setattr(mm, "_resolve_direct_url", lambda url: url)
    monkeypatch.setattr(mm, "Aria2DlClient", FakeClient)
    monkeypatch.setattr(mm._log_manager, "check_running",
                        lambda modal_id=None, log=True: (_ for _ in ()).throw(mm.CancelRunning()))

    dest = tmp_path / "out" / "a.zip"
    with pytest.raises(mm.CancelRunning):
        mm._download_aria2("https://x/a", dest, "false", 0)
    assert removed == ["g1"]  # 取消时已移除 aria2 任务
    assert mm._aria2_users == 0  # 引用已释放
