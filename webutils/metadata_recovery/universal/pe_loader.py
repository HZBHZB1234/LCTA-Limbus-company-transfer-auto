#!/usr/bin/env python3
"""pe_loader.py - PE 解析（零第三方依赖）。

提供：镜像基址、节表（.text/.rdata/.data...）、VA↔文件偏移映射、
原始字节读取。仅用于 x86-64 PE（PE32+）。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


class PEFormatError(ValueError):
    pass


@dataclass
class Section:
    name: str
    virtual_address: int      # RVA
    virtual_size: int
    raw_offset: int           # 文件偏移
    raw_size: int
    characteristics: int


@dataclass
class PEImage:
    path: str
    data: bytes
    image_base: int
    sections: list[Section]
    entry_point: int          # RVA

    @property
    def text_section(self) -> Section | None:
        return next((s for s in self.sections if s.name == ".text"), None)

    def rva_to_off(self, rva: int) -> int | None:
        for s in self.sections:
            if s.virtual_address <= rva < s.virtual_address + max(s.virtual_size, s.raw_size):
                return s.raw_offset + (rva - s.virtual_address)
        return None

    def va_to_off(self, va: int) -> int | None:
        return self.rva_to_off(va - self.image_base)

    def bytes_at_va(self, va: int, size: int) -> bytes | None:
        off = self.va_to_off(va)
        if off is None:
            return None
        return self.data[off:off + size]

    def section_at_va(self, va: int) -> Section | None:
        rva = va - self.image_base
        for s in self.sections:
            if s.virtual_address <= rva < s.virtual_address + max(s.virtual_size, s.raw_size):
                return s
        return None


def load_pe(path: str) -> PEImage:
    data = open(path, "rb").read()
    if data[:2] != b"MZ":
        raise PEFormatError("not a PE (missing MZ header)")

    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        raise PEFormatError("not a PE (missing PE signature)")

    machine, nsec = struct.unpack_from("<HH", data, pe_off + 4)
    opt_size = struct.unpack_from("<H", data, pe_off + 20)[0]
    opt_off = pe_off + 24
    magic = struct.unpack_from("<H", data, opt_off)[0]
    if magic != 0x20B:  # PE32+
        raise PEFormatError(f"unsupported optional header magic {magic:#x}")

    image_base = struct.unpack_from("<Q", data, opt_off + 24)[0]
    entry_rva = struct.unpack_from("<I", data, opt_off + 16)[0]
    if machine != 0x8664:
        raise PEFormatError(f"not x86-64 (machine={machine:#x})")

    sections: list[Section] = []
    for i in range(nsec):
        off = opt_off + opt_size + 40 * i
        name = data[off:off + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, vaddr = struct.unpack_from("<II", data, off + 8)
        rsize, roff = struct.unpack_from("<II", data, off + 16)
        chars = struct.unpack_from("<I", data, off + 36)[0]
        sections.append(Section(name, vaddr, vsize, roff, rsize, chars))

    return PEImage(path, data, image_base, sections, entry_rva)
