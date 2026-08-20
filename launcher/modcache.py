"""统一模组缓存（carra2 转换/解压、bundle 重打包、bank 补丁）。

缓存根：%LOCALAPPDATA%/LCTA/mod-cache/
- carra2-convert/<zip_sha256>.carra2   zip→carra2 转换产物（不再删除源 zip，命中跳过转换）
- carra2-extract/<carra2_sha256>/      解压+展平后的目录
- bundle-patch/<digest>/__data         bundle 重打包产物（key=原版 hash + 模组内容摘要）
- bank/                                rebank 补丁缓存（launcher bankmod 与 WebUI 共用）

另提供 enabled_mod_files：rglob 的 _disable 统一过滤（文件名或任一路径段
以 _disable 结尾即视为禁用），供 patch/sound/bankmod/changes 共用。
"""
import hashlib
import os
from pathlib import Path

_CACHE_SUBDIR = "mod-cache"


def cache_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    root = Path(base) / "LCTA" / _CACHE_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def carra2_convert_dir() -> Path:
    d = cache_root() / "carra2-convert"
    d.mkdir(parents=True, exist_ok=True)
    return d


def carra2_extract_dir() -> Path:
    d = cache_root() / "carra2-extract"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bundle_patch_dir() -> Path:
    d = cache_root() / "bundle-patch"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bank_cache_dir() -> Path:
    d = cache_root() / "bank"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_digest(root) -> str:
    """目录内容摘要（相对路径 + 内容 sha256），与目录名无关。"""
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode("utf-8"))
            h.update(b"\0")
            h.update(sha256_file(str(p)).encode("utf-8"))
            h.update(b"\0")
    return h.hexdigest()


def atomic_write(dest, data: bytes) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, dest)


def prune_lru(directory, max_entries: int = 30) -> int:
    """按 mtime 保留最近 max_entries 个条目（文件或目录，跳过 *.tmp）。"""
    directory = Path(directory)
    if not directory.is_dir():
        return 0
    entries = [p for p in directory.iterdir()
               if (p.is_file() or p.is_dir()) and not p.name.endswith(".tmp")]
    entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for old in entries[max_entries:]:
        try:
            if old.is_dir():
                import shutil
                shutil.rmtree(old)
            else:
                old.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def enabled_mod_files(root, pattern):
    """rglob 结果过滤：任一路径段以 _disable 结尾即视为禁用（整目录禁用）。"""
    out = []
    for p in sorted(Path(root).rglob(pattern)):
        if any(seg.endswith("_disable") for seg in p.parts):
            continue
        out.append(p)
    return out