#!/usr/bin/env python3
"""pipeline.py - universal 解密管线编排（版本无关，无参考文件）。

LCTA 副本：在 upstream universal 基础上增加 on_log / cancel_check
回调钩子（WebUI 模态进度与取消支持），逻辑与上游一致。

用法：
  python -m webutils.metadata_recovery.universal.pipeline --dll <GameAssembly.dll>
      --metadata <global-metadata.dat> [--version 39] [--out-dir out] [--name steam]

阶段：
  1. locate   ：xorshift 字节模板扫描 + 反汇编特征评分（无 IDA）
  2. extract  ：指令级参数提取（header_size/seed/表/7 节，无文本正则）
  3. verify   ：无参考结构验证（布局自动判定 + 解密结构门）
  4. solve    ：无参考 31 节映射（锚点间隙链拼装 + 内容签名）
  5. rebuild  ：标准文件重建 + 四重自验证
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .extract_disasm import extract_from_disasm
from .init_locator import function_start_of, locate
from .pe_loader import load_pe
from .rebuild_validate import rebuild_standard, validate_standard
from .solve_versioned import solve
from .verify_structural import verify
from .xorshift_scan import scan_pe

TRUTH_INIT = 0x18069C5E0  # 07-30/08-06/08-13 三版实测 init 地址（仅测试断言用）


def run(dll_path: str, metadata_path: str, version: int = 39,
        out_dir: Path = Path("out"), name: str = "universal",
        on_log=None, cancel_check=None) -> dict:
    """运行管线。

    on_log(msg)      阶段日志回调（默认 print）
    cancel_check()   阶段边界取消检查（抛异常即中止）
    """
    if on_log is None:
        on_log = lambda msg: print(msg, flush=True)  # noqa: E731
    if cancel_check is None:
        cancel_check = lambda: None  # noqa: E731
    t0 = time.time()
    report: dict = {"version": version, "stages": {}, "verdicts": {}}
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. 定位 -----------------------------------------------------------
    on_log("阶段 1/5（定位）：xorshift 字节模板扫描 + 反汇编特征评分 ...")
    cancel_check()
    image = load_pe(dll_path)
    hits = scan_pe(image)
    cands = locate(image, top_k=5)
    report["stages"]["locate"] = {
        "xorshift_hits": len(hits),
        "candidates": cands,
        "top1": cands[0]["ea"] if cands else None,
    }
    report["verdicts"]["locate"] = "PASS" if cands else "FAIL"
    on_log(f"  定位：xorshift 命中 {len(hits)} 处，候选 {len(cands)} 个，"
           f"top1=0x{cands[0]['ea']:X}" if cands else "  定位：无候选")
    if not cands:
        return report
    init_va = cands[0]["ea"]

    # ---- 2. 提取 -----------------------------------------------------------
    on_log(f"阶段 2/5（提取）：对 0x{init_va:X} 指令级参数提取 ...")
    cancel_check()
    ext = extract_from_disasm(image, init_va)
    profile = ext.to_profile()
    report["stages"]["extract"] = {
        "func_ea": init_va,
        "header_size": ext.header_size,
        "header_seed": ext.header_seed and f"0x{ext.header_seed:X}",
        "table_addr": ext.table_addr,
        "sections": ext.sections,
        "errors": ext.errors,
    }
    report["verdicts"]["extract"] = "PASS" if not ext.errors else "FAIL"
    on_log(f"  提取：header_size={ext.header_size} seed="
           f"{ext.header_seed and f'0x{ext.header_seed:X}'} table={ext.table_addr} "
           f"sections={len(ext.sections)} errors={ext.errors or '无'}")
    if ext.errors:
        return report

    # ---- 3. 验证 -----------------------------------------------------------
    on_log("阶段 3/5（验证）：header 解密 + 布局自动判定 + 节段结构门 ...")
    cancel_check()
    metadata = Path(metadata_path).read_bytes()
    vres = verify(metadata, profile)
    report["stages"]["verify"] = {
        "layout": vres.get("layout", {}).get("best"),
        "gates": vres.get("gates", []),
    }
    report["verdicts"]["verify"] = vres["verdict"]
    on_log(f"  验证：布局={report['stages']['verify']['layout']} 裁决={vres['verdict']}")

    # ---- 4. 求解 -----------------------------------------------------------
    on_log("阶段 4/5（求解）：31 节锚点间隙链拼装 ...")
    cancel_check()
    try:
        solution = solve(metadata, profile, version=version)
        report["stages"]["solve"] = {
            "layout": solution.get("layout"),
            "anchor_slots": solution.get("anchor_slots"),
            "protected": solution.get("protected"),
            "review": solution.get("review", []),
        }
        report["verdicts"]["solve"] = "PASS" if not solution.get("review") else "REVIEW"
    except Exception as e:  # noqa: BLE001
        report["stages"]["solve"] = {"error": str(e)}
        report["verdicts"]["solve"] = "FAIL"
        on_log(f"  求解失败：{e}")
        return report
    on_log(f"  求解：布局={solution.get('layout')} 受保护节={len(solution.get('protected', {}))} "
           f"review={report['stages']['solve']['review'] or '无'}")

    # ---- 5. 重建 + 自验证 --------------------------------------------------
    on_log("阶段 5/5（重建）：标准文件重建 + 四重自验证 ...")
    cancel_check()
    std = rebuild_standard(metadata, solution, profile["table_hex"], version=version)
    gates = validate_standard(std, solution, metadata, profile["table_hex"], version=version)
    report["stages"]["rebuild"] = {
        "size": len(std),
        "gates": gates,
    }
    report["verdicts"]["rebuild"] = "PASS" if all(g["passed"] for g in gates) else "FAIL"
    on_log(f"  重建：{len(std)} 字节，"
           + "；".join(f"{g['name']}={'PASS' if g['passed'] else 'FAIL'}" for g in gates))

    std_path = out_dir / f"{name}-standard.dat"
    std_path.write_bytes(std)
    (out_dir / f"{name}-profile.json").write_text(
        json.dumps({**profile, "solution": solution}, indent=1, ensure_ascii=False),
        encoding="utf-8")
    report["outputs"] = {
        "standard": str(std_path),
        "profile": str(out_dir / f"{name}-profile.json"),
    }
    report["elapsed_sec"] = round(time.time() - t0, 1)
    cancel_check()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="universal metadata 解密管线")
    parser.add_argument("--dll", required=True, help="GameAssembly.dll 路径")
    parser.add_argument("--metadata", required=True, help="加密 global-metadata.dat")
    parser.add_argument("--version", type=int, default=39, help="IL2CPP metadata 版本")
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--name", default="universal")
    args = parser.parse_args()

    report = run(args.dll, args.metadata, args.version, args.out_dir, args.name)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    verdicts = report.get("verdicts", {})
    ok = all(v in ("PASS", "REVIEW") for v in verdicts.values()) and bool(verdicts)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
