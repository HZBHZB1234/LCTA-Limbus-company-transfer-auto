"""
translateFunc — LCTA 自动翻译模块。

公开 API:
    NativeTranslationPipeline — Rust 原生端到端编排桥接
    TranslationPipeline  — 旧测试与诊断工具的懒加载兼容入口
    TranslateConfig      — 配置数据类
    ProcessResult        — 文件处理结果枚举
    FileType             — 文件类别枚举
    MatchConfidence      — 专有名词匹配置信度枚举
    PipelineSummary      — 聚合运行结果
    ProcessOutcome       — 单文件处理结果
"""

from translateFunc.config import TranslateConfig, PipelineSummary, ProcessOutcome
from translateFunc.enums import ProcessResult, FileType, MatchConfidence
from translateFunc.native_pipeline import NativeTranslationPipeline

__all__ = [
    "NativeTranslationPipeline",
    "TranslationPipeline",
    "TranslateConfig",
    "PipelineSummary",
    "ProcessOutcome",
    "ProcessResult",
    "FileType",
    "MatchConfidence",
]


def __getattr__(name):
    if name == "TranslationPipeline":
        from translateFunc.pipeline import TranslationPipeline

        return TranslationPipeline
    raise AttributeError(name)
