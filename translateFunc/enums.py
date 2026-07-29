"""
translateFunc/enums.py
控制流枚举 —— 替代基于异常的控制流和魔术字符串。
"""
from enum import Enum, auto


class ProcessResult(Enum):
    """单个文件的处理结果。"""
    SUCCESS_SAVED        = auto()   # 翻译成功并保存
    ALREADY_TRANSLATED   = auto()   # 已翻译，跳过
    EMPTY_WITH_LLC       = auto()   # 空文件，已复制现有 LLC
    EMPTY_SKIPPED        = auto()   # 空文件，无 LLC 可复制
    JSON_DECODE_ERROR    = auto()   # JSON 解析失败
    SAVE_ERROR           = auto()   # 保存失败
    TRANSLATION_MISMATCH = auto()   # 翻译结果数量与输入数量不匹配
    FALLBACK_TO_ORIGINAL = auto()   # 全部格式解析失败，回退保存为 KR 原文
