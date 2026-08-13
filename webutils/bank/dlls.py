"""FMOD/FSBANK 64 位 DLL 定位与 ctypes 绑定。

DLL 由运行时获取（不入库不入发布包）。定位顺序见 default_dll_candidates()。
"""
import ctypes
import os
from typing import List, Optional, Sequence

from globalManagers.ConfigManager import ConfigManager
from .errors import BankDllMissingError, BankToolError
from .wav import write_wav_header

DLL_NAMES = ("fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll")

FMOD_OK = 0
FMOD_OPENONLY = 0x00002000
FMOD_INIT_NORMAL = 0x00000000
FMOD_TIMEUNIT_PCMBYTES = 0x00000004

FSBANK_FSBVERSION_FSB5 = 0
FSBANK_INIT_GENERATEPROGRESSITEMS = 0x00000010
FSBANK_FORMAT_PCM = 0
FSBANK_FORMAT_VORBIS = 5
FSBANK_FORMAT_FADPCM = 6
FSBANK_STATE_FINISHED = 5
FSBANK_STATE_WARNING = 7

CHUNK_SIZE = 262144  # 256 KiB 读取缓冲


class FMOD_CREATESOUNDEXINFO(ctypes.Structure):
    _fields_ = [
        ("cbsize", ctypes.c_int),
        ("length", ctypes.c_uint),
        ("fileoffset", ctypes.c_uint),
        ("numchannels", ctypes.c_int),
        ("defaultfrequency", ctypes.c_int),
        ("format", ctypes.c_int),
        ("decodebuffersize", ctypes.c_uint),
        ("initialsubsound", ctypes.c_int),
        ("numsubsounds", ctypes.c_int),
        ("inclusionlist", ctypes.c_void_p),
        ("inclusionlistnum", ctypes.c_int),
        ("pcmreadcallback", ctypes.c_void_p),
        ("pcmsetposcallback", ctypes.c_void_p),
        ("nonblockcallback", ctypes.c_void_p),
        ("dlsname", ctypes.c_char_p),
        ("encryptionkey", ctypes.c_char_p),
        ("maxpolyphony", ctypes.c_int),
        ("userdata", ctypes.c_void_p),
        ("suggestedsoundtype", ctypes.c_int),
        ("fileuseropen", ctypes.c_void_p),
        ("fileuserclose", ctypes.c_void_p),
        ("fileuserread", ctypes.c_void_p),
        ("fileuserseek", ctypes.c_void_p),
        ("fileuserasyncread", ctypes.c_void_p),
        ("fileuserasynccancel", ctypes.c_void_p),
        ("fileuserdata", ctypes.c_void_p),
        ("filebuffersize", ctypes.c_int),
        ("channelorder", ctypes.c_int),
        ("channelmask", ctypes.c_uint),
        ("initialsoundgroup", ctypes.c_void_p),
        ("initialseekposition", ctypes.c_uint),
        ("initialseekpostype", ctypes.c_int),
        ("ignoresetfilesystem", ctypes.c_int),
        ("audioqueuepolicy", ctypes.c_uint),
        ("minmidigranularity", ctypes.c_uint),
        ("nonblockthreadid", ctypes.c_int),
        ("fsbguid", ctypes.c_void_p),
    ]


class FSBANK_SUBSOUND(ctypes.Structure):
    _fields_ = [
        ("fileNames", ctypes.c_void_p),        # const char* const*
        ("fileData", ctypes.c_void_p),         # const void* const*
        ("fileDataLengths", ctypes.c_void_p),  # const unsigned int*
        ("numFiles", ctypes.c_uint),
        ("overrideFlags", ctypes.c_uint),
        ("overrideQuality", ctypes.c_uint),
        ("desiredSampleRate", ctypes.c_float),
        ("percentOptimizedRate", ctypes.c_float),
    ]


class FSBANK_PROGRESSITEM(ctypes.Structure):
    _fields_ = [
        ("subSoundIndex", ctypes.c_int),
        ("threadIndex", ctypes.c_int),
        ("state", ctypes.c_int),
        ("stateData", ctypes.c_void_p),
    ]


