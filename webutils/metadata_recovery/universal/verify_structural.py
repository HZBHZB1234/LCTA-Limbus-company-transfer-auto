#!/usr/bin/env python3
"""verify_structural.py - 解密参数验证（无参考文件，纯结构门）。

验证内容（复用 gen1 candidate_verify 语义）：
1. header 用 header_seed+table 解密 → 6 排列布局自动判定（≥0.7 门）
2. 每个节块：范围校验 + 用其 seed 解密 + 结构门（text/index/binary）
3. 至少一个 text/index 节段（证明 seed 真实有效）

判定：PASS / PASS_WITH_REVIEW / FAIL。
"""

from __future__ import annotations

import struct

from .layouts import LAYOUTS, decrypt_bytes, detect_layout, parse_triplets

VERDICT_PASS = "PASS"
VERDICT_PASS_WITH_REVIEW = "PASS_WITH_REVIEW"
VERDICT_FAIL = "FAIL"


def classify_section(data: bytes) -> tuple[str, dict]:
    """结构分类：text / index / binary，附证据。"""
    n = len(data)
    printable = sum(1 for b in data if 0x20 <= b <= 0x7E or b in (0x09, 0x0A, 0x0D)) / max(n, 1)
    monotonic = 0.0
    if n >= 8 and n % 4 == 0:
        values = struct.unpack(f"<{n // 4}I", data)
        non_decreasing = sum(1 for i in range(len(values) - 1) if values[i] <= values[i + 1])
        monotonic = non_decreasing / max(len(values) - 1, 1)
    if printable >= 0.6:
        return "text", {"printable": round(printable, 3), "monotonic": round(monotonic, 3)}
    if monotonic >= 0.99 and n % 4 == 0:
        return "index", {"printable": round(printable, 3), "monotonic": round(monotonic, 3)}
    return "binary", {"printable": round(printable, 3), "monotonic": round(monotonic, 3)}


def verify(metadata: bytes, profile: dict) -> dict:
    """返回 {verdict, gates, sections, layout}。"""
    gates: list[dict] = []
    result: dict = {"verdict": VERDICT_PASS, "gates": gates}

    missing = [k for k in ("header_size", "header_seed", "table_hex", "sections")
               if not profile.get(k)]
    gates.append({"name": "profile 完整性", "passed": not missing,
                  "evidence": f"missing={missing or '无'}"})
    if missing:
        result["verdict"] = VERDICT_FAIL
        return result

    header_size = profile["header_size"]
    header_seed = int(profile["header_seed"], 16)
    table = bytes.fromhex(profile["table_hex"])
    if len(table) != 256:
        gates.append({"name": "替换表长度", "passed": False,
                      "evidence": f"len={len(table)} != 256"})
        result["verdict"] = VERDICT_FAIL
        return result

    header = decrypt_bytes(metadata[:header_size], header_seed, table)
    best_layout, entries, scores = detect_layout(header, len(metadata))
    result["layout"] = {"best": best_layout, "scores": scores, "entries": entries}
    gates.append({"name": "header 解密 + 布局判定",
                  "passed": scores[best_layout] >= 0.7,
                  "evidence": f"best={best_layout} score={scores[best_layout]:.3f} "
                              f"entries={len(entries)}"})

    section_results = []
    text_or_index = 0
    for idx, sec in enumerate(profile["sections"]):
        size_off = sec["size_off"]
        offset_off = sec.get("offset_off")
        adj = sec.get("adj", 0)
        seed = sec.get("seed")
        # 二进制 memmove 语义：直接按 profile 显式偏移读字段（08-13 起
        # 字段不再对齐 entry 起点；offset 为有符号）
        if size_off is not None and offset_off is not None:
            size = struct.unpack_from("<i", header, size_off)[0]
            logical = struct.unpack_from("<i", header, offset_off)[0]
        else:
            entry = entries[size_off // 12] if size_off is not None and size_off // 12 < len(entries) else None
            size = entry["size"] if entry else None
            logical = entry["offset"] if entry else None
        physical = (logical + adj) if (logical is not None and adj is not None) else None

        res = {"index": idx, "size_off": size_off, "offset_off": offset_off,
               "adj": adj, "seed": seed, "header_size": size,
               "logical_offset": logical, "physical_offset": physical}
        if size is None or physical is None or size < 0 or physical < 0 or physical + size > len(metadata):
            res["error"] = "header 条目缺失或物理范围越界"
            res["pass"] = False
            section_results.append(res)
            continue
        raw = metadata[physical:physical + size]
        if seed:
            try:
                data = decrypt_bytes(raw, int(seed, 16), table)
            except ValueError:
                res["error"] = "seed 解析失败"
                res["pass"] = False
                section_results.append(res)
                continue
        else:
            data = raw
        kind, evidence = classify_section(data)
        res["kind"] = kind
        res["evidence"] = evidence
        if kind in ("text", "index"):
            text_or_index += 1
        res["pass"] = kind in ("text", "index", "binary")
        section_results.append(res)

    passed_sections = sum(1 for r in section_results if r.get("pass"))
    gates.append({"name": "节段范围与解密",
                  "passed": passed_sections == len(section_results) and len(section_results) > 0,
                  "evidence": f"{passed_sections}/{len(section_results)} 通过"})
    gates.append({"name": "结构门（text/index 节段存在）",
                  "passed": text_or_index >= 1,
                  "evidence": f"text/index sections={text_or_index}"})
    result["sections"] = section_results

    if not all(g["passed"] for g in gates):
        result["verdict"] = VERDICT_FAIL
    return result
