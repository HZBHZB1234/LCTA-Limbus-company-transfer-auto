#!/usr/bin/env python3
"""xorshift_scan.py - 字节级 xorshift64(13,7,17) 指令模板扫描。

模板为一步 xorshift 的 MSVC 典型展开（寄存器无关）：
    shl r64, 0Dh ; xor r64,r64 ; mov r64,r64 ; shr r64,07h
    ; xor r64,r64 ; mov r64,r64 ; shl r64,11h ; xor r64,r64

寄存器字段用通配符，mov/xor 的 89/8B、31/33 双编码均接受。
"""

from __future__ import annotations

import re

# 8 字节宽通配：modrm 寄存器字段任意。
# 注意：shl 用 opcode 扩展 4（modrm E0-E7），shr 用扩展 5（E8-EF）。
_TEMPLATE = (
    b"\x48\xC1[\xE0-\xE7]\x0D"   # shl r64, 0Dh
    b"\x48[\x31\x33]."           # xor r64, r64   (31/33 双编码)
    b"\x48[\x89\x8B]."           # mov r64, r64   (89/8B 双编码)
    b"\x48\xC1[\xE8-\xEF]\x07"   # shr r64, 07h
    b"\x48[\x31\x33]."
    b"\x48[\x89\x8B]."
    b"\x48\xC1[\xE0-\xE7]\x11"   # shl r64, 11h
    b"\x48[\x31\x33]."
)

RE_TEMPLATE = re.compile(_TEMPLATE)


def scan(text_bytes: bytes, base_va: int) -> list[int]:
    """扫描返回命中的 VA 列表（按升序）。"""
    hits = []
    for m in RE_TEMPLATE.finditer(text_bytes):
        hits.append(base_va + m.start())
    return hits


def scan_pe(image) -> list[int]:
    """扫描 PE .text 段，返回命中 VA。"""
    sec = image.text_section
    if sec is None:
        raise ValueError("PE has no .text section")
    raw = image.data[sec.raw_offset:sec.raw_offset + sec.raw_size]
    return scan(raw, image.image_base + sec.virtual_address)
