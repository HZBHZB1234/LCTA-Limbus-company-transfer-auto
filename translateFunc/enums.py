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


class FileType(Enum):
    """翻译文件类别 —— 驱动提示词模板选择。"""
    STORY = auto()   # StoryData/ 剧情文件
    SKILL = auto()   # Skills_* 技能文件
    UI    = auto()   # UI 文本文件
    OTHER = auto()   # 其他类型


class MatchConfidence(Enum):
    """专有名词匹配经 JP/EN 交叉验证后的置信度。"""
    HIGH        = auto()   # JP 和 EN 均与正向上下文匹配
    MEDIUM      = auto()   # 仅 JP 或仅 EN 匹配
    LOW         = auto()   # 弱匹配，可能不适用
    UNKNOWN     = auto()   # 术语无上下文数据，无法判断
    FALSE_MATCH = auto()   # 更接近负向上下文，判定为假阳性
