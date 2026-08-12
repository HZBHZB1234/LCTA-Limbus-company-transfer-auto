import os

import pytest

from webutils.bank.fmod import FORMAT_IDS, bank_password, extract_bank, rebuild_bank
from webutils.bank.format import extract_fsb_bytes, parse_bank, parse_bank_for_rebuild

from tests.test_bank_format import build_test_bank


class FakeDlls:
    """记录调用、不真正加载 DLL 的替身。"""

    def __init__(self):
        self.decoded = []
        self.encoded = []
        self.out_fsb = []

    def decode_fsb_to_wav(self, fsb_path, wav_dir, wav_name_base, password=None, log=None):
        self.decoded.append((fsb_path, wav_dir, wav_name_base, password))
        os.makedirs(wav_dir, exist_ok=True)
        # 每个 fsb 产出 1 个 wav + 1 个清单
        (open(os.path.join(wav_dir, "s.wav"), "wb")).close()
        with open(os.path.join(wav_dir, wav_name_base + ".txt"), "w", encoding="utf-8") as fh:
            fh.write("s.wav\n")
        return ["s.wav"]

    def encode_wavs_to_fsb(self, wav_files, out_fsb, format_id, quality, threads, cache_dir,
                           encrypt_key=None, log=None):
        self.encoded.append((wav_files, format_id, quality, threads, encrypt_key))
        self.out_fsb.append(out_fsb)
        with open(out_fsb, "wb") as fh:
            fh.write(b"FSB5" + b"E" * 64)


def _write_bank(tmp_path, payloads):
    p = tmp_path / "Weapon.bank"
    p.write_bytes(build_test_bank(payloads))
    return str(p)


def test_extract_bank(tmp_path):
    bank = _write_bank(tmp_path, [b"FSB5" + b"A" * 64, b"FSB5" + b"B" * 64])
    dlls = FakeDlls()
    wav_dir, fsb_dir = str(tmp_path / "wav"), str(tmp_path / "fsb")
    r = extract_bank(dlls, bank, wav_dir, fsb_dir)
    assert r["bank_base"] == "Weapon"
    assert r["fsb_count"] == 2
    assert r["encrypted"] is False
    assert len(dlls.decoded) == 2
    assert (tmp_path / "fsb" / "Weapon[0].fsb").read_bytes() == b"FSB5" + b"A" * 64


def test_extract_bank_encrypted_password_file(tmp_path):
    payload = b"\x11\x22\x33\x44" + b"A" * 32
    bank = _write_bank(tmp_path, [payload])
    (tmp_path / "Weapon.txt").write_text("mysecret\n", encoding="utf-8")
    dlls = FakeDlls()
    r = extract_bank(dlls, bank, str(tmp_path / "wav"), str(tmp_path / "fsb"))
    assert r["encrypted"] is True
    assert r["password_used"] == "mysecret"
    assert dlls.decoded[0][3] == "mysecret"


def test_rebuild_bank(tmp_path):
    payloads = [b"FSB5" + b"A" * 100, b"FSB5" + b"B" * 100]
    bank = _write_bank(tmp_path, payloads)
    dlls = FakeDlls()
    wav_dir, fsb_dir = str(tmp_path / "wav"), str(tmp_path / "fsb")
    extract_bank(dlls, bank, wav_dir, fsb_dir)
    build_dir = str(tmp_path / "build")
    options = {"format": FORMAT_IDS["vorbis"], "quality": 92, "threads": 2,
               "cache_dir": str(tmp_path / "cache"), "password": None}
    out = rebuild_bank(dlls, bank, wav_dir, fsb_dir, build_dir, options)
    assert out == str(tmp_path / "build" / "Weapon.bank")
    assert len(dlls.encoded) == 2
    assert dlls.encoded[0][1] == 5  # vorbis
    rebuilt = open(out, "rb").read()
    info = parse_bank_for_rebuild(rebuilt)
    assert info is not None
    # 新 FSB 数据已拼入（fake 编码产物 64 字节）
    assert len(extract_fsb_bytes(rebuilt, parse_bank(rebuilt))) == 2


def test_bank_password(tmp_path):
    (tmp_path / "A.txt").write_text("a1\n", encoding="utf-8")
    (tmp_path / "password.txt").write_text("pw\n", encoding="utf-8")
    assert bank_password(str(tmp_path / "A.bank")) == "a1"
    assert bank_password(str(tmp_path / "B.bank")) == "pw"
    assert bank_password(str(tmp_path / "C.bank"), explicit="ex") == "ex"
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert bank_password(str(empty_dir / "D.bank")) is None
