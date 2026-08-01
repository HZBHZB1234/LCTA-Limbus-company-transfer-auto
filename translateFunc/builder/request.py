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
        text_blocks = self.unified_request.get("text_blocks", [])
        total_blocks = len(text_blocks)

        # 预计算每个 text_block 的独立渲染长度（各格式一次），
        # 之后分割估算只做 O(blocks) 累加，避免对每个 part × 格式重复完整渲染。
        block_lens = self._precompute_block_lens(text_blocks)

        # 同一 part 在同一格式族（xml_json/xml_xml 共用 XML 渲染）下只估算一次
        est_cache: dict[tuple[int, str], int] = {}

        def estimate(request_dict, fmt: str) -> int:
            family = "xml" if fmt in ("xml_json", "xml_xml") else "json"
            key = (id(request_dict), family)
            cached = est_cache.get(key)
            if cached is not None:
                return cached
            val = self._estimate_prompt_len(request_dict, fmt, block_lens)
            est_cache[key] = val
            return val

        # 不分割检查：对三种格式均验证不超限，确保后续格式回退安全
        if all(estimate(self.unified_request, fmt) <= self.max_length for fmt in all_formats):
            self.split_requests = [self.unified_request]
            return

        max_parts = min(total_blocks, 50)

        def _build_parts(num_parts: int) -> list[dict]:
            """构建分片，每个分片的 reference 仅含该分片实际引用的术语。"""
            part_size = total_blocks // num_parts
            remainder = total_blocks % num_parts
            parts = []
            start_idx = 0
            for i in range(num_parts):
                end_idx = start_idx + part_size + (1 if i < remainder else 0)
                parts.append(self._make_part(text_blocks[start_idx:end_idx]))
                start_idx = end_idx
            return parts

        # 动态递增分片数：从 2 份开始，逐步增加直到所有分片均不超限
        for num_parts in range(2, max_parts + 1):
            parts = _build_parts(num_parts)
            if all(estimate(p, fmt) <= self.max_length
                   for p in parts for fmt in all_formats):
                self.split_requests = parts
                return

        # 即使分到上限仍超限：对超限 part 在块粒度继续切分（逐 block 降级），
        # 保证每个请求都不超限，且不破坏 split_requests 与 user_prompt 的对齐。
        parts = _build_parts(max_parts)
        self.split_requests = []
        for p in parts:
            self.split_requests.extend(self._split_part_to_fit(p, estimate, all_formats))

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

    def _make_part(self, chunk_blocks: list[dict]) -> dict:
        """按给定 text_block 切片构建分片，reference 仅含该切片实际引用的术语。"""
        reference = self.unified_request.get("reference", {})
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

        return {
            "metadata": {**self.unified_request["metadata"],
                         "total_text_blocks": len(chunk_blocks)},
            "reference": chunk_reference,
            "text_blocks": chunk_blocks,
        }

    def _split_part_to_fit(
        self,
        part: dict,
        estimate,
        all_formats: list[str],
    ) -> list[dict]:
        """将超限 part 按块粒度二分切分，直到全部达标或不可再分（单块）。

        保持各 part 的 text_blocks 为原始顺序的连续切片，
        因此 split_requests 与 get_request_text 的索引对齐不受影响。
        """
        blocks = part.get("text_blocks", [])
        if len(blocks) <= 1:
            return [part]
        if all(estimate(part, fmt) <= self.max_length for fmt in all_formats):
            return [part]
        mid = len(blocks) // 2
        left = self._make_part(blocks[:mid])
        right = self._make_part(blocks[mid:])
        return (
            self._split_part_to_fit(left, estimate, all_formats)
            + self._split_part_to_fit(right, estimate, all_formats)
        )

    def _precompute_block_lens(self, text_blocks: list[dict]) -> dict:
        """预计算每个 text_block 在 XML/JSON 格式下的独立渲染长度（id=1 基准）。

        返回 {xml: {id(block): len}, json: {id(block): len}}，
        供 _estimate_prompt_len 做 O(blocks) 累加估算。
        """
        from translateFunc.builder.prompt import PromptFactory
        pf = PromptFactory()
        xml_lens: dict[int, int] = {}
        json_lens: dict[int, int] = {}
        for bl in text_blocks:
            key = id(bl)
            xml_lens[key] = len(pf.render_text_blocks([bl]))
            item = self._json_text_item(bl, 0)
            ser = json.dumps({"text_blocks": [item]}, ensure_ascii=False, indent=2)
            json_lens[key] = len(ser) - len('{\n  "text_blocks": [\n') - len('\n  ]\n}')
        return {"xml": xml_lens, "json": json_lens}

    def _estimate_prompt_len(self, request_data: dict, fmt: str, block_lens: dict) -> int:
        """估算请求渲染长度，与 _make_xml_user_prompt / _make_json_user_prompt 精确一致。

        参考区（glossary/affects/role_styles/skill_doc）量小，直接渲染；
        文本区用预计算的 block 长度累加，避免重复完整渲染。
        """
        if fmt in ("xml_json", "xml_xml"):
            return self._estimate_xml_len(request_data, block_lens["xml"])
        return self._estimate_json_len(request_data, block_lens["json"])

    def _estimate_xml_len(self, request_data: dict, xml_lens: dict) -> int:
        from translateFunc.builder.prompt import PromptFactory
        pf = PromptFactory()
        reference = request_data.get("reference", {})
        blocks = request_data.get("text_blocks", [])

        sections = []
        if reference.get("proper_terms"):
            sections.append(len(pf.render_glossary(reference["proper_terms"])))
        if reference.get("affects"):
            sections.append(len(self._render_affects_xml(reference["affects"])))
        if self.is_story and reference.get("model_docs"):
            for doc in reference["model_docs"]:
                sections.append(len(pf._render_role_styles([doc])))
        if self.is_skill and reference.get("skill_doc"):
            sections.append(len(f"<skill_reference>\n{reference['skill_doc']}\n</skill_reference>\n"))
        sections.append(self._xml_text_section_len(blocks, xml_lens))
        return sum(sections) + len(sections) - 1

    def _xml_text_section_len(self, blocks: list[dict], xml_lens: dict) -> int:
        """render_text_blocks 渲染长度的精确累加式。

        每个 block 独立渲染（含 <text> 包装）后：
        - 每额外一个 block 少一套包装、多一个 '\n' 分隔 → -15
        - block id 从 1 变为 (j+1) → +len(str(j+1)) - 1
        """
        n = len(blocks)
        total = 0
        for j, bl in enumerate(blocks):
            total += xml_lens[id(bl)] + (len(str(j + 1)) - 1)
        return total - 15 * (n - 1)

    def _estimate_json_len(self, request_data: dict, json_lens: dict) -> int:
        reference = request_data.get("reference", {})
        blocks = request_data.get("text_blocks", [])

        keys = []
        if reference.get("proper_terms"):
            keys.append(("glossary", self._json_emb_dict_len(
                "glossary", self._json_glossary(reference["proper_terms"]))))
        if reference.get("affects"):
            keys.append(("affects", self._json_emb_dict_len(
                "affects", reference["affects"])))
        if self.is_story and reference.get("model_docs"):
            keys.append(("role_styles", self._json_emb_dict_len(
                "role_styles", reference["model_docs"])))
        if self.is_skill and reference.get("skill_doc"):
            keys.append(("skill_doc", self._json_emb_dict_len(
                "skill_doc", reference["skill_doc"])))
        keys.append(("text_blocks", self._json_text_value_len(blocks, json_lens)))

        total = len("{\n") + len("\n}")
        for i, (k, vlen) in enumerate(keys):
            total += len('  "' + k + '": ') + vlen
            if i < len(keys) - 1:
                total += len(",\n")
        return total

    def _json_emb_dict_len(self, key: str, value) -> int:
        """值嵌入 dict（indent=2）后的序列化长度，与 json.dumps 一致。"""
        ser = json.dumps({key: value}, ensure_ascii=False, indent=2)
        prefix = '{\n  "' + key + '": '
        return len(ser) - len(prefix) - len("\n}")

    def _json_text_value_len(self, blocks: list[dict], json_lens: dict) -> int:
        """json.dumps({"text_blocks": items}) 中 text_blocks 值的精确长度。"""
        n = len(blocks)
        if n == 0:
            return len("[]")
        total = len("[\n")
        for j, bl in enumerate(blocks):
            total += json_lens[id(bl)] + (len(str(j + 1)) - 1)
        total += 2 * (n - 1) + len("\n  ]")
        return total

    def _json_text_item(self, block: dict, idx: int) -> dict:
        """构造 text_block 的 JSON item（与 _make_json_user_prompt 保持一致）。"""
        item: dict = {"id": idx + 1, "kr": block.get("kr", "")}
        if block.get("jp"):
            item["jp"] = block["jp"]
        if block.get("en"):
            item["en"] = block["en"]
        if block.get("proper_refs"):
            item["proper_refs"] = block["proper_refs"]
        if block.get("affect_refs"):
            item["affect_refs"] = block["affect_refs"]
        if block.get("model"):
            item["model"] = block["model"]
        return item

    def _json_glossary(self, proper_terms: list[dict]) -> list[dict]:
        """构造 glossary 条目（与 _make_json_user_prompt 保持一致）。"""
        glossary = []
        for t in proper_terms:
            kr = t.get("kr", t.get("term", ""))
            cn = t.get("cn", t.get("translation", ""))
            note = t.get("note", "")
            entry = {"kr": kr, "cn": cn}
            if note:
                entry["note"] = note
            glossary.append(entry)
        return glossary

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
            # 逐位置补齐：缺失位置使用该位置对应的 KR 原文，
            # 避免尾部追加（kr_fallback_by_pos[actual_count:]）导致中间缺失时后续译文整体错位
            translated_texts = [
                translated_texts[pos] if pos < actual_count else kr_fallback_by_pos[pos]
                for pos in range(expected_count)
            ]
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
        """获取角色说话风格参考。

        兼容两类角色 id 来源：
        - ScenarioModelCodes 的 id（韩文角色名，如 "이상"）→ 经 RLOE_COMPARE 映射
        - 英文模型码（如 "Yisang"）→ 直接命中 ROLE_STYLE 键，或经角色数据回退
        """
        if not self.is_story:
            return []
        docs = []
        seen: set[str] = set()
        for role_id in role_list:
            with suppress(Exception):
                style_key = self._resolve_role_style_key(role_id, role_list.get(role_id))
                if style_key and style_key not in seen:
                    seen.add(style_key)
                    docs.append(translate_doc.ROLE_STYLE[style_key])
        return docs

    def _resolve_role_style_key(self, role_id: str, role_data: Any) -> str | None:
        """将角色 id/名称解析为 ROLE_STYLE 键（英文名），找不到时返回 None。"""
        # 1. id 直接命中韩文名映射（如 "이상" → "Yisang"）
        if role_id in translate_doc.RLOE_COMPARE:
            return translate_doc.RLOE_COMPARE[role_id]
        # 2. id 本身即 ROLE_STYLE 英文键（如 "Yisang"）
        if role_id in translate_doc.ROLE_STYLE:
            return role_id
        # 3. 大小写容错（如 "YiSang" vs "Yisang"）
        lowered = role_id.casefold()
        for key in translate_doc.ROLE_STYLE:
            if key.casefold() == lowered:
                return key
        # 4. 英文键 + 数字后缀容错（如 "Dante2" → "Dante"）
        base = role_id.rstrip("0123456789")
        if base and base != role_id:
            if base in translate_doc.ROLE_STYLE:
                return base
            for key in translate_doc.ROLE_STYLE:
                if key.casefold() == base.casefold():
                    return key
        # 5. 通过角色数据中的韩文名/ID 字段回退
        if isinstance(role_data, dict):
            for field in ("id", "kr", "name"):
                val = role_data.get(field, "")
                if val in translate_doc.RLOE_COMPARE:
                    return translate_doc.RLOE_COMPARE[val]
                if val in translate_doc.ROLE_STYLE:
                    return val
        return None

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
            output["glossary"] = self._json_glossary(proper_terms)

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
        output["text_blocks"] = [
            self._json_text_item(block, i)
            for i, block in enumerate(text_blocks)
        ]

        return _json.dumps(output, ensure_ascii=False, indent=2)
