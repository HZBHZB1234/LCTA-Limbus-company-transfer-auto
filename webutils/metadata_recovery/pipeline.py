#!/usr/bin/env python3
"""pipeline.py - metadata 解密恢复流水线编排（v2，版本无关）。

由 universal 子包（移植自 upstream metadata-recovery）执行五阶段：
    定位 → 提取 → 验证 → 求解 → 重建
输入仅需 GameAssembly.dll + 加密 global-metadata.dat（无需 IDA、
无需参考标准文件）。本模块负责：

- 输入校验与 capstone 可用性检查
- 运行产物目录（<path_>/metadata_recovery/run_<时间戳>/）
- 期望 SHA-256 自检门（可选）
- 汇总 run-report.json / run-report.md

公共入口：run_recovery()（页面/测试/CLI 共用）。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable

from .universal.pipeline import run as run_universal

VERSION_DEFAULT = 39


def capstone_available() -> bool:
    """capstone 反汇编库是否可用。"""
    import importlib.util
    return importlib.util.find_spec("capstone") is not None


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


# ------------------------------------------------------------- 主流程

def run_recovery(
    metadata_path: str,
    game_dll: str = "",
    expect_sha256: str = "",
    version: int = VERSION_DEFAULT,
    out_dir: str = "",
    on_log: Callable = None,
    cancel_check: Callable = None,
) -> dict:
    """执行完整解密恢复流水线（v2，无参考文件），返回汇总结果 dict。

    参数：
    - metadata_path  加密的 global-metadata.dat（必需）
    - game_dll       GameAssembly.dll（必需：定位/提取均从其反汇编）
    - expect_sha256  期望重建 SHA-256（可选，自检比对门）
    - version        IL2CPP metadata 版本（默认 39）
    - out_dir        输出目录（默认 <path_>/metadata_recovery/run_<时间戳>）
    - on_log(msg)    日志回调
    - cancel_check() 取消检查回调（抛异常即中止）

    返回：{success, run_dir, verdicts, stages, outputs, elapsed_sec}
    """
    if on_log is None:
        on_log = lambda msg: print(msg, flush=True)  # noqa: E731
    if cancel_check is None:
        cancel_check = lambda: None  # noqa: E731

    if not metadata_path or not Path(metadata_path).is_file():
        raise ValueError("请选择加密的 global-metadata.dat")
    if not game_dll or not Path(game_dll).is_file():
        raise ValueError("请选择 GameAssembly.dll（定位/提取需要反汇编它）")
    if not capstone_available():
        raise RuntimeError(
            "缺少 capstone 反汇编库：请先在页面「步骤 1」点击安装，"
            "或运行 pip install capstone")

    run_dir = Path(out_dir) if out_dir else new_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    on_log(f"输出目录：{run_dir}")

    cancel_check()
    report = run_universal(
        str(Path(game_dll)),
        str(Path(metadata_path)),
        version=version,
        out_dir=run_dir,
        name="standard-rebuilt",
        on_log=on_log,
        cancel_check=cancel_check,
    )

    # ---- 产物规范化命名 ----------------------------------------------------
    # upstream 输出 {name}-standard.dat / {name}-profile.json，统一改为
    # standard-rebuilt.dat / profile.json，便于页面与脚本引用。
    std_dst = run_dir / "standard-rebuilt.dat"
    profile_dst = run_dir / "profile.json"
    for src, dst in ((run_dir / "standard-rebuilt-standard.dat", std_dst),
                     (run_dir / "standard-rebuilt-profile.json", profile_dst)):
        if src.is_file() and not dst.exists():
            src.rename(dst)

    # ---- 期望 SHA 自检门（可选） ------------------------------------------
    if expect_sha256 and std_dst.is_file():
        actual_sha = hashlib.sha256(std_dst.read_bytes()).hexdigest().upper()
        expect = expect_sha256.strip().upper()
        passed = actual_sha == expect
        report["verdicts"]["expect_sha"] = "PASS" if passed else "FAIL"
        report["stages"]["expect_sha"] = {
            "actual": actual_sha, "expected": expect, "passed": passed}
        on_log(f"期望 SHA 比对：{'PASS' if passed else 'FAIL'} "
               f"actual={actual_sha[:16]}... expect={expect[:16]}...")

    # ---- 汇总与产物 -------------------------------------------------------
    verdicts = report.get("verdicts", {})
    outputs = {
        "standard_rebuilt": str(std_dst),
        "profile": str(profile_dst),
    }
    for key, path in (report.get("outputs") or {}).items():
        if key in ("standard", "profile"):
            continue  # 已规范化重命名，避免重复条目
        outputs[key] = str(path)

    summary = {
        "version": version,
        "verdicts": verdicts,
        "stages": report.get("stages", {}),
        "outputs": outputs,
        "elapsed_sec": report.get("elapsed_sec"),
        "run_dir": str(run_dir),
    }
    (run_dir / "run-report.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    (run_dir / "run-report.md").write_text(
        _md_report(summary), encoding="utf-8")
    outputs["report_json"] = str(run_dir / "run-report.json")
    outputs["report_md"] = str(run_dir / "run-report.md")

    success = bool(verdicts) and all(
        v in ("PASS", "REVIEW") for v in verdicts.values())
    on_log(f"流水线完成：success={success} verdicts={verdicts}")
    return {
        "success": success,
        "run_dir": str(run_dir),
        "verdicts": verdicts,
        "stages": report.get("stages", {}),
        "outputs": outputs,
        "elapsed_sec": report.get("elapsed_sec"),
    }


_STAGE_LABELS = {
    "locate": "定位（解密入口候选）",
    "extract": "参数提取",
    "verify": "结构验证",
    "solve": "31 节映射求解",
    "rebuild": "标准文件重建",
    "expect_sha": "期望 SHA 比对",
}


def _md_report(summary: dict) -> str:
    lines = [
        "# Metadata 恢复运行报告",
        "",
        f"- 运行目录：`{summary['run_dir']}`",
        f"- IL2CPP 版本：v{summary['version']}",
        f"- 耗时：{summary['elapsed_sec']} 秒",
        "",
        "## 阶段裁决",
        "",
        "| 阶段 | 说明 | 裁决 |",
        "| --- | --- | --- |",
    ]
    for stage, verdict in summary["verdicts"].items():
        label = _STAGE_LABELS.get(stage, stage)
        lines.append(f"| {stage} | {label} | **{verdict}** |")
    lines += ["", "## 输出文件", ""]
    for key, path in summary["outputs"].items():
        lines.append(f"- `{key}`：`{path}`")
    lines += ["", "## 详细阶段数据", ""]
    lines.append("```json")
    lines.append(json.dumps(summary["stages"], indent=1, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="metadata 解密恢复流水线（v2）")
    parser.add_argument("--metadata", required=True, help="加密的 global-metadata.dat")
    parser.add_argument("--game-dll", required=True, help="GameAssembly.dll")
    parser.add_argument("--expect-sha256", default="", help="期望重建 SHA-256（可选）")
    parser.add_argument("--version", type=int, default=VERSION_DEFAULT)
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    result = run_recovery(
        metadata_path=args.metadata,
        game_dll=args.game_dll,
        expect_sha256=args.expect_sha256,
        version=args.version,
        out_dir=args.out_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    import sys
    sys.exit(0 if result["success"] else 1)
