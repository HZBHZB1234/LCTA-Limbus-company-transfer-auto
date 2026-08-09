#!/usr/bin/env python3
"""solve_section_map.py - 31 段映射求解器（DESIGN_SECTION_SOLVER.md 的实现）。

输入：
- 加密的 global-metadata.dat
- candidate_profile.json（extract_decrypt_params.py 产出：header_size/header_seed/
  table_hex/sections[{size_off,offset_off,adj,seed}]）
- 参考标准文件 global-metadata-standard-*.dat（v39 标准布局，提供 31 节的
  (offset,size,count) 与节首内容锚点）

算法（四相）：
1. 相 1 C1：记录大小匹配 —— ref 的 rec_size = size/count；entry 候选节 =
   size%rec==0 且 size//rec==count；零尺寸节匹配零尺寸 entry；同版本 blob
   追加 size 精确匹配。
2. 相 2 C5：内容指纹 —— 非加密节取节首多窗口 16B 锚点，在加密文件中定位
   物理位置 p_s（允许 ≤10% 字节漂移）；adj = p_s - entry.offset（C4 |adj|<0x4000）。
3. 相 3 C3：链装配 —— 受保护节物理 = logical + extractor.adj，必须恰好填充
   相邻非加密节间隙；全链按规范序严格递增且 end==next_start（≤4 padding）。
   零尺寸节：snap 到 ≥ logical 的最小链边界（C4 校验）。
4. 相 4：重建标准 v39 文件 → sanity/version/31 节连续 + --expect-sha256 比对。

输出：section_map.json（31 节 {name, custom_entry_index, physical_offset_adjustment}）
+ report.json/md。
"""

from __future__ import annotations

import argparse
import hashlib
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
METADATA_SANITY = 0xFAB11BAF
MAX_ADJ = 0x4000
MAX_PAD = 4
FINGERPRINT_WINDOW = 16
FINGERPRINT_OFFSETS = [0, 32, 64, 96, 128, 160, 192, 224]
EXTEND_LIMIT = 4096
MIN_RATIO = 0.9

LAYOUTS = {
    "offset_size_count": ["offset", "size", "count"],
    "size_count_offset": ["size", "count", "offset"],
}

# 标准 v39 的 31 节规范顺序（跨版本稳定）
STANDARD_NAMES = [
    "stringLiteral", "stringLiteralData", "string", "events", "properties",
    "methods", "parameterDefaultValues", "fieldDefaultValues",
    "fieldAndParameterDefaultValueData", "fieldMarshaledSizes", "parameters",
    "fields", "genericParameters", "genericParameterConstraints",
    "genericContainers", "nestedTypes", "interfaces", "vtableMethods",
    "interfaceOffsets", "typeDefinitions", "images", "assemblies", "fieldRefs",
    "referencedAssemblies", "attributeData", "attributeDataRange",
    "unresolvedVirtualCallParameterTypes",
    "unresolvedVirtualCallParameterRanges", "windowsRuntimeTypeNames",
    "windowsRuntimeStrings", "exportedTypeDefinitions",
]


# ------------------------------------------------------------- crypto/layout

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


def score_layout(entries: list[dict], file_size: int) -> float:
    if not entries:
        return 0.0
    score = 0.0
    for e in entries:
        ok = 0.0
        if e["offset"] >= 0 and e["size"] >= 0:
            ok += 0.35
            if e["offset"] + e["size"] <= file_size:
                ok += 0.3
            else:
                ok += 0.1
        if e["count"] > 0 and e["size"] % e["count"] == 0:
            ok += 0.35
        elif e["size"] == 0:
            ok += 0.35
        score += ok
    return score / len(entries)


def decrypt_header(metadata: bytes, profile: dict) -> tuple[list[dict], str, bytes]:
    header_size = profile["header_size"]
    header_seed = int(profile["header_seed"], 16)
    table = bytes.fromhex(profile["table_hex"])
    header = decrypt_bytes(metadata[:header_size], header_seed, table)
    scores = {name: score_layout(parse_triplets(header, layout), len(metadata))
              for name, layout in LAYOUTS.items()}
    best_layout = max(scores, key=scores.get)
    return parse_triplets(header, LAYOUTS[best_layout]), best_layout, table


# ------------------------------------------------------------- reference

