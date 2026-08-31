# -*- coding: utf-8 -*-
"""旧版「服务器切换」遗留物迁移：重写已发送到桌面的 lethe 快捷方式启动脚本。

背景：v5.0.4 起「服务器切换」功能（含 lethe 私服资源同步与「开启 lethe 私服」
桌面快捷方式）已整体移除，迁往独立插件仓库
`github.com/HZBHZB1234/KeepCachedVersions`。旧版本允许用户在「服务器切换」页
把快捷方式发送到桌面；该快捷方式指向
`%LOCALAPPDATA%/LCTA/resource-updater/server_switch/launch_lethe.cmd`
（旧脚本先同步 lethe 资源，再启动私服 exe）。`server_sync.py` 删除后旧脚本会以
ModuleNotFoundError 静默失败并直接启动游戏（不再同步资源），行为具有误导性。

本模块在启动早期（`start_webui.py init_env`，纯标准库经 importlib 按文件路径
加载，不触发 webutils/resource_updater 的重型导入）把仍存在的旧
`launch_lethe.cmd` 重写为弹窗提示：告知用户服务器切换已迁移，可前往
`github.com/HZBHZB1234/KeepCachedVersions` 获取更好的服务器切换插件。
桌面 .lnk 无需改动（仍指向同一脚本路径，双击即命中新脚本）。
"""
import os
from pathlib import Path

GITHUB_URL = "https://github.com/HZBHZB1234/KeepCachedVersions"

_NOTICE_PS1 = """Add-Type -AssemblyName System.Windows.Forms
$result = [System.Windows.Forms.MessageBox]::Show(
    "服务器切换功能已从 LCTA 工具箱中移除。`n`n旧版「开启 lethe 私服」快捷方式不再同步资源或启动游戏。`n`n如需继续在官服与 lethe 私服之间切换游戏资源，请前往以下地址获取更好的服务器切换插件：`n`n{GITHUB_URL}",
    "LCTA - 服务器切换已迁移",
    [System.Windows.Forms.MessageBoxButtons]::YesNo,
    [System.Windows.Forms.MessageBoxIcon]::Information
)
if ($result -eq [System.Windows.Forms.DialogResult]::Yes) {{
    Start-Process "{GITHUB_URL}"
}}
""".format(GITHUB_URL=GITHUB_URL)

_LAUNCH_CMD = """@echo off
rem LCTA: server-switch feature removed; legacy shortcut now only shows a notice.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0lethe_shortcut_notice.ps1"
"""


def _legacy_dir() -> Path:
    """旧快捷方式脚本所在目录（与旧 server_sync.create_lethe_shortcut 的
    `default_work_dir() / "server_switch"` 保持一致，覆盖 LOCALAPPDATA 重定向）。"""
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / "LCTA" / "resource-updater" / "server_switch"
    return Path.home() / ".lcta" / "resource-updater" / "server_switch"


def migrate_legacy_lethe_shortcut() -> bool:
    """若存在旧版 lethe 快捷方式启动脚本，则重写为弹窗提示。

    返回 True 表示检测到并重写（用于日志上报）；不存在或写入失败返回 False。
    幂等：已重写过的脚本再次运行只覆盖为相同内容。
    """
    script_dir = _legacy_dir()
    cmd_path = script_dir / "launch_lethe.cmd"
    if not cmd_path.is_file():
        return False
    try:
        script_dir.mkdir(parents=True, exist_ok=True)
        # .ps1 必须带 UTF-8 BOM：Windows PowerShell 5.1 对无 BOM 的 .ps1
        # 按 ANSI（中文系统为 GBK）解码，UTF-8 中文会乱码
        ps1_path = script_dir / "lethe_shortcut_notice.ps1"
        ps1_path.write_text(_NOTICE_PS1, encoding="utf-8-sig")
        cmd_path.write_text(_LAUNCH_CMD, encoding="ascii")
        return True
    except OSError:
        return False


if __name__ == "__main__":
    print("legacy lethe shortcut migrated: {}".format(migrate_legacy_lethe_shortcut()))
