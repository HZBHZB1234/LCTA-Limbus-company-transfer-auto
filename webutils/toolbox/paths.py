# -*- coding: utf-8 -*-
"""工具箱路径安全：游戏根校验、受管布局、成员名净化。

这是 P6 最安全关键的一层。所有 move/delete/写入都必须先经过本模块解析出
**已核验的绝对路径**，且必须落在受管区域内 —— 不允许任何调用方自己拼字符串
再交给 shutil/os.remove。

## 为什么不能用 ``str(target).startswith(str(root))``

这是常见但**错误**的包含判断：``C:\\Games\\LCTA-evil`` 也以 ``C:\\Games\\LCTA``
开头。必须按路径分量比较（``relative_to`` / ``commonpath``）。

## 覆盖的路径攻击面（plan 10.3）

- Zip Slip（``..`` 逃逸）、绝对路径、盘符、UNC（``\\\\server\\share``）
- 反斜杠/正斜杠歧义（ZIP 规范用 ``/``，Windows 也接受 ``\\``）
- 备用数据流 ADS（``file.txt:hidden``）
- Windows 保留设备名（``CON``、``NUL``、``COM1``…，**含带扩展名形式**）
- 尾部点/空格（Windows 会静默裁剪，导致「写入 A 实际落到 B」）
- 符号链接 / junction / reparse point 造成的真实路径逃逸
- 大小写不敏感下的同名冲突（``A.dll`` 与 ``a.dll`` 在 NTFS 是同一个）
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# Windows 保留设备名（不区分大小写，且**带扩展名也算**：NUL.txt 仍是 NUL）
_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)

# 非法文件名字符（Windows）
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# 受管区域目录名（相对于游戏根）
TOOLBOX_DIR = ".lcta-toolbox"
DISABLED_DIR = "disabled"
BACKUPS_DIR = "backups"
STAGING_DIR = "staging"
MANIFEST_NAME = "toolbox-manifest.json"
JOURNAL_NAME = "toolbox-journal.json"
LOCK_NAME = "toolbox.lock"

# BepInEx 插件加载树（受管 DLL 的启用位置）
BEPINEX_PLUGINS = ("BepInEx", "plugins", "LCTA")


class UnsafePathError(ValueError):
    """路径不安全（逃逸/设备名/ADS/链接等）：一律中止，不做「尽力而为」的修正。"""


def is_windows() -> bool:
    return os.name == "nt"


# ---------------------------------------------------------------------------
# 成员名净化（来自 ZIP 等不可信来源）
# ---------------------------------------------------------------------------


def sanitize_member_name(name: str) -> str:
    """把压缩包成员名净化成安全的相对路径（用 ``/`` 分隔）。

    任何可疑形态**直接报错**而不是静默修正：静默修正会让攻击者用
    「看起来被清理了」的名字落到别处，也让审计看不到异常输入。
    """
    if not name:
        raise UnsafePathError("空成员名")

    # ZIP 规范是 '/'，但 Windows 工具常写入 '\'；先统一再判定
    unified = name.replace("\\", "/")

    # 控制字符与 NUL
    if "\x00" in unified:
        raise UnsafePathError(f"成员名含 NUL：{name!r}")

    # 绝对路径 / 盘符 / UNC
    if unified.startswith("/"):
        raise UnsafePathError(f"成员名为绝对路径：{name!r}")
    if re.match(r"^[A-Za-z]:", unified):
        raise UnsafePathError(f"成员名含盘符：{name!r}")
    if name.replace("\\", "/").startswith("//"):
        raise UnsafePathError(f"成员名为 UNC 路径：{name!r}")

    parts: List[str] = []
    for raw_part in unified.split("/"):
        if raw_part in ("", "."):
            # 空段（连续斜杠）与 '.' 直接跳过：它们不改变目标位置
            continue
        if raw_part == "..":
            raise UnsafePathError(f"成员名含上跳路径：{name!r}")

        # ADS：'file.txt:hidden'（盘符已在上面拦掉，这里的 ':' 一律非法）
        if ":" in raw_part:
            raise UnsafePathError(f"成员名含备用数据流（ADS）：{name!r}")

        if _ILLEGAL_CHARS.search(raw_part):
            raise UnsafePathError(f"成员名含非法字符：{name!r}")

        # 尾部点/空格：Windows 会静默裁剪，导致实际落点与声明不一致
        if raw_part != raw_part.rstrip(" ."):
            raise UnsafePathError(f"成员名以点或空格结尾：{name!r}")

        stem = raw_part.split(".")[0].upper()
        if stem in _RESERVED_NAMES:
            raise UnsafePathError(f"成员名是保留设备名：{name!r}")

        parts.append(raw_part)

    if not parts:
        raise UnsafePathError(f"成员名净化后为空：{name!r}")

    return "/".join(parts)


def check_case_collisions(names: Iterable[str]) -> None:
    """检测大小写不敏感下的同名冲突（NTFS 上 ``A.dll``/``a.dll`` 是同一文件）。

    不做检测的话，后写入的成员会静默覆盖前一个，最终文件内容与清单哈希
    不一致 —— 表现为「安装成功但文件损坏」，极难排查。
    """
    seen = {}
    for raw in names:
        key = unicodedata.normalize("NFC", raw).casefold()
        if key in seen and seen[key] != raw:
            raise UnsafePathError(
                f"压缩包存在大小写冲突成员：{seen[key]!r} 与 {raw!r}（在 Windows 上是同一路径）"
            )
        seen[key] = raw


# ---------------------------------------------------------------------------
# 真实路径解析与包含判断
# ---------------------------------------------------------------------------


def _norm(path: os.PathLike | str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def is_within(child: os.PathLike | str, parent: os.PathLike | str) -> bool:
    """child 是否在 parent **之内**（按路径分量比较，不是字符串前缀）。"""
    child_n = _norm(child)
    parent_n = _norm(parent)
    if child_n == parent_n:
        return True
    try:
        return os.path.commonpath([child_n, parent_n]) == parent_n
    except ValueError:
        # 不同盘符 → 必然不在其内
        return False


def resolve_within(base: os.PathLike | str, relative: str) -> Path:
    """把相对路径解析到 base 之内，任何逃逸/链接歧义都报错。

    ``strict_symlink`` 行为：只要路径链上存在符号链接/junction 且其真实目标
    落在 base 之外，就拒绝。这是防「ZIP 里放一个指向 C:\\Windows 的链接，
    后续写入顺链跑到系统目录」。
    """
    safe_rel = sanitize_member_name(relative)
    base_path = Path(base).resolve()
    target = (base_path / safe_rel).resolve()

    if not is_within(target, base_path):
        raise UnsafePathError(f"路径逃逸：{relative!r} → {target}")

    # 逐级检查：已存在的祖先若是指向区外的链接，必须拒绝
    probe = base_path
    for part in safe_rel.split("/"):
        probe = probe / part
        if probe.exists() and _is_link(probe):
            real = Path(os.path.realpath(str(probe)))
            if not is_within(real, base_path):
                raise UnsafePathError(f"路径链含指向区外的链接：{probe} → {real}")
    return target


def _is_link(path: Path) -> bool:
    """是否为符号链接/junction（Windows 上 is_symlink 不覆盖 junction）。"""
    try:
        if path.is_symlink():
            return True
        if is_windows():
            # FILE_ATTRIBUTE_REPARSE_POINT
            attrs = os.stat(str(path), follow_symlinks=False).st_file_attributes  # type: ignore[attr-defined]
            return bool(attrs & 0x400)
    except (OSError, AttributeError):
        return False
    return False


def assert_not_link(path: os.PathLike | str, what: str = "目标") -> None:
    """拒绝对链接/junction 本身做写操作（避免顺链改到区外）。"""
    p = Path(path)
    if p.exists() and _is_link(p):
        raise UnsafePathError(f"{what}是符号链接或 junction，已中止：{p}")


# ---------------------------------------------------------------------------
# 受管布局
# ---------------------------------------------------------------------------


def toolbox_dir(game_root: os.PathLike | str) -> Path:
    """受管区域根（``<game_root>/.lcta-toolbox``）。"""
    return Path(game_root) / TOOLBOX_DIR


def disabled_dir(game_root: os.PathLike | str, tool_id: str, release_id: str) -> Path:
    """停用插件的存放位置 —— 必须在 BepInEx 加载树**之外**。

    只改配置里的 enabled 布尔值是不够的：BepInEx 仍然会加载它。
    """
    return toolbox_dir(game_root) / DISABLED_DIR / _safe_id(tool_id) / _safe_id(release_id)


def backups_dir(game_root: os.PathLike | str) -> Path:
    return toolbox_dir(game_root) / BACKUPS_DIR


def staging_dir(game_root: os.PathLike | str) -> Path:
    return toolbox_dir(game_root) / STAGING_DIR


def plugin_dir(game_root: os.PathLike | str, tool_id: str) -> Path:
    """插件的固定加载路径：``BepInEx/plugins/LCTA/<tool_id>/``。"""
    return Path(game_root).joinpath(*BEPINEX_PLUGINS, _safe_id(tool_id))


def manifest_path(game_root: os.PathLike | str) -> Path:
    return toolbox_dir(game_root) / MANIFEST_NAME


def journal_path(game_root: os.PathLike | str) -> Path:
    return toolbox_dir(game_root) / JOURNAL_NAME


def lock_path(game_root: os.PathLike | str) -> Path:
    return toolbox_dir(game_root) / LOCK_NAME


_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _safe_id(value: str) -> str:
    """工具/发布 ID 白名单：服务端只应给出这种形态的 ID。

    不接受任意字符串 —— 否则 ID 里塞 ``..\\`` 就能让受管路径逃逸。
    """
    v = (value or "").strip().lower()
    if not _SAFE_ID.match(v) or ".." in v:
        raise UnsafePathError(f"非法工具/发布 ID：{value!r}")
    return v


def validate_game_root(game_root: os.PathLike | str) -> Path:
    """校验游戏目录：存在、是目录、不是链接、可写。

    返回解析后的绝对路径。任何不满足都抛错 —— 不猜、不自动纠正。
    """
    p = Path(game_root)
    if not str(p):
        raise UnsafePathError("游戏目录为空")
    if not p.exists():
        raise UnsafePathError(f"游戏目录不存在：{p}")
    if not p.is_dir():
        raise UnsafePathError(f"游戏目录不是目录：{p}")
    assert_not_link(p, "游戏目录")

    resolved = p.resolve()
    if resolved.parent == resolved:
        # 盘符根（C:\）几乎不可能是游戏目录，且在其下建受管区极危险
        raise UnsafePathError(f"拒绝把盘符根当作游戏目录：{resolved}")
    if not os.access(str(resolved), os.W_OK):
        raise UnsafePathError(f"游戏目录不可写：{resolved}")
    return resolved


def managed_paths_under(game_root: os.PathLike | str) -> Tuple[Path, ...]:
    """受管区域列表（用于「只在受管区内做删除」的断言）。"""
    root = Path(game_root)
    return (toolbox_dir(root), plugin_dir(root, "x").parent)


def assert_managed_target(game_root: os.PathLike | str, target: os.PathLike | str) -> None:
    """删除/移动前的最终断言：目标必须在受管区内，且不是链接。

    所有删除路径都必须经过这里，禁止「调用方自己拼路径直接 remove」。
    """
    root = Path(game_root)
    allowed = managed_paths_under(root)
    t = Path(target)
    if not any(is_within(t, a) for a in allowed):
        raise UnsafePathError(f"拒绝操作受管区外的路径：{t}")
    assert_not_link(t)


def safe_join_under(base: os.PathLike | str, *parts: str) -> Path:
    """在 base 下安全拼接（每段都按成员名规则净化）。"""
    rel = "/".join(sanitize_member_name(p) for p in parts)
    return resolve_within(base, rel)


def short_hash(path: os.PathLike | str) -> str:
    """文件 SHA256（流式，避免大文件整块读入）。"""
    import hashlib

    h = hashlib.sha256()
    with open(str(path), "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_disk_free(path: os.PathLike | str) -> Optional[int]:
    """所在卷剩余空间（字节）；取不到返回 None（调用方按「未知」处理）。"""
    try:
        import shutil as _shutil

        return _shutil.disk_usage(str(path)).free
    except OSError:
        return None