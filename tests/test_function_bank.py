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


def _make_sound_dir(tmp_path):
    from tests.test_bank_format import build_fsb5_payload, build_test_bank
    sd = tmp_path / "sound"
    sd.mkdir()
    (sd / "SFX_1.assets.bank").write_bytes(
        build_test_bank([build_fsb5_payload(num_samples=31, data_len=1024),
                         build_fsb5_payload(num_samples=7, data_len=64)]))
    (sd / "SFX_1.bank").write_bytes(b"RIFF" + b"\0" * 4 + b"FEV " + b"\0" * 36)  # 事件 bank
    return sd


def test_bank_get_game_banks_subsound_counts(tmp_path, monkeypatch):
    sd = _make_sound_dir(tmp_path)
    monkeypatch.setattr(fb, "_game_sound_dir", lambda game_path: str(sd))
    monkeypatch.setattr(fb.ConfigManager, "get",
                        lambda self, k, d=None: str(tmp_path) if k == "game_path" else d)
    r = fb.bank_get_game_banks()
    assert r["success"] is True
    by_name = {b["name"]: b for b in r["banks"]}
    assert by_name["SFX_1.assets.bank"]["fsb_count"] == 2
    assert by_name["SFX_1.assets.bank"]["subsound_count"] == 38   # 31 + 7
    assert by_name["SFX_1.bank"]["fsb_count"] == 0
    assert by_name["SFX_1.bank"]["subsound_count"] == 0


def test_bank_info_event_bank_no_audio(tmp_path):
    p = tmp_path / "SFX_1.bank"
    p.write_bytes(b"RIFF" + b"\0" * 4 + b"FEV " + b"\0" * 36)
    r = fb.bank_info(str(p))
    assert r["success"] is True
    assert r["fsb_count"] == 0 and r["subsound_count"] == 0
    assert "无音频" in r.get("note", "")


def test_bank_info_with_audio(tmp_path):
    from tests.test_bank_format import build_fsb5_payload, build_test_bank
    p = tmp_path / "Weapon.assets.bank"
    p.write_bytes(build_test_bank([build_fsb5_payload(num_samples=5)]))
    r = fb.bank_info(str(p))
    assert r["success"] is True
    assert r["fsb_count"] == 1
    assert r["subsound_count"] == 5
    assert r["audio_size"] > 0


def test_bank_extract_ok(tmp_path, monkeypatch):
    p = tmp_path / "Weapon.bank"
    p.write_bytes(b"x" * 100)
    monkeypatch.setattr(fb, "FmodDlls", lambda d=None: object())
    monkeypatch.setattr(fb, "extract_bank", lambda dlls, bank, wav, fsb, log: {
        "bank_base": "Weapon", "fsb_count": 2, "encrypted": False})
    r = fb.bank_extract(str(p), str(tmp_path / "out"))
    assert r["success"] is True
    assert r["fsb_count"] == 2
    assert r["wav_dir"] == str(tmp_path / "out")


def test_bank_export_rebank_ok(tmp_path, monkeypatch):
    orig, modded = tmp_path / "a.bank", tmp_path / "b.bank"
    orig.write_bytes(b"a"); modded.write_bytes(b"b")
    calls = {}
    monkeypatch.setattr(fb, "FmodDlls", lambda d=None: object())
    monkeypatch.setattr(fb, "build_rebank", lambda dlls, o, m, out, meta, work_dir=None,
                        log=None: calls.update(o=o, m=m, meta=meta) or
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
                        log=None: {"modified": [], "added": [(0, "a.wav")],
                                   "count": 1, "out": out})
    monkeypatch.setattr(fb, "get_mod_path", lambda: str(mod_dir))
    out = str(mod_dir / "b.rebank")
    r = fb.bank_export_rebank(str(orig), str(modded), out, "n", "1.0", "", "", True)
    assert r["success"] is True
    assert r["into_mod_folder"] is True
    assert r["out"] == out


# ═══════════════ 缓存（bank_patch_full / bank_convert_mod） ═══════════════

