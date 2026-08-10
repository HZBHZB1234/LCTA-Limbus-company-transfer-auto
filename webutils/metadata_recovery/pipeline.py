#!/usr/bin/env python3
"""pipeline.py - metadata 解密恢复流水线编排（离线四阶段）。

将 extractor / verify / solver / profile 串成一条可在 WebUI 中执行的流水线：

    阶段 0（可选）：替换表 hex 解析 —— 手工粘贴，或从 GameAssembly.dll
                    按反编译文本中的 VA 读取 256 字节
    阶段 1 extract ：反编译文本 → candidate_profile.json + 提取报告
    阶段 2 verify  ：加密 metadata + profile → 参数级验证（布局判定/结构门）
    阶段 3 solve   ：+ 参考标准文件 → 31 段映射 + 重建标准 v39 文件
    阶段 4 apply   ：→ 正式 profile（自检重建 SHA-256）

每个阶段产出 report.json / report.md 与独立产物；阶段裁决
PASS / PASS_WITH_REVIEW / FAIL 汇总到结果 dict。可取消（cancel_check 在
阶段边界抛异常）。
"""

from __future__ import annotations

import json
import os
import re
import struct
import sys
import time
from pathlib import Path
from typing import Callable

from .extractor import RE_TABLE, build_report, extract_from_text
from .profile import build_profile
from .report import VERDICT_PASS, Report
from .solver import STANDARD_NAMES, decrypt_header, parse_reference, rebuild_standard, solve
from .verify import verify_profile

UINT64_MASK = (1 << 64) - 1
METADATA_SANITY = 0xFAB11BAF


# ------------------------------------------------------------- 输出目录

def output_dir() -> Path:
    """流水线输出根目录：<工作目录>/metadata_recovery/（与 fancy/ 同风格）。"""
    return Path(os.getenv("path_", ".")) / "metadata_recovery"


def new_run_dir() -> Path:
    root = output_dir()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = root / f"run_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


# ------------------------------------------------------------- PE 读取

def read_rva_data(dll_path: str, rva: int, size: int) -> bytes:
    """从 PE32+ 文件按 RVA 读取字节（stdlib 实现，无 pefile 依赖）。"""
    data = Path(dll_path).read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("不是有效的 PE 文件（缺少 MZ 头）")
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        raise ValueError("PE 签名无效")
    num_sections = struct.unpack_from("<H", data, pe_off + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe_off + 20)[0]
    opt_off = pe_off + 24
    magic = struct.unpack_from("<H", data, opt_off)[0]
    if magic != 0x20B:
        raise ValueError(f"非 PE32+（magic=0x{magic:X}）")
    image_base = struct.unpack_from("<Q", data, opt_off + 24)[0]
    if rva < image_base:
        raise ValueError(f"RVA {rva:#x} 低于镜像基址 {image_base:#x}")
    rva_to_read = rva - image_base
    section_off = opt_off + opt_size
    for i in range(num_sections):
        off = section_off + i * 40
        name = data[off:off + 8].rstrip(b"\0")
        vaddr = struct.unpack_from("<I", data, off + 12)[0]
        vsize = struct.unpack_from("<I", data, off + 8)[0]
        rawsize = struct.unpack_from("<I", data, off + 16)[0]
        rawptr = struct.unpack_from("<I", data, off + 20)[0]
        if vaddr <= rva_to_read < vaddr + max(vsize, rawsize):
            file_off = rawptr + (rva_to_read - vaddr)
            if file_off + size > len(data):
                raise ValueError(f"读取越界：RVA {rva:#x} 大小 {size} 超出文件")
            return data[file_off:file_off + size]
    raise ValueError(f"RVA {rva:#x} 不属于任何节区")


def resolve_table_hex(game_dll: str = "", decompile_text: str = "",
                      table_hex: str = "", on_log: Callable = None) -> str | None:
    """解析替换表 256 字节 hex。

    优先级：手工 table_hex > 反编译文本 VA + GameAssembly.dll 读取。
    返回 None 表示无法解析。
    """
    if table_hex and len(bytes.fromhex(table_hex)) == 256:
        return table_hex.lower()
    if table_hex:
        raise ValueError(f"手工 table_hex 长度 {len(bytes.fromhex(table_hex))} != 256")
    match = RE_TABLE.search(decompile_text or "")
    if not match:
        return None
    table_va = int(match.group(1), 16)
    if not game_dll or not Path(game_dll).is_file():
        return None
    if on_log:
        on_log(f"从 {Path(game_dll).name} 读取替换表 VA {table_va:#x} ...")
    raw = read_rva_data(game_dll, table_va, 256)
    if len(raw) != 256:
        raise ValueError(f"替换表读取长度 {len(raw)} != 256")
    return raw.hex()


