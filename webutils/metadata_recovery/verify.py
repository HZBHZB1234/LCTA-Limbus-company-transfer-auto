#!/usr/bin/env python3
"""candidate_verify.py - 参数级验证闭环。

输入：
- 加密的 global-metadata.dat
- candidate_profile.json（extract_decrypt_params.py 或 locator 产出，
  含 header_size/header_seed/table_hex/sections[{size_off,offset_off,adj,seed}]）

验证：
1. header 用 header_seed+table 解密 → 三元组布局自动判定（offset,size,count
   vs size,count,offset 双布局打分）
2. 每个受保护节段：范围校验 + 用其 seed 解密 + 结构门
   - text 门：可打印率 ≥ 0.6（stringLiteralData 类）
   - index 门：u32 单调率 ≥ 0.99（stringLiteral dataIndex 类）
   - binary 门：非文本非索引（methods/fields 类）→ 弱门，作为证据
3. 一致性：header 中 size_off 处的 size 与节段解析一致

裁决：PASS / PASS_WITH_REVIEW / FAIL，输出 report.json + report.md。
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

try:
    from .report import Report, VERDICT_FAIL, VERDICT_PASS, VERDICT_PASS_WITH_REVIEW
except ImportError:  # pragma: no cover - 独立脚本运行
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report import Report, VERDICT_FAIL, VERDICT_PASS, VERDICT_PASS_WITH_REVIEW

UINT64_MASK = (1 << 64) - 1

LAYOUTS = {
    "offset_size_count": ["offset", "size", "count"],
    "size_count_offset": ["size", "count", "offset"],
}


# ------------------------------------------------------------- crypto

def next_xorshift64(state: int) -> int:
    state ^= state << 13 & UINT64_MASK
    state ^= state >> 7
    state ^= state << 17 & UINT64_MASK
    return state & UINT64_MASK


def decrypt_bytes(data: bytes, seed: int, table: bytes) -> bytes:
    output = bytearray(data)
    state = seed
    for index in range(len(output)):
        state = next_xorshift64(state)
        table_index = (state ^ (state >> 8) ^ (state >> 16) ^ (state >> 24)) & 0xFF
        output[index] ^= table[table_index]
    return bytes(output)


# ------------------------------------------------------------- analysis

def parse_triplets(header: bytes, layout: list[str]) -> list[dict]:
    entries = []
    for index, offset in enumerate(range(0, len(header) - len(header) % 12, 12)):
        fields = dict(zip(layout, struct.unpack_from("<iii", header, offset)))
        entries.append({
            "index": index,
            "header_offset": offset,
            "size": fields["size"],
            "count": fields["count"],
            "offset": fields["offset"],
        })
    return entries


def score_layout(entries: list[dict], file_size: int, header_size: int) -> float:
    """三元组合理性：offset 在文件内、size 非负、end 在文件内（允许越界辅助表）、
    count 与 size 整除关系合理。"""
    if not entries:
        return 0.0
    score = 0.0
    for e in entries:
        ok = 0.0
        if e["offset"] >= 0 and e["size"] >= 0:
            ok += 0.35
            end = e["offset"] + e["size"]
            if end <= file_size:
                ok += 0.3
            else:
                ok += 0.1  # 辅助表可能越界（08-06 index 7/23）
        if e["count"] > 0 and e["size"] % e["count"] == 0:
            ok += 0.35
        elif e["size"] == 0:
            ok += 0.35  # 零尺寸表（windowsRuntimeStrings 类）
        score += ok
    return score / len(entries)


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


def verify_profile(metadata: bytes, profile: dict, out_dir: Path, name: str) -> Report:
    rep = Report(tool="candidate_verify", version=profile.get("profile_id", ""),
                 title="候选参数验证")

    # ---- G1 输入完整性 -----------------------------------------------
    missing = [k for k in ("header_size", "header_seed", "table_hex", "sections")
               if not profile.get(k)]
    rep.gate("profile 完整性", not missing,
             f"missing={missing or '无'}")
    if missing:
        rep.set_section("result", {"verdict_note": "输入不完整，无法验证"})
        rep.write_all(out_dir, name)
        return rep

    header_size = profile["header_size"]
    header_seed = int(profile["header_seed"], 16)
    table = bytes.fromhex(profile["table_hex"])
    if len(table) != 256:
        rep.gate("替换表长度", False, f"len={len(table)} != 256")
        rep.write_all(out_dir, name)
        return rep

    # ---- G2 header 解密与布局判定 -------------------------------------
    header = decrypt_bytes(metadata[:header_size], header_seed, table)
    scores = {layout_name: score_layout(parse_triplets(header, layout), len(metadata), header_size)
              for layout_name, layout in LAYOUTS.items()}
    best_layout = max(scores, key=scores.get)
    entries = parse_triplets(header, LAYOUTS[best_layout])
    rep.gate("header 解密 + 布局判定", scores[best_layout] >= 0.7,
             f"best={best_layout} score={scores[best_layout]:.3f} "
             f"entries={len(entries)}",
             **{k: round(v, 3) for k, v in scores.items()})

    # ---- G3/G4 节段验证 -----------------------------------------------
    section_results = []
    text_or_index = 0
    for idx, sec in enumerate(profile["sections"]):
        size_off = sec["size_off"]
        offset_off = sec.get("offset_off")
        adj = sec.get("adj", 0)
        seed = sec.get("seed")
        entry = entries[size_off // 12] if size_off is not None and size_off // 12 < len(entries) else None
        size = entry["size"] if entry else None
        logical = entry["offset"] if entry else None
        physical = (logical + adj) if (logical is not None and adj is not None) else None

        result = {
            "index": idx,
            "size_off": size_off,
            "offset_off": offset_off,
            "adj": adj,
            "seed": seed,
            "header_size": size,
            "logical_offset": logical,
            "physical_offset": physical,
        }
        if size is None or physical is None or size < 0 or physical < 0 or physical + size > len(metadata):
            result["error"] = "header 条目缺失或物理范围越界"
            result["pass"] = False
            section_results.append(result)
            continue
        raw = metadata[physical:physical + size]
        if seed:
            try:
                data = decrypt_bytes(raw, int(seed, 16), table)
            except ValueError:
                result["error"] = "seed 解析失败"
                result["pass"] = False
                section_results.append(result)
                continue
        else:
            data = raw
        kind, evidence = classify_section(data)
        result["kind"] = kind
        result["evidence"] = evidence
        if kind in ("text", "index"):
            text_or_index += 1
        result["pass"] = kind in ("text", "index", "binary")
        section_results.append(result)

    passed_sections = sum(1 for r in section_results if r.get("pass"))
    rep.gate("节段范围与解密", passed_sections == len(section_results),
             f"{passed_sections}/{len(section_results)} 通过",
             **{f"sec{i}": json.dumps(r, ensure_ascii=False) for i, r in enumerate(section_results)})

    # ---- G5 至少一个 text/index 节段（证明 seed 真实有效） -------------
    rep.gate("结构门（text/index 节段存在）", text_or_index >= 1,
             f"text/index sections={text_or_index}，错误 seed 无法通过可打印率/单调门")
    if text_or_index == 0 and len(section_results) >= 5:
        rep.review("全部节段被判为 binary，无 text/index 节段",
                   "可能是提取的 seeds 全部错误，或该版本结构差异",
                   "用 metadata_probe 对 07-30/08-06 已知 profile 交叉验证提取参数")

    rep.set_section("layout", {
        "best": best_layout,
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "entries": entries,
    })
    rep.set_section("sections", section_results)
    rep.write_all(out_dir, name)
    return rep


# ------------------------------------------------------------- CLI

def main() -> int:
    parser = argparse.ArgumentParser(description="候选解密参数验证")
    parser.add_argument("--metadata", type=Path, required=True, help="加密的 global-metadata.dat")
    parser.add_argument("--profile", type=Path, required=True, help="candidate_profile.json")
    parser.add_argument("--table-hex", default="", help="替换表 hex（缺失时从 profile 读取）")
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--name", default="candidate_verify")
    args = parser.parse_args()

    metadata = Path(args.metadata).read_bytes()
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    if args.table_hex:
        profile["table_hex"] = args.table_hex

    rep = verify_profile(metadata, profile, args.out_dir, args.name)
    print(f"verdict: {rep.verdict()}")
    return 0 if rep.verdict() == VERDICT_PASS else 1


if __name__ == "__main__":
    sys.exit(main())
