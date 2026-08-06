"""
webutils/llm_fancy/splitter.py
将候选文本按估算长度打包分割为 LLM 请求批次。
"""

from __future__ import annotations

from typing import Iterable, TypeVar

T = TypeVar("T")

# 单个候选中 id/text 包装、换行与缩进的估算开销
_PER_ITEM_OVERHEAD = 64


def estimate_item_size(value: str) -> int:
    """估算单个文本在请求 JSON 中的渲染长度。"""
    return len(value) + _PER_ITEM_OVERHEAD


def split_items(items: Iterable[T], size_of, max_length: int) -> list[list[T]]:
    """按累计估算长度将 items 贪心分批。

    单个元素超过 max_length 时单独成批，保证每批请求长度不超限。
    """
    batches: list[list[T]] = []
    current: list[T] = []
    current_size = 0
    for item in items:
        size = size_of(item)
        if current and current_size + size > max_length:
            batches.append(current)
            current = []
            current_size = 0
        current.append(item)
        current_size += size
    if current:
        batches.append(current)
    return batches
