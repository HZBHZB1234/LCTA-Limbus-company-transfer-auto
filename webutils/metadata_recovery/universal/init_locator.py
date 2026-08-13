#!/usr/bin/env python3
"""init_locator.py - 解密入口候选函数定位与评分（capstone，无 IDA）。

输入：PE + xorshift 命中列表。
对每个命中反扫函数起始（前一个 ret/int3 填充），反汇编函数窗口，
统计版本无关特征并评分。特征设计基于 07-30/08-06/08-13 三版 init 函数
共有的指令形态：xorshift 循环数、128 位拷贝（header 拷贝循环）、
64 位立即数（seeds）、数据段 lea（替换表）、全局写入（基址槽）。
"""

from __future__ import annotations

try:
    from capstone import CS_ARCH_X86, CS_MODE_64, Cs
    _CAPSTONE_OK = True
except ImportError:  # capstone 未安装时保持模块可导入（页面提示一键安装）
    CS_ARCH_X86 = CS_MODE_64 = Cs = None
    _CAPSTONE_OK = False

from .pe_loader import PEImage
from .xorshift_scan import RE_TEMPLATE, scan_pe

# 数据段地址范围（镜像内）
_DATA_MIN = 0x180000000
_DATA_MAX = 0x190000000

BACK_WINDOW = 0x4000      # 反扫函数起点的最大距离
FUNC_WINDOW = 0x4000      # 单函数反汇编窗口
PADDING_RUN = 4           # CC 填充判定阈值


def _require_capstone():
    if not _CAPSTONE_OK:
        raise RuntimeError(
            "缺少 capstone 反汇编库：请先在 Metadata 恢复页「步骤 1」一键安装"
            "（或 pip install capstone）")


def function_start_of(hit_va: int, image: PEImage, back_window: int = BACK_WINDOW) -> int:
    """从命中地址反扫到函数起点。

    普通反扫（前一个 retn/int3 填充）会误停在函数内的早期 return 路径
    （init 函数失败分支在 0x18069C626 retn）。因此对每个候选起点附加
    "init 前导签名"验证：起点与命中之间必须存在
        call xxx ; mov cs:[data_global], rax
    （文件加载调用 + 文件基址全局写入）——这是三版 init 共有的稳定形态。
    """
    _require_capstone()
    sec = image.text_section
    raw = image.data[sec.raw_offset:sec.raw_offset + sec.raw_size]
    base = image.image_base + sec.virtual_address
    idx = hit_va - base
    lo = max(0, idx - back_window)

    md = Cs(CS_ARCH_X86, CS_MODE_64)

    def has_fileload(lo_off: int, hi_off: int) -> bool:
        """[lo, hi) 内是否存在文件加载签名：
        call xxx → mov [rip+imm], r64 → test r64,r64 → jcc。
        （分配调用也会写全局，但无 test/jcc 空指针检查，可区分。）"""
        for insn in md.disasm(raw[lo_off:lo_off + (hi_off - lo_off)], base + lo_off):
            addr = insn.address
            if addr + 12 > base + hi_off:
                break
            if insn.mnemonic != "call":
                continue
            seq = list(md.disasm(raw[(addr - base):(addr - base) + 32], addr))
            got_mov = got_test = got_jcc = False
            for n in seq[1:6]:
                if n.mnemonic == "mov" and "[rip" in n.op_str:
                    got_mov = True
                elif n.mnemonic == "test" and n.op_str.startswith("rax"):
                    got_test = True
                elif n.mnemonic.startswith("j") and got_test:
                    got_jcc = True
                    break
            if got_mov and got_test and got_jcc:
                return True
            break
        return False

    i = idx - 1
    cc_run = 0
    while i >= lo:
        b = raw[i]
        if b == 0xCC:
            cc_run += 1
            i -= 1
            continue
        marker = None
        if cc_run >= 2:
            marker = i + cc_run + 1
        elif b == 0xC3:
            marker = i + 1
        if marker is not None:
            if has_fileload(marker, idx):
                return base + marker
            cc_run = 0
            i = marker - 2  # 跳过候选起点，继续向更早的 marker 反扫
            continue
        cc_run = 0
        i -= 1
    return base + sec.virtual_address


