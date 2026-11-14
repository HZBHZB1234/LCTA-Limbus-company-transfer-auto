# -*- coding: utf-8 -*-
"""webutils.metadata_recovery - Limbus Company IL2CPP metadata 解密恢复工具。

移植自 upstream metadata-recovery 仓库（v2 universal 管线）：

    定位 → 提取 → 验证 → 求解 → 重建

- 输入仅需 GameAssembly.dll + 加密 global-metadata.dat，无需 IDA、
  无需参考标准文件、无需反编译文本（版本无关，v39 系列跨版本适用）。
- 核心逻辑在 `universal/` 子包（pe_loader / xorshift_scan / init_locator /
  extract_disasm / layouts / versions / verify_structural / solve_versioned /
  rebuild_validate / pipeline）。
- 依赖 capstone（x86-64 反汇编），缺失时页面可一键 pip 安装；安装完成后
  **当前进程立即可用**（capstone_env 惰性导入 + 安装后重置探测），无需重启。

公共 API：
    run_recovery()            完整离线流水线（页面/CLI/测试入口）
    capstone_available()      capstone 是否真的可用（真实导入探测）
    install_capstone(on_log)  用当前解释器 pip 安装 capstone 并当场验证
    derive_game_files()       从游戏根目录推导 metadata 与 DLL 路径
    output_dir() / new_run_dir()  运行产物目录（<工作目录>/metadata_recovery/）
"""

from __future__ import annotations

import os
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
from .universal import capstone_env
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

# pip 输出尾部保留行数（失败时回显给用户/日志）
_PIP_TAIL_LINES = 20


def _log_default(msg: str) -> None:
    print(msg, flush=True)


def _run_pip(args: list[str], on_log: Callable) -> tuple[int, list[str]]:
    """执行 `python -m pip <args>`，逐行回传日志。

    返回 (返回码, 输出尾部)。打包版无控制台，必须用 CREATE_NO_WINDOW，
    否则每次安装都会闪出一个黑框。
    """
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [sys.executable, "-m", "pip"] + args,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", env=env,
        creationflags=creationflags,
    )
    tail: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            on_log(line)
        tail.append(line)
        if len(tail) > _PIP_TAIL_LINES:
            tail.pop(0)
    return proc.wait(), tail


def _is_network_error(text: str) -> bool:
    """pip 失败是否为网络原因（复用更新流程的判定表）。"""
    try:
        from globalManagers.pending_pip_ops import _is_network_error as _inner
    except Exception:  # noqa: BLE001 - 判定表可缺失，退化为"非网络错误"
        return False
    return _inner(text)


def _tsinghua_index() -> str:
    try:
        from globalManagers.pending_pip_ops import _TSINGHUA_PYPI_INDEX
    except Exception:  # noqa: BLE001
        return "https://pypi.tuna.tsinghua.edu.cn/simple"
    return _TSINGHUA_PYPI_INDEX


def _schedule_pending_install() -> bool:
    """把 capstone 排进下次启动早期的依赖重试队列。

    仅在「pip 说装好了、但当前进程仍加载不了」时使用（典型原因：安全软件
    锁住刚写入的 .pyd）。下次启动时 pending_pip_ops 会在任何第三方库导入
    之前重试安装，用户无需手动操作。
    """
    try:
        from globalManagers.pending_pip_ops import (
            load_pending_ops,
            save_pending_ops,
        )
        ops = load_pending_ops()
        specs = list(ops.get("install", []))
        if not any(s.split("=")[0].split(">")[0].strip().lower() == "capstone"
                   for s in specs):
            specs.append("capstone")
        return save_pending_ops({"install": specs})
    except Exception:  # noqa: BLE001 - 兜底路径失败不影响主流程返回
        return False


def install_capstone(on_log: Callable = None) -> dict:
    """用当前 Python 解释器安装 capstone（pip），装完当场验证可用性。

    返回 {success, message, need_restart}：
    - success=True          capstone 已被导入并可实际反汇编 → 直接可运行
    - success=False         安装或加载失败；need_restart=True 表示 pip 已装好
                            但当前进程加载不了（已排入下次启动重试）

    关键点：pip 完成后必须调用 capstone_env.reset() + smoke_test() 做真实
    验证。历史问题是模块级 import 把"缺失"状态冻结在进程内，导致装完仍要
    重启应用才能解密。
    """
    if on_log is None:
        on_log = _log_default

    # 幂等：已经可用（可能是上一次安装、或用户手动装过）直接返回
    if capstone_env.smoke_test():
        on_log(f"capstone 已就绪（版本 {capstone_env.version() or '未知'}），无需安装")
        return {"success": True, "need_restart": False,
                "message": "capstone 已就绪"}

    on_log("正在安装 capstone（pip install --upgrade capstone）...")
    try:
        rc, tail = _run_pip(["install", "--upgrade", "capstone"], on_log)
        output = "\n".join(tail)

        # pip 自身缺失（嵌入式环境）：先引导 ensurepip 再重试一次
        if rc != 0 and "no module named pip" in output.lower():
            on_log("当前解释器缺少 pip，使用 ensurepip 引导安装...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "ensurepip", "--upgrade"],
                    capture_output=True,
                    creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                   if sys.platform == "win32" else 0),
                )
            except Exception as exc:  # noqa: BLE001
                on_log(f"ensurepip 执行失败：{exc}")
            rc, tail = _run_pip(["install", "--upgrade", "capstone"], on_log)
            output = "\n".join(tail)

        # 网络原因失败：按更新流程的既有约定切清华源重试一次
        if rc != 0 and _is_network_error(output):
            index = _tsinghua_index()
            on_log(f"默认源连接失败，正在通过清华源安装（{index}）...")
            rc, tail = _run_pip(
                ["install", "--upgrade", "--index-url", index, "capstone"], on_log)
            output = "\n".join(tail)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "need_restart": False,
                "message": f"安装失败：{exc}"}

    if rc != 0:
        return {"success": False, "need_restart": False,
                "message": "pip 安装失败（返回码非 0）：\n" + output}

    # 装完立刻在当前进程验证：清导入缓存 → 重新探测 → 真实反汇编自检
    capstone_env.reset()
    if capstone_env.smoke_test():
        on_log(f"capstone 安装完成（版本 {capstone_env.version() or '未知'}），"
               "当前会话即可运行恢复，无需重启")
        return {"success": True, "need_restart": False,
                "message": "capstone 安装完成，已可直接运行恢复（无需重启）"}

    # pip 成功但进程内加载不了（文件锁/安全软件/位数不符等）
    detail = capstone_env.last_error() or "未知原因"
    scheduled = _schedule_pending_install()
    hint = ("已排入下次启动自动重试" if scheduled
            else "可重启应用后重试")
    return {
        "success": False,
        "need_restart": True,
        "message": (
            "pip 已完成，但当前进程仍无法加载 capstone，需要重启应用后生效"
            f"（{hint}）。\n真实错误：{detail}"),
    }


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