def parse_reference(ref_data: bytes) -> dict:
    sanity, version = struct.unpack_from("<II", ref_data, 0)
    if sanity != METADATA_SANITY:
        raise ValueError(f"reference sanity mismatch: {sanity:#x}")
    sections = []
    for i, name in enumerate(STANDARD_NAMES):
        offset, size, count = struct.unpack_from("<iii", ref_data, 8 + 12 * i)
        rec_size = None
        if count > 0 and size > 0 and size % count == 0:
            rec_size = size // count
        sections.append({
            "index": i,
            "name": name,
            "offset": offset,
            "size": size,
            "count": count,
            "rec_size": rec_size,
            "data": ref_data[offset:offset + size],
        })
    return {"version": version, "sections": sections}


# ------------------------------------------------------------- phase 2: fingerprint

def find_all(needle: bytes, haystack: bytes) -> list[int]:
    positions = []
    start = 0
    while True:
        pos = haystack.find(needle, start)
        if pos < 0:
            break
        positions.append(pos)
        start = pos + 1
    return positions


def locate_section(ref_section: bytes, metadata: bytes) -> tuple[int | None, dict]:
    """在加密文件中定位参考节的内容。返回 (物理位置, 证据)。"""
    size = len(ref_section)
    windows = []
    for offset in FINGERPRINT_OFFSETS:
        if offset >= size:
            break
        windows.append((offset, ref_section[offset:offset + FINGERPRINT_WINDOW]))

    hits: dict[int, dict] = {}
    for window_offset, needle in windows:
        for pos in find_all(needle, metadata):
            anchor = pos - window_offset
            if anchor >= 0:
                hits.setdefault(anchor, {"windows": 0})["windows"] += 1

    best = None
    best_score = 0.0
    for anchor, evidence in hits.items():
        probe = metadata[anchor:anchor + min(EXTEND_LIMIT, size)]
        ref_probe = ref_section[:len(probe)]
        mismatches = sum(1 for a, b in zip(ref_probe, probe) if a != b)
        ratio = 1.0 - (mismatches / max(len(probe), 1))
        evidence["mismatch"] = mismatches
        evidence["total"] = len(probe)
        evidence["ratio"] = round(ratio, 4)
        score = evidence["windows"] * 0.5 + ratio * 10
        if score > best_score:
            best_score = score
            best = anchor
    if best is None:
        return None, {"windows": len(windows), "hits": len(hits)}
    return best, {k: hits[best][k] for k in ("windows", "mismatch", "total", "ratio")}


# ------------------------------------------------------------- phase 4: rebuild

def rebuild_standard(metadata: bytes, entries: list[dict], table: bytes,
                     solution: dict, version: int) -> bytes:
    """按标准 v39 布局重建 metadata（与主工作区 metadata_probe 相同语义）。"""
    protected = {name: sec for name, sec in solution["protected"].items()}
    header_size = 8 + 31 * 12
    output = bytearray(header_size)
    struct.pack_into("<II", output, 0, METADATA_SANITY, version)
    output_offset = header_size
    for index, name in enumerate(STANDARD_NAMES):
        mapped = solution["sections"][name]
        entry = entries[mapped["custom_entry_index"]]
        size = entry["size"]
        section_offset = output_offset if size else 0
        struct.pack_into(
            "<iii", output, 8 + index * 12, section_offset, size, entry["count"])
        if size:
            physical = entry["offset"] + mapped["physical_offset_adjustment"]
            data = metadata[physical:physical + size]
            if name in protected:
                data = decrypt_bytes(data, int(protected[name]["seed"], 16), table)
            output.extend(data)
            output_offset += size
    return bytes(output)


# ------------------------------------------------------------- solver

