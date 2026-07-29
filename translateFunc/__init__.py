"""
translateFunc — LCTA 自动翻译模块。

公开 API:
    NativeTranslationPipeline — Rust 原生端到端编排桥接
    TranslateConfig      — 配置数据类
    ProcessResult        — 文件处理结果枚举
    PipelineSummary      — 聚合运行结果
    ProcessOutcome       — 单文件处理结果
"""

from translateFunc.config import TranslateConfig, PipelineSummary, ProcessOutcome
from translateFunc.enums import ProcessResult
from translateFunc.native_pipeline import NativeTranslationPipeline

__all__ = [
    "NativeTranslationPipeline",
    "TranslateConfig",
    "PipelineSummary",
    "ProcessOutcome",
    "ProcessResult",
]
