"""启动期 .rebank 模组补丁 + 哈希缓存。

与 launcher/sound.py 同一 .bank.bak 备份/还原机制：
- 补丁前若目标无 .bak，先改名备份（还原统一走 sound.restore_sound()）
- 补丁发生在 wait_for_validation 之后（sound_replace_thread 内调用），避免游戏校验回滚
缓存键 = 原版 bank sha256 + 模组文件内容摘要；命中直接复制，不重编码。
"""
import datetime
import glob
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from globalManagers.LogManager import LogManager

_log_manager = LogManager()

_REBANK_EXT = ".rebank"
CACHE_SUBDIR = "bank-cache"


def rebank_files_in(mod_root: str):
    """启用的 .rebank 列表（递归 rglob，精确匹配后缀，天然排除 *_disable）。"""
    files = []
    for p in sorted(Path(mod_root).rglob("*" + _REBANK_EXT)):
        files.append(str(p))
    return files


def cache_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "LCTA", CACHE_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mod_digest(rebank_paths) -> str:
    """模组内容摘要：按包内文件 rel 排序，拼接 (rel + sha256)。"""
    h = hashlib.sha256()
    for rp in sorted(rebank_paths):
        h.update(os.path.basename(rp).encode("utf-8"))
        h.update(b"\0")
        h.update(sha256_file(rp).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def _base_bank_of(rebank_path: str) -> str:
    import zipfile
    try:
        with zipfile.ZipFile(rebank_path) as z:
            import json as _json
            cfg = _json.loads(z.read("rebank.json").decode("utf-8"))
            base = cfg.get("base_bank") or ""
            if base and not base.endswith(".bank"):
                base += ".bank"
            return base
    except Exception:
        return ""


def apply_rebanks(mod_root: str) -> dict:
    """对模组目录中所有启用 .rebank 就地补丁游戏 bank（含缓存）。"""
    import launcher.sound as sound

    rebanks = rebank_files_in(mod_root)
    if not rebanks:
        return {"patched": [], "skipped": [], "cache_hit": 0, "cache_miss": 0}

    sound_dir = sound.sound_folder()
    if not os.path.isdir(sound_dir):
        return {"patched": [], "skipped": [("(无音频目录)", "游戏音频目录不存在")],
                "cache_hit": 0, "cache_miss": 0}

    # 按目标 bank 分组（同 bank 的多个模组按文件名排序依次应用）
    by_target = {}
    for rp in rebanks:
        base = _base_bank_of(rp) or (os.path.basename(rp)[:-len(_REBANK_EXT)] + ".bank")
        by_target.setdefault(base, []).append(rp)
    for base in by_target:
        by_target[base].sort()

    patched, skipped = [], []
    cache_hit = cache_miss = 0
    for base, mods in sorted(by_target.items()):
        target = os.path.join(sound_dir, base)
        if not os.path.isfile(target):
            skipped.append((base, "目标 bank 不存在"))
            continue
        if os.path.isfile(target + ".bak"):
            # 存在 .bak 说明本次会话整包 .bank 模组已替换该 bank（整包 .bank 优先）
            skipped.append((base, "已被整包 .bank 模组覆盖，跳过"))
            continue
        orig_path = target + ".bak" if os.path.isfile(target + ".bak") else target
        orig_hash = sha256_file(orig_path)
        digest = hashlib.sha256((orig_hash + "|" + mod_digest(mods)).encode("utf-8")).hexdigest()
        cache_file = os.path.join(cache_dir(), digest + ".bank")
        meta_file = cache_file + ".json"
        if os.path.isfile(cache_file) and os.path.isfile(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
                if meta.get("orig_sha256") == orig_hash:
                    if not os.path.isfile(target + ".bak"):
                        os.replace(target, target + ".bak")
                    shutil.copyfile(cache_file, target + ".tmp")
                    os.replace(target + ".tmp", target)
                    _log_manager.log("缓存命中 %s -> %s" % (base, target))
                    cache_hit += 1
                    patched.append(base)
                    continue
            except (OSError, ValueError):
                pass
        try:
            if not os.path.isfile(target + ".bak"):
                os.replace(target, target + ".bak")
            source = target + ".bak" if os.path.isfile(target + ".bak") else target
            _patch_into(source, target, mods)
            meta = {"orig_sha256": orig_hash, "mod_digest": mod_digest(mods),
                    "created": datetime.datetime.now().isoformat(timespec="seconds")}
            with open(meta_file, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=2)
            shutil.copyfile(target, cache_file)
            cache_miss += 1
            patched.append(base)
            _log_manager.log("* 补丁完成（未命中缓存）: %s" % base)
        except Exception as e:
            _log_manager.log_error(e)
            skipped.append((base, str(e)))
            if os.path.isfile(target + ".bak"):
                os.replace(target + ".bak", target)  # 回滚
    prune_cache()
    return {"patched": patched, "skipped": skipped, "cache_hit": cache_hit,
            "cache_miss": cache_miss}


def _patch_into(original_path: str, target_path: str, rebanks, log=None) -> None:
    """解包 original_path（原版字节）→ 应用模组 wav → 重打包 → 写 target_path。"""
    work = tempfile.mkdtemp(prefix="bankmod_")
    try:
        from webutils.bank.dlls import FmodDlls
        from webutils.bank.errors import BankToolError
        from webutils.bank.fmod import default_threads, extract_bank, rebuild_bank
        from webutils.bank.rebank import collect_wavs, iter_rebank_wavs
        from webutils.bank.wav import read_wav_info

        def _log(msg):
            if log:
                log(msg)

        wav_dir = os.path.join(work, "wav"); fsb_dir = os.path.join(work, "fsb")
        dlls = FmodDlls()
        extract_bank(dlls, original_path, wav_dir, fsb_dir, None, _log)
        T = collect_wavs(wav_dir)
        replaced = 0
        for rp in rebanks:
            for idx, fname, data in iter_rebank_wavs(rp):
                key = (idx, fname)
                if key not in T or read_wav_info(data) is None:
                    continue
                with open(T[key], "wb") as fh:
                    fh.write(data)
                replaced += 1
        if replaced == 0:
            raise BankToolError("没有可应用的 wav")
        out_dir = os.path.join(work, "out")
        options = {"format": 5, "quality": 92, "threads": default_threads(),
                   "cache_dir": os.path.join(work, "cache"), "password": None}
        patched = rebuild_bank(dlls, original_path, wav_dir, fsb_dir, out_dir, options, _log)
        os.replace(patched, target_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def prune_cache(max_entries: int = 20) -> int:
    """按 mtime 保留最近 max_entries 个缓存条目（.bank 与 .json 成对）。"""
    entries = sorted(glob.glob(os.path.join(cache_dir(), "*.bank")),
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