def solve(metadata: bytes, profile: dict, reference: dict, rep: Report) -> dict:
    missing = [k for k in ("header_size", "header_seed", "table_hex", "sections")
               if not profile.get(k)]
    rep.gate("输入完整性", not missing, f"missing={missing or '无'}")
    if missing:
        rep.set_section("result", {"verdict_note": "输入不完整"})
        return {}

    entries, best_layout, table = decrypt_header(metadata, profile)
    rep.gate("header 解密 + 布局判定", True,
             f"layout={best_layout} entries={len(entries)}")
    rep.set_section("layout", {"best": best_layout, "entries": entries})

    ref_sections = {s["name"]: s for s in reference["sections"]}

    # ---- 受保护节（来自 extractor）------------------------------------
    protected: dict[int, dict] = {}
    for idx, sec in enumerate(profile["sections"]):
        entry_index = sec["size_off"] // 12
        if entry_index >= len(entries):
            rep.gate(f"受保护节 {idx} 槽位越界", False, f"entry={entry_index}")
            continue
        protected[entry_index] = {
            "index": idx,
            "entry_index": entry_index,
            "adj": int(sec.get("adj", 0)),
            "seed": int(sec.get("seed", "0"), 16),
            "size_off": sec["size_off"],
        }
    rep.gate("受保护节数（期望 7）", len(protected) == 7, f"n={len(protected)}")

    # ---- 相 1 C1：候选节集合 ------------------------------------------
    def candidates_for(entry: dict) -> list[str]:
        result = []
        for s in ref_sections.values():
            if s["size"] == 0:
                if entry["size"] == 0 and entry["count"] == 0:
                    result.append(s["name"])
                continue
            if s["rec_size"] is not None:
                if (entry["size"] > 0 and entry["size"] % s["rec_size"] == 0
                        and entry["size"] // s["rec_size"] == entry["count"]):
                    result.append(s["name"])
            if entry["size"] == s["size"]:
                result.append(s["name"])
        return list(dict.fromkeys(result))

    entry_candidates = {e["index"]: candidates_for(e) for e in entries}

    # ---- 相 2 C5：内容指纹定位（全部 size>0 参考节）--------------------
    # 受保护节内容是加密的，指纹必然失败 → 失败集合 = 受保护候选名。
    located: dict[str, dict] = {}
    unlocated: list[str] = []
    for s in reference["sections"]:
        if s["size"] == 0:
            continue
        pos, evidence = locate_section(s["data"][:EXTEND_LIMIT], metadata)
        if pos is None or evidence["ratio"] < MIN_RATIO:
            unlocated.append(s["name"])
            continue
        located[s["name"]] = {"physical": pos, "evidence": evidence}
        rep.gate(f"指纹定位 {s['name']}", evidence["ratio"] >= MIN_RATIO,
                 f"physical=0x{pos:X} ratio={evidence['ratio']} "
                 f"windows={evidence['windows']}")
    rep.gate("相 2 指纹定位：失败集合 == 受保护节数",
             len(unlocated) == len(protected),
             f"located={len(located)} unlocated={len(unlocated)} "
             f"protected={len(protected)} "
             f"unlocated={unlocated or '无'}",
             review="若失败集合不是 7 个，说明参考文件与目标版本内容漂移，"
                    "需人工确认未定位节")

    # ---- 非加密节（已定位）映射：entry = C1 候选 ∩ C4 距离 -------------
    solution = {"sections": {}, "protected": {}, "evidence": {}}
    used_entries: set[int] = set()
    unresolved: list[str] = []

    for name in located:
        physical = located[name]["physical"]
        best, best_dist = None, None
        for entry in entries:
            if name not in entry_candidates[entry["index"]]:
                continue
            adj = physical - entry["offset"]
            if abs(adj) >= MAX_ADJ:
                continue
            if best_dist is None or abs(adj) < best_dist:
                best, best_dist = entry["index"], abs(adj)
        if best is None:
            unresolved.append(name)
            continue
        solution["sections"][name] = {
            "custom_entry_index": best,
            "physical_offset_adjustment": physical - entries[best]["offset"],
        }
        used_entries.add(best)
        solution["evidence"][name] = {"physical": physical, "located": True}
    rep.gate("非加密节映射齐全", not unresolved,
             f"unresolved={unresolved or '无'}")

    # ---- 受保护节：物理位置 + 命名 -------------------------------------
    protected_physical: dict[int, int] = {}
    for entry_index, p in protected.items():
        entry = entries[entry_index]
        physical = entry["offset"] + p["adj"]
        protected_physical[entry_index] = physical
        if physical < 0 or physical + entry["size"] > len(metadata):
            rep.gate(f"受保护节 {entry_index} 物理范围", False,
                     f"0x{physical:X} size={entry['size']} file={len(metadata)}")

    # 非加密节按物理位置排序后必须保持规范序递增
    non_protected_order = sorted((located[n]["physical"], n)
                                 for n in located)
    canonical_of = {name: i for i, name in enumerate(STANDARD_NAMES)}
    prev_index = -1
    order_note = []
    for physical, name in non_protected_order:
        ok = canonical_of[name] > prev_index
        prev_index = canonical_of[name] if ok else prev_index
        order_note.append(f"{name}@{physical}" + ("" if ok else "(!)"))
    rep.gate("非加密节规范序递增", all("(!)" not in x for x in order_note),
             " → ".join(order_note))

    # 受保护节命名：C1 候选 ∩ 指纹失败集合（加密节）∩ 链间隙规范序
    for entry_index, p in protected.items():
        entry = entries[entry_index]
        physical = protected_physical[entry_index]
        cands = [n for n in entry_candidates[entry["index"]]
                 if n in unlocated
                 and n not in solution["sections"]
                 and (ref_sections[n]["size"] == 0) == (entry["size"] == 0)]
        chosen = None
        if len(cands) == 1:
            chosen = cands[0]
        elif cands:
            gap_prev, gap_next = None, None
            for a, b in zip(non_protected_order, non_protected_order[1:]):
                gap_start = a[0] + ref_sections[a[1]]["size"]
                gap_end = b[0]
                if gap_start - MAX_PAD <= physical <= gap_end + MAX_PAD:
                    gap_prev, gap_next = a[1], b[1]
                    break
            for cand in cands:
                if (gap_prev and canonical_of[gap_prev] < canonical_of[cand]
                        and (gap_next is None or canonical_of[cand] < canonical_of[gap_next])):
                    chosen = cand
                    break
        if chosen is None:
            rep.gate(f"受保护节 {entry_index} 命名", False,
                     f"cands={cands or '无'}",
                     review="链间隙与 C1 无法唯一确定该节")
            continue
        solution["sections"][chosen] = {
            "custom_entry_index": entry["index"],
            "physical_offset_adjustment": p["adj"],
        }
        used_entries.add(entry["index"])
        solution["evidence"][chosen] = {
            "physical": physical, "protected": True, "seed": hex(p["seed"])}
        p["name"] = chosen

    # ---- 零尺寸节：snap 到 ≥ logical 的最小链边界 ----------------------
    boundaries = sorted(
        {located[n]["physical"] for n in located}
        | {located[n]["physical"] + ref_sections[n]["size"]
           for n in located}
        | set(protected_physical.values())
        | {v + entries[k]["size"] for k, v in protected_physical.items()})
    zero_names = [n for n in STANDARD_NAMES if ref_sections[n]["size"] == 0]
    zero_entries = [e["index"] for e in entries
                    if e["size"] == 0 and e["count"] == 0
                    and e["index"] not in used_entries
                    and any(n in zero_names
                            for n in entry_candidates[e["index"]])]
    snap_fail = []
    for idx, entry_index in enumerate(zero_entries):
        entry = entries[entry_index]
        if idx >= len(zero_names):
            snap_fail.append(f"entry{entry_index} 零尺寸名用尽")
            continue
        name = zero_names[idx]
        physical = next((b for b in boundaries if b >= entry["offset"]), None)
        if physical is None:
            snap_fail.append(f"entry{entry_index} 无 ≥ logical 的边界")
            continue
        adj = physical - entry["offset"]
        if abs(adj) >= MAX_ADJ:
            snap_fail.append(f"entry{entry_index} adj={adj} 超 C4 界")
            continue
        solution["sections"][name] = {
            "custom_entry_index": entry_index,
            "physical_offset_adjustment": adj,
        }
        solution["evidence"][name] = {"physical": physical,
                                      "zero_size": True}
    rep.gate("零尺寸节 snap（C4 界内）", not snap_fail,
             "; ".join(snap_fail) or "OK")

    # ---- 相 3 链连续（全部 31 节物理端接）-------------------------------
    all_chain = []
    for name in located:
        all_chain.append((located[name]["physical"],
                          ref_sections[name]["size"], name))
    for entry_index, p in protected.items():
        entry = entries[entry_index]
        all_chain.append((protected_physical[entry_index], entry["size"],
                          p.get("name", f"P{entry_index}")))
    all_chain.sort(key=lambda t: (t[0], t[1]))
    chain_fail = []
    for a, b in zip(all_chain, all_chain[1:]):
        gap = b[0] - (a[0] + a[1])
        if not (0 <= gap <= MAX_PAD):
            chain_fail.append(f"{a[2]}(end={a[0]+a[1]}) -> {b[2]}(start={b[0]}) gap={gap}")
    rep.gate("相 3 全链连续（≤4 padding）", not chain_fail,
             "; ".join(chain_fail) or "全链连续")

    # ---- 完整性：31 节齐全 + entry 唯一 ---------------------------------
    missing_names = [n for n in STANDARD_NAMES if n not in solution["sections"]]
    dup_entries = sorted(e for e in used_entries
                         if sum(1 for m in solution["sections"].values()
                                if m["custom_entry_index"] == e) > 1)
    rep.gate("31 节映射齐全", not missing_names,
             f"missing={missing_names or '无'}")
    rep.gate("entry 唯一性", not dup_entries, f"dup={dup_entries or '无'}")
    # 受保护节名回填 solution["protected"]（rebuild 需要 name->seed）
    solution["protected"] = {}
    for entry_index, p in protected.items():
        name = p.get("name")
        if name:
            solution["protected"][name] = {
                "entry_index": entry_index,
                "adj": p["adj"],
                "seed": hex(p["seed"]),
            }

    rep.set_section("solution", solution)
    return solution


def main() -> int:
    parser = argparse.ArgumentParser(description="31 段映射求解器")
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True,
                        help="candidate_profile.json（extractor 产出）")
    parser.add_argument("--reference", type=Path, required=True,
                        help="global-metadata-standard-*.dat")
    parser.add_argument("--expect-sha256", default="")
    parser.add_argument("--rebuild-output", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--name", default="solve_section_map")
    args = parser.parse_args()

    metadata = args.metadata.read_bytes()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    reference = parse_reference(args.reference.read_bytes())

    rep = Report(tool="solve_section_map",
                 version=profile.get("profile_id", ""),
                 title="31 段映射求解")
    solution = solve(metadata, profile, reference, rep)

    if solution:
        missing_names = [n for n in STANDARD_NAMES
                         if n not in solution.get("sections", {})]
        if missing_names:
            rep.gate("相 4 重建前提（31 节齐全）", False,
                     f"missing={missing_names}")
        else:
            entries, _layout, table = decrypt_header(metadata, profile)
            rebuilt = rebuild_standard(metadata, entries, table, solution,
                                       reference["version"])
            actual_sha = hashlib.sha256(rebuilt).hexdigest().upper()
            expect_sha = args.expect_sha256.upper()
            rep.gate("相 4 重建 SHA-256",
                     not expect_sha or actual_sha == expect_sha,
                     f"{actual_sha}" + (f" == {expect_sha}" if expect_sha else ""))
            sanity, version = struct.unpack_from("<II", rebuilt, 0)
            rep.gate("重建 sanity/version",
                     sanity == METADATA_SANITY and version == reference["version"],
                     f"sanity={sanity:#x} version={version}")
            if args.rebuild_output:
                args.rebuild_output.parent.mkdir(parents=True, exist_ok=True)
                args.rebuild_output.write_bytes(rebuilt)
            rep.set_section("rebuild", {
                "size": len(rebuilt),
                "sha256": actual_sha,
                "output": str(args.rebuild_output) if args.rebuild_output else None,
            })

    # 独立 section_map.json（apply_profile 消费）
    section_map_path = args.out_dir / f"{args.name}-section-map.json"
    section_map_path.write_text(json.dumps({
        "profile_id": profile.get("profile_id", ""),
        "layout": solution.get("layout"),
        "protected": {
            name: {"entry_index": v["entry_index"], "adj": v["adj"], "seed": v["seed"]}
            for name, v in solution.get("protected", {}).items()},
        "sections": solution["sections"],
        "evidence": solution.get("evidence", {}),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    rep.set_section("section_map", {"output": str(section_map_path)})

    rep.write_all(args.out_dir, args.name)
    print(f"verdict: {rep.verdict()}")
    return 0 if rep.verdict() == VERDICT_PASS else 1


if __name__ == "__main__":
    sys.exit(main())
