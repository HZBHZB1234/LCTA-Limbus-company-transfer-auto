# -*- coding: utf-8 -*-
"""WebUI 桥接：bank 解包/重打包/.rebank 模组导出转换（每函数返回 dict）。"""
import os

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager

from webutils.bank.dlls import (
    FmodDlls, default_dll_candidates, find_dll_dir, missing_dlls,
)
from webutils.bank.fmod import FORMAT_IDS, default_threads, extract_bank, rebuild_bank
from webutils.bank.format import bank_base, bank_is_encrypted, parse_bank
from webutils.bank.rebank import build_rebank, patch_banks, read_rebank_info
from webutils.bank.errors import BankToolError
from webutils.packages.manage import get_mod_path

_log_manager = LogManager()


def _game_sound_dir(game_path: str) -> str:
    return os.path.join(game_path, "LimbusCompany_Data", "StreamingAssets",
                        "Assets", "Sound", "FMODBuilds", "Desktop")


def _ok(**kw):
    return dict({"success": True}, **kw)


def _err(message):
    _log_manager.log_error(message)
    return {"success": False, "message": str(message)}


def _dlls():
    return FmodDlls()  # 自动按 default_dll_candidates 定位


# -- DLL ------------------------------------------------------------
def bank_dll_status():
    dll_dir = find_dll_dir(default_dll_candidates())
    missing = missing_dlls(dll_dir)
    return _ok(ok=not missing, dir=dll_dir, missing=missing)


def bank_set_dll_dir(dll_dir: str):
    try:
        if not dll_dir.strip():
            ConfigManager().set("ui_default.bank.dll_dir", "")
            return _ok(message="已清除 DLL 目录设置")
        if not os.path.isdir(dll_dir):
            return _err("目录不存在: %s" % dll_dir)
        miss = missing_dlls(dll_dir)
        if miss:
            return _err("该目录缺少 DLL: %s" % ", ".join(miss))
        ConfigManager().set("ui_default.bank.dll_dir", os.path.abspath(dll_dir))
        return _ok(message="DLL 目录已设置")
    except Exception as e:
        return _err(e)


# -- bank 信息 --------------------------------------------------------
def bank_get_game_banks():
    try:
        game_path = ConfigManager().get("game_path", "")
        banks = []
        if game_path:
            sound_dir = _game_sound_dir(game_path)
            for name in sorted(os.listdir(sound_dir)):
                if not name.lower().endswith(".bank"):
                    continue
                path = os.path.join(sound_dir, name)
                try:
                    with open(path, "rb") as fh:
                        data = fh.read()
                    info = parse_bank(data)
                    banks.append({
                        "name": name, "path": path, "size": os.path.getsize(path),
                        "fsb_count": info["fsb_count"] if info else 0,
                        "encrypted": bool(info and bank_is_encrypted(data, info)),
                    })
                except OSError:
                    continue
        return _ok(banks=banks, game_path=game_path)
    except Exception as e:
        return _err(e)


def bank_info(path: str):
    try:
        if not os.path.isfile(path):
            return _err("文件不存在: %s" % path)
        with open(path, "rb") as fh:
            data = fh.read()
        info = parse_bank(data)
        if info is None:
            return _err("无法解析 bank 文件: %s" % os.path.basename(path))
        total = sum(info["fsb_size"])
        return _ok(name=bank_base(path), fsb_count=info["fsb_count"],
                   size=os.path.getsize(path), audio_size=total,
                   encrypted=bank_is_encrypted(data, info))
    except Exception as e:
        return _err(e)


# -- 解包 / 重打包 -----------------------------------------------------
def bank_extract(bank_path: str, out_dir: str, password: str = ""):
    try:
        if not os.path.isfile(bank_path):
            return _err("bank 文件不存在: %s" % bank_path)
        os.makedirs(out_dir, exist_ok=True)
        dlls = _dlls()
        r = extract_bank(dlls, bank_path, out_dir,
                         os.path.join(out_dir, "fsb"), password or None,
                         lambda msg: _log_manager.log(msg))
        return _ok(wav_dir=out_dir, fsb_count=r["fsb_count"],
                   encrypted=r["encrypted"])
    except Exception as e:
        return _err(e)


