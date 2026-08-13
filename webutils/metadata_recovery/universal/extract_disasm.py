#!/usr/bin/env python3
"""extract_disasm.py - 指令级解密参数提取（capstone，版本无关）。

对 init 函数反汇编应用指令形态规则（无文本正则、无函数名依赖）：

- file_base：文件加载签名（call → mov [rip+],rax → test rax,rax → jcc）后的
  全局写入目标。
- header_size：文件加载后首个分配调用前的 `mov ecx, imm`；与 header xor
  循环边界 `cmp rX, imm` 交叉验证。
- header_seed：首个 xorshift 块前的首个 `mov r64, imm64`。
- table_addr：函数内首个指向数据段的目标 lea（替换表）。
- 节块（每个 `add rX, [rip+file_base]` 对应一个拷贝调用）：
    size_off    = 锚点前最后一个 movsxd r32,[rHdr+disp] 的 disp
    offset_off  = 锚点前最后一个 mov r32,[rHdr+disp]（非 movsxd）的 disp
    adj         = offset 加载后 3 条内的 sub/add 立即数
    seed        = 拷贝调用后首个 `mov r64, imm64`
"""

from __future__ import annotations

import re

try:
    from capstone import CS_ARCH_X86, CS_MODE_64, Cs
    _CAPSTONE_OK = True
except ImportError:  # capstone 未安装时保持模块可导入（页面提示一键安装）
    CS_ARCH_X86 = CS_MODE_64 = Cs = None
    _CAPSTONE_OK = False

from .init_locator import disasm_func
from .pe_loader import PEImage

_DATA_MIN = 0x180000000
_DATA_MAX = 0x190000000
_LOOKBACK = 30          # 节块锚点反扫窗口
_LOOKAHEAD = 20         # 拷贝调用后 seed 前扫窗口
FUNC_WINDOW = 0x4000    # 函数反汇编窗口（与 init_locator 一致）


def _require_capstone():
    if not _CAPSTONE_OK:
        raise RuntimeError(
            "缺少 capstone 反汇编库：请先在 Metadata 恢复页「步骤 1」一键安装"
            "（或 pip install capstone）")


class Extraction:
    def __init__(self) -> None:
        self.header_size: int | None = None
        self.header_seed: int | None = None
        self.table_addr: str | None = None
        self.table_hex: str | None = None
        self.file_base: str | None = None
        self.header_base: str | None = None
        self.sections: list[dict] = []
        self.errors: list[str] = []
        self.evidence: list[str] = []

    def to_dict(self) -> dict:
        return {
            "header_size": self.header_size,
            "header_seed": None if self.header_seed is None else f"0x{self.header_seed:X}",
            "table_addr": self.table_addr,
            "file_base": self.file_base,
            "header_base": self.header_base,
            "sections": self.sections,
            "errors": self.errors,
        }

    def to_profile(self) -> dict:
        """gen1 兼容的 profile 格式（candidate_verify / solve 可直接消费）。"""
        return {
            "header_size": self.header_size,
            "header_seed": None if self.header_seed is None else f"0x{self.header_seed:X}",
            "table_addr": self.table_addr,
            "table_hex": self.table_hex,
            "file_base": self.file_base,
            "header_base": self.header_base,
            "sections": self.sections,
        }


def _imm(s: str) -> int | None:
    m = re.search(r"0x([0-9A-Fa-f]+)", s)
    return int(m.group(1), 16) if m else None


def _is_reg64(s: str) -> bool:
    return s in ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp",
                 "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15")


def _is_mem_rip(ops: str, imm: int) -> bool:
    return f"0x{imm:x}" in ops.lower() and "[rip" in ops


def _trim_to_function(image: PEImage, func_va: int,
                      insns: list[tuple[int, int, str, str]]) -> list[tuple[int, int, str, str]]:
    """裁剪到函数实际范围：首个 ≥4 字节 CC 填充（函数间 padding）为止。"""
    sec = image.text_section
    raw = image.data[sec.raw_offset:sec.raw_offset + sec.raw_size]
    base = image.image_base + sec.virtual_address
    off = func_va - base
    end_off = None
    run = 0
    for i in range(off, min(off + FUNC_WINDOW, len(raw))):
        if raw[i] == 0xCC:
            run += 1
            if run >= 4:
                end_off = i - run + 1
                break
        else:
            run = 0
    if end_off is None:
        return insns
    end_va = base + end_off
    return [insn for insn in insns if insn[0] < end_va]


