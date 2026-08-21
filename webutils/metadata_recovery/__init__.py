# -*- coding: utf-8 -*-
"""webutils.metadata_recovery - Limbus Company IL2CPP metadata 解密恢复工具。

移植自 upstream metadata-recovery 仓库（v2 universal 管线）：

    定位 → 提取 → 验证 → 求解 → 重建

- 输入仅需 GameAssembly.dll + 加密 global-metadata.dat，无需 IDA、
  无需参考标准文件、无需反编译文本（版本无关，v39 系列跨版本适用）。
- 核心逻辑在 `universal/` 子包（pe_loader / xorshift_scan / init_locator /
  extract_disasm / layouts / versions / verify_structural / solve_versioned /
  rebuild_validate / pipeline）。
- 依赖 capstone（x86-64 反汇编），缺失时页面可一键 pip 安装。

公共 API：
    run_recovery()            完整离线流水线（页面/CLI/测试入口）
    capstone_available()      capstone 是否可用
    install_capstone(on_log)  用当前解释器 pip 安装 capstone
    derive_game_files()       从游戏根目录推导 metadata 与 DLL 路径
    output_dir() / new_run_dir()  运行产物目录（<工作目录>/metadata_recovery/）
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

from .pipeline import (
    VERSION_DEFAULT,
    capstone_available,
    new_run_dir,
    output_dir,
    run_recovery,
)
from .universal.pipeline import run as run_universal

__all__ = [
    "run_recovery",
    "capstone_available",
    "install_capstone",
    "derive_game_files",
    "output_dir",
    "new_run_dir",
    "VERSION_DEFAULT",
    "run_universal",
]


def install_capstone(on_log: Callable = None) -> dict:
    """用当前 Python 解释器安装 capstone（pip），实时回传日志。

    返回 {"success", "message"}。失败时 message 含 pip 输出片段。
    """
    if on_log is None:
        on_log = lambda msg: print(msg, flush=True)  # noqa: E731
    on_log("正在安装 capstone（pip install capstone）...")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "capstone"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        tail: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                on_log(line)
            tail.append(line)
            if len(tail) > 20:
                tail.pop(0)
        rc = proc.wait()
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"安装失败：{exc}"}
    if rc != 0:
        return {"success": False,
                "message": "pip 安装失败（返回码非 0）：\n" + "\n".join(tail)}
    if not capstone_available():
        return {"success": False, "message": "pip 已完成但 capstone 仍不可用，请重启应用"}
    on_log("capstone 安装完成")
    return {"success": True, "message": "capstone 安装完成"}


def derive_game_files(game_path: str = "") -> dict:
    """从游戏根目录推导加密 metadata 与 GameAssembly.dll 的路径。

    标准布局（Steam 版）：
    - <game>/LimbusCompany_Data/il2cpp_data/Metadata/global-metadata.dat
    - <game>/GameAssembly.dll

    返回 dict 含 exists 标记（路径即使不存在也返回，便于 UI 提示位置）。
    """
    if not game_path:
        return {"game_path": "", "derived": False,
                "metadata_path": "", "metadata_exists": False,
                "dll_path": "", "dll_exists": False}
    root = Path(game_path)
    metadata = root / "LimbusCompany_Data" / "il2cpp_data" / "Metadata" / "global-metadata.dat"
    dll = root / "GameAssembly.dll"
    return {
        "game_path": str(root),
        "derived": True,
        "metadata_path": str(metadata),
        "metadata_exists": metadata.is_file(),
        "dll_path": str(dll),
        "dll_exists": dll.is_file(),
    }