def bank_rebuild(bank_path: str, wav_dir: str, out_dir: str, password: str = "",
                 format_id: str = "vorbis", quality: int = 92):
    try:
        if not os.path.isfile(bank_path):
            return _err("原版 bank 不存在: %s" % bank_path)
        if format_id not in FORMAT_IDS:
            return _err("未知编码格式: %s" % format_id)
        dlls = _dlls()
        options = {"format": FORMAT_IDS[format_id], "quality": int(quality),
                   "threads": default_threads(),
                   "cache_dir": os.path.join(out_dir, "cache"), "password": password or None}
        out_bank = rebuild_bank(dlls, bank_path, wav_dir,
                                os.path.join(out_dir, "fsb"), out_dir, options,
                                lambda msg: _log_manager.log(msg))
        return _ok(out_bank=out_bank)
    except Exception as e:
        return _err(e)


# -- .rebank 导出 / 转换 / 补丁 -----------------------------------------
def bank_export_rebank(original_path: str, modded_path: str, out_path: str,
                       name: str, version: str, author: str, desc: str,
                       into_mod_folder: bool):
    try:
        for p in (original_path, modded_path):
            if not os.path.isfile(p):
                return _err("文件不存在: %s" % p)
        dlls = _dlls()
        meta = {"name": name, "version": version, "author": author, "description": desc}
        r = build_rebank(dlls, original_path, modded_path, out_path, meta,
                         password=None, log=lambda msg: _log_manager.log(msg))
        if into_mod_folder:
            dst = os.path.join(get_mod_path(), os.path.basename(out_path))
            import shutil
            shutil.copy2(out_path, dst)
            r["out"] = dst
            r["into_mod_folder"] = True
        return _ok(**r)
    except Exception as e:
        return _err(e)


def bank_convert_mod(mod_name: str, keep_original: bool = True):
    """把模组目录里的整包 .bank 转成 .rebank（以游戏当前 bank 为原版）。"""
    try:
        game_path = ConfigManager().get("game_path", "")
        if not game_path:
            return _err("未设置游戏路径")
        mod_path = get_mod_path()
        mod_file = os.path.join(mod_path, mod_name)
        if not os.path.isfile(mod_file):
            return _err("模组文件不存在: %s" % mod_file)
        base = bank_base(mod_name)
        original = os.path.join(_game_sound_dir(game_path), base + ".bank")
        if not os.path.isfile(original):
            return _err("游戏目录没有对应的原版 bank: %s" % original)
        out_path = os.path.join(mod_path, base + ".rebank")
        dlls = _dlls()
        r = build_rebank(dlls, original, mod_file, out_path,
                         {"name": base, "version": "1.0", "author": "", "description": ""},
                         password=None, log=lambda msg: _log_manager.log(msg))
        if not keep_original:
            disable_path = os.path.join(mod_path, base + ".bank_disable")
            os.replace(mod_file, disable_path)
            r["original"] = "disabled"
        return _ok(**r)
    except Exception as e:
        return _err(e)


def bank_patch_full(rebank_path: str, bank_path: str, out_dir: str, password: str = ""):
    try:
        if not os.path.isfile(rebank_path):
            return _err("模组不存在: %s" % rebank_path)
        if not os.path.isfile(bank_path):
            return _err("目标 bank 不存在: %s" % bank_path)
        dlls = _dlls()
        r = patch_banks(dlls, bank_path, [rebank_path], out_dir, password=password or None,
                        log=lambda msg: _log_manager.log(msg))
        return _ok(**r)
    except Exception as e:
        return _err(e)


def bank_rebank_info(path: str):
    try:
        if not os.path.isfile(path):
            return _err("文件不存在: %s" % path)
        cfg, wavs = read_rebank_info(path)
        if cfg is None:
            return _err("没有 rebank.json 配置（可能不是 .rebank 包）")
        return _ok(config=cfg, files=wavs)
    except Exception as e:
        return _err(e)
