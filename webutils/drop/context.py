from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class FileExecutionContext:
    """单个拖放文件的执行上下文。"""

    file_path: str
    file_type: str
    modal_id: str
    index: int
    total: int
    game_path: str
    mod_path: str

    @property
    def file_name(self) -> str:
        return Path(self.file_path).name

    @property
    def progress_pct(self) -> int:
        return int((self.index / self.total) * 100)
