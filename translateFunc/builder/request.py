"""
translateFunc/builder/request.py
RequestBuilder —— 从扁平化文本数据构建结构化翻译请求。
"""
from __future__ import annotations
from contextlib import suppress
from copy import deepcopy
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

from translateFunc.enums import FileType
from translateFunc.matcher.engine import MatcherEngine
import translateFunc.translate_doc as translate_doc

EMPTY_TEXT = {'', '-'}
AVOID_PATH = {'usage', 'id', 'model'}


class RequestBuilder:
    """构建附带匹配元数据的结构化翻译请求。"""

    def __init__(
        self,
        request_text: dict,
        matcher_engine: MatcherEngine,
        is_story: bool = False,
        is_skill: bool = False,
        is_text_format: bool = False,
        max_length: int = 20000,
        file_type: FileType = FileType.OTHER,
    ):
        self.kr_text = request_text["kr"]
        self.jp_text = request_text.get("jp", {})
        self.en_text = request_text.get("en", {})
        self._engine = matcher_engine
        self.is_story = is_story
        self.is_skill = is_skill
        self.is_text_format = is_text_format
        self.max_length = max_length
        self.file_type = file_type
        # 构建状态
        self.unified_request: dict | None = None
        self.split_requests: list[dict] = []

    # ========== 构建 ==========

    def build(self, prompt_format: str = "xml_json") -> dict:
        """构建统一请求结构。prompt_format 用于长度估算。

        Args:
            prompt_format: "xml_json" | "xml_xml" | "json_json"
        """
        text_items: list[dict] = []
        all_proper_terms: dict[str, dict] = {}
        all_affects: dict[str, dict] = {}
        all_models: dict[str, dict] = {}

        for idx in self.kr_text:
            kr_item = self.kr_text.get(idx, {})
            jp_item = self.jp_text.get(idx, {})
            en_item = self.en_text.get(idx, {})

            kr_paths = list(kr_item.keys())
            for path_tuple in kr_paths:
                kr_text_val = kr_item.get(path_tuple, "")
                jp_text_val = jp_item.get(path_tuple, "")
                en_text_val = en_item.get(path_tuple, "")

                if kr_text_val in EMPTY_TEXT and jp_text_val in EMPTY_TEXT and en_text_val in EMPTY_TEXT:
                    continue

                text_block: dict[str, Any] = {
                    "kr": kr_text_val,
                    "jp": jp_text_val,
                    "en": en_text_val,
                }

                # 匹配专有名词
                match_result = self._engine.match_all(kr_text_val)
                if match_result.proper_matches:
                    text_block["proper_refs"] = []
                    for m in match_result.proper_matches:
                        if m.data:
                            term_data = m.data if isinstance(m.data, dict) else {"term": m.pattern}
                            term_key = term_data.get("term", m.pattern)
                            if term_key not in all_proper_terms:
                                all_proper_terms[term_key] = term_data
                            text_block["proper_refs"].append(term_key)
                        else:
                            if m.pattern not in all_proper_terms:
                                all_proper_terms[m.pattern] = {"term": m.pattern, "translation": ""}
                            text_block["proper_refs"].append(m.pattern)

                # 匹配状态效果
                affect_matches = match_result.affect_id_matches + match_result.affect_name_matches
                if affect_matches:
                    text_block["affect_refs"] = []
                    seen_affects: set[str] = set()
                    for m in affect_matches:
                        if m.data and isinstance(m.data, dict):
                            aff_id = m.data.get("id", "")
                            if aff_id not in seen_affects:
                                seen_affects.add(aff_id)
                                text_block["affect_refs"].append(f'[{aff_id}]')
                                if aff_id not in all_affects:
                                    all_affects[aff_id] = m.data

                # 匹配角色（仅剧情文件）
                if self.is_story:
                    with suppress(Exception):
                        model = kr_text_val.get("model", "") if isinstance(kr_text_val, dict) else ""
                        if not model:
                            # 尝试从引擎匹配角色
                            for rm in match_result.role_matches:
                                model = rm.pattern
                                break
                        if model:
                            model_idx = None
                            for i, rd in enumerate(self._engine.role_data):
                                if rd.get("id") == model:
                                    model_idx = i
                                    break
                            if model_idx is not None:
                                model_info = self._engine.role_data[model_idx]
                                all_models[model] = model_info
                                text_block["model"] = model

                text_items.append(text_block)

        # 构建统一请求
        self.unified_request = {
            "metadata": {
                "total_text_blocks": len(text_items),
                "proper_terms_count": len(all_proper_terms),
                "affects_count": len(all_affects),
                "models_count": len(all_models),
                "file_type": self.file_type.name,
            },
            "reference": {
                "proper_terms": list(all_proper_terms.values()),
                "affects": list(all_affects.values()),
                "models": list(all_models.values()),
                "model_docs": self._get_role_docs(all_models),
                "skill_doc": self._get_skill_doc(),
            },
            "text_blocks": text_items,
        }

        self._split_by_length(prompt_format)
        return self.unified_request

    # ========== 分割 ==========

    def _split_by_length(self, prompt_format: str = "xml_json") -> None:
        """将请求按 max_length 分割，使用格式感知长度估算。

        对三种格式均取 max 估算，确保无论后续回退到何种格式都不超限。
        """
        if self.unified_request is None:
            return

        all_formats = ["xml_json", "xml_xml", "json_json"]

        def estimate(request_dict, fmt: str) -> int:
            return len(self._get_request_text(request_dict, fmt))

        # 不分割检查：对三种格式均验证不超限，确保后续格式回退安全
        if all(estimate(self.unified_request, fmt) <= self.max_length for fmt in all_formats):
            self.split_requests = [self.unified_request]
            return

        text_blocks = self.unified_request.get("text_blocks", [])
        total_blocks = len(text_blocks)

        # 尝试 2..min(10, total_blocks) 份分割
        for num_parts in range(2, min(10, total_blocks) + 1):
            part_size = total_blocks // num_parts
            remainder = total_blocks % num_parts
            parts = []
            start_idx = 0
            for i in range(num_parts):
                end_idx = start_idx + part_size + (1 if i < remainder else 0)
                part = {
                    "metadata": {**self.unified_request["metadata"],
                                 "total_text_blocks": end_idx - start_idx},
                    "reference": self.unified_request["reference"],
                    "text_blocks": text_blocks[start_idx:end_idx],
                }
                parts.append(part)
                start_idx = end_idx

            # 每个 part 对三种格式均不超限
            if all(estimate(p, fmt) <= self.max_length
                   for p in parts for fmt in all_formats):
                self.split_requests = parts
                return

        # 回退：固定按 5 份分割
        parts = []
        part_size = max(1, total_blocks // 5)
        for i in range(0, total_blocks, part_size):
            end_idx = min(i + part_size, total_blocks)
            parts.append({
                "metadata": {**self.unified_request["metadata"],
                             "total_text_blocks": end_idx - i},
                "reference": self.unified_request["reference"],
                "text_blocks": text_blocks[i:end_idx],
            })
        self.split_requests = parts

        # 回退后校验：检查各 part 是否仍超限，记录警告
        over_limit_parts = []
        for idx, p in enumerate(self.split_requests):
            max_est = max(estimate(p, fmt) for fmt in all_formats)
            if max_est > self.max_length:
                over_limit_parts.append((idx, max_est))
        if over_limit_parts:
            details = "; ".join(f"part[{i}]={v}" for i, v in over_limit_parts)
            logger.warning(
                "回退分割后仍有 %d/%d 个 part 超限 (limit=%d): %s",
                len(over_limit_parts), len(self.split_requests),
                self.max_length, details,
            )

    # ========== 输出 ==========

    def get_request_text(self, prompt_format: str = "xml_json") -> list[str]:
        """获取所有分割后的请求文本（按格式渲染）。

        Args:
            prompt_format: "xml_json" | "xml_xml" | "json_json"
        """
        if self.unified_request is None:
            self.build()

        result = []
        for request in self.split_requests:
            if prompt_format in ("xml_json", "xml_xml"):
                result.append(self._make_xml_user_prompt(request))
            elif prompt_format == "json_json":
                result.append(self._make_json_user_prompt(request))
            else:
                # 未知格式回退到 JSON
                result.append(json.dumps(request, indent=2, ensure_ascii=False))
        return result

    def _get_request_text(self, request_data: dict, prompt_format: str = "xml_json") -> str:
        """获取请求文本用于长度检查。"""
        if prompt_format in ("xml_json", "xml_xml"):
            return self._make_xml_user_prompt(request_data)
        elif prompt_format == "json_json":
            return self._make_json_user_prompt(request_data)
        import json as _json
        return _json.dumps(request_data, indent=2, ensure_ascii=False)

    # ========== 还原 ==========

    def deBuild(self, translated_texts: list[str]) -> dict:
        """将扁平翻译文本列表还原为嵌套字典结构。"""
        translated_iter = iter(translated_texts)
        result_dict = deepcopy(self.kr_text)

        for idx in result_dict:
            kr_item = self.kr_text.get(idx, {})
            jp_item = self.jp_text.get(idx, {})
            en_item = self.en_text.get(idx, {})
            kr_paths = list(kr_item.keys())

            for path_tuple in kr_paths:
                jp_val = jp_item.get(path_tuple, "")
                en_val = en_item.get(path_tuple, "")
                kr_val = kr_item.get(path_tuple, "")
                if not (jp_val in EMPTY_TEXT and en_val in EMPTY_TEXT and kr_val in EMPTY_TEXT):
                    result_dict[idx][path_tuple] = next(translated_iter)

        # 验证没有多余的翻译结果
        has_extra = False
        try:
            next(translated_iter)
            has_extra = True
        except StopIteration:
            pass
        if has_extra:
            raise ValueError("翻译文本数量多于预期")

        return result_dict

    # ========== 辅助方法 ==========

    def _get_role_docs(self, role_list: dict) -> list[dict]:
        """获取角色说话风格参考。"""
        if not self.is_story:
            return []
        docs = []
        for role_id in role_list:
            with suppress(Exception):
                if role_id in translate_doc.RLOE_COMPARE:
                    true_role = translate_doc.RLOE_COMPARE[role_id]
                    docs.append(translate_doc.ROLE_STYLE[true_role])
        return docs

    def _get_skill_doc(self) -> str:
        """获取技能翻译指南。"""
        if self.is_skill:
            return translate_doc.SKILLL_DOC
        return ""

    def _escape_text(self, text: str) -> str:
        """转义特殊字符以便 LLM 理解。"""
        if not isinstance(text, str):
            return text
        escape_map = {
            "\n": "\\n", "\t": "\\t", "\r": "\\r",
            "\"": '\\"', "\'": "\\'", "\\": "\\\\",
            "---": "\\-\\-\\-",
        }
        result = text
        for old, new in escape_map.items():
            result = result.replace(old, new)
        return result

    def _make_text(self, texts: dict) -> str:
        """将统一请求字典转换为纯文本格式。"""
        result_lines = []

        metadata = texts.get("metadata", {})
        result_lines.append("【翻译请求元数据】")
        result_lines.append(f"文本块总数: {metadata.get('total_text_blocks', 0)}")

        reference = texts.get("reference", {})

        if reference.get("proper_terms"):
            result_lines.append("\n【专有名词术语表】")
            for i, item in enumerate(reference["proper_terms"]):
                note = f" (备注: {item.get('note')})" if item.get("note") else ""
                result_lines.append(
                    f"{i + 1}. {item.get('term', '')} → {item.get('translation', '')}{note}"
                )

        if reference.get("affects"):
            result_lines.append("\n【状态效果术语表】")
            for i, item in enumerate(reference["affects"]):
                result_lines.append(
                    f"{i + 1}. [ID: {item.get('id', '')}] {item.get('kr', '')} → {item.get('cn', '')}"
                )

        if self.is_story and reference.get("model_docs"):
            result_lines.append("\n【角色说话风格参考】")
            for doc in reference["model_docs"]:
                for k, v in doc.items():
                    result_lines.append(f"  {k}: {v}")

        if self.is_skill and reference.get("skill_doc"):
            result_lines.append("\n【技能翻译指南】")
            result_lines.append(reference["skill_doc"])

        result_lines.append("\n" + "=" * 30)
        result_lines.append("【以下为需要翻译的文本块】")

        text_blocks = texts.get("text_blocks", [])
        for idx, block in enumerate(text_blocks):
            if idx > 0:
                result_lines.append("\n" + "-" * 20)
            result_lines.append(f"\n【文本块 {idx + 1}】")
            result_lines.append(f"韩文: {self._escape_text(block.get('kr', ''))}")
            result_lines.append(f"英文: {self._escape_text(block.get('en', ''))}")
            result_lines.append(f"日文: {self._escape_text(block.get('jp', ''))}")

        return "\n".join(result_lines)

    def _make_xml_user_prompt(self, request_data: dict) -> str:
        """将统一请求字典转换为 XML 格式的 user prompt。"""
        from translateFunc.builder.prompt import PromptFactory
        pf = PromptFactory()

        reference = request_data.get("reference", {})
        text_blocks = request_data.get("text_blocks", [])

        parts: list[str] = []

        # Glossary（专有名词）
        if reference.get("proper_terms"):
            parts.append(pf.render_glossary(reference["proper_terms"]))

        # Affects（状态效果）
        if reference.get("affects"):
            parts.append(self._render_affects_xml(reference["affects"]))

        # 角色风格参考
        if self.is_story and reference.get("model_docs"):
            for doc in reference["model_docs"]:
                parts.append(pf._render_role_styles([doc]))

        # 技能指南
        if self.is_skill and reference.get("skill_doc"):
            parts.append(f"<skill_guide>\n{reference['skill_doc']}\n</skill_guide>\n")

        # 文本块
        parts.append(pf.render_text_blocks(text_blocks))

        return "\n".join(parts)

    def _render_affects_xml(self, affects: list[dict]) -> str:
        """渲染 affects 为 XML。"""
        if not affects:
            return ""
        lines = ["<affects>"]
        for a in affects:
            lines.append(f"  <affect id=\"{a.get('id', '')}\" kr=\"{a.get('kr', '')}\" cn=\"{a.get('cn', '')}\" />")
        lines.append("</affects>")
        return "\n".join(lines) + "\n"

    def _make_json_user_prompt(self, request_data: dict) -> str:
        """将统一请求字典转换为 JSON 格式的 user prompt。"""
        import json as _json

        reference = request_data.get("reference", {})
        text_blocks = request_data.get("text_blocks", [])

        output: dict = {}

        # Glossary
        proper_terms = reference.get("proper_terms", [])
        if proper_terms:
            glossary = []
            for t in proper_terms:
                kr = t.get("kr", t.get("term", ""))
                cn = t.get("cn", t.get("translation", ""))
                note = t.get("note", "")
                entry = {"kr": kr, "cn": cn}
                if note:
                    entry["note"] = note
                glossary.append(entry)
            output["glossary"] = glossary

        # Affects
        if reference.get("affects"):
            output["affects"] = reference["affects"]

        # 角色风格
        if self.is_story and reference.get("model_docs"):
            output["role_styles"] = reference["model_docs"]

        # 技能指南
        if self.is_skill and reference.get("skill_doc"):
            output["skill_doc"] = reference["skill_doc"]

        # 文本块
        items = []
        for i, block in enumerate(text_blocks):
            item: dict = {"id": i + 1, "kr": block.get("kr", "")}
            if block.get("jp"):
                item["jp"] = block["jp"]
            if block.get("en"):
                item["en"] = block["en"]
            # Per-block 引用字段
            if block.get("proper_refs"):
                item["proper_refs"] = block["proper_refs"]
            if block.get("affect_refs"):
                item["affect_refs"] = block["affect_refs"]
            if block.get("model"):
                item["model"] = block["model"]
            items.append(item)
        output["text_blocks"] = items

        return _json.dumps(output, ensure_ascii=False, indent=2)
