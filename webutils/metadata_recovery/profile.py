#!/usr/bin/env python3
"""apply_profile.py - 把候选参数 + 求解出的 31 段映射提升为正式 profile。

输入：
- --metadata   加密的 global-metadata.dat（提供 metadata_size / metadata_sha256 溯源）
- --candidate  candidate_profile.json（extract_decrypt_params.py 产出）
- --section-map solve_section_map.py 产出的 *-section-map.json
- --reference  参考标准文件（metadata_version 来源）

输出：
- 正式 profile JSON（格式与主工作区 profiles/steam-*.json 一致，
  含 header/substitution_table_hex/protected_sections/standard_sections/
  metadata_size/metadata_sha256）
- 自检：用生成的 profile 重建标准 v39 文件并比对 --expect-sha256（可选）

用法示例：
python tools/apply_profile.py \
  --metadata E:\\desktop\\work\\LimbusDecompile\\samples\\steam-2026-08-06\\global-metadata.dat \
  --candidate out\\candidate_profile_08_06.json \
  --section-map out\\solve-08-06-section-map.json \
  --reference E:\\desktop\\work\\LimbusDecompile\\analysis\\global-metadata-standard-steam-2026-08-06.dat \
  --profile-id steam-2026-08-06 \
  --expect-sha256 73194A637E4BEF48F5D0396158F2CFEEAC484EFF4864AE01F6CDAE603057A2E7 \
  --output out\\steam-2026-08-06.generated.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

try:
    from .verify import classify_section
    from .report import Report, VERDICT_FAIL, VERDICT_PASS
    from .solver import (LAYOUTS, STANDARD_NAMES, decrypt_bytes,
                         decrypt_header, parse_reference, rebuild_standard)
except ImportError:  # pragma: no cover - 独立脚本运行
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    from candidate_verify import classify_section
    from report import Report, VERDICT_FAIL, VERDICT_PASS
    from solve_section_map import (LAYOUTS, STANDARD_NAMES, decrypt_bytes,
                                   decrypt_header, parse_reference, rebuild_standard)

UINT64_MASK = (1 << 64) - 1


def build_profile(metadata: bytes, candidate: dict, section_map: dict,
                  reference: dict, profile_id: str,
                  game: str = "LimbusCompany", unity_version: str = "",
                  decrypt_fn: str = "", table_rva_note: str = "") -> dict:
    entries, layout_name, table = decrypt_header(metadata, candidate)
    header = {
        "size": candidate["header_size"],
        "seed": candidate["header_seed"],
        "decrypt_start": 0,
        "entry_layout": list(LAYOUTS[layout_name]),
    }
    if candidate.get("header_base"):
        header["header_base"] = candidate["header_base"]

    protected_sections = []
    cand_by_entry = {}
    for idx, sec in enumerate(candidate.get("sections", [])):
        cand_by_entry[sec["size_off"] // 12] = sec
    for name, p in section_map["protected"].items():
        entry_index = p["entry_index"]
        cand_sec = cand_by_entry.get(entry_index)
        offset_field_offset = (cand_sec["offset_off"] if cand_sec and "offset_off" in cand_sec
                               else entry_index * 12 + 8)
        size_off = cand_sec["size_off"] if cand_sec else entry_index * 12
        entry = entries[entry_index]
        raw = metadata[entry["offset"] + p["adj"]: entry["offset"] + p["adj"] + entry["size"]]
        kind, _evidence = classify_section(decrypt_bytes(raw, int(p["seed"], 16), table))
        protected_sections.append({
            "id": f"protected_{len(protected_sections)}",
            "name": name,
            "logical_offset": offset_field_offset,
            "size_field_offset": size_off,
            "physical_offset_adjustment": p["adj"],
            "seed": p["seed"],
            "identified_as": kind,
        })

    standard_sections = [
        {"name": name,
         "custom_entry_index": section_map["sections"][name]["custom_entry_index"],
         "physical_offset_adjustment": section_map["sections"][name]["physical_offset_adjustment"]}
        for name in STANDARD_NAMES
    ]

    # 链注记（证据 → 人类可读）
    evidence = section_map.get("evidence", {})
    chain = " -> ".join(
        f"{name}@{evidence.get(name, {}).get('physical', '?')}"
        for name in STANDARD_NAMES)
    key_fields = {
        "header_triplet_count": len(entries),
        "chain": chain,
    }
    # 常规计数（可读性）：stringLiteral 条目数、string 条目数
    sl = section_map["sections"].get("stringLiteral", {})
    st = section_map["sections"].get("string", {})
    if sl:
        entry = entries[sl["custom_entry_index"]]
        key_fields["stringLiteralEntries"] = entry["count"]
    if st:
        entry = entries[st["custom_entry_index"]]
        key_fields["stringEntries"] = entry["count"]

    profile = {
        "profile_id": profile_id,
        "game": game,
        "unity_version": unity_version,
        "metadata_version": reference["version"],
        "header": header,
        "substitution_table_rva": table_rva_note or candidate.get("table_addr", ""),
        "substitution_table_hex": candidate["table_hex"],
        "protected_sections": protected_sections,
        "standard_sections": standard_sections,
        "key_fields": key_fields,
        "decrypt_fn": decrypt_fn,
        "algorithm": "xorshift64(13,7,17) + table[(s^s>>8^s>>16^s>>24)&0xFF] bytewise xor; per-section seeds",
        "metadata_size": len(metadata),
        "metadata_sha256": hashlib.sha256(metadata).hexdigest().upper(),
        "source": {
            "candidate_profile": "extract_decrypt_params.py",
            "section_map": "solve_section_map.py",
        },
    }
    return profile


def main() -> int:
    parser = argparse.ArgumentParser(description="提升为正式 profile")
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--section-map", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--game", default="LimbusCompany")
    parser.add_argument("--unity-version", default="")
    parser.add_argument("--decrypt-fn", default="")
    parser.add_argument("--table-rva-note", default="")
    parser.add_argument("--expect-sha256", default="")
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--name", default="apply_profile")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    metadata = args.metadata.read_bytes()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    section_map = json.loads(args.section_map.read_text(encoding="utf-8"))
    reference = parse_reference(args.reference.read_bytes())

    rep = Report(tool="apply_profile", version=args.profile_id, title="候选提升为正式 profile")
    profile = build_profile(metadata, candidate, section_map, reference,
                            args.profile_id, args.game, args.unity_version,
                            args.decrypt_fn, args.table_rva_note)

    # ---- 自检：用生成的 profile 重建标准 v39 文件 ----------------------
    entries, _layout, table = decrypt_header(metadata, candidate)
    solution = {
        "sections": {s["name"]: {"custom_entry_index": s["custom_entry_index"],
                                 "physical_offset_adjustment": s["physical_offset_adjustment"]}
                     for s in profile["standard_sections"]},
        "protected": {p["name"]: {"seed": p["seed"]} for p in profile["protected_sections"]},
    }
    rebuilt = rebuild_standard(metadata, entries, table, solution, reference["version"])
    actual_sha = hashlib.sha256(rebuilt).hexdigest().upper()
    expect_sha = args.expect_sha256.upper()
    rep.gate("自检重建 SHA-256", not expect_sha or actual_sha == expect_sha,
             f"{actual_sha}" + (f" == {expect_sha}" if expect_sha else ""))
    sanity, version = struct.unpack_from("<II", rebuilt, 0)
    rep.gate("重建 sanity/version", sanity == 0xFAB11BAF and version == reference["version"],
             f"sanity={sanity:#x} version={version}")
    rep.gate("profile 字段完整性",
             all(k in profile for k in ("header", "substitution_table_hex",
                                        "protected_sections", "standard_sections")),
             "必填字段齐全")

    output = args.output or (args.out_dir / f"{args.profile_id}.generated.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, indent=1, ensure_ascii=False), encoding="utf-8")
    rep.set_section("profile", {
        "output": str(output),
        "profile_id": profile["profile_id"],
        "metadata_size": profile["metadata_size"],
        "metadata_sha256": profile["metadata_sha256"],
        "rebuild_sha256": actual_sha,
    })
    rep.write_all(args.out_dir, args.name)
    print(f"verdict: {rep.verdict()}")
    print(f"profile: {output}")
    return 0 if rep.verdict() == VERDICT_PASS else 1


if __name__ == "__main__":
    sys.exit(main())
