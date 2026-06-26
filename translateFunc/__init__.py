"""
translateFunc — LCTA 自动翻译模块。

公开 API:
    TranslationPipeline  — 端到端编排
    TranslateConfig      — 配置数据类
    ProcessResult        — 文件处理结果枚举
    FileType             — 文件类别枚举
    MatchConfidence      — 专有名词匹配置信度枚举
    PipelineSummary      — 聚合运行结果
    ProcessOutcome       — 单文件处理结果
"""

from translateFunc.pipeline import TranslationPipeline
from translateFunc.config import TranslateConfig, PipelineSummary, ProcessOutcome
from translateFunc.enums import ProcessResult, FileType, MatchConfidence

__all__ = [
    "TranslationPipeline",
    "TranslateConfig",
    "PipelineSummary",
    "ProcessOutcome",
    "ProcessResult",
    "FileType",
    "MatchConfidence",
]
