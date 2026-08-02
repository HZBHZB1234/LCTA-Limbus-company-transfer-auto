from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZipFormatInspection:
    """zip 文件格式判断所需的只读信息。"""

    names: tuple[str, ...]
    non_json_names: tuple[str, ...]

    @property
    def amount(self) -> int:
        return len(self.names)

    @property
    def non_json_amount(self) -> int:
        return len(self.non_json_names)

    @property
    def has_font(self) -> bool:
        return any('Font' in name for name in self.non_json_names)


@dataclass(frozen=True)
class FolderFormatInspection:
    """目录格式判断所需的只读信息。"""

    path: str
    items: tuple[str, ...]


@dataclass(frozen=True)
class JsonFormatInspection:
    """JSON 格式判断所需的只读信息。"""

    data: object
