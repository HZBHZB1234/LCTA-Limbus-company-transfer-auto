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


def _no_dlls(monkeypatch, tmp_path):
    fake = tmp_path / "empty"
    fake.mkdir()
    monkeypatch.setattr(fb, "missing_dlls", lambda d: ["fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll"])
    monkeypatch.setattr(fb, "default_download_dir", lambda: str(fake))
    monkeypatch.setattr(fb.ConfigManager, "set", lambda self, k, v: None)
    return fake


def test_already_present_skips_download(monkeypatch, tmp_path):
    monkeypatch.setattr(fb, "missing_dlls", lambda d: [])
    calls = []
    monkeypatch.setattr(fb, "download_with", lambda *a, **k: calls.append(("with",)) or True)
    monkeypatch.setattr(fb, "download_with_github", lambda *a, **k: calls.append(("github",)) or True)
    r = fb.bank_download_dlls()
    assert r["success"] is True and r["source"] == "already_present"
    assert calls == []


def test_download_from_github_release(monkeypatch, tmp_path):
    dest = _no_dlls(monkeypatch, tmp_path)
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


def test_configured_url_takes_priority(monkeypatch, tmp_path):
    dest = _no_dlls(monkeypatch, tmp_path)
    zip_path = _dll_zip(tmp_path)
    monkeypatch.setattr(fb.ConfigManager, "get",
                        lambda self, k, d=None: "https://example.com/fmod.zip" if k == "ui_default.bank.dll_url" else d)
    monkeypatch.setattr(fb, "download_with",
                        lambda url, save_path, **k: (open(save_path, "wb").write(open(zip_path, "rb").read()) or True))
    monkeypatch.setattr(fb, "get_latest_release", lambda *a: pytest.fail("不应走 release"))
    r = fb.bank_download_dlls()
    assert r["success"] is True and r["source"] == "configured_url"


def test_zip_missing_dll_fails_and_cleans(monkeypatch, tmp_path):
    dest = _no_dlls(monkeypatch, tmp_path)
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
