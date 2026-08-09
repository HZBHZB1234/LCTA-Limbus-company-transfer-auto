#!/usr/bin/env python3
"""extract_decrypt_params.py - 从反编译文本全自动提取解密参数。

输入：解密入口函数的反编译文本（IDA 反编译输出）。
输出：candidate_profile.json（可被 candidate_verify.py 消费）+ 报告。

提取内容：
- header_size    （首个 malloc 常量，header 拷贝缓冲）
- header_seed    （第一个解密循环前的 64 位立即数）
- table_addr     （XOR 替换表：byte_XXXX[ 引用）
- file_base / header_base 全局名（数据流锚点，仅报告）
- sections       [{size_off, offset_off, adj, seed}] 按源码顺序

每条提取都记录证据行（行号+原文），供人工/LLM 复核。模式失败时产生
requires_review 项而不是静默输出。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from .report import Report, VERDICT_FAIL, VERDICT_PASS, VERDICT_PASS_WITH_REVIEW
except ImportError:  # pragma: no cover - 独立脚本运行
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report import Report, VERDICT_FAIL, VERDICT_PASS, VERDICT_PASS_WITH_REVIEW

# LCTA 仓库根目录（tests/fixtures 位于仓库根，本模块位于 webutils/metadata_recovery/）
_REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- regexes

# 64 位立即数（seed 级别，≥12 hex 位）
RE_IMM64 = re.compile(r"=\s*0x([0-9A-Fa-f]{12,16})")
# 任意立即数（含 0x2F4 等）
RE_ANY_IMM = re.compile(r"=\s*(0x[0-9A-Fa-f]+|\d+)")
# 表引用
RE_TABLE = re.compile(r"byte_([0-9A-Fa-f]+)\[")
# 文件基址/header 基址全局（qword_XXXX = (__int64)vN 形式）
RE_GLOBAL_ASSIGN = re.compile(r"(qword|dword)_([0-9A-Fa-f]+)\s*=\s*\(__int64\)\s*v\d+")
# malloc/分配调用（字面量大小，可能带 u/L 后缀；hex 分支必须在前）
# 07-30 为 j__malloc_base，08-06 为 sub_18072F980（内联分配器）
RE_MALLOC = re.compile(r"(?:j__malloc_base|sub_[0-9A-Fa-f]{4,16})\(\s*(0x[0-9A-Fa-f]+u?l?l?|\d+)")
# header 字段读取（size 字段）：*(int *)(qword_XXXX + N)
RE_FIELD_READ = re.compile(r"\*\(int \*\)\(qword_([0-9A-Fa-f]+)\s*\+\s*(\d+)\)")
# 拷贝源表达式（核心模式，拷贝调用独有形态，不带前缀避免误匹配函数声明）：
#   qword_<file> + *(_DWORD *)(qword_<hdr> + <off>) ± <adj>
RE_COPY_SRC = re.compile(
    r"qword_([0-9A-Fa-f]+)\s*\+\s*\*\(_DWORD \*\)\s*\(qword_([0-9A-Fa-f]+)\s*\+\s*(\d+)\)"
    r"\s*([+-])\s*(\d+)",
    re.DOTALL,
)
# 08-06 变体：qword_<file> + *(_DWORD *)qword_<hdr> ± <adj>（offset 字段为 header 0 处）
RE_COPY_SRC_ALT = re.compile(
    r"qword_([0-9A-Fa-f]+)\s*\+\s*\*\(_DWORD \*\)\s*qword_([0-9A-Fa-f]+)"
    r"\s*([+-])\s*(\d+)",
    re.DOTALL,
)
# 节块头部：malloc 前一行或同一块内的 size 字段读取（兜底用）
RE_SIZE_READ = re.compile(r"\*\(int \*\)\(qword_([0-9A-Fa-f]+)\s*\+\s*(\d+)\)")
# 解密循环特征
RE_XORSHIFT = re.compile(r"<<\s*13")


def _norm_hex(text: str) -> int:
    return int(text, 16)


class Extraction:
    def __init__(self) -> None:
        self.header_size: int | None = None
        self.header_seed: int | None = None
        self.table_addr: str | None = None
        self.file_base: str | None = None
        self.header_base: str | None = None
        self.sections: list[dict] = []
        self.xorshift_loops = 0
        self.errors: list[str] = []
        self.evidence: list[str] = []

    def to_dict(self) -> dict:
        return {
            "header_size": self.header_size,
            "header_seed": None if self.header_seed is None else f"0x{self.header_seed:X}",
            "table_addr": self.table_addr,
            "file_base": self.file_base,
            "header_base": self.header_base,
            "xorshift_loops": self.xorshift_loops,
            "sections": self.sections,
            "errors": self.errors,
        }


def extract_from_text(text: str, func_addr: str = "") -> Extraction:
    lines = text.splitlines()
    ext = Extraction()

    # ---- 表引用 ------------------------------------------------------
    for match in RE_TABLE.finditer(text):
        ext.table_addr = f"0x{match.group(1)}"
        _evidence(ext, lines, match.start(), f"替换表引用 byte_{match.group(1)}[")
        break

    # ---- 全局基址 -----------------------------------------------------
    globals_found = []
    for match in RE_GLOBAL_ASSIGN.finditer(text):
        name = f"qword_{match.group(2)}"
        globals_found.append(name)
    if globals_found:
        ext.file_base = globals_found[0] if len(globals_found) >= 1 else None
        ext.header_base = globals_found[1] if len(globals_found) >= 2 else globals_found[0]

    # ---- xorshift 循环数 ----------------------------------------------
    ext.xorshift_loops = len(RE_XORSHIFT.findall(text))

    # ---- header_size：首个 malloc 常量 --------------------------------
    for match in RE_MALLOC.finditer(text):
        value_text = match.group(1).rstrip("uUlL")
        value = int(value_text, 16) if value_text.lower().startswith("0x") else int(value_text)
        # header 缓冲通常先于所有 memmove 节块分配
        if value < 0x100000:
            ext.header_size = value
            _evidence(ext, lines, match.start(), f"header 缓冲分配 malloc({value_text})")
            break

    # ---- header_seed：首个解密循环前的 64 位立即数 ---------------------
    first_loop = text.find("<< 13")
    if first_loop >= 0:
        window = text[:first_loop]
        for match in RE_IMM64.finditer(window):
            ext.header_seed = _norm_hex(match.group(1))
            _evidence(ext, lines, match.start(), f"header seed 0x{match.group(1).upper()}")
            break
    else:
        ext.errors.append("未找到 xorshift 循环特征（<< 13）")

    # ---- 节块：拷贝调用源 + 后续 seed ----------------------------------
    def _section_from_copy(match, src) -> dict | None:
        """从拷贝调用提取节块参数。src 为匹配到的拷贝表达式。"""
        if src.lastindex == 5:
            file_base_hex, hdr_base_hex, off_text, sign, adj_text = src.groups()
            offset_off = int(off_text)
        else:
            file_base_hex, hdr_base_hex, sign, adj_text = src.groups()
            offset_off = 0
        adj = int(adj_text)
        if sign == "-":
            adj = -adj
        block_start = max(
            text.rfind("j__malloc_base", 0, match.start()),
            text.rfind("sub_18072F980", 0, match.start()),
        )
        if block_start < 0:
            block_start = match.start() - 500
        window_text = text[block_start:min(match.end() + 300, len(text))]
        size_off = _find_size_offset(window_text)
        next_src = RE_COPY_SRC.search(text, match.end() + 1)
        if next_src is None:
            next_src = RE_COPY_SRC_ALT.search(text, match.end() + 1)
        tail_end = next_src.start() if next_src else match.end() + 1200
        tail = text[match.end():tail_end]
        seed = None
        for smatch in RE_IMM64.finditer(tail):
            seed = _norm_hex(smatch.group(1))
            break
        return {
            "size_off": size_off,
            "offset_off": offset_off,
            "adj": adj,
            "seed": None if seed is None else f"0x{seed:X}",
        }

    for match in RE_COPY_SRC.finditer(text):
        section = _section_from_copy(match, match)
        if section is None:
            continue
        ext.sections.append(section)
        _evidence(ext, lines, match.start(),
                  f"节块 size_off={section['size_off']} offset_off={section['offset_off']} "
                  f"adj={section['adj']} seed={section['seed']}")
    for match in RE_COPY_SRC_ALT.finditer(text):
        section = _section_from_copy(match, match)
        if section is None:
            continue
        ext.sections.append(section)
        _evidence(ext, lines, match.start(),
                  f"节块(alt) size_off={section['size_off']} offset_off={section['offset_off']} "
                  f"adj={section['adj']} seed={section['seed']}")

    # ---- 一致性检查 ----------------------------------------------------
    if ext.sections:
        bases = {s.get("size_off") for s in ext.sections}
        if len(bases) < len(ext.sections):
            ext.errors.append("存在重复 size_off，节块划分可能错乱")
    if ext.header_seed is None and ext.sections:
        ext.errors.append("未提取到 header_seed")
    if ext.header_size is None:
        ext.errors.append("未提取到 header_size")
    if not ext.sections:
        ext.errors.append("未提取到任何节块")
    return ext


def _find_size_offset(window_text: str) -> int | None:
    """在节块窗口内找 size 字段偏移：取该块内最后一个 header 字段读取。

    07-30 中 memmove 长度参数为 *(int *)(qword_<hdr> + <size_off>)，
    而 memmove 源参数用的是 *_DWORD* 读取，两者不混淆。
    """
    reads = RE_FIELD_READ.findall(window_text)
    if reads:
        return int(reads[-1][1])
    return None


def _evidence(ext: Extraction, lines: list[str], offset: int, note: str) -> None:
    """按全文坐标定位行号，记录证据行。"""
    total = 0
    line_no = 1
    for idx, line in enumerate(lines):
        if total <= offset < total + len(line) + 1:
            line_no = idx + 1
            break
        total += len(line) + 1
    else:
        line_no = len(lines)
    raw = lines[line_no - 1].strip() if 0 <= line_no - 1 < len(lines) else ""
    ext.evidence.append(f"L{line_no}: {note}  |  {raw[:120]}")


# ---------------------------------------------------------------- report

def build_report(ext: Extraction, version: str, func_addr: str = "") -> Report:
    rep = Report(tool="extract_decrypt_params", version=version,
                 title=f"解密参数提取 {func_addr}")
    rep.set_section("candidate_profile", {
        "func_addr": func_addr,
        **ext.to_dict(),
    })
    rep.gate("header 基本参数", ext.header_size is not None and ext.header_seed is not None,
             f"size={ext.header_size} seed={'0x%X' % ext.header_seed if ext.header_seed is not None else None}")
    rep.gate("替换表定位", ext.table_addr is not None, f"table={ext.table_addr}")
    rep.gate("节块数量", len(ext.sections) >= 5,
             f"sections={len(ext.sections)}（07-30/08-06 均为 7）")
    rep.gate("xorshift 循环", ext.xorshift_loops >= 5,
             f"loops={ext.xorshift_loops}（期望 ≥ header+节 数）")
    rep.gate("无提取错误", not ext.errors, "; ".join(ext.errors) or "ok")
    for err in ext.errors:
        rep.review(f"提取失败：{err}",
                   suggestion="检查反编译文本格式变化，调整 RE_* 正则或人工复核")
    if len(ext.sections) not in (5, 6, 7, 8):
        rep.review("节块数量异常", f"extracted={len(ext.sections)}",
                   "受保护 section 数量以二进制为准；数量偏差需确认函数是否完整")
    rep.set_section("evidence", ext.evidence)
    return rep


# ---------------------------------------------------------------- CLI

def main() -> int:
    parser = argparse.ArgumentParser(description="从反编译文本提取 metadata 解密参数")
    parser.add_argument("--text", type=Path, help="反编译文本文件（- 表示 stdin）")
    parser.add_argument("--addr", default="", help="函数地址（仅报告用）")
    parser.add_argument("--version", default="", help="版本标识")
    parser.add_argument("--table-hex", default="", help="替换表 256 字节 hex（来自定位器 dump）")
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--name", default="candidate_profile", help="输出名")
    parser.add_argument("--fixture-test", action="store_true", help="对 07-30/08-06 夹具执行 TDD")
    args = parser.parse_args()

    if args.fixture_test:
        rc = _fixture_test()
        rc2 = _fixture_test_08_06()
        return 0 if (rc == 0 and rc2 == 0) else 1

    if args.text is None or str(args.text) == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.text).read_text(encoding="utf-8")

    ext = extract_from_text(text, args.addr)
    rep = build_report(ext, args.version, args.addr)
    json_path, md_path = rep.write_all(args.out_dir, args.name)
    # 同时写出候选 profile
    profile = {
        "profile_id": f"candidate-{args.name}",
        "extracted_from": args.addr,
        **ext.to_dict(),
    }
    if args.table_hex:
        profile["table_hex"] = args.table_hex
    (args.out_dir / f"{args.name}.json").write_text(
        json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"verdict: {rep.verdict()}")
    print(f"report:  {json_path}")
    print(f"report:  {md_path}")
    print(f"profile: {args.out_dir / (args.name + '.json')}")
    return 0 if rep.verdict() == VERDICT_PASS else 1


def _fixture_test() -> int:
    """07-30 真值回归：profiles/steam-2026-07-30.json 已知参数。"""
    fixture = _REPO_ROOT / "tests" / "fixtures" / "metadata_initialize_current.c"
    text = fixture.read_text(encoding="utf-8")
    ext = extract_from_text(text, "0x1806AB0E0")

    checks = {
        "header_size == 756 (0x2F4)": ext.header_size == 0x2F4,
        "header_seed == 0xE039BA990B051CD7": ext.header_seed == 0xE039BA990B051CD7,
        "table == 0x18759C190": ext.table_addr == "0x18759C190",
        "sections == 7": len(ext.sections) == 7,
        "xorshift_loops == 16": ext.xorshift_loops == 16,
    }

    expected_sections = [
        (216, 224, -6756, 0x6437F7B47BCC353D),
        (420, 428, 5028, 0x2991189FDDC51967),
        (144, 152, 8036, 0x5647FAF029DA7235),
        (408, 416, -404, 0x9B1470F67FDC86B4),
        (396, 404, -4112, 0x01CEDA6B470922C8),
        (36, 44, 4228, 0x3B596B9B21B69FF1),
        (684, 692, 7856, 0x6E47EB74067D4A7F),
    ]
    for idx, (size_off, offset_off, adj, seed) in enumerate(expected_sections):
        got = ext.sections[idx]
        got_seed = int(got["seed"], 16) if got["seed"] else None
        checks[f"section[{idx}] size_off={size_off}"] = got["size_off"] == size_off
        checks[f"section[{idx}] offset_off={offset_off}"] = got["offset_off"] == offset_off
        checks[f"section[{idx}] adj={adj}"] = got["adj"] == adj
        checks[f"section[{idx}] seed=0x{seed:X}"] = got_seed == seed

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if failed:
        print("FAILED:", *failed, sep="\n  ")
        print("errors:", ext.errors)
        return 1
    print(f"fixture-test OK（{len(checks)} 项）")
    return 0


def _fixture_test_08_06() -> int:
    """08-06 真值回归：profiles/steam-2026-08-06.json 已知参数。"""
    fixture = _REPO_ROOT / "tests" / "fixtures" / "metadata_initialize_08-06.c"
    text = fixture.read_text(encoding="utf-8")
    ext = extract_from_text(text, "sub_18069C5E0")

    checks = {
        "header_size == 1044": ext.header_size == 1044,
        "header_seed == 0xBC41EAFC33962B00": ext.header_seed == 0xBC41EAFC33962B00,
        "table == 0x187356110": ext.table_addr == "0x187356110",
        "sections == 7": len(ext.sections) == 7,
        "no errors": not ext.errors,
    }

    expected_sections = [
        (1024, 1020, -1508, 0x116C4B46EACABA5),
        (664, 660, 3476, 0xD4C07427B74C818E),
        (964, 960, -6696, 0xAFDAE7074F40F834),
        (136, 132, 4304, 0xA28BFC303CE665BA),
        (592, 588, -3984, 0xFF3532DDAC34BA66),
        (652, 648, -7080, 0x1DFCEDD20A3EE02C),
        (4, 0, 2268, 0x88942C9716431E06),
    ]
    for idx, (size_off, offset_off, adj, seed) in enumerate(expected_sections):
        got = ext.sections[idx]
        got_seed = int(got["seed"], 16) if got["seed"] else None
        checks[f"s[{idx}] size_off={size_off}"] = got["size_off"] == size_off
        checks[f"s[{idx}] offset_off={offset_off}"] = got["offset_off"] == offset_off
        checks[f"s[{idx}] adj={adj}"] = got["adj"] == adj
        checks[f"s[{idx}] seed=0x{seed:X}"] = got_seed == seed

    print("\n== 08-06 夹具 ==")
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if failed:
        print("FAILED:", *failed, sep="\n  ")
        print("errors:", ext.errors)
        print("sections:", json.dumps(ext.sections, ensure_ascii=False))
        return 1
    print(f"08-06 fixture-test OK（{len(checks)} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
