from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from typing import Any, ClassVar
from collections.abc import Iterable

from globalManagers.LogManager import LogManager
from .context import FileExecutionContext

_log_manager = LogManager()


def remove_existing(path: str | os.PathLike[str]) -> None:
    """删除已存在的目标文件/文件夹（遵循项目惯例）"""
    if os.path.exists(path):
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


class DropFileHandler(ABC):
    """拖放文件分支处理器接口：检测 + 执行 + 显示名收敛于单类。"""

    #: 本类对应的类型字符串，如 'full'
    file_type: ClassVar[str]
    #: 确认弹窗 / 日志中的显示名
    label: ClassVar[str]
    #: 执行日志中使用的动作名（如 '模组'）；未定义时回退到 label
    action_label: ClassVar[str] = ''

    @property
    def action_name(self) -> str:
        return self.action_label or self.label

    @property
    def progress_label(self) -> str:
        return f"安装{self.action_name}"

    @abstractmethod
    def detect(self, item: Any) -> str | None:
        """判断 item（容器快照或原始路径）是否属于本分支；命中返回类型字符串，否则 None。"""

    @abstractmethod
    def execute(self, context: FileExecutionContext) -> str:
        """执行安装/处理，返回结果键（installed/modded/updated/imported/skipped）。"""

    def update_progress(self, context: FileExecutionContext) -> None:
        _log_manager.update_modal_progress(
            context.progress_pct,
            f"{self.progress_label} ({context.index + 1}/{context.total}): {context.file_name}",
            context.modal_id,
        )


class DropFileHandlerRegistry:
    """按容器类型分组的有序处理器注册表。"""

    def __init__(self, handlers: Iterable[DropFileHandler],
                 detect_order: dict[str, list[DropFileHandler]]):
        self._handlers = list(handlers)
        self._detect_order = detect_order
        self._by_type = {handler.file_type: handler for handler in self._handlers}

    def detect(self, kind: str, item: Any) -> str:
        """按容器类型对应的注册顺序执行检测，无命中时兜底为 'invalid'。"""
        for handler in self._detect_order.get(kind, ()):
            result = handler.detect(item)
            if result is not None:
                return result
        return 'invalid'

    def handler_for(self, file_type: str) -> DropFileHandler | None:
        return self._by_type.get(file_type)

    def labels(self) -> dict[str, str]:
        """类型字符串 → 显示名映射（供确认弹窗使用）。"""
        return {handler.file_type: handler.label for handler in self._handlers}