def disasm_func(image: PEImage, start_va: int, window: int = FUNC_WINDOW) -> list[tuple[int, int, str, str]]:
    """反汇编 [start, start+window)，返回 [(addr, size, mnemonic, op_str)]。"""
    _require_capstone()
    sec = image.text_section
    raw = image.data[sec.raw_offset:sec.raw_offset + sec.raw_size]
    base = image.image_base + sec.virtual_address
    off = start_va - base
    if off < 0 or off >= len(raw):
        return []
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = False
    out = []
    for insn in md.disasm(raw[off:off + window], start_va):
        out.append((insn.address, insn.size, insn.mnemonic, insn.op_str))
    return out


def _imm_of(op_str: str) -> int | None:
    """解析 '0x1234' / '1234' 形式的立即数。"""
    s = op_str.replace(" ", "")
    if s.startswith("0x") or s.startswith("0X"):
        return int(s[2:], 16)
    return None


def fine_features(image: PEImage, start_va: int) -> dict:
    insns = disasm_func(image, start_va)

    table_ref = 0
    oword = 0
    imm64 = 0
    global_write = 0
    calls = 0
    for addr, size, mnem, ops in insns:
        if mnem == "lea":
            if "," in ops:
                val = _imm_of(ops.split(",")[1])
                if val is not None and _DATA_MIN <= val <= _DATA_MAX:
                    table_ref += 1
        if mnem in ("movups", "movdqu", "movaps", "movapd", "movupd"):
            oword += 1
        if mnem == "mov":
            parts = ops.split(",")
            if len(parts) == 2 and parts[0].startswith(("r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15", "rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp")):
                val = _imm_of(parts[1])
                if val is not None and val > 0xFFFFFFFF:
                    imm64 += 1
            if "[rip" in parts[0]:
                # 全局写入：mov qword ptr [rip + imm], r64
                import re as _re
                m = _re.search(r"0x([0-9A-Fa-f]+)", parts[0])
                if m:
                    target = (addr + size + int(m.group(1), 16)) & 0xFFFFFFFFFFFFFFFF
                    if _DATA_MIN <= target <= _DATA_MAX:
                        global_write += 1
        if mnem == "call":
            calls += 1

    # xorshift 循环数：用字节模板在函数窗口内统计
    sec = image.text_section
    raw = image.data[sec.raw_offset:sec.raw_offset + sec.raw_size]
    base = image.image_base + sec.virtual_address
    off = start_va - base
    window = raw[off:off + FUNC_WINDOW]
    xorshift_loops = len(RE_TEMPLATE.findall(window))

    score = (xorshift_loops * 2.5 + oword * 1.5 + min(imm64, 20) * 0.5
             + table_ref * 3.0 + global_write * 2.0 + calls * 0.05)
    return {
        "xorshift_loops": xorshift_loops,
        "oword": oword,
        "imm64": imm64,
        "table_ref": table_ref,
        "global_write": global_write,
        "calls": calls,
        "score": round(score, 1),
    }


def locate(image: PEImage, top_k: int = 10) -> list[dict]:
    """主入口：扫描 → 分组 → 评分 → 排名。"""
    _require_capstone()
    hits = scan_pe(image)
    if not hits:
        return []

    starts: list[int] = []
    for hit in hits:
        s = function_start_of(hit, image)
        if s not in starts:
            starts.append(s)

    cands = []
    for s in starts:
        feats = fine_features(image, s)
        if feats["xorshift_loops"] < 3:
            continue
        cands.append({"ea": s, **feats})
    cands.sort(key=lambda c: c["score"], reverse=True)
    return cands[:top_k]
