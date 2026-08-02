"""杂项工具函数。"""

from __future__ import annotations

import os
from pathlib import Path


# ============================================================
# Steam 启动命令
# ============================================================

def get_steam_command():
    """生成用于 Steam 启动选项的命令行字符串。"""
    froze = os.getenv('is_frozen', '')
    cwd = Path(os.getcwd())
    if froze == 'true':
        this_launcher = list(cwd.glob('LCTA*.exe'))[0]
    elif froze == 'false':
        if os.getenv('debug', '') == 'true':
            this_launcher = cwd / 'start_webui.py'
            if not this_launcher.exists():
                raise FileNotFoundError(f"启动脚本不存在: {this_launcher}")
            if (cwd / 'venv').exists():
                cmd = f'"{cwd / "venv" / "Scripts" / "python.exe"}" "{this_launcher}" -launcher %command%'
                return cmd
        else:
            this_launcher = cwd / 'launcher.exe'
            if not this_launcher.exists():
                raise FileNotFoundError(f"启动器不存在: {this_launcher}")
    else:
        raise RuntimeError(f"未知的 is_frozen 值: {froze}")
    cmd = f'"{this_launcher}" -launcher %command%'
    return cmd


# ============================================================
# 窗口图标（占位）
# ============================================================

def change_icon():
    """更改窗口图标（暂未实现）。"""
    return
