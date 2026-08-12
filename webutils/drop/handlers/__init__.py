"""拖放文件分支处理器注册表：每个 NAMEREFER 类别对应一个处理器类。

检测顺序按容器类型分组（zip / folder / json / path），与重构前行为严格一致：
- zip: full → nofont → FLmod → update → jsononly（update 必须优先于 jsononly）
- folder: full → nofont → FLmod → jsononly
- json: busimport → textFile → LCTAchange → FLchange
- path: carra → bank → font
"""

from ..handler import DropFileHandlerRegistry
from .translation import FullHandler, NoFontHandler
from .archive_mod import FLModHandler, JsonOnlyHandler
from .copy_mod import (
    CarraHandler,
    BankHandler,
    TextFileHandler,
    LCTAChangeHandler,
    FLChangeHandler,
)
from .font import FontHandler
from .bus_import import BusImportHandler
from .update import UpdatePackageHandler
from .invalid import InvalidHandler
from .fmod_dlls import FmodDllZipHandler

FULL = FullHandler()
NOFONT = NoFontHandler()
FLMOD = FLModHandler()
JSONONLY = JsonOnlyHandler()
UPDATE = UpdatePackageHandler()
CARRA = CarraHandler()
BANK = BankHandler()
FONT = FontHandler()
TEXT_FILE = TextFileHandler()
LCTA_CHANGE = LCTAChangeHandler()
FL_CHANGE = FLChangeHandler()
BUS_IMPORT = BusImportHandler()
INVALID = InvalidHandler()
FMOD_DLLS = FmodDllZipHandler()

HANDLERS = [
    FULL,
    NOFONT,
    FLMOD,
    JSONONLY,
    UPDATE,
    CARRA,
    BANK,
    FONT,
    TEXT_FILE,
    LCTA_CHANGE,
    FL_CHANGE,
    BUS_IMPORT,
    FMOD_DLLS,
    INVALID,
]

REGISTRY = DropFileHandlerRegistry(
    HANDLERS,
    detect_order={
        'zip': [FMOD_DLLS, FULL, NOFONT, FLMOD, UPDATE, JSONONLY],
        'folder': [FULL, NOFONT, FLMOD, JSONONLY],
        'json': [BUS_IMPORT, TEXT_FILE, LCTA_CHANGE, FL_CHANGE],
        'path': [CARRA, BANK, FONT],
    },
)
