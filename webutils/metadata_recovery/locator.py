#!/usr/bin/env python3
"""locate_metadata_init.py - 解密入口函数候选定位器（证据驱动评分）。

运行形态（双入口）：
1. MCP 后台：`ida-pro-mcp py_exec_file` 执行本文件，调用 run_background()
2. IDA 插件：metadata_locator_plugin.py（Ctrl-Alt-Shift-M），复用同一核心

算法：
- 粗筛（指令级，单遍 .text）：
    xorshift64(13,7,17) 三元组字节模式
      shl r64,0Dh / shr r64,07h / shl r64,11h
    命中指令归入所属函数 → 候选池（解密循环每节 3 个模式）
    + 引用 "global-metadata.dat"/"Metadata" 字符串的函数
- 精评（反编译级，仅对候选池）：
    F1 xorshift 循环数（<< 13 次数）
    F3 memmove/malloc 数、64 位立即数（seed）数
    F5 _OWORD 未展开拷贝（header 拷贝）
    F2 全局写-读扇出（写入的全局被多少其他函数读取——结构不变量）
- 输出 top-K 候选：分数、分项证据、反编译片段、替换表字节 dump
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:  # 是否在 IDA 内
    import ida_hexrays
    import ida_lines
    import ida_segment
    import idaapi
    import idautils
    import ida_bytes
    import ida_funcs

    INSIDE_IDA = True
except ImportError:
    INSIDE_IDA = False
    idaapi = idautils = ida_bytes = ida_funcs = ida_hexrays = ida_lines = ida_segment = None

# 兼容三种运行形态：包内导入（LCTA）、独立脚本、IDA 内 MCP py_exec_file
try:
    from .report import Report
except ImportError:  # pragma: no cover - IDA 内独立执行
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report import Report

# xorshift64(13,7,17) 指令模式：REX.W(48-4F) C1 /E0-EF imm8
XORSHIFT_PATTERNS = [
    re.compile(rb"[\x48-\x4F]\xC1[\xE0-\xEF]\x0D"),  # shl r64, 0Dh
    re.compile(rb"[\x48-\x4F]\xC1[\xE0-\xEF]\x07"),  # shr r64, 07h
    re.compile(rb"[\x48-\x4F]\xC1[\xE0-\xEF]\x11"),  # shl r64, 11h
]

RE_IMM64 = re.compile(r"=\s*0x[0-9A-Fa-f]{12,16}")
RE_TABLE = re.compile(r"byte_([0-9A-Fa-f]+)\[")
# 反编译文本中的全局赋值：qword_XXXX = ...（函数写入的全局）
RE_GLOBAL_WRITE = re.compile(r"\b(qword|dword)_([0-9A-Fa-f]{4,16})\s*=\s*(?!.*\(__int64\)\s*v\d+)")


# ------------------------------------------------------------- 粗筛

def get_text_segment() -> tuple[int, int] | None:
    seg = ida_segment.get_first_seg()
    while seg:
        name = ida_segment.get_segm_name(seg)
        if name in (".text", "text", ".textbss"):
            return seg.start_ea, seg.end_ea
        seg = ida_segment.get_next_seg(seg.start_ea)
    return None


def scan_xorshift_hits() -> dict[int, int]:
    """单遍 .text 扫描：返回 {函数起始地址: 三元组命中数}。"""
    bounds = get_text_segment()
    if not bounds:
        return {}
    start, end = bounds
    data = ida_bytes.get_bytes(start, end - start) or b""
    counts: dict[int, int] = {}
    for pattern in XORSHIFT_PATTERNS:
        for match in pattern.finditer(data):
            ea = start + match.start()
            func = ida_funcs.get_func(ea)
            if func:
                counts[func.start_ea] = counts.get(func.start_ea, 0) + 1
    return counts


def string_ref_functions() -> dict[int, int]:
    """引用 Metadata/global-metadata.dat 字符串的函数（0/1 计分）。"""
    targets = []
    for s in idautils.Strings():
        text = str(s)
        if text in ("global-metadata.dat", "Metadata") or "Metadata" in text:
            targets.append(s.ea)
    hits: dict[int, int] = {}
    for tgt in targets:
        for xref in idautils.XrefsTo(tgt):
            func = ida_funcs.get_func(xref.frm)
            if func:
                hits[func.start_ea] = hits.get(func.start_ea, 0) + 1
    return hits


# ------------------------------------------------------------- 精评

def global_fanout(text: str) -> dict[str, int]:
    """F2：从反编译文本提取函数写入的全局，统计被其他函数读取的扇出和。

    基于反编译文本而非逐指令 xref，避免数百函数 × 数千指令的爆炸开销。
    """
    written: dict[int, int] = {}
    for match in RE_GLOBAL_WRITE.finditer(text):
        name = f"{match.group(1)}_{match.group(2)}"
        try:
            addr = int(match.group(2), 16)
        except ValueError:
            continue
        if 0x180000000 <= addr <= 0x190000000:
            written[addr] = written.get(addr, 0) + 1
    fanout = 0
    for addr, writes in written.items():
        try:
            total = len(list(idautils.XrefsTo(addr)))
        except Exception:
            total = writes
        fanout += max(0, total - writes)
    return {"fanout": fanout, "written_globals": len(written)}


def decompile_text(func_ea: int) -> str | None:
    if not ida_hexrays.init_hexrays_plugin():
        return None
    cfunc = ida_hexrays.decompile(func_ea)
    if not cfunc:
        return None
    return "\n".join(ida_lines.tag_remove(line.line) for line in cfunc.get_pseudocode())


def fine_features(func_ea: int, text: str, string_score: int) -> dict:
    f = {
        "xorshift_loops": len(re.findall(r"<<\s*13", text)),
        "memmove": len(re.findall(r"memmove\s*\(", text)),
        "malloc": len(re.findall(r"j__malloc_base\s*\(", text)),
        "imm64": len(RE_IMM64.findall(text)),
        "oword": len(re.findall(r"_OWORD", text)),
        "table_ref": len(RE_TABLE.findall(text)),
        "string_ref": string_score,
    }
    f["score"] = (
        f["xorshift_loops"] * 2.5
        + f["memmove"] * 2.0
        + f["malloc"] * 1.5
        + min(f["imm64"], 20) * 0.5
        + f["oword"] * 1.5
        + f["string_ref"] * 3.0
    )
    return f


def dump_table_hex(text: str) -> str | None:
    """从反编译文本提取替换表地址并 dump 256 字节。"""
    match = RE_TABLE.search(text)
    if not match:
        return None
    addr = int(match.group(1), 16)
    data = ida_bytes.get_bytes(addr, 256)
    if data and len(data) == 256:
        return data.hex()
    return None


def evidence_lines(text: str, max_total: int = 40) -> list[str]:
    """抽取关键证据行：memmove / << 13 / byte_ / _OWORD / 16 位立即数。"""
    wanted = re.compile(r"memmove|<<\s*13|byte_[0-9A-Fa-f]+\[|_OWORD|= 0x[0-9A-Fa-f]{12,16}")
    out = []
    for idx, line in enumerate(text.splitlines(), 1):
        if wanted.search(line):
            out.append(f"L{idx}: {line.strip()[:160]}")
            if len(out) >= max_total:
                break
    return out


# ------------------------------------------------------------- 主流程

def analyze(top_k: int = 20, max_decompile: int = 400,
            progress_file: Path | None = None) -> tuple[list[dict], Report]:
    rep = Report(tool="locate_metadata_init", version="", title="解密入口候选定位")

    print("[*] 粗筛：xorshift 指令扫描 .text ...", flush=True)
    xorshift_hits = scan_xorshift_hits()
    string_hits = string_ref_functions()
    print(f"[*] xorshift 命中函数 {len(xorshift_hits)}，字符串引用函数 {len(string_hits)}", flush=True)

    pool: dict[int, dict] = {}
    for ea, count in xorshift_hits.items():
        pool[ea] = {"xorshift_byte_hits": count, "string_ref": 0}
    for ea, count in string_hits.items():
        entry = pool.setdefault(ea, {"xorshift_byte_hits": 0, "string_ref": 0})
        entry["string_ref"] += count

    # 优先反编译：xorshift 命中数高的排前，其次字符串引用
    ranked = sorted(pool.items(), key=lambda kv: (-kv[1]["xorshift_byte_hits"], -kv[1]["string_ref"]))
    ranked = ranked[:max_decompile]
    print(f"[*] 精评：反编译 {len(ranked)} 个候选函数 ...", flush=True)

    results = []
    texts: dict[int, str] = {}
    for idx, (ea, meta) in enumerate(ranked, 1):
        text = decompile_text(ea)
        if not text:
            continue
        texts[ea] = text
        features = fine_features(ea, text, meta["string_ref"])
        features.update({"ea": ea, "name": idaapi.get_func_name(ea), **meta})
        results.append(features)
        if idx % 25 == 0:
            print(f"[*] ... {idx}/{len(ranked)}", flush=True)
            if progress_file:
                progress_file.write_text(f"decompiled {idx}/{len(ranked)}\n", encoding="utf-8")

    results.sort(key=lambda r: r["score"], reverse=True)
    top = results[:top_k]

    # 扇出（F2）只对 top-K 计算：反编译文本提取全局名 + XrefsTo
    for i, r in enumerate(top):
        r["rank"] = i + 1
        text = texts.get(r["ea"], "")
        r["fanout_stats"] = global_fanout(text)
        r["evidence"] = evidence_lines(text) if text else []
        r["table_hex"] = dump_table_hex(text) if text else None

    rep.set_section("candidates", top)
    rep.set_section("pool", {
        "xorshift_functions": len(xorshift_hits),
        "string_ref_functions": len(string_hits),
        "decompiled": len(results),
    })
    rep.set_section("scoring", {
        "weights": "loops*2.5 + memmove*2 + malloc*1.5 + imm64(cap20)*0.5 + oword*1.5 + fanout(cap100)*0.15 + string_ref*3",
    })

    # 裁决：top-1 必须同时具备强信号
    # 07-30 风格：memmove 节块；08-06 风格：封装拷贝函数 + 表引用/展开拷贝
    if top:
        t1 = top[0]
        fanout = t1.get("fanout_stats", {}).get("fanout", 0)
        copy_like = t1["memmove"] >= 3 or t1["table_ref"] >= 3 or t1["oword"] >= 3
        strong = (
            t1["xorshift_loops"] >= 5
            and t1["imm64"] >= 5
            and copy_like
        )
        rep.gate("top-1 强信号", strong,
                 f"name={t1['name']} score={t1['score']:.1f} "
                 f"loops={t1['xorshift_loops']} memmove={t1['memmove']} imm64={t1['imm64']} "
                 f"table_ref={t1['table_ref']} oword={t1['oword']} fanout={fanout}")
        if not strong:
            rep.review("top-1 未达到强信号阈值",
                       json.dumps(t1, ensure_ascii=False, default=str),
                       "扩大候选池或检查构建是否改变了算法结构")
    else:
        rep.gate("候选池非空", False, "无候选函数")
    return top, rep


def run_background(out_dir: Path, top_k: int = 20, max_decompile: int = 400) -> Path:
    """MCP 后台入口：分析并落盘候选 JSON + 反编译文本 + 报告。

    反编译阶段写 progress.txt；MCP 请求超时后可从文件确认后台进度。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    progress = out_dir / "progress.txt"
    top, rep = analyze(top_k=top_k, max_decompile=max_decompile, progress_file=progress)
    if progress.exists():
        progress.unlink()
    rep.version = idaapi.get_root_filename() if INSIDE_IDA else ""
    json_path, md_path = rep.write_all(out_dir, "locate_candidates")
    candidates = rep.to_dict()["sections"]["candidates"]
    for r in candidates:
        r.pop("evidence", None)
    (out_dir / "locate_candidates.json").write_text(
        json.dumps({"verdict": rep.verdict(), "candidates": candidates}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    # 保存 top 反编译文本供提取器使用
    for r in top[:5]:
        text = decompile_text(r["ea"])
        if text:
            (out_dir / f"decompile_rank{r['rank']}_{r['name']}.c").write_text(text, encoding="utf-8")
    print(f"[*] verdict: {rep.verdict()}")
    print(f"[*] report: {json_path}")
    return json_path


def main() -> int:
    """插件/命令行入口（在 IDA 内执行）。"""
    import argparse

    parser = argparse.ArgumentParser(description="解密入口候选定位（IDA 内运行）")
    parser.add_argument("--out-dir", default="out", help="输出目录")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--max-decompile", type=int, default=400)
    args = parser.parse_args()
    run_background(Path(args.out_dir), top_k=args.top_k, max_decompile=args.max_decompile)
    return 0


if __name__ == "__main__":
    if not INSIDE_IDA:
        print("locate_metadata_init.py 必须在 IDA 内执行（插件或 MCP py_exec_file）。")
        print("MCP 用法：导入模块后调用 run_background(out_dir, top_k=20)。")
        sys.exit(1)
    sys.exit(main())
