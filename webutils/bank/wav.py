"""WAV 文件头读写、时长解析与清单工具。"""
import os
import struct
from typing import List, Optional, Tuple

HEADER_FMT = 18  # fmt chunk: 16 + 2 (cbSize)


def write_wav_header(fileobj, sample_rate, bits_per_sample, channels, data_len):
    fmt_type = 3 if bits_per_sample == 32 else 1  # 3 = IEEE float
    fileobj.write(b"RIFF")
    fileobj.write(struct.pack("<I", data_len + 38))
    fileobj.write(b"WAVE")
    fileobj.write(b"fmt ")
    fileobj.write(struct.pack("<I", HEADER_FMT))
    fileobj.write(struct.pack("<H", fmt_type))
    fileobj.write(struct.pack("<H", channels))
    fileobj.write(struct.pack("<I", sample_rate))
    block_align = channels * bits_per_sample // 8
    fileobj.write(struct.pack("<I", sample_rate * block_align))
    fileobj.write(struct.pack("<H", block_align))
    fileobj.write(struct.pack("<H", bits_per_sample))
    fileobj.write(struct.pack("<H", 0))  # cbSize
    fileobj.write(b"data")
    fileobj.write(struct.pack("<I", data_len))


def read_wav_info(data: bytes) -> Optional[Tuple[int, Optional[int], Optional[int], Optional[int]]]:
    """返回 (data_len, sample_rate, channels, bits_per_sample)；非法返回 None。"""
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    pos = 12
    rate = ch = bits = None
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        pos += 8
        if cid == b"fmt ":
            fmt = data[pos:pos + min(size, 40)]
            if len(fmt) >= 16:
                ch = struct.unpack_from("<H", fmt, 2)[0]
                rate = struct.unpack_from("<I", fmt, 4)[0]
                bits = struct.unpack_from("<H", fmt, 14)[0]
        elif cid == b"data":
            return size, rate, ch, bits
        pos += size + (size & 1)
    return None


def wav_duration(data_len, rate, ch, bits) -> float:
    if not rate or not ch or not bits:
        return 0.0
    return data_len / (rate * ch * (bits // 8))


def wav_duration_file(path: str) -> Optional[float]:
    try:
        with open(path, "rb") as fh:
            info = read_wav_info(fh.read())
    except OSError:
        return None
    if info is None:
        return None
    return round(wav_duration(*info), 3)


def find_wav_txt(wav_dir: str, base: str) -> Optional[str]:
    """定位 <base>.txt wav 清单：优先 wav_dir 根，其次子目录。"""
    for cand in (os.path.join(wav_dir, base + ".txt"),
                 os.path.join(wav_dir, base, base + ".txt")):
        if os.path.isfile(cand):
            return cand
    for root, _, files in os.walk(wav_dir):
        for f in files:
            if f.endswith(".txt") and f[:-4] == base:
                return os.path.join(root, f)
    return None


def read_wav_list(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return [line.rstrip("\r\n") for line in fh if line.strip() != ""]
