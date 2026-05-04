"""
LLM提示词模块
提供翻译系统提示词、技能翻译指南、角色说话风格参考
"""

from .system_prompts import JSON_SYSTEM_PROMPT, TEXT_SYSTEM_PROMPT
from .skill_doc import SKILLL_DOC
from .role_styles import ROLE_STYLE, RLOE_COMPARE

__all__ = [
    'JSON_SYSTEM_PROMPT', 'TEXT_SYSTEM_PROMPT',
    'SKILLL_DOC', 'ROLE_STYLE', 'RLOE_COMPARE',
]