# ------------------------------------------------------------- 阶段执行

def _run_extract(decompile_text: str, decompile_file: str, candidate_profile: str,
                 table_hex: str, run_dir: Path, on_log: Callable,
                 cancel_check: Callable) -> tuple[dict, Report | None]:
    if candidate_profile:
        on_log("阶段 1（提取）：使用已有 candidate_profile.json，跳过反编译文本提取")
        profile = json.loads(Path(candidate_profile).read_text(encoding="utf-8"))
        if table_hex:
            profile["table_hex"] = table_hex
        rep = None
        (run_dir / "candidate_profile.json").write_text(
            json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
        return profile, rep

    text = decompile_text or ""
    if not text and decompile_file:
        text = Path(decompile_file).read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ValueError("反编译文本为空：请粘贴文本或选择反编译 .c 文件")

    on_log(f"阶段 1（提取）：从反编译文本提取解密参数（{len(text)} 字符）...")
    cancel_check()
    ext = extract_from_text(text)
    cancel_check()
    rep = build_report(ext, version=Path(decompile_file).name if decompile_file else "",
                       func_addr="")
    on_log(f"  提取：header_size={ext.header_size} header_seed={ext.header_seed} "
           f"table={ext.table_addr} sections={len(ext.sections)}")
    rep.write_all(run_dir, "extract-report")
    profile = {
        "profile_id": f"candidate-{run_dir.name}",
        "extracted_from": decompile_file or "pasted-text",
        **ext.to_dict(),
    }
    if table_hex:
        profile["table_hex"] = table_hex
    (run_dir / "candidate_profile.json").write_text(
        json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return profile, rep


def _run_verify(metadata_path: str, profile: dict, run_dir: Path, on_log: Callable,
                cancel_check: Callable) -> Report:
    on_log("阶段 2（验证）：参数级验证闭环（header 解密 + 布局判定 + 节段结构门）...")
    metadata = Path(metadata_path).read_bytes()
    cancel_check()
    rep = verify_profile(metadata, profile, run_dir, "verify-report")
    cancel_check()
    on_log(f"  裁决：{rep.verdict()}")
    return rep


def _run_solve(metadata_path: str, profile: dict, reference_path: str,
               run_dir: Path, expect_sha256: str, on_log: Callable,
               cancel_check: Callable) -> tuple[dict, Report]:
    on_log("阶段 3（求解）：31 段映射求解（记录大小匹配 + 内容指纹 + 链装配）...")
    metadata = Path(metadata_path).read_bytes()
    reference = parse_reference(Path(reference_path).read_bytes())
    rep = Report(tool="solve_section_map", version=profile.get("profile_id", ""),
                 title="31 段映射求解")
    cancel_check()
    solution = solve(metadata, profile, reference, rep)
    cancel_check()
    section_map = {
        "profile_id": profile.get("profile_id", ""),
        "protected": {
            name: {"entry_index": v["entry_index"], "adj": v["adj"], "seed": v["seed"]}
            for name, v in solution.get("protected", {}).items()},
        "sections": solution.get("sections", {}),
        "evidence": solution.get("evidence", {}),
    }
    (run_dir / "section-map.json").write_text(
        json.dumps(section_map, indent=2, ensure_ascii=False), encoding="utf-8")
    rep.set_section("section_map", {"output": str(run_dir / "section-map.json")})
    missing_names = [n for n in STANDARD_NAMES
                     if n not in section_map["sections"]]
    if solution and not missing_names:
        entries, _layout, table = decrypt_header(metadata, profile)
        rebuilt = rebuild_standard(metadata, entries, table, solution,
                                   reference["version"])
        actual_sha = __import__("hashlib").sha256(rebuilt).hexdigest().upper()
        expect = expect_sha256.upper()
        rep.gate("相 4 重建 SHA-256",
                 not expect or actual_sha == expect,
                 f"{actual_sha}" + (f" == {expect}" if expect else ""))
        sanity, version = struct.unpack_from("<II", rebuilt, 0)
        rep.gate("重建 sanity/version",
                 sanity == METADATA_SANITY and version == reference["version"],
                 f"sanity={sanity:#x} version={version}")
        rebuilt_path = run_dir / "standard-rebuilt.dat"
        rebuilt_path.write_bytes(rebuilt)
        rep.set_section("rebuild", {"size": len(rebuilt), "sha256": actual_sha,
                                    "output": str(rebuilt_path)})
    else:
        rep.gate("相 4 重建前提（31 节齐全）", False,
                 f"missing={missing_names or '求解器无解'}")
    rep.write_all(run_dir, "solve-report")
    on_log(f"  裁决：{rep.verdict()}  映射节数={len(section_map['sections'])}")
    return section_map, rep


def _run_apply(metadata_path: str, profile: dict, section_map: dict,
               reference_path: str, profile_id: str, run_dir: Path,
               expect_sha256: str, on_log: Callable, cancel_check: Callable) -> Report:
    on_log("阶段 4（提升）：生成正式 profile 并自检重建 ...")
    metadata = Path(metadata_path).read_bytes()
    reference = parse_reference(Path(reference_path).read_bytes())
    cancel_check()
    final_profile = build_profile(metadata, profile, section_map, reference, profile_id)
    rep = Report(tool="apply_profile", version=profile_id, title="候选提升为正式 profile")
    entries, _layout, table = decrypt_header(metadata, profile)
    solution = {
        "sections": {s["name"]: {"custom_entry_index": s["custom_entry_index"],
                                 "physical_offset_adjustment": s["physical_offset_adjustment"]}
                     for s in final_profile["standard_sections"]},
        "protected": {p["name"]: {"seed": p["seed"]}
                      for p in final_profile["protected_sections"]},
    }
    rebuilt = rebuild_standard(metadata, entries, table, solution, reference["version"])
    actual_sha = __import__("hashlib").sha256(rebuilt).hexdigest().upper()
    expect = expect_sha256.upper()
    rep.gate("自检重建 SHA-256", not expect or actual_sha == expect,
             f"{actual_sha}" + (f" == {expect}" if expect else ""))
    sanity, version = struct.unpack_from("<II", rebuilt, 0)
    rep.gate("重建 sanity/version", sanity == METADATA_SANITY and version == reference["version"],
             f"sanity={sanity:#x} version={version}")
    rep.gate("profile 字段完整性",
             all(k in final_profile for k in ("header", "substitution_table_hex",
                                              "protected_sections", "standard_sections")),
             "必填字段齐全")
    out_path = run_dir / f"{profile_id}.generated.json"
    out_path.write_text(json.dumps(final_profile, indent=1, ensure_ascii=False),
                        encoding="utf-8")
    rep.set_section("profile", {
        "output": str(out_path), "profile_id": final_profile["profile_id"],
        "metadata_size": final_profile["metadata_size"],
        "metadata_sha256": final_profile["metadata_sha256"],
        "rebuild_sha256": actual_sha,
    })
    rep.write_all(run_dir, "apply-report")
    on_log(f"  裁决：{rep.verdict()}  输出：{out_path.name}")
    return rep


# ------------------------------------------------------------- 主流程

def run_recovery(
    metadata_path: str,
    reference_path: str = "",
    decompile_text: str = "",
    decompile_file: str = "",
    candidate_profile: str = "",
    game_dll: str = "",
    table_hex: str = "",
    expect_sha256: str = "",
    profile_id: str = "",
    out_dir: str = "",
    on_log: Callable = None,
    cancel_check: Callable = None,
) -> dict:
    """执行完整离线恢复流水线，返回汇总结果 dict。

    参数：
    - metadata_path      加密的 global-metadata.dat（必需）
    - reference_path     参考标准 global-metadata-standard-*.dat（阶段 3/4 必需）
    - decompile_text/decompile_file  反编译文本（阶段 1；二选一）
    - candidate_profile  已有 candidate_profile.json（跳过阶段 1）
    - game_dll / table_hex  替换表来源（阶段 0；至少其一，否则阶段 2 起无法验证）
    - expect_sha256      期望重建 SHA-256（可选，用于自检）
    - profile_id         正式 profile 标识（默认 metadata_<日期>）
    - out_dir            输出目录（默认 <path_>/metadata_recovery/run_<时间戳>）
    - on_log(msg)        日志回调
    - cancel_check()     取消检查回调（抛异常即中止）
    """
    if on_log is None:
        on_log = lambda msg: print(msg, flush=True)  # noqa: E731
    if cancel_check is None:
        cancel_check = lambda: None  # noqa: E731
    if not metadata_path or not Path(metadata_path).is_file():
        raise ValueError("请选择加密的 global-metadata.dat")
    if not profile_id:
        profile_id = "metadata_" + time.strftime("%Y%m%d")

    run_dir = Path(out_dir) if out_dir else new_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    on_log(f"输出目录：{run_dir}")

    # ---- 阶段 0：替换表解析 -------------------------------------------
    cancel_check()
    table_hex = resolve_table_hex(game_dll, decompile_text or "",
                                  table_hex, on_log=on_log)
    if table_hex:
        on_log(f"替换表 hex 就绪：{len(bytes.fromhex(table_hex))} 字节")
    else:
        on_log("警告：未提供替换表 hex（可手工粘贴或选择 GameAssembly.dll），"
               "阶段 2 起将无法通过验证")

    # ---- 阶段 1：提取 ---------------------------------------------------
    cancel_check()
    profile, extract_rep = _run_extract(
        decompile_text, decompile_file, candidate_profile, table_hex,
        run_dir, on_log, cancel_check)
    if extract_rep:
        on_log(f"  裁决：{extract_rep.verdict()}")

    # ---- 阶段 2：验证 ---------------------------------------------------
    cancel_check()
    verify_rep = _run_verify(metadata_path, profile, run_dir, on_log, cancel_check)

    result = {
        "success": verify_rep.verdict() == VERDICT_PASS,
        "run_dir": str(run_dir),
        "verdicts": {
            "extract": extract_rep.verdict() if extract_rep else "SKIP",
            "verify": verify_rep.verdict(),
        },
        "outputs": {
            "candidate_profile": str(run_dir / "candidate_profile.json"),
            "extract_report_json": str(run_dir / "extract-report.json"),
            "verify_report_json": str(run_dir / "verify-report.json"),
            "verify_report_md": str(run_dir / "verify-report.md"),
        },
    }

    # ---- 阶段 3：求解 + 阶段 4：提升 ------------------------------------
    if reference_path and Path(reference_path).is_file():
        cancel_check()
        section_map, solve_rep = _run_solve(
            metadata_path, profile, reference_path, run_dir, expect_sha256,
            on_log, cancel_check)
        result["verdicts"]["solve"] = solve_rep.verdict()
        result["outputs"].update({
            "section_map": str(run_dir / "section-map.json"),
            "solve_report_json": str(run_dir / "solve-report.json"),
            "solve_report_md": str(run_dir / "solve-report.md"),
            "standard_rebuilt": str(run_dir / "standard-rebuilt.dat"),
        })
        complete_map = all(n in section_map["sections"] for n in STANDARD_NAMES)
        if complete_map:
            cancel_check()
            apply_rep = _run_apply(metadata_path, profile, section_map, reference_path,
                                   profile_id, run_dir, expect_sha256, on_log, cancel_check)
            result["verdicts"]["apply"] = apply_rep.verdict()
            result["outputs"].update({
                "profile": str(run_dir / f"{profile_id}.generated.json"),
                "apply_report_json": str(run_dir / "apply-report.json"),
                "apply_report_md": str(run_dir / "apply-report.md"),
            })
        else:
            on_log("31 节映射不完整，跳过阶段 4（提升）")
            result["verdicts"]["apply"] = "SKIP"
    else:
        on_log("未提供参考标准文件，跳过阶段 3/4（可先用阶段 2 验证提取参数）")
        result["verdicts"]["solve"] = "SKIP"
        result["verdicts"]["apply"] = "SKIP"

    result["success"] = all(
        v == VERDICT_PASS or v == "SKIP"
        for v in result["verdicts"].values())
    on_log(f"流水线完成：success={result['success']} "
           f"verdicts={result['verdicts']}")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="metadata 解密恢复流水线")
    parser.add_argument("--metadata", required=True, help="加密的 global-metadata.dat")
    parser.add_argument("--reference", default="", help="参考标准文件")
    parser.add_argument("--decompile-file", default="", help="反编译文本 .c 文件")
    parser.add_argument("--candidate-profile", default="", help="已有 candidate_profile.json")
    parser.add_argument("--game-dll", default="", help="GameAssembly.dll（替换表来源）")
    parser.add_argument("--table-hex", default="", help="替换表 256 字节 hex")
    parser.add_argument("--expect-sha256", default="")
    parser.add_argument("--profile-id", default="")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    result = run_recovery(
        metadata_path=args.metadata,
        reference_path=args.reference,
        decompile_file=args.decompile_file,
        candidate_profile=args.candidate_profile,
        game_dll=args.game_dll,
        table_hex=args.table_hex,
        expect_sha256=args.expect_sha256,
        profile_id=args.profile_id,
        out_dir=args.out_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["success"] else 1)
