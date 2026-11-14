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

因此本程序采用「探针」策略：每次启动时先探测一个必然存在的探针文件
是否带标记；未被标记则跳过整目录遍历，被标记则对整个程序目录递归清除
一次。下载标记必然整目录同步，一个探针文件即可代表整个目录的状态。

但 venv 常与主程序目录来源不同（整包拷贝、单独解压、CI 产物），此时
只有 venv 子树带标记、探针文件干净，整目录清理永远不会触发。而
pythonnet 的 `Python.Runtime.dll` 一旦带标记，.NET Framework 会拒绝
`Assembly.LoadFrom`（HRESULT 0x80131515「不支持操作」），clr_loader 只报
"Failed to resolve Python.Runtime.Loader.Initialize"，CLR 从此起不来。
故启动时对这些「致命程序集」单独探测、命中即定向清除（单文件成本）。

本模块保持纯标准库、零第三方依赖，可在启动早期经 importlib 直接按文件
路径加载，不触发 webutils/__init__.py 的重型导入。
"""
from __future__ import annotations

import os
from pathlib import Path

_ZONE_IDENTIFIER = "Zone.Identifier"

# venv 目录名与「致命程序集」相对 glob。
# pythonnet 的 Python.Runtime.dll 一旦带 MOTW，.NET Framework 会拒绝
# LoadFrom（HRESULT 0x80131515「不支持操作」），clr_loader 只报
# "Failed to resolve Python.Runtime.Loader.Initialize"，WebUI/Launcher 全部
# 起不来；而 venv 往往与主程序目录来源不同（整包拷贝、单独解压），
# 主程序探针永远看不到它的标记，因此这些文件必须单独确认。
_VENV_DIR_NAMES = ("venv", ".venv", "env")
_CRITICAL_ASSEMBLY_GLOBS = (
    "*/site-packages/pythonnet/runtime/Python.Runtime.dll",
    "*/site-packages/clr_loader/ffi/dlls/*/ClrLoader.dll",
)


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


def critical_assembly_paths(code_root=None) -> list:
    """返回 venv 内必须无 MOTW 标记的致命程序集（仅返回实际存在者）。

    覆盖 pythonnet 的主程序集与 clr_loader 的原生加载库：两者任一被标记，
    CLR 都无法初始化（.NET 拒绝加载来自 Internet 区域（ZoneId=3）的程序集）。
    开发态与打包态都在 `code` 目录下找 venv，标准 venv 与 uv/嵌入式布局
    （`Lib` / `lib`）都能命中——glob 在 Windows 上大小写不敏感。
    """
    if os.name != "nt":
        return []
    root = Path(code_root) if code_root is not None else _app_code_root()
    found = []
    for venv_name in _VENV_DIR_NAMES:
        venv_dir = root / venv_name
        if not venv_dir.is_dir():
            continue
        for pattern in _CRITICAL_ASSEMBLY_GLOBS:
            try:
                candidates = sorted(venv_dir.glob(pattern))
            except OSError:
                continue
            for path in candidates:
                if path.is_file() and path not in found:
                    found.append(path)
    return found


def cleanup_app_on_startup(on_error=None) -> int:
    """启动时探测程序目录与关键程序集的 MOTW，命中则清除。

    探测顺序（任一命中才清除，全未命中零目录遍历）：
    1) 主程序探针文件（`start_webui.py`）：命中则对整个应用目录递归清除；
    2) venv 内的致命程序集（pythonnet / clr_loader）：命中则只定向清除
       这几个文件——主程序与 venv 来源不同时的典型情形，此前因探针看不到
       venv 子树而永远不清理，导致 CLR 初始化每次都失败。

    `on_error` 为可选回调（启动流程不应因清理失败中断，但失败原因要能被
    调用方落盘）。返回清除的文件数；0 表示未检测到标记（快路径）。
    """
    if os.name != "nt":
        return 0
    try:
        code_root = _app_code_root()
        if has_zone_identifier(_probe_file(code_root)):
            return clear_motw(_app_root(), recursive=True)
        marked = [p for p in critical_assembly_paths(code_root)
                  if has_zone_identifier(p)]
        if not marked:
            return 0
        return sum(1 for p in marked if remove_zone_identifier(p))
    except Exception as exc:
        if on_error is not None:
            try:
                on_error(exc)
            except Exception:
                pass
        return 0
