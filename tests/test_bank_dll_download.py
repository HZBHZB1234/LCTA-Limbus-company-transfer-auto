import os
import zipfile

import pytest

import webutils.function_bank as fb


def _dll_zip(tmp_path, names=("fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll")):
    p = tmp_path / "tool.zip"
    with zipfile.ZipFile(p, "w") as z:
        for n in names:
            z.writestr(n, b"dll-content")
    return str(p)


class _FakeRelease:
    def get_asset_by_name(self, name):
        return object()


def _no_dlls(monkeypatch, tmp_path):
    fake = tmp_path / "empty"
    fake.mkdir()
    monkeypatch.setattr(fb, "missing_dlls", lambda d: ["fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll"])
    monkeypatch.setattr(fb, "default_download_dir", lambda: str(fake))
    set_calls = []
    monkeypatch.setattr(fb.ConfigManager, "set",
                        lambda self, k, v: set_calls.append((k, v)))
    return fake, set_calls


def test_already_present_skips_download(monkeypatch, tmp_path):
    monkeypatch.setattr(fb, "missing_dlls", lambda d: [])
    calls = []
    monkeypatch.setattr(fb, "download_with", lambda *a, **k: calls.append(("with",)) or True)
    monkeypatch.setattr(fb, "download_with_github", lambda *a, **k: calls.append(("github",)) or True)
    r = fb.bank_download_dlls()
    assert r["success"] is True and r["source"] == "already_present"
    assert calls == []


def test_download_from_github_release(monkeypatch, tmp_path):
    dest, set_calls = _no_dlls(monkeypatch, tmp_path)
    zip_path = _dll_zip(tmp_path)

    class FakeAsset:
        def __init__(self, zpath):
            self.zpath = zpath
        name = "Fmod_Bank_Tools.zip"

    class FakeRelease:
        def get_asset_by_name(self, name):
            return FakeAsset(zip_path)

    class FakeRequester:
        @staticmethod
        def get_latest_release(owner, repo):
            return FakeRelease()

    monkeypatch.setattr(fb, "get_latest_release", lambda *a: FakeRelease())
    monkeypatch.setattr(fb, "download_with_github",
                        lambda asset, save_path, **k: (open(save_path, "wb").write(open(zip_path, "rb").read()) or True))
    r = fb.bank_download_dlls()
    assert r["success"] is True
    assert r["source"] == "github_release"
    for n in ("fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll"):
        assert (dest / n).read_bytes() == b"dll-content"
    assert r["dir"] == str(dest)
    assert ("ui_default.bank.dll_dir", str(dest)) in set_calls


def test_force_redownloads_into_configured_dir(monkeypatch, tmp_path):
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    for n in ("fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll"):
        (cfg_dir / n).write_bytes(b"old-content")
    set_calls = []
    monkeypatch.setattr(fb.ConfigManager, "get",
                        lambda self, k, d=None: str(cfg_dir) if k == "ui_default.bank.dll_dir" else d)
    monkeypatch.setattr(fb.ConfigManager, "set",
                        lambda self, k, v: set_calls.append((k, v)))
    zip_path = _dll_zip(tmp_path)
    monkeypatch.setattr(fb, "get_latest_release", lambda *a: _FakeRelease())
    monkeypatch.setattr(fb, "download_with_github",
                        lambda asset, save_path, **k: (open(save_path, "wb").write(open(zip_path, "rb").read()) or True))
    r = fb.bank_download_dlls(force=True)
    assert r["success"] is True
    assert r["source"] == "github_release"
    assert r["dir"] == str(cfg_dir)
    for n in ("fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll"):
        assert (cfg_dir / n).read_bytes() == b"dll-content"
    assert ("ui_default.bank.dll_dir", str(cfg_dir)) in set_calls


def test_configured_url_takes_priority(monkeypatch, tmp_path):
    dest, _ = _no_dlls(monkeypatch, tmp_path)
    zip_path = _dll_zip(tmp_path)
    monkeypatch.setattr(fb.ConfigManager, "get",
                        lambda self, k, d=None: "https://example.com/fmod.zip" if k == "ui_default.bank.dll_url" else d)
    monkeypatch.setattr(fb, "download_with",
                        lambda url, save_path, **k: (open(save_path, "wb").write(open(zip_path, "rb").read()) or True))
    monkeypatch.setattr(fb, "get_latest_release", lambda *a: pytest.fail("不应走 release"))
    r = fb.bank_download_dlls()
    assert r["success"] is True and r["source"] == "configured_url"