def missing_dlls(dll_dir: Optional[str]) -> List[str]:
    if not dll_dir or not os.path.isdir(dll_dir):
        return list(DLL_NAMES)
    return [n for n in DLL_NAMES if not os.path.isfile(os.path.join(dll_dir, n))]


def find_dll_dir(candidates: Sequence[str]) -> Optional[str]:
    for d in candidates:
        if d and not missing_dlls(d):
            return os.path.abspath(d)
    return None


def default_download_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "LCTA", "fmod-dlls")


def default_dll_candidates() -> List[str]:
    cands = []
    cfg_dir = ConfigManager().get("ui_default.bank.dll_dir", "")
    if cfg_dir:
        cands.append(cfg_dir)
    env_dir = os.environ.get("LCTA_FMOD_DLL_DIR", "")
    if env_dir:
        cands.append(env_dir)
    cands.append(default_download_dir())
    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
    cands.append(app_root)
    cands.append(os.path.join(app_root, "tools", "fmod"))
    cands.append(os.getcwd())
    return cands


def _make_error_text(where, rc):
    return "%s: FMOD/FSBANK 返回错误码 %d" % (where, rc)


class FmodDlls:
    """FMOD 解码 / FSBANK 编码的 ctypes 封装（供单元测试注入替身）。"""

    def __init__(self, dll_dir: Optional[str] = None):
        if not dll_dir:
            dll_dir = find_dll_dir(default_dll_candidates())
        miss = missing_dlls(dll_dir)
        if miss:
            raise BankDllMissingError(
                "缺少 FMOD 工具 DLL: %s。可在「音频工具」页一键下载，"
                "或手动选择包含全部 3 个 DLL 的目录。" % ", ".join(miss))
        self._dir = os.path.abspath(dll_dir)
        self._fmod = ctypes.CDLL(os.path.join(self._dir, "fmod64.dll"))
        self._fsbank = ctypes.CDLL(os.path.join(self._dir, "fsbank64.dll"))
        self._bind()

    @property
    def dll_dir(self) -> str:
        return self._dir

    def _bind(self):
        f = self._fmod
        f.FMOD_System_Create.restype = ctypes.c_int
        f.FMOD_System_Create.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        f.FMOD_System_Init.restype = ctypes.c_int
        f.FMOD_System_Init.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]
        f.FMOD_System_Release.restype = ctypes.c_int
        f.FMOD_System_Release.argtypes = [ctypes.c_void_p]
        f.FMOD_System_CreateSound.restype = ctypes.c_int
        f.FMOD_System_CreateSound.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint,
            ctypes.POINTER(FMOD_CREATESOUNDEXINFO), ctypes.POINTER(ctypes.c_void_p),
        ]
        f.FMOD_Sound_Release.restype = ctypes.c_int
        f.FMOD_Sound_Release.argtypes = [ctypes.c_void_p]
        f.FMOD_Sound_GetNumSubSounds.restype = ctypes.c_int
        f.FMOD_Sound_GetNumSubSounds.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        f.FMOD_Sound_GetSubSound.restype = ctypes.c_int
        f.FMOD_Sound_GetSubSound.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        f.FMOD_Sound_SeekData.restype = ctypes.c_int
        f.FMOD_Sound_SeekData.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        f.FMOD_Sound_GetDefaults.restype = ctypes.c_int
        f.FMOD_Sound_GetDefaults.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_int)]
        f.FMOD_Sound_GetFormat.restype = ctypes.c_int
        f.FMOD_Sound_GetFormat.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                           ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        f.FMOD_Sound_GetLength.restype = ctypes.c_int
        f.FMOD_Sound_GetLength.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint), ctypes.c_uint]
        f.FMOD_Sound_GetName.restype = ctypes.c_int
        f.FMOD_Sound_GetName.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        f.FMOD_Sound_ReadData.restype = ctypes.c_int
        f.FMOD_Sound_ReadData.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]

        b = self._fsbank
        b.FSBank_Init.restype = ctypes.c_int
        b.FSBank_Init.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_char_p]
        b.FSBank_Release.restype = ctypes.c_int
        b.FSBank_Release.argtypes = []
        b.FSBank_Build.restype = ctypes.c_int
        b.FSBank_Build.argtypes = [
            ctypes.POINTER(FSBANK_SUBSOUND), ctypes.c_uint, ctypes.c_int, ctypes.c_uint,
            ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ]
        b.FSBank_FetchNextProgressItem.restype = ctypes.c_int
        b.FSBank_FetchNextProgressItem.argtypes = [ctypes.POINTER(ctypes.POINTER(FSBANK_PROGRESSITEM))]
        b.FSBank_ReleaseProgressItem.restype = ctypes.c_int
        b.FSBank_ReleaseProgressItem.argtypes = [ctypes.POINTER(FSBANK_PROGRESSITEM)]

    @staticmethod
    def _check(rc, where):
        if rc != FMOD_OK:
            raise BankToolError(_make_error_text(where, rc))

    # -- 解码: FSB -> WAV --------------------------------------------------
    def decode_fsb_to_wav(self, fsb_path, wav_dir, wav_name_base, password=None, log=None) -> List[str]:
        system = ctypes.c_void_p()
        exinfo = FMOD_CREATESOUNDEXINFO()
        exinfo.cbsize = ctypes.sizeof(FMOD_CREATESOUNDEXINFO)
        if password:
            exinfo.encryptionkey = password.encode("utf-8")
        self._check(self._fmod.FMOD_System_Create(ctypes.byref(system)), "FMOD_System_Create")
        try:
            self._check(self._fmod.FMOD_System_Init(system, 1, FMOD_INIT_NORMAL, None), "FMOD_System_Init")
        except BankToolError:
            self._fmod.FMOD_System_Release(system)
            raise

        sound = ctypes.c_void_p()
        name_b = os.path.abspath(fsb_path).encode("utf-8")
        try:
            self._check(self._fmod.FMOD_System_CreateSound(
                system, name_b, FMOD_OPENONLY, ctypes.byref(exinfo), ctypes.byref(sound)),
                "FMOD_System_CreateSound")
            num_sub = ctypes.c_int(0)
            self._check(self._fmod.FMOD_Sound_GetNumSubSounds(sound, ctypes.byref(num_sub)),
                        "FMOD_Sound_GetNumSubSounds")
            n = num_sub.value
            os.makedirs(wav_dir, exist_ok=True)
            txt_names = []
            for j in range(n):
                sub = ctypes.c_void_p()
                try:
                    self._check(self._fmod.FMOD_Sound_GetSubSound(sound, j, ctypes.byref(sub)),
                                "FMOD_Sound_GetSubSound")
                    self._check(self._fmod.FMOD_Sound_SeekData(sub, 0), "FMOD_Sound_SeekData")
                    freq = ctypes.c_float(0)
                    priority = ctypes.c_int(0)
                    self._check(self._fmod.FMOD_Sound_GetDefaults(sub, ctypes.byref(freq),
                                                                  ctypes.byref(priority)), "FMOD_Sound_GetDefaults")
                    stype = ctypes.c_int(0)
                    sformat = ctypes.c_int(0)
                    channels = ctypes.c_int(0)
                    bits = ctypes.c_int(0)
                    self._check(self._fmod.FMOD_Sound_GetFormat(sub, ctypes.byref(stype),
                                                                ctypes.byref(sformat),
                                                                ctypes.byref(channels),
                                                                ctypes.byref(bits)), "FMOD_Sound_GetFormat")
                    length = ctypes.c_uint(0)
                    self._check(self._fmod.FMOD_Sound_GetLength(sub, ctypes.byref(length),
                                                                FMOD_TIMEUNIT_PCMBYTES), "FMOD_Sound_GetLength")
                    cname = ctypes.create_string_buffer(64)
                    self._check(self._fmod.FMOD_Sound_GetName(sub, cname, 64), "FMOD_Sound_GetName")
                    sub_name = cname.value.decode("utf-8", "replace") or ("sound_%d" % j)

                    base_name = sub_name
                    file_name = base_name + ".wav"
                    suffix = j
                    while os.path.exists(os.path.join(wav_dir, file_name)):
                        sub_name = "%s_%d" % (base_name, suffix)
                        file_name = sub_name + ".wav"
                        suffix += 1

                    data_len = length.value
                    wav_path = os.path.join(wav_dir, file_name)
                    with open(wav_path, "wb") as wav:
                        write_wav_header(wav, int(freq.value), bits.value, channels.value, data_len)
                        remaining = data_len
                        buf = ctypes.create_string_buffer(CHUNK_SIZE)
                        while remaining > 0:
                            want = min(CHUNK_SIZE, remaining)
                            got = ctypes.c_uint(0)
                            self._check(self._fmod.FMOD_Sound_ReadData(sub, buf, want, ctypes.byref(got)),
                                        "FMOD_Sound_ReadData(%s)" % file_name)
                            if got.value == 0:
                                break
                            wav.write(buf.raw[:got.value])
                            remaining -= got.value
                    self._fmod.FMOD_Sound_Release(sub)
                    sub = None
                    txt_names.append(sub_name + ".wav")
                    if log:
                        log("[%s] %s" % (wav_name_base, sub_name + ".wav"))
                except BankToolError as e:
                    if log:
                        log("[警告] 跳过无法解码的子音 #%d: %s" % (j, e))
                    if sub.value:
                        self._fmod.FMOD_Sound_Release(sub)
            with open(os.path.join(wav_dir, wav_name_base + ".txt"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(txt_names) + "\n")
            return txt_names
        finally:
            if sound.value:
                self._fmod.FMOD_Sound_Release(sound)
            self._fmod.FMOD_System_Release(system)

    # -- 编码: WAV -> FSB --------------------------------------------------
    def encode_wavs_to_fsb(self, wav_files, out_fsb, format_id, quality, threads, cache_dir,
                           encrypt_key=None, log=None) -> None:
        os.makedirs(cache_dir, exist_ok=True)
        # FSBANK 1.x 签名 (version, initFlags, numThreads, tempdir)，与 Fmod-Bank-Tools 的
        # include/fsbank.h 一致（捆绑的 fsbank64.dll 即该版本），勿按 2.x 顺序改动
        rc = self._fsbank.FSBank_Init(FSBANK_FSBVERSION_FSB5, FSBANK_INIT_GENERATEPROGRESSITEMS,
                                      threads, cache_dir.encode("utf-8"))
        if rc != FMOD_OK:
            raise BankToolError(_make_error_text("FSBank_Init", rc))
        try:
            n = len(wav_files)
            enc = [w.encode("utf-8") for w in wav_files]
            ptr_arrays = [(ctypes.c_char_p * 1)(b) for b in enc]
            arr = (FSBANK_SUBSOUND * n)()
            for i in range(n):
                arr[i].fileNames = ctypes.cast(ptr_arrays[i], ctypes.c_void_p)
                arr[i].numFiles = 1
            key_b = encrypt_key.encode("utf-8") if encrypt_key else None
            rc = self._fsbank.FSBank_Build(arr, n, format_id, 0, quality, key_b, out_fsb.encode("utf-8"))
            if rc != FMOD_OK:
                raise BankToolError(_make_error_text("FSBank_Build", rc))
            while True:
                item_p = ctypes.POINTER(FSBANK_PROGRESSITEM)()
                rc = self._fsbank.FSBank_FetchNextProgressItem(ctypes.byref(item_p))
                if rc != FMOD_OK or not item_p:
                    break
                item = item_p.contents
                if item.state == FSBANK_STATE_FINISHED and item.subSoundIndex != -1:
                    if log:
                        log("[编码完成 %d]" % item.subSoundIndex)
                elif item.state == FSBANK_STATE_WARNING and log:
                    log("[警告] 某个 wav 文件存在问题")
                self._fsbank.FSBank_ReleaseProgressItem(item_p)
        finally:
            self._fsbank.FSBank_Release()
