import os

import pytest

import webutils.function_bank as fb


def test_dll_status_without_dlls(monkeypatch):
    monkeypatch.setattr(fb, "missing_dlls", lambda d: ["fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll"])
    monkeypatch.setattr(fb, "find_dll_dir", lambda c: None)
    r = fb.bank_dll_status()
    assert r["success"] is True
    assert r["ok"] is False
    assert len(r["missing"]) == 3


def test_dll_status_ok(monkeypatch):
    monkeypatch.setattr(fb, "missing_dlls", lambda d: [])
    monkeypatch.setattr(fb, "find_dll_dir", lambda c: "C:/dlls")
    r = fb.bank_dll_status()
    assert r["ok"] is True
    assert r["dir"] == "C:/dlls"


def test_set_dll_dir_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(fb, "missing_dlls", lambda d: ["fmod64.dll"])
    r = fb.bank_set_dll_dir(str(tmp_path / "nope"))
    assert r["success"] is False
    r2 = fb.bank_set_dll_dir("")
    assert r2["success"] is True  # 清除


def test_bank_info_invalid(tmp_path):
    p = tmp_path / "x.bank"
    p.write_bytes(b"garbage")
    r = fb.bank_info(str(p))
    assert r["success"] is False
    assert "无法解析" in r["message"]


def test_bank_extract_ok(tmp_path, monkeypatch):
    p = tmp_path / "Weapon.bank"
    p.write_bytes(b"x" * 100)
    monkeypatch.setattr(fb, "FmodDlls", lambda d=None: object())
    monkeypatch.setattr(fb, "extract_bank", lambda dlls, bank, wav, fsb, pw, log: {
        "bank_base": "Weapon", "fsb_count": 2, "encrypted": False, "password_used": None})
    r = fb.bank_extract(str(p), str(tmp_path / "out"), "")
    assert r["success"] is True
    assert r["fsb_count"] == 2
    assert r["wav_dir"] == str(tmp_path / "out")


def test_bank_export_rebank_ok(tmp_path, monkeypatch):
    orig, modded = tmp_path / "a.bank", tmp_path / "b.bank"
    orig.write_bytes(b"a"); modded.write_bytes(b"b")
    calls = {}
    monkeypatch.setattr(fb, "FmodDlls", lambda d=None: object())
    monkeypatch.setattr(fb, "build_rebank", lambda dlls, o, m, out, meta, work_dir=None,
                        password=None, log=None: calls.update(o=o, m=m, meta=meta) or
                        {"modified": [(0, "a.wav")], "added": [], "count": 1, "out": out})
    out = str(tmp_path / "mod.rebank")
    r = fb.bank_export_rebank(str(orig), str(modded), out, "n", "1.0", "au", "de", False)
    assert r["success"] is True
    assert calls["meta"]["name"] == "n"
    assert calls["o"] == str(orig)


def test_bank_export_rebank_missing_file(tmp_path):
    r = fb.bank_export_rebank(str(tmp_path / "no.bank"), str(tmp_path / "no2.bank"),
                              str(tmp_path / "x.rebank"), "n", "1", "", "", False)
    assert r["success"] is False


def test_bank_export_rebank_into_mod_same_path(tmp_path, monkeypatch):
    """out_path 已在模组目录（模组版 bank 取自模组目录的常见流程）时不应 SameFileError。"""
    mod_dir = tmp_path / "mods"
    mod_dir.mkdir()
    orig, modded = tmp_path / "a.bank", mod_dir / "b.bank"
    orig.write_bytes(b"a"); modded.write_bytes(b"b")
    monkeypatch.setattr(fb, "FmodDlls", lambda d=None: object())
    monkeypatch.setattr(fb, "build_rebank", lambda dlls, o, m, out, meta, work_dir=None,
                        password=None, log=None: {"modified": [], "added": [(0, "a.wav")],
                                                  "count": 1, "out": out})
    monkeypatch.setattr(fb, "get_mod_path", lambda: str(mod_dir))
    out = str(mod_dir / "b.rebank")
    r = fb.bank_export_rebank(str(orig), str(modded), out, "n", "1.0", "", "", True)
    assert r["success"] is True
    assert r["into_mod_folder"] is True
    assert r["out"] == out
