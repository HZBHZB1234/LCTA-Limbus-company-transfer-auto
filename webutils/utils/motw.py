# -*- coding: utf-8 -*-
"""Windows「来自互联网」标记（MOTW / Zone.Identifier ADS）检测与清除。

背景
----
- 从网络下载的 zip 用资源管理器解压时，Windows 会把「来自互联网」标记
  （Zone.Identifier 备用数据流）同步附加到整个解压文件夹的每一个文件上
  ——要么整个目录的文件都带标记，要么全都不带。
- 该标记会导致部分资源加载失败：
  · .NET（pythonnet / clr_loader）加载 Python.Runtime.dll 等程序集时报
    「来自其他计算机的文件被阻止」（FileLoadException）；
  · SmartScreen 会拦截带标记的可执行文件（launcher.exe 等）。
- Python 的 zipfile / 7z 解压不会传播该标记；标记只在资源管理器解压或
  Shell 移动（SHFileOperation）时保留。

因此本程序采用「单文件探针」策略：每次启动时只探测一个必然存在的探针
文件是否带标记；未被标记则直接跳过（零目录遍历开销），被标记则对整个
程序目录递归清除一次。下载标记必然整目录同步，一个探针文件即可代表
整个目录的状态。

本模块保持纯标准库、零第三方依赖，可在启动早期经 importlib 直接按文件
路径加载，不触发 webutils/__init__.py 的重型导入。
"""
from __future__ import annotations

import os
from pathlib import Path

_ZONE_IDENTIFIER = "Zone.Identifier"


def _ads_path(path) -> str:
    """构造文件对应的 Zone.Identifier 备用数据流路径。"""
    return str(path) + ":" + _ZONE_IDENTIFIER


def _extended(path: str) -> str:
    """为绝对路径添加 \\\\?\\ 长路径前缀（ADS 删除对长路径更可靠）。"""
    if path.startswith("\\\\?\\"):
        return path
    return "\\\\?\\" + path


def has_zone_identifier(path) -> bool:
    """检查单个文件是否带「来自互联网」标记（非 Windows 恒为 False）。"""
    if os.name != "nt":
        return False
    try:
        return os.path.exists(_ads_path(path))
    except Exception:
        return False


def remove_zone_identifier(path) -> bool:
    """删除单个文件的「来自互联网」标记。

    无标记或删除失败时返回 False（best-effort，不抛错）。
    """
    if os.name != "nt":
        return False
    ads = _ads_path(path)
    for candidate in (ads, _extended(ads)):
        try:
            os.remove(candidate)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            continue
    return False


def clear_motw(root, recursive: bool = True) -> int:
    """清除文件或目录（递归）下所有文件的「来自互联网」标记。

    返回成功清除标记的文件数量；非 Windows 或路径不存在返回 0。
    全程 best-effort：单个文件失败不影响其余文件。
    """
    if os.name != "nt":
        return 0
    count = 0
    try:
        if os.path.isfile(root):
            return 1 if remove_zone_identifier(root) else 0
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                try:
                    if remove_zone_identifier(os.path.join(dirpath, name)):
                        count += 1
                except Exception:
                    continue
    except Exception:
        pass
    return count


def _app_code_root() -> Path:
    """程序 code 目录（path_ 环境变量；未设置时按本模块位置推导）。"""
    path_ = os.getenv("path_")
    if path_:
        return Path(path_)
    return Path(__file__).resolve().parent.parent.parent


def _app_root() -> Path:
    """应用根目录：打包态为 launcher.exe 所在目录，开发态为项目根。"""
    code_root = _app_code_root()
    parent = code_root.parent
    if (parent / "launcher.exe").exists() or (parent / "launcher_debug.exe").exists():
        return parent
    return code_root


def _probe_file(code_root: Path) -> Path:
    """返回一个必然存在于程序目录内的探针文件。"""
    candidates = (
        code_root / "start_webui.py",
        Path(__file__).resolve(),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(__file__).resolve()


def cleanup_app_on_startup() -> int:
    """启动时探测程序目录 MOTW；探针被标记则对整个应用目录递归清除。

    返回清除的文件数；0 表示未检测到标记（快路径，不做目录遍历）。
    """
    if os.name != "nt":
        return 0
    try:
        code_root = _app_code_root()
        probe = _probe_file(code_root)
        if not has_zone_identifier(probe):
            return 0
        return clear_motw(_app_root(), recursive=True)
    except Exception:
        return 0
