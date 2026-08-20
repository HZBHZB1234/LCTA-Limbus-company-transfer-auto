""".rebank 差分模组格式：导出（compare）与补丁（patch）。

包内布局（与外部工具兼容）:
    rebank.json                    配置（format/name/version/author/description/base_bank/...）
    {fsb序号}/{wav文件名}.wav      改动的音频
修改判定：时长（3 位小数）不同视为改动；新增只记录不删。
"""
import datetime
import glob
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from typing import Iterator, List, Optional, Tuple

from .dlls import FmodDlls
from .errors import BankToolError
from .fmod import extract_bank, rebuild_bank
from .format import bank_base
from .wav import read_wav_info, wav_duration_file

CONFIG_NAME = "rebank.json"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rebank_cache_dir() -> str:
    """rebank 补丁缓存目录（launcher bankmod 与 WebUI 共用，%LOCALAPPDATA%/LCTA/mod-cache/bank）。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "LCTA", "mod-cache", "bank")
    os.makedirs(d, exist_ok=True)
    return d


def rebank_mod_digest(rebank_paths) -> str:
    """模组内容摘要（与 launcher bankmod.mod_digest 同公式：basename + 内容 sha256）。"""
    h = hashlib.sha256()
    for rp in sorted(rebank_paths):
        h.update(os.path.basename(rp).encode("utf-8"))
        h.update(b"\0")
        h.update(sha256_file(rp).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def patch_cache_key(orig_sha256: str, mod_digest: str, quality: int, threads: int) -> str:
    """补丁缓存键：原版 bank + 模组内容 + 编码参数（质量/线程）共同决定。"""
    return hashlib.sha256(
        ("%s|%s|%d|%d" % (orig_sha256, mod_digest, int(quality), int(threads))).encode("utf-8")
    ).hexdigest()


def patch_options() -> dict:
    """重打包参数（读 ui_default.bank.quality/threads，默认 92 / 默认线程数）。"""
    from globalManagers.ConfigManager import ConfigManager
    from .fmod import default_threads

    cfg = ConfigManager()
    try:
        quality = int(cfg.get("ui_default.bank.quality", 92))
    except (TypeError, ValueError):
        quality = 92
    try:
        threads = int(cfg.get("ui_default.bank.threads", 0) or 0) or default_threads()
    except (TypeError, ValueError):
        threads = default_threads()
    return {"quality": quality, "threads": threads}


def prune_rebank_cache(max_entries: int = 20) -> int:
    """按 mtime 保留最近 max_entries 个缓存条目（*.bank 补丁缓存 + export-*.rebank 导出缓存）。"""
    cache_dir = rebank_cache_dir()
    entries = sorted(
        glob.glob(os.path.join(cache_dir, "*.bank")) + glob.glob(os.path.join(cache_dir, "export-*.rebank")),
        key=os.path.getmtime, reverse=True)
    removed = 0
    for old in entries[max_entries:]:
        try:
            os.remove(old)
            os.remove(old + ".json")
            removed += 1
        except OSError:
            pass
    return removed


def collect_wavs(wav_dir: str) -> dict:
    out = {}
    for name in sorted(os.listdir(wav_dir)):
        sub = os.path.join(wav_dir, name)
        if not os.path.isdir(sub) or "[" not in name or not name.endswith("]"):
            continue
        try:
            idx = int(name[name.rindex("[") + 1:name.rindex("]")])
        except ValueError:
            continue
        for f in os.listdir(sub):
            if f.lower().endswith(".wav"):
                out[(idx, f)] = os.path.join(sub, f)
    return out


def _make_work_dir(base: Optional[str]) -> str:
    if base:
        root = os.path.abspath(base)
    else:
        root = os.path.join(tempfile.gettempdir(), "lcta_bank")
    os.makedirs(root, exist_ok=True)
    return root


def _clean_work_dir(work: str) -> None:
    shutil.rmtree(work, ignore_errors=True)


def make_rebank(stage_dir: str, out_path: str) -> None:
    if os.path.exists(out_path):
        os.remove(out_path)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(stage_dir):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, stage_dir).replace("\\", "/")
                z.write(full, rel)


def read_rebank_info(path: str) -> Tuple[Optional[dict], List[str]]:
    cfg = None
    wavs = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if CONFIG_NAME in names:
            try:
                cfg = json.loads(z.read(CONFIG_NAME).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                cfg = None
        wavs = [n for n in names if not n.startswith(CONFIG_NAME) and not n.endswith("/")]
    return cfg, wavs


def iter_rebank_wavs(path: str) -> Iterator[Tuple[int, str, bytes]]:
    with zipfile.ZipFile(path) as z:
        for zi in z.infolist():
            if zi.is_dir() or zi.filename.replace("\\", "/").lower() == CONFIG_NAME:
                continue
            rel = zi.filename.replace("\\", "/")
            parts = rel.split("/")
            try:
                idx = int(parts[0])
                fname = parts[-1]
            except (ValueError, IndexError):
                continue
            yield idx, fname, z.read(zi)


def _diff_wavs(a_wav: dict, b_wav: dict, log=None):
    modified = [k for k in b_wav if k in a_wav and wav_duration_file(a_wav[k]) != wav_duration_file(b_wav[k])]
    added = [k for k in b_wav if k not in a_wav]
    if log:
        for idx, name in modified:
            log("[修改] fsb[%d] %s" % (idx, name))
        for idx, name in added:
            log("[新增] fsb[%d] %s" % (idx, name))
    return modified, added


def build_rebank(dlls: FmodDlls, original_path: str, modded_path: str, out_path: str,
                 meta: dict, work_dir: Optional[str] = None, log=None) -> dict:
    """对比原版与模组 bank，生成 .rebank 差分包。"""
    work = _make_work_dir(work_dir)
    try:
        a_wav = os.path.join(work, "a_wav"); a_fsb = os.path.join(work, "a_fsb")
        b_wav = os.path.join(work, "b_wav"); b_fsb = os.path.join(work, "b_fsb")
        a = extract_bank(dlls, original_path, a_wav, a_fsb, log)
        b = extract_bank(dlls, modded_path, b_wav, b_fsb, log)
        A = collect_wavs(a_wav)
        B = collect_wavs(b_wav)
        modified, added = _diff_wavs(A, B, log)
        if not modified and not added:
            raise BankToolError("两个 bank 的音频完全一致，没有差异。")

        stage = os.path.join(work, "stage")
        for idx, name in modified + added:
            dst = os.path.join(stage, str(idx))
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(B[(idx, name)], os.path.join(dst, name))

        cfg = {
            "format": "rebank",
            "name": meta.get("name") or bank_base(modded_path),
            "version": meta.get("version") or "1.0",
            "author": meta.get("author") or "",
            "description": meta.get("description") or "",
            "base_bank": a["bank_base"],
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "count": len(modified) + len(added),
            "files": [{"index": i, "name": n,
                       "status": "modified" if (i, n) in modified else "added"}
                      for (i, n) in modified + added],
        }
        with open(os.path.join(stage, CONFIG_NAME), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        make_rebank(stage, out_path)
        return {"modified": modified, "added": added, "count": cfg["count"],
                "out": out_path, "base_bank": cfg["base_bank"]}
    finally:
        _clean_work_dir(work)


def patch_banks(dlls: FmodDlls, bank_path: str, rebank_paths: List[str], out_dir: str,
                work_dir: Optional[str] = None, log=None) -> dict:
    """把若干 .rebank 应用到目标 bank，输出重打包后的 bank。"""
    work = _make_work_dir(work_dir)
    try:
        wav_dir = os.path.join(work, "wav"); fsb_dir = os.path.join(work, "fsb")
        extract_bank(dlls, bank_path, wav_dir, fsb_dir, log)
        T = collect_wavs(wav_dir)

        replaced = skipped_new = skipped_bad = 0
        for m in rebank_paths:
            mname = os.path.basename(m)
            if log:
                log("处理 %s" % mname)
            for idx, fname, mod_data in iter_rebank_wavs(m):
                key = (idx, fname)
                if key not in T:
                    skipped_new += 1
                    if log:
                        log("[%s] %s 目标 bank 无此文件，跳过（新增不受支持）" % (mname, key))
                    continue
                if read_wav_info(mod_data) is None:
                    skipped_bad += 1
                    if log:
                        log("[%s] %s 不是有效 wav，跳过" % (mname, fname))
                    continue
                with open(T[key], "wb") as fh:
                    fh.write(mod_data)
                replaced += 1
                if log:
                    log("[替换] fsb[%d] %s" % key)
        if replaced == 0:
            raise BankToolError("没有成功替换任何文件，取消重打包。")

        opts = patch_options()
        options = {"format": 5, "quality": opts["quality"], "threads": opts["threads"],
                   "cache_dir": os.path.join(work, "cache")}
        out_bank = rebuild_bank(dlls, bank_path, wav_dir, fsb_dir, out_dir, options, log)
        return {"replaced": replaced, "skipped_new": skipped_new, "skipped_bad": skipped_bad,
                "out_bank": out_bank}
    finally:
        _clean_work_dir(work)
