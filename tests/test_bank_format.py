import os
import struct

from webutils.bank.format import (
    assemble_bank, bank_base, bank_is_encrypted, extract_fsb_bytes,
    parse_bank, parse_bank_for_rebuild, parse_fsb5_header,
)


def build_fsb5_payload(num_samples=7, data_len=0):
    """构造 FSB5 头部（36 字节）+ 占位数据。"""
    return (b"FSB5" + struct.pack("<6I", 1, num_samples, 0, 0, data_len, 0)
            + b"\0" * 8 + b"D" * 16)


def build_test_bank(fsb_payloads, pad_len=4, version=0x59):
    """构造最小合法 FEV bank：RIFF + FEV + LIST(PROJ/BNKI) + SNDH + SND 块×n。
    fsb_payloads: 每个 FSB 的原始字节（测试中用假 FSB5 数据）。"""
    n = len(fsb_payloads)
    head = bytearray()
    head += b"RIFF" + struct.pack("<I", 0) + b"FEV "
    head += struct.pack("<I", version)     # 0x0C 版本
    head += struct.pack("<I", 0x2100)      # 0x10 自由
    head += struct.pack("<I", 0x21)        # 0x14 必须非 0
    head += struct.pack("<I", 0)           # 0x18 自由
    head += b"LIST" + struct.pack("<I", 8) + b"PROJ"
    head += b"BNKI" + struct.pack("<I", 0)  # PROJ/BNKI chunk（size=0）
    assert len(head) == 0x30
    sndh_body_len = 4 + 8 * n
    sndh_chunk = (b"SNDH" + struct.pack("<I", sndh_body_len)
                  + struct.pack("<I", 0) + struct.pack("<II", 0, 0) * n)
    sndh_start = len(head)
    snd_start = sndh_start + len(sndh_chunk)
    offsets, sizes = [], []
    p = snd_start
    for fsb in fsb_payloads:
        sizes.append(len(fsb))
        offsets.append(p + 8 + pad_len)
        p += 8 + pad_len + len(fsb)
    sndh_chunk = sndh_chunk[:-8 * n] + b"".join(
        struct.pack("<II", off, sz) for off, sz in zip(offsets, sizes))
    bank = head + sndh_chunk
    for fsb in fsb_payloads:
        bank += b"SND " + struct.pack("<I", pad_len + len(fsb)) + b"\0" * pad_len + fsb
    bank = bytearray(bank)
    struct.pack_into("<I", bank, 4, len(bank) - 8)
    return bytes(bank)


def test_parse_bank_ok():
    p1, p2 = b"FSB5" + b"A" * 100, b"FSB5" + b"B" * 200
    data = build_test_bank([p1, p2])
    info = parse_bank(data)
    assert info is not None
    assert info["fsb_count"] == 2
    assert data[info["fsb_offset"][0]:info["fsb_offset"][0] + info["fsb_size"][0]] == p1
    assert data[info["fsb_offset"][1]:info["fsb_offset"][1] + info["fsb_size"][1]] == p2


def test_parse_bank_invalid():
    assert parse_bank(b"") is None
    assert parse_bank(b"RIFF" + b"\0" * 100) is None
    assert parse_bank(build_test_bank([b"FSB5" + b"A" * 8])[:0x20]) is None


def test_bank_is_encrypted():
    data = build_test_bank([b"FSB5" + b"A" * 32])
    assert bank_is_encrypted(data, parse_bank(data)) is False
    data2 = build_test_bank([b"\x11\x22\x33\x44" + b"A" * 32])
    assert bank_is_encrypted(data2, parse_bank(data2)) is True


def test_extract_fsb_bytes():
    p1, p2 = b"FSB5" + b"A" * 64, b"FSB5" + b"B" * 64
    data = build_test_bank([p1, p2])
    assert extract_fsb_bytes(data, parse_bank(data)) == [p1, p2]


def test_parse_bank_for_rebuild_layout():
    p1, p2 = b"FSB5" + b"A" * 100, b"FSB5" + b"B" * 200
    data = build_test_bank([p1, p2], pad_len=4)
    info = parse_bank_for_rebuild(data)
    assert info is not None
    assert info["fsb_count"] == 2
    # sndh_location 指向 SNDH 表中第一个条目（sndh_unknown 之后）
    assert info["sndh_location"] == data.index(b"SNDH") + 8 + 4
    # snd_location[0] 为第一个 "SND " 块起点
    assert data[info["snd_location"][0]:info["snd_location"][0] + 4] == b"SND "
    # snd_buffer = chunk_size - fsb_size
    assert info["snd_buffer"][0] == 4
    assert info["snd_location"][1] == info["fsb_offset"][0] + info["fsb_size"][0]


def test_assemble_bank_roundtrip(tmp_path):
    p1, p2 = b"FSB5" + b"A" * 100, b"FSB5" + b"B" * 200
    data = build_test_bank([p1, p2])
    info = parse_bank_for_rebuild(data)
    out = str(tmp_path / "out.bank")
    new1, new2 = b"FSB5" + b"C" * 150, b"FSB5" + b"D" * 50  # 变长变短
    size = assemble_bank(data, info, [new1, new2], out)
    with open(out, "rb") as fh:
        rebuilt = fh.read()
    assert size == len(rebuilt)
    assert struct.unpack_from("<I", rebuilt, 4)[0] == len(rebuilt) - 8
    info2 = parse_bank_for_rebuild(rebuilt)
    assert info2 is not None
    assert info2["fsb_count"] == 2
    assert rebuilt[info2["fsb_offset"][0]:info2["fsb_offset"][0] + info2["fsb_size"][0]] == new1
    assert rebuilt[info2["fsb_offset"][1]:info2["fsb_offset"][1] + info2["fsb_size"][1]] == new2


def test_bank_base():
    assert bank_base("Weapon.bank") == "Weapon"
    assert bank_base("C:/x/Weapon.bank") == "Weapon"
    assert bank_base("Master.strings.bank") == "Master.strings"


def test_parse_fsb5_header():
    payload = build_fsb5_payload(num_samples=31, data_len=1024)
    h = parse_fsb5_header(payload)
    assert h is not None
    assert h["version"] == 1
    assert h["num_samples"] == 31
    assert h["data_size"] == 1024


def test_parse_fsb5_header_offsets_inside_bank():
    data = build_test_bank([build_fsb5_payload(num_samples=5)])
    info = parse_bank(data)
    off = info["fsb_offset"][0]
    h = parse_fsb5_header(data, off)
    assert h is not None and h["num_samples"] == 5


def test_parse_fsb5_header_invalid():
    assert parse_fsb5_header(b"") is None
    assert parse_fsb5_header(b"ABCD" + b"\0" * 32) is None           # 非 FSB5 魔数
    assert parse_fsb5_header(b"FSB5" + b"\0" * 8) is None            # 截断
    assert parse_fsb5_header(b"FSB5" + b"\0" * 40, offset=100) is None  # 越界
