"""游戏异常退出时的日志导出。

游戏进程非正常退出（退出码非 0）时，把 Unity 的 Player.log / Player-prev.log、
%LOCALAPPDATA%\\Temp 下的 Crashes 崩溃报告目录，以及**启动器自身日志**
（LogManager 落盘的 logs/app.log）打包成 zip，导出到系统「下载」文件夹并在
资源管理器中定位。
"""

import os
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from globalManagers.ConfigManager import ConfigManager
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

# 启动器自身日志：与 globalManagers.LogManager 的默认 log_dir/log_file 一致
# （相对当前工作目录；launcher.c 与 start_webui.py 均把 CWD 设为应用目录）。
# 只收当前 app.log —— 轮转备份体积大且与本次异常关联弱，不纳入导出。
LAUNCHER_LOG_DIR = Path("logs")
LAUNCHER_LOG_FILE_NAME = "app.log"
LAUNCHER_LOG_DIR_NAME = "LauncherLogs"

ZIP_PREFIX = "LCTA_游戏日志导出"

IGNORED_CODES_CONFIG_KEY = "launcher.work.crash_popup_ignored_codes"


def get_ignored_exit_codes() -> List[int]:
    """读取弹窗「忽略此种异常退出码」的退出码列表。

    配置存为逗号分隔的整数字符串（可为负数，如 "-1073741819,1"）；
    解析失败（空串/垃圾项）的条目直接跳过，不视为配置损坏。
    """
    try:
        raw = ConfigManager().get(IGNORED_CODES_CONFIG_KEY, "")
    except Exception as e:
        _log_manager.log(f"读取忽略退出码配置失败: {e}")
        return []
    codes: List[int] = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            codes.append(int(part))
        except ValueError:
            continue
    return codes


def add_ignored_exit_code(exit_code: int) -> bool:
    """把退出码加入忽略列表并立即落盘；已在列表中时不重复写入。

    返回是否发生了实际写入（供弹窗侧记录日志/区分首次保存）。
    """
    try:
        codes = get_ignored_exit_codes()
        if exit_code in codes:
            return False
        codes.append(int(exit_code))
        ConfigManager().set(IGNORED_CODES_CONFIG_KEY, ",".join(str(c) for c in codes))
        _log_manager.log(f"已忽略异常退出码 {exit_code}，此后不再弹窗提示")
        return True
    except Exception as e:
        _log_manager.log_error(e)
        return False


def is_abnormal_exit(exit_code: int, game_process=None, cancel_event=None) -> bool:
    """判断游戏是否为异常退出。

    用户主动取消（cancel_event 已置位）或游戏进程未成功创建时不算异常；
    用户在弹窗勾选过「忽略此种异常退出码」的退出码不算异常；
    其余退出码非 0 均视为异常退出。
    """
    if cancel_event is not None and cancel_event.is_set():
        return False
    if game_process is None:
        return False
    if exit_code != 0 and exit_code in get_ignored_exit_codes():
        return False
    return exit_code != 0


def collect_launcher_log_sources() -> List[Tuple[str, str]]:
    """收集启动器自身日志，返回 [(绝对路径, zip 内相对路径)]。

    只收 LogManager 当前正在写的 logs/app.log（存在且为文件即收），
    归档到 zip 内的 LauncherLogs/ 子目录，与游戏日志分开便于区分来源。
    """
    sources: List[Tuple[str, str]] = []
    path = LAUNCHER_LOG_DIR / LAUNCHER_LOG_FILE_NAME
    if path.exists() and path.is_file():
        sources.append((str(path), f"{LAUNCHER_LOG_DIR_NAME}/{LAUNCHER_LOG_FILE_NAME}"))
    return sources


def collect_log_sources(
    include_launcher_logs: bool = True,
) -> List[Tuple[str, str]]:
    """收集待导出的日志源，返回 [(绝对路径, zip 内相对路径)]。

    Player.log / Player-prev.log 存在即收；Crashes 目录存在则递归收集
    其下全部文件（崩溃报告含多级子目录）。include_launcher_logs 为真时
    额外收集启动器自身日志（默认包含）。
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
    if include_launcher_logs:
        sources.extend(collect_launcher_log_sources())
    return sources


def export_game_logs(
    output_dir: Optional[str] = None,
    include_launcher_logs: bool = True,
) -> Optional[str]:
    """把日志与崩溃报告打包为 zip 并返回路径；无可导出内容或失败返回 None。

    导出内容：游戏的 Player.log / Player-prev.log、崩溃报告目录，以及启动器
    自身的 logs/app.log（include_launcher_logs 为真时，默认包含）。
    默认导出到系统「下载」文件夹（或指定 output_dir），文件名带时间戳。
    单个文件读取失败（被占用/损坏）时跳过该文件不中断打包；
    完成后自动打开资源管理器定位该文件。
    """
    sources = collect_log_sources(include_launcher_logs=include_launcher_logs)
    if not sources:
        _log_manager.log("未找到可导出的游戏日志（Player.log / Crashes / Launcher 日志均不存在）")
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
        _log_manager.log(f"游戏日志与启动器日志已导出: {zip_path}")
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
