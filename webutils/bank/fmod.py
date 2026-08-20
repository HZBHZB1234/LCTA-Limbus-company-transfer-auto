"""FSB↔WAV 解码/编码与 bank 解包/重打包编排。"""
import os

from .dlls import FmodDlls
from .errors import BankToolError
from .format import (
    assemble_bank, bank_base, bank_is_encrypted, extract_fsb_bytes,
    parse_bank, parse_bank_for_rebuild,
)
from .wav import find_wav_txt, read_wav_list

FORMAT_IDS = {"vorbis": 5, "pcm": 0, "fadpcm": 6}


def default_threads() -> int:
    n = os.cpu_count() or 2
    return max(1, n // 2)


def extract_bank(dlls: FmodDlls, bank_path: str, wav_dir: str, fsb_dir: str, log=None) -> dict:
    """拆包一个 bank：FSB 抽取（纯 Python）+ 每个 FSB 解码为 wav（FMOD）。"""
    with open(bank_path, "rb") as fh:
        data = fh.read()
    info = parse_bank(data)
    if info is None:
        raise BankToolError("无法解析 bank 文件: %s" % os.path.basename(bank_path))
    base = bank_base(bank_path)
    encrypted = bank_is_encrypted(data, info)

    os.makedirs(fsb_dir, exist_ok=True)
    for j, fsb_bytes in enumerate(extract_fsb_bytes(data, info)):
        with open(os.path.join(fsb_dir, "%s[%d].fsb" % (base, j)), "wb") as fh:
            fh.write(fsb_bytes)

    os.makedirs(wav_dir, exist_ok=True)
    for j in range(info["fsb_count"]):
        fsb_path = os.path.join(fsb_dir, "%s[%d].fsb" % (base, j))
        sub = os.path.join(wav_dir, "%s[%d]" % (base, j))
        try:
            dlls.decode_fsb_to_wav(fsb_path, sub, "%s[%d]" % (base, j), log)
        except BankToolError as e:
            if log:
                log("[警告] 跳过打不开的 FSB %s[%d]: %s" % (base, j, e))
    return {"bank_base": base, "fsb_count": info["fsb_count"],
            "encrypted": encrypted}


def rebuild_bank(dlls: FmodDlls, bank_path: str, wav_dir: str, fsb_dir: str, build_dir: str,
                 options: dict, log=None) -> str:
    """重打包 bank：按 wav 清单编码 FSB → 拼回原布局。返回输出路径。"""
    with open(bank_path, "rb") as fh:
        bank_data = fh.read()
    info = parse_bank_for_rebuild(bank_data)
    if info is None:
        raise BankToolError("无法解析 bank 头部: %s" % os.path.basename(bank_path))
    base = bank_base(bank_path)

    fsb_paths = []
    for j in range(info["fsb_count"]):
        list_path = find_wav_txt(wav_dir, "%s[%d]" % (base, j))
        if list_path is None:
            raise BankToolError("缺少 wav 清单 %s[%d].txt（位于 %s）" % (base, j, wav_dir))
        wav_files = [os.path.join(wav_dir, "%s[%d]" % (base, j), w)
                     for w in read_wav_list(list_path)]
        missing = [w for w in wav_files if not os.path.isfile(w)]
        if missing:
            raise BankToolError("缺少 wav 文件: %s" % ", ".join(missing))
        fsb_out = os.path.join(fsb_dir, "%s[%d].fsb" % (base, j))
        dlls.encode_wavs_to_fsb(wav_files, fsb_out, options["format"], options["quality"],
                                options["threads"], options["cache_dir"], log)
        fsb_paths.append(fsb_out)

    out_path = os.path.join(build_dir, os.path.basename(bank_path))
    fsb_data = [open(p, "rb").read() for p in fsb_paths]
    assemble_bank(bank_data, info, fsb_data, out_path)
    return out_path