def extract_from_disasm(image: PEImage, func_va: int, insns: list[tuple[int, int, str, str]] | None = None) -> Extraction:
    _require_capstone()
    ext = Extraction()
    if insns is None:
        insns = disasm_func(image, func_va)
    insns = _trim_to_function(image, func_va, insns)

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    _ = md  # 保留未来扩展

    # ---- 1. file_base 全局 ------------------------------------------------
    file_base = None
    file_load_idx = None
    for i, (addr, size, mnem, ops) in enumerate(insns):
        if mnem != "call":
            continue
        nxt = insns[i + 1:i + 5]
        got_mov = got_test = got_jcc = False
        for naddr, nm_size, nm, nops in nxt:
            if nm == "mov" and "[rip" in nops:
                m = re.search(r"0x([0-9A-Fa-f]+)", nops)
                if m:
                    target = (naddr + nm_size + int(m.group(1), 16)) & 0xFFFFFFFFFFFFFFFF
                    if _DATA_MIN <= target <= _DATA_MAX:
                        got_mov = target
            elif nm == "test" and "rax" in nops:
                got_test = True
            elif nm.startswith("j") and got_test:
                got_jcc = True
                break
        if got_mov and got_test and got_jcc:
            file_base = got_mov
            file_load_idx = i
            ext.file_base = f"0x{file_base:X}"
            ext.evidence.append(f"L{i}: file_base global=0x{file_base:X} "
                                f"({mnem} {ops})")
            break
    if file_base is None:
        ext.errors.append("未定位到 file_base 全局（文件加载签名缺失）")

    # ---- 2. header_size：文件加载后首个分配调用 ---------------------------
    header_alloc_idx = None
    if file_load_idx is not None:
        for i in range(file_load_idx + 1, len(insns)):
            if insns[i][2] == "call":
                header_alloc_idx = i
                break
    if header_alloc_idx is not None:
        for j in range(max(0, header_alloc_idx - 6), header_alloc_idx):
            _, _, mnem, ops = insns[j]
            if mnem == "mov" and ops.startswith(("ecx", "rcx", "edx", "rdx")):
                val = _imm(ops)
                if val is not None and val < 0x100000:
                    ext.header_size = val
                    ext.evidence.append(
                        f"L{header_alloc_idx}: header 分配 mov {ops} 于 0x{insns[header_alloc_idx][0]:X}")
                    break

    # ---- 3. header_seed + table：首个 xorshift 块前 -----------------------
    # 找首个 xorshift 块（shl r64,0Dh 出现处）
    first_xor_idx = None
    for i, (addr, size, mnem, ops) in enumerate(insns):
        if mnem == "shl" and "0xd" in ops and _is_reg64(ops.split(",")[0].strip()):
            first_xor_idx = i
            break
    if first_xor_idx is not None:
        for j in range(header_alloc_idx or 0, first_xor_idx):
            _, _, mnem, ops = insns[j]
            if mnem in ("mov", "movabs") and _is_reg64(ops.split(",")[0].strip()):
                val = _imm(ops)
                if val is not None and val > 0xFFFFFFFF:
                    ext.header_seed = val
                    ext.evidence.append(f"L{j}: header seed=0x{val:X}")
                    break
        for j in range(header_alloc_idx or 0, first_xor_idx):
            _, jsize, mnem, ops = insns[j]
            if mnem == "lea" and "," in ops and "[rip" in ops:
                m = re.search(r"0x([0-9A-Fa-f]+)", ops)
                if m:
                    addr = insns[j][0]
                    target = (addr + jsize + int(m.group(1), 16)) & 0xFFFFFFFFFFFFFFFF
                    if _DATA_MIN <= target <= _DATA_MAX:
                        ext.table_addr = f"0x{target:X}"
                        table_bytes = image.bytes_at_va(target, 256)
                        if table_bytes and len(table_bytes) == 256:
                            ext.table_hex = table_bytes.hex()
                        ext.evidence.append(f"L{j}: 替换表=0x{target:X}")
                        break
        # 交叉验证：header xor 循环边界立即数
        for j in range(first_xor_idx, min(first_xor_idx + 400, len(insns))):
            _, _, mnem, ops = insns[j]
            if mnem == "cmp" and _is_reg64(ops.split(",")[0].strip()):
                val = _imm(ops)
                if val is not None and val < 0x100000:
                    if ext.header_size is not None and val != ext.header_size:
                        ext.errors.append(
                            f"header_size 冲突：分配={ext.header_size} 循环边界={val}")
                    elif ext.header_size is None:
                        ext.header_size = val
                        ext.evidence.append(f"L{j}: header 循环边界=0x{val:X}（交叉验证）")
                    break

    # ---- 4. 节块 ----------------------------------------------------------
    if file_base is not None:
        for i, (addr, size, mnem, ops) in enumerate(insns):
            if mnem != "add" or "[rip" not in ops:
                continue
            m = re.search(r"0x([0-9A-Fa-f]+)", ops)
            if not m:
                continue
            tgt = (addr + size + int(m.group(1), 16)) & 0xFFFFFFFFFFFFFFFF
            if tgt != file_base:
                continue
            sec = _extract_section(insns, i, file_base)
            if sec is None:
                continue
            ext.sections.append(sec)
            ext.evidence.append(
                f"L{i}: 节块 size_off={sec['size_off']} offset_off={sec['offset_off']} "
                f"adj={sec['adj']} seed={sec['seed']}  @0x{addr:X}")

    # ---- 一致性 ------------------------------------------------------------
    if ext.header_size is None:
        ext.errors.append("未提取到 header_size")
    if ext.header_seed is None:
        ext.errors.append("未提取到 header_seed")
    if ext.table_addr is None:
        ext.errors.append("未提取到替换表")
    if len(ext.sections) < 5:
        ext.errors.append(f"节块数量异常：{len(ext.sections)}")
    bases = {s["size_off"] for s in ext.sections}
    if len(bases) != len(ext.sections):
        ext.errors.append("存在重复 size_off，节块划分可能错乱")
    return ext


