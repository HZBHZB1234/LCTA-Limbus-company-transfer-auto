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

logger = logging.getLogger("LCTA")  # 与 LogManager 一致，确保日志正确路由到 app.log

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
        max_length: int = 20000,
        file_type: FileType = FileType.OTHER,
    ):
        self.kr_text = request_text["kr"]
        self.jp_text = request_text.get("jp", {})
        self.en_text = request_text.get("en", {})
        self._engine = matcher_engine
        self.is_story = is_story
        self.is_skill = is_skill
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
                            model_info = self._engine.role_by_id.get(model)
                            if model_info is not None:
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
        分片的 reference 按需裁剪，仅包含该分片 text_blocks 实际引用的术语。
        """
        if self.unified_request is None:
            return

        all_formats = ["xml_json", "xml_xml", "json_json"]
        reference = self.unified_request.get("reference", {})

        def estimate(request_dict, fmt: str) -> int:
            return len(self._get_request_text(request_dict, fmt))

        # 不分割检查：对三种格式均验证不超限，确保后续格式回退安全
        if all(estimate(self.unified_request, fmt) <= self.max_length for fmt in all_formats):
            self.split_requests = [self.unified_request]
            return

        text_blocks = self.unified_request.get("text_blocks", [])
        total_blocks = len(text_blocks)
        max_parts = min(total_blocks, 50)

        def _build_parts(num_parts: int) -> list[dict]:
            """构建分片，每个分片的 reference 仅含该分片实际引用的术语。"""
            part_size = total_blocks // num_parts
            remainder = total_blocks % num_parts
            parts = []
            start_idx = 0
            for i in range(num_parts):
                end_idx = start_idx + part_size + (1 if i < remainder else 0)
                chunk_blocks = text_blocks[start_idx:end_idx]

                chunk_proper_refs: set[str] = set()
                chunk_affect_refs: set[str] = set()
                for block in chunk_blocks:
                    chunk_proper_refs.update(block.get("proper_refs", []))
                    chunk_affect_refs.update(block.get("affect_refs", []))

                chunk_reference = {
                    "proper_terms": [
                        t for t in reference.get("proper_terms", [])
                        if t.get("term", "") in chunk_proper_refs
                    ],
                    "affects": [
                        a for a in reference.get("affects", [])
                        if f'[{a.get("id", "")}]' in chunk_affect_refs
                    ],
                    "models": reference.get("models", []),
                    "model_docs": reference.get("model_docs", []),
                    "skill_doc": reference.get("skill_doc", ""),
                }

                parts.append({
                    "metadata": {**self.unified_request["metadata"],
                                 "total_text_blocks": end_idx - start_idx},
                    "reference": chunk_reference,
                    "text_blocks": chunk_blocks,
                })
                start_idx = end_idx
            return parts

        # 动态递增分片数：从 2 份开始，逐步增加直到所有分片均不超限
        for num_parts in range(2, max_parts + 1):
            parts = _build_parts(num_parts)
            if all(estimate(p, fmt) <= self.max_length
                   for p in parts for fmt in all_formats):
                self.split_requests = parts
                return

        # 即使分到上限仍超限：使用 max_parts 分片并记录详细警告
        parts = _build_parts(max_parts)
        self.split_requests = parts

        over_limit_parts = []
        for idx, p in enumerate(self.split_requests):
            max_est = max(estimate(p, fmt) for fmt in all_formats)
            if max_est > self.max_length:
                over_limit_parts.append((idx, max_est, len(p.get("text_blocks", []))))
        if over_limit_parts:
            details = "; ".join(
                f"part[{i}]={size}chars({blocks}blocks)"
                for i, size, blocks in over_limit_parts
            )
            logger.warning(
                "分割后仍有 %d/%d 个 part 超限 (limit=%d, max_parts=%d): %s",
                len(over_limit_parts), len(self.split_requests),
                self.max_length, max_parts, details,
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
        """将扁平翻译文本列表还原为嵌套字典结构。

        当翻译数量与预期不符时，按位置用对应 KR 原文填充缺失条目：
        - 不足时：末尾 shortfall 个位置用各自的 KR 原文补齐
        - 多余时：截断多余条目
        """
        result_dict = deepcopy(self.kr_text)

        # 收集每个非空位置的 KR 原文，用于缺失时按位置精确回退
        kr_fallback_by_pos: list[str] = []
        for idx in result_dict:
            kr_item = self.kr_text.get(idx, {})
            jp_item = self.jp_text.get(idx, {})
            en_item = self.en_text.get(idx, {})
            for path_tuple in kr_item.keys():
                jp_val = jp_item.get(path_tuple, "")
                en_val = en_item.get(path_tuple, "")
                kr_val = kr_item.get(path_tuple, "")
                if not (jp_val in EMPTY_TEXT and en_val in EMPTY_TEXT and kr_val in EMPTY_TEXT):
                    kr_fallback_by_pos.append(kr_val)

        expected_count = len(kr_fallback_by_pos)

        # 韧性处理：数量不匹配时按位置补齐或截断
        actual_count = len(translated_texts)
        if actual_count < expected_count:
            shortfall = expected_count - actual_count
            logger.warning(
                f"翻译文本数量不足: 预期 {expected_count}, 实际 {actual_count}"
                f"（{shortfall} 个文本块按位置回退为 KR 原文）"
            )
            translated_texts = list(translated_texts) + kr_fallback_by_pos[actual_count:]
        elif actual_count > expected_count:
            excess = actual_count - expected_count
            logger.warning(
                f"翻译文本数量多于预期: 预期 {expected_count}, 实际 {actual_count}"
                f"（截断多余 {excess} 个）"
            )
            translated_texts = translated_texts[:expected_count]

        translated_iter = iter(translated_texts)
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
            return translate_doc.SKILL_DOC
        return ""

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
            parts.append(f"<skill_reference>\n{reference['skill_doc']}\n</skill_reference>\n")

        # 文本块
        parts.append(pf.render_text_blocks(text_blocks))

        return "\n".join(parts)

    def _render_affects_xml(self, affects: list[dict]) -> str:
        """渲染 affects 为 XML。"""
        if not affects:
            return ""
        from translateFunc.builder.prompt import PromptFactory
        _xml_escape = PromptFactory._xml_escape
        lines = ["<affects>"]
        for a in affects:
            lines.append("  <affect>")
            lines.append(f"    <id>{_xml_escape(a.get('id', ''))}</id>")
            lines.append(f"    <kr>{_xml_escape(a.get('kr', ''))}</kr>")
            lines.append(f"    <cn>{_xml_escape(a.get('cn', ''))}</cn>")
            lines.append("  </affect>")
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
