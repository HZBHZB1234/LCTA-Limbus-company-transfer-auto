'''
通用单例化路径管理。编写代码时应该添加需要的路径到这个类里。
'''


import os
import sys
from typing import Optional
from pathlib import Path

class PathManager:
    def __init__(self):
        self.work_path = Path(os.getcwd())
        self.code_path = Path(__file__).parent.parent
        self.game_path: Optional[Path] = None

pathManager = PathManager()