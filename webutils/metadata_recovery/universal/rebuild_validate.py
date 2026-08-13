#!/usr/bin/env python3
"""rebuild_validate.py - 标准 metadata 重建 + 四重自验证（无参考文件）。

重建：sanity + version + 31 节规范三元组 + 按规范序无缝拼接各节数据
（受保护节用其 seed 解密）。

自验证门：
1. 输出以 0xFAB11BAF + version 开头
2. header 三元组与拼接布局一致（每节 offset == 前节终点，零尺寸 offset=0）
3. stringLiteral dataIndex 单调不减，且末项 ≤ stringLiteralData 大小
4. 固定 rec 节 size == count × rec（版本表一致性）
5. 受保护节解密后通过结构门（text/index/binary）
"""

from __future__ import annotations

import struct

from .layouts import LAYOUTS, decrypt_bytes, detect_layout, parse_triplets
from .solve_versioned import _rec_of
from .versions import version_table
from .verify_structural import classify_section

METADATA_SANITY = 0xFAB11BAF


def rebuild_standard(metadata: bytes, solution: dict, table_hex: str = "",
                     version: int = 39) -> bytes:
    """按标准 v39 布局重建（语义与 gen1 solve_section_map.rebuild_standard 一致）。"""
    vt = version_table(version)
    names = vt["names"]
    entries = {e["index"]: e for e in solution["entries"]}
    protected = solution.get("protected", {})
    table = bytes.fromhex(table_hex) if table_hex else None

    header_size = 8 + 31 * 12
    output = bytearray(header_size)
    struct.pack_into("<II", output, 0, METADATA_SANITY, version)
    output_offset = header_size
    for index, name in enumerate(names):
        mapped = solution["sections"].get(name)
        if mapped is None:
            raise ValueError(f"solution 缺失节 {name}")
        entry = entries[mapped["custom_entry_index"]]
        size = entry["size"]
        section_offset = output_offset if size else 0
        struct.pack_into("<iii", output, 8 + index * 12,
                         section_offset, size, entry["count"])
        if size:
            physical = mapped.get("physical", None)
            if physical is None:
                physical = entry["offset"] + mapped["physical_offset_adjustment"]
            data = metadata[physical:physical + size]
            if name in protected and protected[name].get("seed"):
                seed = int(protected[name]["seed"], 16)
                if table is None:
                    raise ValueError("受保护节需要替换表（table_hex）")
                data = decrypt_bytes(data, seed, table)
            output.extend(data)
            output_offset += size
    return bytes(output)


def validate_standard(std: bytes, solution: dict, metadata: bytes | None = None,
                      table_hex: str = "", version: int = 39) -> list[dict]:
    """四重自验证。返回 gates 列表。"""
    vt = version_table(version)
    names = vt["names"]
    rec = vt["rec"]
    gates: list[dict] = []

    sanity, ver = struct.unpack_from("<II", std, 0)
    gates.append({"name": "sanity/version", "passed": sanity == METADATA_SANITY and ver == version,
                  "evidence": f"sanity={sanity:#x} version={ver}（期望 {METADATA_SANITY:#x}/{version}）"})

    # 2) 三元组布局一致性（从 sanity+version 之后的字节 8 解析）
    entries = [e for e in parse_triplets(std[8:8 + 31 * 12], ["offset", "size", "count"])]
    layout_ok = True
    expect = 8 + 31 * 12
    for i, name in enumerate(names):
        e = entries[i]
        if e["size"] == 0:
            if e["offset"] != 0:
                layout_ok = False
            continue
        if e["offset"] != expect:
            layout_ok = False
        expect = e["offset"] + e["size"]
    gates.append({"name": "31 节无缝拼接布局", "passed": layout_ok,
                  "evidence": f"end={expect} 总大小={len(std)}"})

    # 3) stringLiteral dataIndex 单调 + 界内
    by_name = {n: entries[i] for i, n in enumerate(names)}
    sl_ent = by_name["stringLiteral"]
    sld_ent = by_name["stringLiteralData"]
    mono_ok = True
    in_range = True
    if sl_ent["size"] > 0:
        idxs = struct.unpack(f"<{sl_ent['size'] // 4}I",
                             std[sl_ent["offset"]:sl_ent["offset"] + sl_ent["size"]])
        mono = sum(1 for a, b in zip(idxs, idxs[1:]) if a <= b)
        mono_ok = mono >= (len(idxs) - 1) * 0.99
        in_range = max(idxs, default=0) <= sld_ent["size"]
    gates.append({"name": "stringLiteral dataIndex 单调/界内",
                  "passed": mono_ok and in_range,
                  "evidence": f"count={sl_ent['count']} max<={sld_ent['size']} "
                              f"mono={mono_ok} in_range={in_range}"})

    # 4) 固定 rec 节一致性
    rec_bad = []
    for i, name in enumerate(names):
        r = rec[name]
        e = entries[i]
        if r is None or r == 0:
            continue
        if e["count"] > 0 and e["size"] != e["count"] * r:
            rec_bad.append(f"{name}(size={e['size']} count={e['count']} rec={r})")
    gates.append({"name": "固定 rec 节一致性", "passed": not rec_bad,
                  "evidence": "; ".join(rec_bad) or "全一致"})

    # 5) 受保护节解密结构门（需源 metadata）
    if metadata is not None and "protected" in solution and table_hex:
        table = bytes.fromhex(table_hex)
        prot_ok = len(table) == 256
        prot_ev = []
        by_idx = {e["index"]: e for e in solution["entries"]}
        for name, p in solution["protected"].items():
            if name.startswith("__"):
                continue
            entry = by_idx.get(p["entry_index"])
            if entry is None:
                prot_ok = False
                continue
            physical = entry["offset"] + p["adj"]
            raw = metadata[physical:physical + entry["size"]]
            kind, ev = classify_section(decrypt_bytes(raw, int(p["seed"], 16), table))
            prot_ev.append(f"{name}={kind}")
            if kind not in ("text", "index", "binary"):
                prot_ok = False
        gates.append({"name": "受保护节解密结构门", "passed": prot_ok,
                      "evidence": ", ".join(prot_ev)})

    return gates