def test_bank_patch_full_cache_hit(monkeypatch, tmp_path):
    """同内容二次补丁命中缓存：不重编码、直接复制产物。"""
    from webutils.bank.rebank import (patch_cache_key, patch_options,
                                      rebank_mod_digest)

    rebank_path = tmp_path / "mod.rebank"
    rebank_path.write_bytes(b"rebank")
    bank_path = tmp_path / "Weapon.bank"
    bank_path.write_bytes(b"orig-bank")

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(fb, "rebank_cache_dir", lambda: str(cache_dir))

    orig_hash = fb.sha256_file(str(bank_path))
    opts = patch_options()
    key = patch_cache_key(orig_hash, rebank_mod_digest([str(rebank_path)]),
                          opts["quality"], opts["threads"])
    (cache_dir / (key + ".bank")).write_bytes(b"cached-bank")
    import json as _json
    (cache_dir / (key + ".bank.json")).write_text(
        _json.dumps({"orig_sha256": orig_hash, "replaced": 3,
                     "skipped_new": 1, "skipped_bad": 0}), encoding="utf-8")

    calls = []
    monkeypatch.setattr(fb, "patch_banks",
                        lambda *a, **k: calls.append(1) or {"replaced": 3, "skipped_new": 1,
                                                            "skipped_bad": 0, "out_bank": ""})
    monkeypatch.setattr(fb, "_dlls", lambda: object())

    out_dir = tmp_path / "out"
    r = fb.bank_patch_full(str(rebank_path), str(bank_path), str(out_dir))
    assert r["success"] is True and r["cache_hit"] is True
    assert (out_dir / "Weapon.bank").read_bytes() == b"cached-bank"
    assert calls == []  # 未重编码


def test_bank_patch_full_miss_writes_cache(monkeypatch, tmp_path):
    """首次补丁未命中缓存 → 重编码并写缓存，二次命中。"""
    rebank_path = tmp_path / "mod.rebank"
    rebank_path.write_bytes(b"rebank")
    bank_path = tmp_path / "Weapon.bank"
    bank_path.write_bytes(b"orig-bank")

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(fb, "rebank_cache_dir", lambda: str(cache_dir))

    calls = {"n": 0}

    def fake_patch_banks(dlls, bank_path_, rebank_paths, out_dir, log=None):
        calls["n"] += 1
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, os.path.basename(bank_path_))
        with open(out, "wb") as fh:
            fh.write(b"patched-bank")
        return {"replaced": 2, "skipped_new": 0, "skipped_bad": 0, "out_bank": out}

    monkeypatch.setattr(fb, "patch_banks", fake_patch_banks)
    monkeypatch.setattr(fb, "_dlls", lambda: object())

    out_dir = tmp_path / "out"
    r1 = fb.bank_patch_full(str(rebank_path), str(bank_path), str(out_dir))
    assert r1["success"] is True and r1.get("cache_hit") is None
    assert calls["n"] == 1
    assert len(list(cache_dir.glob("*.bank"))) == 1

    out_dir2 = tmp_path / "out2"
    r2 = fb.bank_patch_full(str(rebank_path), str(bank_path), str(out_dir2))
    assert r2["success"] is True and r2["cache_hit"] is True
    assert calls["n"] == 1  # 第二次命中缓存
    assert (out_dir2 / "Weapon.bank").read_bytes() == b"patched-bank"


def test_bank_convert_mod_export_cache(monkeypatch, tmp_path):
    """同原版+模组内容二次导出 → 复用缓存产物，不重编码。"""
    sound_dir = tmp_path / "sound"
    sound_dir.mkdir()
    (sound_dir / "Weapon.bank").write_bytes(b"orig")

    mod_dir = tmp_path / "mods"
    mod_dir.mkdir()
    mod_file = mod_dir / "Weapon.bank"
    mod_file.write_bytes(b"modded")

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(fb, "rebank_cache_dir", lambda: str(cache_dir))
    monkeypatch.setattr(fb, "_game_sound_dir", lambda game_path: str(sound_dir))
    monkeypatch.setattr(fb, "get_mod_path", lambda: str(mod_dir))
    monkeypatch.setattr(fb.ConfigManager, "get",
                        lambda self, k, d=None: str(tmp_path) if k == "game_path" else d)

    calls = {"n": 0}

    def fake_build_rebank(*a, **k):
        calls["n"] += 1
        out = k.get("out") if "out" in k else a[3]
        with open(out, "wb") as fh:
            fh.write(b"rebuilt-rebank")
        return {"modified": [], "added": [(0, "a.wav")], "count": 1, "out": out, "base_bank": "Weapon"}

    monkeypatch.setattr(fb, "build_rebank", fake_build_rebank)
    monkeypatch.setattr(fb, "_dlls", lambda: object())

    r1 = fb.bank_convert_mod("Weapon.bank", keep_original=True)
    assert r1["success"] is True
    assert calls["n"] == 1
    assert (mod_dir / "Weapon.rebank").read_bytes() == b"rebuilt-rebank"

    r2 = fb.bank_convert_mod("Weapon.bank", keep_original=True)
    assert r2["success"] is True and r2.get("cache_hit") is True
    assert r2["count"] == 1  # 缓存命中仍返回真实改动计数
    assert calls["n"] == 1  # 二次导出未重编码
