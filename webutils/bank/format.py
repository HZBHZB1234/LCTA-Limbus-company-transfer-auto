"""FEV (.bank) 容器格式解析与重组 —— 纯 Python，无 DLL 依赖。

Limbus Company 音频包为 RIFF 容器:
    RIFF size "FEV " [标志区] "LIST" PROJ BNKI ... SNDH ... SND ... STBL ...
SNDH 块携带 (offset, size) 表，指向各 FSB 数据；每个 FSB 以 "SND " 块包裹。
"""
import os
import struct
from typing import List, Optional

SNDH_MAGIC = 0x48444E53   # "SNDH"
STBL_MAGIC = 0x4C425453   # "STBL"
SND_MAGIC = 0x20444E53    # "SND "
END_MAGIC = 0xFFFFFFFF


def _u32(data: bytes, pos: int) -> int:
    return struct.unpack_from("<I", data, pos)[0]


def parse_bank(data: bytes) -> Optional[dict]:
    """解析 bank，返回 {fsb_offset, fsb_size, fsb_count}；非法返回 None。"""
    if len(data) < 0x24 or data[0:4] != b"RIFF" or data[0x08:0x0C] != b"FEV ":
        return None
    if _u32(data, 0x14) == 0 or data[0x1C:0x20] != b"LIST":
        return None
    pos = 0x24
    if data[pos:pos + 4] != b"PROJ" or data[pos + 4:pos + 8] != b"BNKI":
        return None
    pos += 8
    pos += 4 + _u32(data, pos)  # 跳过 PROJ/BNKI chunk 体

    while pos + 8 <= len(data):
        chunk_type = _u32(data, pos)
        chunk_size = _u32(data, pos + 4)
        pos += 8
        if chunk_type == END_MAGIC or chunk_size == END_MAGIC:
            return None
        if chunk_type == SNDH_MAGIC:
            if chunk_size < 4:
                return None
            fsb_count = (chunk_size - 4) // 8
            pos += 4  # sndh_unknown
            offsets = [_u32(data, pos + 8 * j) for j in range(fsb_count)]
            sizes = [_u32(data, pos + 4 + 8 * j) for j in range(fsb_count)]
            if not offsets or not offsets[0] or not sizes[0]:
                return None
            return {"fsb_offset": offsets, "fsb_size": sizes, "fsb_count": fsb_count}
        pos += chunk_size
    return None


def parse_bank_for_rebuild(data: bytes) -> Optional[dict]:
    """解析 bank 全布局（含 SND 块位置），供重打包拼接。"""
    if len(data) < 0x24 or data[0:4] != b"RIFF" or data[0x08:0x0C] != b"FEV ":
        return None
    if _u32(data, 0x14) == 0 or data[0x1C:0x20] != b"LIST":
        return None
    pos = 0x24
    if data[pos:pos + 4] != b"PROJ" or data[pos + 4:pos + 8] != b"BNKI":
        return None
    pos += 8
    pos += 4 + _u32(data, pos)

    fsb_offset = fsb_size = snd_location = snd_buffer = None
    sndh_location = 0
    fsb_count = 1
    sndh_unknown = 0

    while pos + 8 <= len(data):
        chunk_type = _u32(data, pos)
        chunk_size = _u32(data, pos + 4)
        pos += 8
        if chunk_type == END_MAGIC or chunk_size == END_MAGIC:
            return None
        if chunk_type == SNDH_MAGIC:
            fsb_count = (chunk_size - 4) // 8
            sndh_unknown = _u32(data, pos)
            pos += 4
            sndh_location = pos
            fsb_offset = [_u32(data, pos + 8 * j) for j in range(fsb_count)]
            fsb_size = [_u32(data, pos + 4 + 8 * j) for j in range(fsb_count)]
            pos += 8 * fsb_count
            continue
        if chunk_type == STBL_MAGIC:
            if chunk_size != 0:
                hash_pos = pos + chunk_size
                if hash_pos + 4 <= len(data):
                    hash_val = _u32(data, hash_pos)
                    if hash_val not in (0x20444E53, 0x48534148):  # "SND ", "HASH"
                        chunk_size += 1
            pos += chunk_size
            continue
        if chunk_type == SND_MAGIC and snd_location is None:
            snd_location = [0] * fsb_count
            snd_buffer = [0] * fsb_count
            snd_location[0] = pos - 8
            snd_buffer[0] = chunk_size - fsb_size[0]
            if fsb_count > 1:
                for j in range(fsb_count - 1):
                    snd_location[j + 1] = fsb_offset[j] + fsb_size[j]
                    p2 = snd_location[j + 1] + 4
                    if p2 + 4 <= len(data):
                        snd_buffer[j + 1] = _u32(data, p2) - fsb_size[j + 1]
            return {
                "fsb_offset": fsb_offset,
                "fsb_size": fsb_size,
                "fsb_count": fsb_count,
                "snd_location": snd_location,
                "snd_buffer": snd_buffer,
                "sndh_location": sndh_location,
            }
        pos += chunk_size
    return None


