"""
翻译引擎核心模块
提供翻译流水线的所有核心组件
"""

from .data_structures import (
    RequestConfig, PathConfig, FilePathConfig,
    MatcherData, ProcessExitType, ProcesserExit,
    EMPTY_DATA, EMPTY_DATA_LIST, EMPTY_TEXT, AVOID_PATH
)
from .matcher import SimpleMatcher, TextMatcher, MatcherOrganizer
from .builder import RequestTextBuilder, SimpleRequestTextBuilder
from .processor import FileProcessor

__all__ = [
    'RequestConfig', 'PathConfig', 'FilePathConfig',
    'MatcherData', 'ProcessExitType', 'ProcesserExit',
    'EMPTY_DATA', 'EMPTY_DATA_LIST', 'EMPTY_TEXT', 'AVOID_PATH',
    'SimpleMatcher', 'TextMatcher', 'MatcherOrganizer',
    'RequestTextBuilder', 'SimpleRequestTextBuilder',
    'FileProcessor',
]
