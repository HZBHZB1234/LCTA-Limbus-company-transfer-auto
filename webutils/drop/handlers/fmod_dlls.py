from __future__ import annotations

import os
import zipfile
from typing import Any

from globalManagers.ConfigManager import ConfigManager

from ..context import FileExecutionContext
from ..handler import DropFileHandler, remove_existing

DLL_NAMES = ("fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll")


def default_dll_dir() -> str:
    cfg = ConfigManager().get("ui_default.bank.dll_dir", "")
    if cfg:
        return cfg
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                        "LCTA", "fmod-dlls")


class FmodDllZipHandler(DropFileHandler):
    """FMOD 工具包（工具.zip）拖入导入 DLL。"""

    file_type = "fmod_dlls"
    label = "FMOD 工具 DLL 包"

    def detect(self, item: Any) -> str | None:
        if not isinstance(item, str) or not item.lower().endswith(".zip"):
            return None
        try:
            with zipfile.ZipFile(item) as z:
                names = set(z.namelist())
            if "fmodbank.py" not in names or "rebank.py" not in names:
                return None
            if not all(dll in names for dll in DLL_NAMES):
                return None
            return self.file_type
        except (OSError, zipfile.BadZipFile):
            return None

    def execute(self, context: FileExecutionContext) -> str:
        dest = default_dll_dir()
        os.makedirs(dest, exist_ok=True)
        extracted = 0
        with zipfile.ZipFile(context.file_path) as z:
            for dll in DLL_NAMES:
                out = os.path.join(dest, dll)
                remove_existing(out)
                with open(out, "wb") as fh:
                    fh.write(z.read(dll))
                extracted += 1
        ConfigManager().set("ui_default.bank.dll_dir", dest)
        from globalManagers.LogManager import LogManager
        LogManager().log(f"FMOD 工具 DLL 已导入: {dest}（{extracted} 个文件）")
        return "imported"
