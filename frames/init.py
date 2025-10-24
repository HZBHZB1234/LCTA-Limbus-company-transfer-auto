# 框架包初始化文件
from .frame_translate import TranslateFrame
from .frame_install import InstallFrame
from .frame_ourplay import OurPlayFrame
from .frame_clean import CleanFrame
from .frame_llc import LLCFrame
from .frame_config import ConfigFrame
from .frame_search import SearchFrame
from .frame_backup import BackupFrame
from .frame_assets import AssetsFrame

__all__ = [
    'TranslateFrame',
    'InstallFrame', 
    'OurPlayFrame',
    'CleanFrame',
    'LLCFrame',
    'ConfigFrame',
    'SearchFrame',
    'BackupFrame',
    'AssetsFrame'
]