def extract_fsb_bytes(data: bytes, info: dict) -> List[bytes]:
    return [data[info["fsb_offset"][i]:info["fsb_offset"][i] + info["fsb_size"][i]]
            for i in range(info["fsb_count"])]


def bank_is_encrypted(data: bytes, info: dict) -> bool:
    off = info["fsb_offset"][0]
    return off + 4 <= len(data) and data[off:off + 4] != b"FSB5"


FSB5_HEADER_SIZE = 0x24  # 36 字节：魔数 + 6 个 u32


def parse_fsb5_header(data: bytes, offset: int = 0) -> Optional[dict]:
    """解析 FSB5 头部，返回子音数等元数据；非 FSB5 / 截断返回 None。

    字段布局取自 FSB5 公开格式：magic(4) + version(4) + numSamples(4)
    + sampleHeaderSize(4) + nameSize(4) + dataSize(4) + subHeaderSize(4)。
    """
    if offset < 0 or offset + FSB5_HEADER_SIZE > len(data):
        return None
    if data[offset:offset + 4] != b"FSB5":
        return None
    (version, num_samples, sample_header_size, name_size,
     data_size, sub_header_size) = struct.unpack_from("<6I", data, offset + 4)
    return {
        "version": version,
        "num_samples": num_samples,
        "sample_header_size": sample_header_size,
        "name_size": name_size,
        "data_size": data_size,
        "sub_header_size": sub_header_size,
    }


def assemble_bank(original: bytes, info: dict, fsb_data: List[bytes], out_path: str) -> int:
    """把新 FSB 数据拼回原 bank 布局（重写 SNDH 表与 SND 块、修正 RIFF size）。"""
    n = info["fsb_count"]
    new_sizes = [len(b) for b in fsb_data]
    snd_buffer = info["snd_buffer"]
    first_off = info["fsb_offset"][0]
    offsets = [first_off] + [0] * (n - 1)
    for i in range(n - 1):
        offsets[i + 1] = offsets[i] + new_sizes[i] + snd_buffer[i + 1] + 8
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(original[:first_off])
        fh.seek(info["sndh_location"])
        for i in range(n):
            fh.write(struct.pack("<II", offsets[i], new_sizes[i]))
        fh.seek(info["snd_location"][0])
        for i in range(n):
            fh.write(b"SND " + struct.pack("<I", new_sizes[i] + snd_buffer[i]))
            if snd_buffer[i]:
                fh.write(b"\0" * snd_buffer[i])
            fh.write(fsb_data[i])
        end = fh.tell()
        fh.seek(4)
        fh.write(struct.pack("<I", end - 8))
    return os.path.getsize(out_path)


def bank_base(name_or_path: str) -> str:
    name = os.path.basename(name_or_path)
    if name.lower().endswith(".bank"):
        name = name[:-5]
    return name
