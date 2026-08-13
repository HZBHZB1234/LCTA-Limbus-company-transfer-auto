"""游戏异常退出时的日志导出。

游戏进程非正常退出（退出码非 0）时，把 Unity 的 Player.log / Player-prev.log
以及 %LOCALAPPDATA%\\Temp 下的 Crashes 崩溃报告目录打包成 zip，
导出到系统「下载」文件夹并在资源管理器中定位。
"""

import os
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from globalManagers.LogManager import LogManager
from webutils.utils.shell import get_downloads_dir

_log_manager = LogManager()

# Unity 游戏日志与崩溃报告路径（Limbus Company / ProjectMoon 标准目录）
GAME_LOG_DIR = (
    Path(os.environ.get("USERPROFILE", ""))
    / "AppData" / "LocalLow" / "ProjectMoon" / "LimbusCompany"
)
CRASH_DIR = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Temp" / "ProjectMoon" / "LimbusCompany" / "Crashes"
)

LOG_FILE_NAME = "Player.log"
PREV_LOG_FILE_NAME = "Player-prev.log"
CRASH_DIR_NAME = "Crashes"

ZIP_PREFIX = "LCTA_游戏日志导出"


def is_abnormal_exit(exit_code: int, game_process=None, cancel_event=None) -> bool:
    """判断游戏是否为异常退出。

    用户主动取消（cancel_event 已置位）或游戏进程未成功创建时不算异常；
    其余退出码非 0 均视为异常退出。
    """
    if cancel_event is not None and cancel_event.is_set():
        return False
    if game_process is None:
        return False
    return exit_code != 0


def collect_log_sources() -> List[Tuple[str, str]]:
    """收集待导出的日志源，返回 [(绝对路径, zip 内相对路径)]。

    Player.log / Player-prev.log 存在即收；Crashes 目录存在则递归收集
    其下全部文件（崩溃报告含多级子目录）。
    """
    sources: List[Tuple[str, str]] = []
    for name in (LOG_FILE_NAME, PREV_LOG_FILE_NAME):
        path = GAME_LOG_DIR / name
        if path.exists() and path.is_file():
            sources.append((str(path), name))
    if CRASH_DIR.exists():
        for path in sorted(CRASH_DIR.rglob("*")):
            if path.is_file():
                rel = path.relative_to(CRASH_DIR).as_posix()
                sources.append((str(path), f"{CRASH_DIR_NAME}/{rel}"))
    return sources


def export_game_logs(output_dir: Optional[str] = None) -> Optional[str]:
    """把游戏日志与崩溃报告打包为 zip 并返回路径；无可导出内容或失败返回 None。

    默认导出到系统「下载」文件夹（或指定 output_dir），文件名带时间戳。
    单个文件读取失败（被占用/损坏）时跳过该文件不中断打包；
    完成后自动打开资源管理器定位该文件。
    """
    sources = collect_log_sources()
    if not sources:
        _log_manager.log("未找到可导出的游戏日志（Player.log / Crashes 均不存在）")
        return None

    base = output_dir or get_downloads_dir()
    try:
        Path(base).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = Path(base) / f"{ZIP_PREFIX}_{timestamp}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for src, arc in sources:
                try:
                    zf.write(src, arc)
                except Exception as e:
                    _log_manager.log(
                        "导出游戏日志失败（跳过该文件）: {}: {}: {}".format(
                            arc, type(e).__name__, e
                        )
                    )
        _log_manager.log(f"游戏日志已导出: {zip_path}")
        _open_in_explorer(str(zip_path))
        return str(zip_path)
    except Exception as e:
        _log_manager.log_error(e)
        return None


def _open_in_explorer(path: str) -> None:
    """在资源管理器中选中并定位指定文件（失败不影响导出结果）。"""
    try:
        subprocess.Popen(
            ["explorer", "/select," + path],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        _log_manager.log(f"打开资源管理器定位导出文件失败: {e}")
