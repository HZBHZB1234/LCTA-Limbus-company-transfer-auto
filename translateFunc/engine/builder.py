"""
翻译请求构建器模块
RequestTextBuilder: 为LLM翻译器构建结构化的翻译请求
SimpleRequestTextBuilder: 为非LLM翻译器构建简单文本列表

增强改进：
- 独立的 _make_text 区块构建方法，便于调试和维护
- 翻译前状态快照记录
- 更好的文本分块策略日志
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from copy import deepcopy
from contextlib import suppress

from .data_structures import RequestConfig, EMPTY_TEXT
from .matcher import MatcherOrganizer

logger = logging.getLogger(__name__)


class RequestTextBuilder:
    """
    LLM翻译请求构建器
    构建包含元数据、参考信息（术语表/角色风格/技能指南）和文本块的统一请求结构
    """

    def __init__(
        self,
        request_text: Dict[str, Dict[str, Dict[Tuple, str]]],
        matcher: MatcherOrganizer,
        request_config: RequestConfig,
        formal: Dict[Tuple, str]
    ):
        self.en_text = request_text['en']
        self.kr_text = request_text['kr']
        self.jp_text = request_text['jp']
        self.matcher = matcher
        self.request_config = request_config
        self.formal = formal

        self.unified_request = None
        self.split_requests = []
        self._build_snapshot = None  # 构建快照，用于调试

    def build(self) -> Dict[str, Any]:
        """构建统一请求结构"""
        text_items = []
        all_proper_terms = {}
        all_affects = {}
        all_models = {}

        for idx in self.kr_text.keys():
            kr_item = self.kr_text.get(idx, {})
            en_item = self.en_text.get(idx, {})
            jp_item = self.jp_text.get(idx, {})

            kr_texts_item = list(kr_item.values())
            en_texts_item = list(en_item.values())
            jp_texts_item = list(jp_item.values())

            # 过滤空文本
            filtered_texts = []
            for i in range(len(jp_texts_item)):
                JP = jp_texts_item[i] if i < len(jp_texts_item) else ''
                EN = en_texts_item[i] if i < len(en_texts_item) else ''
                KR = kr_texts_item[i] if i < len(kr_texts_item) else ''
                if not (JP in EMPTY_TEXT and EN in EMPTY_TEXT and KR in EMPTY_TEXT):
                    filtered_texts.append({
                        'jp': JP, 'en': EN, 'kr': KR, 'index': i
                    })

            for i, text_info in enumerate(filtered_texts):
                text_block = {
                    'id': len(text_items) + 1,
                    'kr': text_info['kr'],
                    'en': text_info['en'],
                    'jp': text_info['jp']
                }

                # 专有名词匹配
                proper_matches = self.matcher.tMatcher.proper_matcher.match([text_info['kr']])[0]
                if proper_matches:
                    text_block['proper_refs'] = []
                    for match_idx in proper_matches:
                        term_info = self.matcher.mData.proper_data[match_idx]
                        term_refer = self.matcher.mData.proper_refer[match_idx]
                        text_block['proper_refs'].append(term_refer)
                        all_proper_terms[term_refer] = term_info

                # 状态效果匹配（技能文件）
                if self.request_config.is_skill:
                    affect_matches_id = self.matcher.tMatcher.affect_name_matcher.match([text_info['kr']])[0]
                    affect_matches_name = self.matcher.tMatcher.affect_id_matcher.match([text_info['kr']])[0]
                    affect_matches = affect_matches_id + affect_matches_name

                    if affect_matches:
                        text_block['affect_refs'] = []
                        for match_idx in affect_matches:
                            if match_idx < len(self.matcher.mData.affect_data):
                                affect_info = self.matcher.mData.affect_data[match_idx]
                                affect_refer = self.matcher.mData.affect_refer[match_idx]
                                if affect_refer:
                                    text_block['affect_refs'].append(affect_refer)
                                    all_affects[str(affect_refer)] = affect_info

                # 角色信息（故事文件）
                if self.request_config.is_story:
                    with suppress(Exception):
                        raw = self.formal.get(idx, {})
                        model = raw.get('model', '')
                        if model:
                            model_index = self.matcher.tMatcher.role_matcher.match_equal([model])
                            if model_index and model_index[0] != '':
                                idx_val = model_index[0]
                                if idx_val < len(self.matcher.mData.role_data):
                                    model_info = self.matcher.mData.role_data[idx_val]
                                    all_models[model] = model_info
                                    text_block['role_ref'] = model

                text_items.append(text_block)

        # 构建统一请求结构
        self.unified_request = {
            'metadata': {
                'total_text_blocks': len(text_items),
                'proper_terms_count': len(all_proper_terms),
                'affects_count': len(all_affects),
                'models_count': len(all_models)
            },
            'reference': {
                'proper_terms': list(all_proper_terms.values()) if all_proper_terms else [],
                'affects': list(all_affects.values()) if all_affects else [],
                'models': list(all_models.values()) if all_models else [],
                'model_docs': self._get_role_docs(all_models),
                'skill_doc': self._get_skill_doc()
            },
            'text_blocks': text_items
        }

        # 保存构建快照
        self._build_snapshot = {
            'text_blocks_count': len(text_items),
            'proper_terms': list(all_proper_terms.keys()),
            'total_text_length': len(json.dumps(self.unified_request, ensure_ascii=False)),
        }
        logger.debug(f"[RequestTextBuilder] 构建完成: {self._build_snapshot}")

        # 根据长度限制分割
        self._split_by_length()

        return self.unified_request

    def _split_by_length(self):
        """根据最大长度限制分割请求"""
        if self.unified_request is None:
            return

        max_length = self.request_config.max_length
        request_text = self._make_text(self.unified_request)

        if len(request_text) <= max_length:
            self.split_requests = [self.unified_request]
            return

        text_blocks = self.unified_request.get('text_blocks', [])
        total_blocks = len(text_blocks)

        for num_parts in range(2, min(10, total_blocks) + 1):
            part_size = total_blocks // num_parts
            remainder = total_blocks % num_parts

            parts = []
            start_idx = 0
            for i in range(num_parts):
                end_idx = start_idx + part_size + (1 if i < remainder else 0)
                part_text_blocks = text_blocks[start_idx:end_idx]

                part_request = {
                    'metadata': {
                        'total_text_blocks': len(part_text_blocks),
                        'proper_terms_count': len(self.unified_request['reference']['proper_terms']),
                        'affects_count': len(self.unified_request['reference']['affects']),
                        'models_count': len(self.unified_request['reference'].get('model_docs', []))
                    },
                    'reference': self.unified_request['reference'],
                    'text_blocks': part_text_blocks
                }
                parts.append(part_request)
                start_idx = end_idx

            all_valid = True
            for part in parts:
                if len(self._make_text(part)) > max_length:
                    all_valid = False
                    break

            if all_valid:
                logger.info(f"文本过长({len(request_text)}字符)，已分割成 {num_parts} 部分")
                self.split_requests = parts
                return

        # 强制分割
        logger.warning(f"文本过长({len(request_text)}字符)且无法合理分割，强制分5部分")
        parts = []
        part_size = max(1, total_blocks // 5)
        for i in range(0, total_blocks, part_size):
            end_idx = min(i + part_size, total_blocks)
            part_request = {
                'metadata': {
                    'total_text_blocks': end_idx - i,
                    'proper_terms_count': len(self.unified_request['reference']['proper_terms']),
                    'affects_count': len(self.unified_request['reference']['affects']),
                    'models_count': len(self.unified_request['reference'].get('model_docs', []))
                },
                'reference': self.unified_request['reference'],
                'text_blocks': text_blocks[i:end_idx]
            }
            parts.append(part_request)
        self.split_requests = parts

    def get_request_text(self, is_text_format: Optional[bool] = None) -> List[str]:
        """获取分割后的请求文本列表"""
        if self.unified_request is None:
            self.build()

        fmt = is_text_format if is_text_format is not None else self.request_config.is_text_format

        result = []
        for request in self.split_requests:
            if fmt:
                result.append(self._make_text(request))
            else:
                result.append(json.dumps(request, indent=2, ensure_ascii=False))
        return result

    def deBuild(self, translated_texts: List[str]) -> Dict[str, Dict[Tuple, str]]:
        """将翻译后的文本列表还原为原始结构"""
        translated_iter = iter(translated_texts)
        result_dict = deepcopy(self.kr_text)

        for idx in result_dict.keys():
            kr_item = self.kr_text.get(idx, {})
            en_item = self.en_text.get(idx, {})
            jp_item = self.jp_text.get(idx, {})
            kr_paths = list(kr_item.keys())

            for i in kr_paths:
                JP = jp_item.get(i, '')
                EN = en_item.get(i, '')
                KR = kr_item.get(i, '')
                if not (JP in EMPTY_TEXT and EN in EMPTY_TEXT and KR in EMPTY_TEXT):
                    result_dict[idx][i] = next(translated_iter)

        try:
            next(translated_iter)
            logger.warning("警告：翻译文本数量多于预期")
        except StopIteration:
            pass

        return result_dict

    # ========== 文本格式化 ==========

    def _make_text(self, texts: Dict[str, Any]) -> str:
        """将统一请求结构转换为纯文本（供LLM阅读）"""
        sections = [
            self._build_metadata_section(texts),
            self._build_reference_section(texts),
            self._build_text_blocks_section(texts),
            self._build_footer()
        ]
        return "\n".join(sections)

    def _build_metadata_section(self, texts: Dict) -> str:
        """构建元数据区块"""
        metadata = texts.get('metadata', {})
        lines = ["【翻译请求元数据】"]
        lines.append(f"文本块总数: {metadata.get('total_text_blocks', 0)}")
        lines.append(f"专有名词数: {metadata.get('proper_terms_count', 0)}")
        if self.request_config.is_skill:
            lines.append(f"状态效果数: {metadata.get('affects_count', 0)}")
        if self.request_config.is_story:
            lines.append(f"角色信息数: {metadata.get('models_count', 0)}")
        return "\n".join(lines)

    def _build_reference_section(self, texts: Dict) -> str:
        """构建参考信息区块"""
        reference = texts.get('reference', {})
        lines = []

        # 专有名词术语表
        if reference.get('proper_terms'):
            lines.append("\n【专有名词术语表】")
            for i, item in enumerate(reference['proper_terms']):
                term = self._escape(item.get('term', ''))
                trans = self._escape(item.get('translation', ''))
                note = self._escape(item.get('note', ''))
                line = f"{i+1}. {term} → {trans}"
                if note:
                    line += f" (备注: {note})"
                lines.append(line)

        # 状态效果术语表
        if reference.get('affects'):
            lines.append("\n【状态效果术语表】")
            for i, item in enumerate(reference['affects']):
                lines.append(
                    f"{i+1}. [ID: {item.get('id', '')}] "
                    f"{self._escape(item.get('kr', '获取失败'))} → "
                    f"{self._escape(item.get('cn', '获取失败'))}"
                )

        # 角色信息表
        if reference.get('models'):
            lines.append("\n【角色信息表】")
            for i, item in enumerate(reference['models']):
                lines.append(
                    f"{i+1}. {self._escape(item.get('kr', '获取失败'))}"
                    f" / {self._escape(item.get('cn', '获取失败'))}"
                    f" 描述: {self._escape(item.get('nickName', '获取失败'))}"
                )

        # 角色说话风格
        if self.request_config.is_story and reference.get('model_docs'):
            lines.append("\n【角色说话风格参考】")
            for doc in reference['model_docs']:
                for k, v in doc.items():
                    lines.append(f"  {k}: {v}")

        # 技能翻译指南
        if self.request_config.is_skill and reference.get('skill_doc'):
            lines.append("\n【技能翻译指南】")
            lines.append(reference['skill_doc'])

        return "\n".join(lines)

    def _build_text_blocks_section(self, texts: Dict) -> str:
        """构建翻译文本块区块"""
        lines = []
        lines.append("\n" + "=" * 30)
        lines.append("【以下为需要翻译的文本块】")
        lines.append("=" * 30)

        text_blocks = texts.get('text_blocks', [])
        for idx, block in enumerate(text_blocks):
            if idx > 0:
                lines.append("\n" + "-" * 20 + "\n")

            lines.append(f"【文本块 {idx+1}】")
            lines.append(f"  韩文 (KR): {self._escape(block.get('kr', ''))}")
            lines.append(f"  英文 (EN): {self._escape(block.get('en', ''))}")
            lines.append(f"  日文 (JP): {self._escape(block.get('jp', ''))}")

            if 'proper_refs' in block and block['proper_refs']:
                lines.append(f"  引用术语: {', '.join(block['proper_refs'])}")
            if 'affect_refs' in block and block['affect_refs']:
                lines.append(f"  引用状态效果: {', '.join(str(r) for r in block['affect_refs'])}")
            if 'role_ref' in block:
                lines.append(f"  说话者: {block['role_ref']}")

            lines.append(f"【文本块 {idx+1} 结束】")

        return "\n".join(lines)

    def _build_footer(self) -> str:
        """构建结束标记"""
        return "\n" + "*" * 80 + "\n【所有文本块已列出，请开始翻译】\n【翻译时请参考上方的术语表和指南】"

    def _escape(self, text: str) -> str:
        """转义文本中的特殊字符"""
        if not isinstance(text, str):
            return str(text)
        return text.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')

    def _get_role_docs(self, role_list: Dict[str, dict]) -> List[dict]:
        """获取角色说话风格参考文档"""
        if not self.request_config.is_story or not role_list:
            return []

        from translateFunc.prompts.role_styles import ROLE_STYLE, RLOE_COMPARE

        role_docs = []
        for role_id in role_list.keys():
            with suppress(Exception):
                true_role = RLOE_COMPARE.get(role_id)
                if true_role and true_role in ROLE_STYLE:
                    role_docs.append(ROLE_STYLE[true_role])
        return role_docs

    def _get_skill_doc(self) -> str:
        """获取技能翻译指南"""
        if self.request_config.is_skill:
            from translateFunc.prompts.skill_doc import SKILLL_DOC
            return SKILLL_DOC
        return ""


class SimpleRequestTextBuilder:
    """非LLM翻译器的简单请求构建器，直接返回文本列表"""

    def __init__(self, request_text: Dict[str, Dict[str, Dict[Tuple, str]]]):
        self.en_texts = request_text['en']
        self.kr_texts = request_text['kr']
        self.jp_texts = request_text['jp']
        self.KR_build = []
        self.EN_build = []
        self.JP_build = []

    def build(self) -> List:
        """提取需要翻译的文本"""
        EN_result, KR_result, JP_result = [], [], []

        for idx in self.kr_texts.keys():
            kr_item = self.kr_texts.get(idx, {})
            jp_item = self.jp_texts.get(idx, {})
            en_item = self.en_texts.get(idx, {})
            for text in kr_item.values():
                KR_result.append(text)
            for text in jp_item.values():
                JP_result.append(text)
            for text in en_item.values():
                EN_result.append(text)

        # 标记空文本索引
        empty_texts = []
        for index, (KR, EN, JP) in enumerate(zip(KR_result, EN_result, JP_result)):
            if KR in EMPTY_TEXT and EN in EMPTY_TEXT and JP in EMPTY_TEXT:
                empty_texts.append(index)

        self.KR_build = [t for idx, t in enumerate(KR_result) if idx not in empty_texts]
        self.EN_build = [t for idx, t in enumerate(EN_result) if idx not in empty_texts]
        self.JP_build = [t for idx, t in enumerate(JP_result) if idx not in empty_texts]

    def get_request_text(self, from_lang: str = 'KR') -> List[str]:
        """获取指定语言的文本列表"""
        return getattr(self, f"{from_lang}_build", [])

    def deBuild(self, translated_texts: List[str], from_lang: str = 'kr') -> Dict[str, Dict[Tuple, str]]:
        """还原翻译结果"""
        original_texts = deepcopy(getattr(self, f"{from_lang}_texts"))
        translated_iter = iter(translated_texts)

        for idx in original_texts.keys():
            kr_item = self.kr_texts.get(idx, {})
            en_item = self.en_texts.get(idx, {})
            jp_item = self.jp_texts.get(idx, {})
            kr_paths = list(kr_item.keys())

            for i in kr_paths:
                JP = jp_item.get(i, '')
                EN = en_item.get(i, '')
                KR = kr_item.get(i, '')
                if not (JP in EMPTY_TEXT and EN in EMPTY_TEXT and KR in EMPTY_TEXT):
                    original_texts[idx][i] = next(translated_iter)

        try:
            next(translated_iter)
            logger.warning("警告：翻译文本数量多于预期")
        except StopIteration:
            pass

        return original_texts
