# -*- coding: utf-8 -*-
"""工具箱压缩包安全解压：路径净化 + 资源上限 + 布局白名单。

在 ``webutils/function_mod_mirror.py::_extract_zip_safe`` 的基础上**加强**，
而不是复制它的宽松点：

- 成员名走 ``paths.sanitize_member_name``（覆盖 ADS / 设备名 / 尾点空格 / UNC）；
- 大小写冲突检测（NTFS 上 ``A.dll`` 与 ``a.dll`` 是同一文件）；
- 解压总大小 / 成员数 / 单成员大小上限（防 zip bomb）；
- 压缩比上限（高压缩比 + 大体积 = 典型炸弹特征）；
- 解压后**逐个成员校验落点**，并对已存在路径检查链接；
- 支持「布局白名单」：底座包只允许落在声明的相对路径前缀内。

不在此模块执行任何文件（plan 10.3 第 10 条：不自动运行游戏或 DLL 验证）。
"""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from . import paths

# 上限（可按包大小调整；默认值面向「底座 + 插件」量级）
MAX_MEMBERS = 5000
MAX_TOTAL_UNCOMPRESSED = 2 * 1024 * 1024 * 1024   # 2 GiB
MAX_SINGLE_UNCOMPRESSED = 512 * 1024 * 1024       # 512 MiB
MAX_COMPRESSION_RATIO = 200                       # 解压后 / 压缩后


class ArchiveError(ValueError):
    """压缩包不安全或损坏：一律中止，不「跳过该成员继续」。"""


def _clean_member_name(name: str) -> str:
    """净化成员名，并把路径层异常统一成 ``ArchiveError``。

    统一异常类型是刻意的：调用方只需捕获 ``ArchiveError`` 就能覆盖
    「路径逃逸 / 大小超限 / 包损坏」全部情况。若让 ``UnsafePathError``
    直接冒出去，调用方漏捕一种就会让不安全输入变成未处理异常。
    """
    try:
        return paths.sanitize_member_name(name)
    except paths.UnsafePathError as exc:
        raise ArchiveError(str(exc)) from exc


def _resolve_member(dest: Path, name: str) -> Path:
    try:
        return paths.resolve_within(dest, name)
    except paths.UnsafePathError as exc:
        raise ArchiveError(str(exc)) from exc


def _human(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GiB"


def inspect_archive(
    zip_path: os.PathLike | str,
    *,
    max_members: int = MAX_MEMBERS,
    max_total: int = MAX_TOTAL_UNCOMPRESSED,
    max_single: int = MAX_SINGLE_UNCOMPRESSED,
    max_ratio: int = MAX_COMPRESSION_RATIO,
) -> List[Tuple[str, int]]:
    """只读地检查压缩包，返回 ``[(净化后成员名, 大小)]``。

    先检查后解压：这样「超限/不安全」在写任何字节之前就被拒绝，
    不会留下解压到一半的目录。
    """
    try:
        zf = zipfile.ZipFile(str(zip_path))
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"压缩包损坏或格式错误：{exc}") from exc

    with zf:
        infos = zf.infolist()
        if len(infos) > max_members:
            raise ArchiveError(f"压缩包成员数超限：{len(infos)} > {max_members}")

        total = 0
        compressed_total = 0
        cleaned: List[Tuple[str, int]] = []
        raw_names: List[str] = []

        for info in infos:
            name = _clean_member_name(info.filename)
            if info.is_dir():
                continue

            size = int(info.file_size)
            if size > max_single:
                raise ArchiveError(
                    f"成员 {name} 超过单文件上限（{_human(size)} > {_human(max_single)}）"
                )
            total += size
            compressed_total += int(info.compress_size)

            # 单成员压缩比：极小的压缩体积 + 极大解压体积 = 炸弹特征
            if info.compress_size > 0 and size / info.compress_size > max_ratio:
                raise ArchiveError(
                    f"成员 {name} 压缩比异常（{size / info.compress_size:.0f}:1），疑似压缩炸弹"
                )

            cleaned.append((name, size))
            raw_names.append(info.filename)

        if total > max_total:
            raise ArchiveError(f"压缩包解压总大小超限：{_human(total)} > {_human(max_total)}")
        if compressed_total > 0 and total / compressed_total > max_ratio:
            raise ArchiveError(
                f"压缩包整体压缩比异常（{total / compressed_total:.0f}:1），疑似压缩炸弹"
            )

        # 大小写冲突：NTFS 上会互相覆盖，导致内容与清单哈希不符
        try:
            paths.check_case_collisions(raw_names)
        except paths.UnsafePathError as exc:
            raise ArchiveError(str(exc)) from exc

        # 完整性（CRC）检查：损坏包不应进入安装流程
        bad = zf.testzip()
        if bad:
            raise ArchiveError(f"压缩包完整性校验失败（损坏成员：{bad}）")

    return cleaned


def _check_layout(name: str, allowed_prefixes: Optional[Sequence[str]]) -> None:
    """布局白名单：底座包只允许写入声明的路径前缀内。

    插件包不受此限制（它们的落点由受管目录决定），底座包则必须受限 ——
    否则一个「底座」包可以往游戏根任意位置写文件。
    """
    if not allowed_prefixes:
        return
    normalized = name.replace("\\", "/")
    for prefix in allowed_prefixes:
        p = prefix.replace("\\", "/").rstrip("/")
        if normalized == p or normalized.startswith(p + "/"):
            return
    raise ArchiveError(f"成员 {name} 不在允许的安装布局内（允许：{list(allowed_prefixes)}）")


def extract_zip_safe(
    zip_path: os.PathLike | str,
    dest_dir: os.PathLike | str,
    *,
    allowed_prefixes: Optional[Sequence[str]] = None,
    progress: Optional[Callable[[str, int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> List[Path]:
    """安全解压到 ``dest_dir``，返回已写入的文件路径列表。

    ``dest_dir`` 必须是调用方已经核验过的受管目录；本函数仍会再做一次
    包含判断（纵深防御：不假设调用方一定做对了）。
    """
    cleaned = inspect_archive(zip_path)

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    if paths._is_link(dest):
        raise ArchiveError(f"目标目录是符号链接/junction，已中止：{dest}")

    written: List[Path] = []
    done = 0
    total = sum(size for _, size in cleaned)

    try:
        zf = zipfile.ZipFile(str(zip_path))
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"压缩包损坏：{exc}") from exc

    with zf:
        by_name = {i.filename: i for i in zf.infolist()}
        for name, size in cleaned:
            if should_cancel and should_cancel():
                raise ArchiveError("已取消")

            _check_layout(name, allowed_prefixes)
            target = _resolve_member(dest, name)
            if paths._is_link(target.parent):
                raise ArchiveError(f"目标父目录是链接，已中止：{target.parent}")

            target.parent.mkdir(parents=True, exist_ok=True)
            info = _find_info(by_name, name)
            if info is None:
                raise ArchiveError(f"内部错误：找不到成员 {name}")

            # 已存在同名文件时先检查是否为链接（避免顺链写出区外）
            if target.exists() and paths._is_link(target):
                raise ArchiveError(f"目标已存在且是链接，已中止：{target}")

            with zf.open(info) as src, open(str(target), "wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)

            written.append(target)
            done += size
            if progress:
                progress(name, done, total)

    return written


def _find_info(by_name: dict, cleaned_name: str):
    """按净化后的名字回查 ZipInfo（成员名可能含反斜杠，需归一化匹配）。"""
    for raw, info in by_name.items():
        try:
            if _clean_member_name(raw) == cleaned_name:
                return info
        except paths.UnsafePathError:
            continue
    return None