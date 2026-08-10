"""
webutils/llm_fancy/splitter.py
将候选文本按估算长度打包分割为 LLM 请求批次。
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional, TypeVar

T = TypeVar("T")

# 单个候选中 id/text 包装、换行与缩进的估算开销
_PER_ITEM_OVERHEAD = 64

# 单条目请求 JSON 的固定包装开销：{"items": [{"id": N, "text": "..."}]}
_JSON_WRAPPER_OVERHEAD = 34

# 批次外层固定包装开销（不含条目本身）：{"items": [ ... ]}
_BATCH_WRAPPER_OVERHEAD = 13

# 切分超长文本时优先寻找的自然边界字符
_NATURAL_BOUNDARIES = ("\n", "。", "！", "？", "!", "?", ".", "；", ";", "，", ",", " ")


def estimate_item_size(value: str) -> int:
    """估算单个文本在请求 JSON 中的渲染长度。"""
    return len(value) + _PER_ITEM_OVERHEAD


def split_text(value: str, max_length: int) -> list[str]:
    """将超长文本切分为多个片段，保证每段长度不超过 max_length。

    优先在换行、句末标点、逗号等自然边界处断开，边界字符保留在片段末尾，
    按序拼接可还原原文；无可用边界时按字符硬切。max_length 需 >= 1。
    """
    if len(value) <= max_length:
        return [value]
    chunks: list[str] = []
    start = 0
    total = len(value)
    while total - start > max_length:
        limit = start + max_length
        cut = -1
        for boundary in _NATURAL_BOUNDARIES:
            index = value.rfind(boundary, start, limit)
            if index > cut:
                cut = index
        if cut < start:
            cut = limit - 1
        chunks.append(value[start:cut + 1])
        start = cut + 1
    chunks.append(value[start:])
    return chunks


def split_items(
    items: Iterable[T],
    size_of: Callable[[T], int],
    max_length: int,
    *,
    splitter: Optional[Callable[[T, int], list[T]]] = None,
    batch_overhead: int = 0,
) -> list[list[T]]:
    """按累计估算长度将 items 贪心分批。

    单个元素超过 max_length 时单独成批；若提供 splitter，超限元素会被
    切分为多个子元素（每个子元素独立成批），保证每批请求长度不超限。
    batch_overhead 为批次外层固定包装开销（如 {"items": [...]}），计入分批判断。
    """
    batches: list[list[T]] = []
    current: list[T] = []
    current_size = 0
    for item in items:
        size = size_of(item)
        if current and current_size + size + batch_overhead > max_length:
            batches.append(current)
            current = []
            current_size = 0
        if size + batch_overhead > max_length:
            if splitter is not None:
                batches.extend([sub] for sub in splitter(item, max_length))
                continue
        current.append(item)
        current_size += size
    if current:
        batches.append(current)
    return batches