def _extract_section(insns: list[tuple[int, int, str, str]],
                     anchor: int, file_base: int) -> dict | None:
    """从 `add rX, [rip+file_base]` 锚点提取一个节块参数。"""
    # ---- 锚点后：拷贝调用 → seed ------------------------------------------
    seed = None
    call_idx = None
    for j in range(anchor + 1, min(anchor + 12, len(insns))):
        if insns[j][2] == "call":
            call_idx = j
            break
    if call_idx is not None:
        for j in range(call_idx + 1, min(call_idx + _LOOKAHEAD, len(insns))):
            _, _, mnem, ops = insns[j]
            if mnem in ("mov", "movabs") and _is_reg64(ops.split(",")[0].strip()):
                val = _imm(ops)
                if val is not None and val > 0xFFFFFFFF:
                    seed = val
                    break

    # ---- 锚点前：size_off / offset_off / adj ------------------------------
    # disp 可为 0（08-06 末节 offset 字段在 header 偏移 0 处，capstone 渲染无 +disp）；
    # capstone 小位移渲染为十进制（如 [rbx + 4]），大位移为十六进制。
    size_off = None
    offset_off = None
    adj = 0
    re_disp = re.compile(
        r"dword ptr \[([^\]\s]+)(?:\s*\+\s*(-?0x[0-9A-Fa-f]+|-?\d+))?\]")

    def _disp(m) -> int:
        g = m.group(2)
        if g is None:
            return 0
        return int(g, 16) if g.lower().startswith("0x") else int(g)

    lo = max(0, anchor - _LOOKBACK)
    for j in range(anchor - 1, lo - 1, -1):
        _, _, mnem, ops = insns[j]
        if mnem == "movsxd" and "dword ptr [" in ops:
            m = re_disp.search(ops)
            if m and size_off is None:
                size_off = _disp(m)
            continue
        if mnem == "mov" and re.match(r"e[a-d]x|r8d|r9d|r10d|r11d|r12d|r13d|r14d|r15d, dword ptr \[", ops):
            m = re_disp.search(ops)
            if m and offset_off is None:
                offset_off = _disp(m)
                # 后 3 条内找 sub/add 立即数（adj）
                for k in range(j + 1, min(j + 4, len(insns))):
                    km, kops = insns[k][2], insns[k][3]
                    if km in ("sub", "add"):
                        mm = re.match(r"\S+,\s*(-?0x[0-9A-Fa-f]+|-?\d+)", kops)
                        if mm:
                            v = int(mm.group(1), 16) if mm.group(1).lower().startswith("0x") else int(mm.group(1))
                            adj = -v if km == "sub" else v
                            break
            if offset_off is not None and size_off is not None:
                break
        if mnem in ("call", "ret", "jmp", "jne", "je", "ja", "jb", "jae", "jbe", "jg", "jl"):
            if size_off is not None:
                break

    if size_off is None or offset_off is None:
        return None
    return {
        "size_off": size_off,
        "offset_off": offset_off,
        "adj": adj,
        "seed": None if seed is None else f"0x{seed:X}",
    }