def test_zip_missing_dll_fails_and_cleans(monkeypatch, tmp_path):
    dest, _ = _no_dlls(monkeypatch, tmp_path)
    zip_path = _dll_zip(tmp_path, names=("fmod64.dll", "fsbank64.dll"))

    class FakeRelease:
        def get_asset_by_name(self, name):
            return object()

    monkeypatch.setattr(fb, "get_latest_release", lambda *a: FakeRelease())
    monkeypatch.setattr(fb, "download_with_github",
                        lambda asset, save_path, **k: (open(save_path, "wb").write(open(zip_path, "rb").read()) or True))
    r = fb.bank_download_dlls()
    assert r["success"] is False
    assert "libfsbvorbis64.dll" in r["message"]
    assert list(dest.iterdir()) == []  # 半成品已清理


def test_mid_extract_failure_cleans_partial_dlls(monkeypatch, tmp_path):
    dest, _ = _no_dlls(monkeypatch, tmp_path)
    zip_path = _dll_zip(tmp_path)
    real_read = zipfile.ZipFile.read

    def failing_read(self, name, *args, **kwargs):
        if name == "fsbank64.dll":
            raise zipfile.BadZipFile("crc mismatch")
        return real_read(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "read", failing_read)
    monkeypatch.setattr(fb, "get_latest_release", lambda *a: _FakeRelease())
    monkeypatch.setattr(fb, "download_with_github",
                        lambda asset, save_path, **k: (open(save_path, "wb").write(open(zip_path, "rb").read()) or True))
    r = fb.bank_download_dlls()
    assert r["success"] is False
    assert "crc mismatch" in r["message"]
    assert list(dest.iterdir()) == []  # 已写入的 fmod64.dll 也被清理


# ═══════════════ ensure_fmod_dlls（自动下载入口） ═══════════════

def test_ensure_fmod_dlls_downloads_when_missing(monkeypatch, tmp_path):
    import webutils.bank.dlls as dlls_mod
    from webutils.bank.dlls import ensure_fmod_dlls
    from webutils.bank.errors import BankDllMissingError

    fake_dir = tmp_path / "dlls"
    fake_dir.mkdir()
    for n in ("fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll"):
        (fake_dir / n).write_bytes(b"dll")

    monkeypatch.setattr(dlls_mod, "find_dll_dir", lambda cands: None)  # 环境无关：视为缺失

    calls = []
    monkeypatch.setattr(fb, "bank_download_dlls",
                        lambda force=False: calls.append(force) or
                        {"success": True, "dir": str(fake_dir), "message": "ok"})

    assert ensure_fmod_dlls() == str(fake_dir)
    assert calls == [False]


def test_ensure_fmod_dlls_raises_on_failure(monkeypatch):
    import webutils.bank.dlls as dlls_mod
    from webutils.bank.dlls import ensure_fmod_dlls
    from webutils.bank.errors import BankDllMissingError

    monkeypatch.setattr(dlls_mod, "find_dll_dir", lambda cands: None)  # 环境无关：视为缺失

    monkeypatch.setattr(fb, "bank_download_dlls",
                        lambda force=False: {"success": False, "message": "网络失败"})
    with pytest.raises(BankDllMissingError, match="自动下载失败"):
        ensure_fmod_dlls()


def test_ensure_fmod_dlls_concurrent_single_download(monkeypatch, tmp_path):
    """并发调用只触发一次下载（线程安全锁 + 锁内重复检查）。"""
    import threading

    import webutils.bank.dlls as dlls_mod
    from webutils.bank.dlls import DLL_NAMES, ensure_fmod_dlls

    fake_dir = tmp_path / "dlls"
    fake_dir.mkdir()
    monkeypatch.setattr(dlls_mod, "default_dll_candidates", lambda: [str(fake_dir)])

    calls = []
    lock = threading.Lock()

    def fake_download(force=False):
        with lock:
            calls.append(force)
        for n in DLL_NAMES:
            (fake_dir / n).write_bytes(b"dll")
        return {"success": True, "dir": str(fake_dir), "message": "ok"}

    monkeypatch.setattr(fb, "bank_download_dlls", fake_download)

    barrier = threading.Barrier(4)
    results = []

    def worker():
        barrier.wait()
        results.append(ensure_fmod_dlls())

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1  # 锁串行化 + 锁内复查，只下载一次
    assert all(r == str(fake_dir) for r in results)
