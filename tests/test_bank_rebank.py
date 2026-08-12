import io
import json
import os
import zipfile

from webutils.bank.rebank import (
    CONFIG_NAME, build_rebank, iter_rebank_wavs, make_rebank, patch_banks,
    read_rebank_info,
)
from webutils.bank.wav import write_wav_header

from tests.test_bank_fmod import FakeDlls
from tests.test_bank_format import build_test_bank


def _wav_bytes(seconds=1.0, rate=44100, bits=16, ch=2):
    buf = io.BytesIO()
    write_wav_header(buf, rate, bits, ch, int(seconds * rate * ch * (bits // 8)))
    return buf.getvalue()


def _bank_with_wavs(tmp_path, name, wav_specs):
    """wav_specs: {fsb_idx: [(wav_name, seconds), ...]} → 生成含对应 FSB 的 bank 文件。

    FakeDlls.decode 不检查 fsb 内容，所以 payload 任意即可。
    """
    bank = tmp_path / name
    n = max(wav_specs) + 1
    bank.write_bytes(build_test_bank([b"FSB5" + b"P" * (32 + i) for i in range(n)]))
    return str(bank)


class FakeDllsRecord(FakeDlls):
    """FakeDlls 扩展：decode 时按 bank 基名 + FSB 序号生成 wav 清单与文件。

    build_rebank 用同一实例解码原版与模组两个 bank，因此 spec 需按 bank 基名区分。
    """

    def __init__(self, spec_by_base):
        super().__init__()
        self.spec_by_base = spec_by_base

    def decode_fsb_to_wav(self, fsb_path, wav_dir, wav_name_base, password=None, log=None):
        self.decoded.append((fsb_path, wav_dir, wav_name_base, password))
        base = wav_name_base[:wav_name_base.rindex("[")]
        idx = int(wav_name_base[wav_name_base.rindex("[") + 1:-1])
        os.makedirs(wav_dir, exist_ok=True)
        names = []
        for wname, secs in self.spec_by_base.get(base, {}).get(idx, []):
            with open(os.path.join(wav_dir, wname + ".wav"), "wb") as fh:
                fh.write(_wav_bytes(secs))
            names.append(wname + ".wav")
        with open(os.path.join(wav_dir, wav_name_base + ".txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(names) + "\n")
        return names


def test_make_and_read_rebank(tmp_path):
    stage = tmp_path / "stage"
    sub = stage / "0"
    sub.mkdir(parents=True)
    (sub / "a.wav").write_bytes(b"x")
    (stage / CONFIG_NAME).write_text(json.dumps({"name": "m"}), encoding="utf-8")
    out = str(tmp_path / "m.rebank")
    make_rebank(str(stage), out)
    cfg, wavs = read_rebank_info(out)
    assert cfg == {"name": "m"}
    assert wavs == ["0/a.wav"]
    got = list(iter_rebank_wavs(out))
    assert got == [(0, "a.wav", b"x")]


def test_build_rebank(tmp_path):
    orig_specs = {0: [("a", 1.0), ("b", 2.0)], 1: [("c", 1.0)]}
    mod_specs = {0: [("a", 1.0), ("b", 3.0)], 1: [("c", 1.0), ("d", 1.0)]}  # b 变长, d 新增
    original = _bank_with_wavs(tmp_path, "Weapon.bank", orig_specs)
    modded = _bank_with_wavs(tmp_path, "WeaponMod.bank", mod_specs)
    out = str(tmp_path / "mod.rebank")
    dlls = FakeDllsRecord({"Weapon": orig_specs, "WeaponMod": mod_specs})
    r = build_rebank(dlls, original, modded, out,
                     {"name": "测试模组", "version": "1.0", "author": "x", "description": "y"},
                     work_dir=str(tmp_path / "work"))
    assert r["base_bank"] == "Weapon"
    assert r["modified"] == [(0, "b.wav")]
    assert r["added"] == [(1, "d.wav")]
    assert r["count"] == 2
    cfg, wavs = read_rebank_info(out)
    assert cfg["base_bank"] == "Weapon"
    assert wavs == ["0/b.wav", "1/d.wav"]
    assert {n for _, n, _ in iter_rebank_wavs(out)} == {"b.wav", "d.wav"}
    assert not os.path.exists(str(tmp_path / "work"))  # 临时目录已清理


def test_patch_banks(tmp_path):
    orig_specs = {0: [("a", 1.0), ("b", 2.0)], 1: [("c", 1.0)]}
    target = _bank_with_wavs(tmp_path, "Weapon.bank", orig_specs)
    dlls = FakeDllsRecord({"Weapon": orig_specs})

    # 用 build_rebank 构造一个补丁（b 变长 3s，d 新增）
    mod_specs = {0: [("a", 1.0), ("b", 3.0)], 1: [("c", 1.0), ("d", 1.0)]}
    modded = _bank_with_wavs(tmp_path, "WeaponMod.bank", mod_specs)
    rebank = str(tmp_path / "mod.rebank")
    build_rebank(FakeDllsRecord({"Weapon": orig_specs, "WeaponMod": mod_specs}),
                 target, modded, rebank,
                 {"name": "m", "version": "1", "author": "", "description": ""},
                 work_dir=str(tmp_path / "work2"))

    # 打补丁到目标（b 被替换为 3s 版，d 是新增 → 跳过）
    out_dir = str(tmp_path / "build")
    r = patch_banks(dlls, target, [rebank], out_dir, work_dir=str(tmp_path / "work3"))
    assert r["replaced"] == 1
    assert r["skipped_new"] == 1
    assert r["skipped_bad"] == 0
    assert os.path.isfile(r["out_bank"])
    # 重建后 bank 仍可解析
    from webutils.bank.format import parse_bank
    with open(r["out_bank"], "rb") as fh:
        assert parse_bank(fh.read()) is not None
