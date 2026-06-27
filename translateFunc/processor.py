"""
translateFunc/processor.py
FileProcessor —— 对单个文件执行完整的翻译管线处理。
返回 ProcessOutcome，不再抛出 ProcesserExit 异常。
"""
from __future__ import annotations
from copy import deepcopy
import json
import logging
import shutil

from translateFunc.enums import ProcessResult, FileType
from translateFunc.config import ProcessOutcome, TranslateConfig, FilePathConfig, _suppress_translatekit_log
from translateFunc.matcher.engine import MatcherEngine
from translateFunc.builder.request import RequestBuilder, EMPTY_TEXT, AVOID_PATH
from translateFunc.builder.stages import StageStrategy
from translateFunc.proper import flatten_dict_enhanced, update_dict_with_flattened

EMPTY_DATA = [{"dataList": []}, {}, []]
EMPTY_DATA_LIST = [[], [{}]]


class FileProcessor:
    """对单个翻译文件进行端到端处理。

    控制流：每个退出路径都返回 ProcessOutcome。
    不使用异常进行正常控制流。
    """

    def __init__(
        self,
        path_config: FilePathConfig,
        engine: MatcherEngine,
        translate_config: TranslateConfig,
        translator,  # translatekit TranslatorBase 实例
    ):
        self.path_config = path_config
        self._engine = engine
        self._config = translate_config
        self._translator = translator
        self._dump = translate_config.dump

        # 内部状态（在 process() 中填充）
        self.kr_json: dict = {}
        self.en_json: dict = {}
        self.jp_json: dict = {}
        self.llc_json: dict = {}
        self.kr_data: list = []
        self.en_data: list = []
        self.jp_data: list = []
        self.llc_data: list = []
        self.kr_index: dict = {}
        self.en_index: dict = {}
        self.jp_index: dict = {}
        self.llc_index: dict = {}
        self.is_story: bool = False
        self.is_skill: bool = False
        self.translating_list: list = []
        self._base_index: dict = {}

    @property
    def file_name(self) -> str:
        return self.path_config.real_name

    @property
    def file_type(self) -> FileType:
        if self.is_story:
            return FileType.STORY
        if self.is_skill:
            return FileType.SKILL
        # UI 文件的启发式判断
        if "UI" in str(self.path_config.rel_path).upper():
            return FileType.UI
        return FileType.OTHER

    def _log(self, msg: str) -> None:
        if self._dump:
            from globalManagers.LogManager import LogManager
            LogManager().log(msg)

    # ========== 主处理流程 ==========

    def process(self) -> ProcessOutcome:
        """执行完整的翻译处理。返回 ProcessOutcome。"""
        # 1. 加载 JSON 文件
        outcome = self._load_jsons()
        if outcome:
            return outcome

        # 2. 检查空文件
        outcome = self._check_empty()
        if outcome:
            return outcome

        # 3. 初始化基础数据
        self._init_base_data()

        # 4. 构建数据索引
        self._make_data_index()

        # 5. 检查是否已翻译
        outcome = self._check_translated()
        if outcome:
            return outcome

        # 6. 获取待翻译列表
        self._get_translating()
        if not self.translating_list:
            return ProcessOutcome(ProcessResult.ALREADY_TRANSLATED, self.file_name)

        # 7. 构建请求文本
        request_text = {
            "kr": self._get_translating_text("kr"),
            "jp": self._get_translating_text("jp"),
            "en": self._get_translating_text("en"),
        }

        # 8. 构建并翻译
        try:
            translated_data, had_fallback = self._translate(request_text)
        except ValueError:
            self._save_except()
            return ProcessOutcome(
                ProcessResult.TRANSLATION_MISMATCH,
                self.file_name,
                {"reason": "译文数量与原文不匹配"},
            )
        except Exception as e:
            self._save_except()
            return ProcessOutcome(
                ProcessResult.SAVE_ERROR,
                self.file_name,
                {"reason": str(e)},
            )

        # 9. 重建并保存
        self._de_get_translating_text(translated_data)
        result = self._de_get_translating()

        try:
            self._save_result(result)
        except Exception as e:
            return ProcessOutcome(
                ProcessResult.SAVE_ERROR,
                self.file_name,
                {"reason": str(e)},
            )

        if had_fallback:
            return ProcessOutcome(
                ProcessResult.FALLBACK_TO_ORIGINAL,
                self.file_name,
                {"fallback_parts": "部分文本块回退为 KR 原文"},
            )

        return ProcessOutcome(ProcessResult.SUCCESS_SAVED, self.file_name)

    # ========== 翻译执行 ==========

    def _translate(self, request_text: dict) -> tuple[dict, bool]:
        """通过配置的管线阶段执行翻译，支持格式回退。

        Returns:
            (翻译结果字典, had_fallback) — had_fallback=True 表示至少一个
            part 的全部格式失败，已回退为 KR 原文。
        """
        # 构建请求
        builder = RequestBuilder(
            request_text,
            self._engine,
            is_story=self.is_story,
            is_skill=self.is_skill,
            max_length=20000,
            file_type=self.file_type,
        )

        if self._config.is_llm:
            builder.build(prompt_format=self._config.prompt_format)
            stage_strategy = StageStrategy(self._config)

            # ====== 阶段 0：消歧（仅主格式） ======
            user_format = self._config.prompt_format
            if stage_strategy.needs_disambiguation():
                logging.debug(f"[{self.file_name}] 阶段 0: 术语消歧 (mode={self._config.disambiguation_mode})")
                ambiguous_terms = self._collect_ambiguous_terms(builder)
                if ambiguous_terms:
                    try:
                        s0_system = stage_strategy.build_stage_0_prompt(
                            ambiguous_terms,
                            builder.unified_request.get("text_blocks", []),
                            prompt_format=user_format,
                        )
                        s0_translator = self._build_translator_for_format(s0_system, user_format)
                        # user prompt 用主格式渲染
                        s0_user_prompts = builder.get_request_text(prompt_format=user_format)
                        s0_user = s0_user_prompts[0] if s0_user_prompts else ""

                        raw_response = s0_translator.translate(s0_user, timeout=60)
                        disambiguated = stage_strategy.parse_stage_0_result(raw_response, prompt_format=user_format)

                        if disambiguated:
                            if self._dump:
                                self._log(f"阶段 0 消歧：{len(disambiguated)} 个术语被评估")
                            self._apply_disambiguation(builder, disambiguated)
                        elif self._dump:
                            self._log("阶段 0 消歧：解析结果为空，使用原始术语表")
                    except Exception as e:
                        logging.warning(f"[{self.file_name}] 阶段 0 消歧失败 ({e})，使用原始术语表继续")

            # 确定格式回退链
            formats_chain = self._build_format_chain()
            if len(formats_chain) > 1:
                logging.info(
                    f"[{self.file_name}] 阶段 1: 主翻译 "
                    f"(格式链: {' → '.join(formats_chain)})"
                )
            else:
                logging.debug(f"[{self.file_name}] 阶段 1: 主翻译 ({formats_chain[0]})")

            result: list[str] = []
            had_fallback = False
            for i, request_part in enumerate(builder.split_requests if builder.split_requests else [builder.unified_request]):
                if builder.split_requests:
                    part_data = request_part
                else:
                    part_data = builder.unified_request
                if part_data is None:
                    continue

                part_result = None
                tried_formats: list[str] = []

                for fmt in formats_chain:
                    tried_formats.append(fmt)
                    # 按当前格式构建 system prompt
                    system_prompt = stage_strategy.build_stage_1_prompt(
                        self.file_type,
                        prompt_format=fmt,
                    )

                    # 按当前格式构建 user prompt
                    user_prompt = builder.get_request_text(prompt_format=fmt)
                    user_text = user_prompt[i] if i < len(user_prompt) else user_prompt[0]

                    # 自适应超时：基于实际请求长度
                    timeout = max(len(json.dumps(request_part, ensure_ascii=False)) // 200 + 1, 40)

                    # 每种格式都创建新 translator（注入当前 system_prompt）
                    # 放在 try 外：translator 构建失败不应被当作解析失败
                    translator = self._build_translator_for_format(system_prompt, fmt)

                    try:
                        # 调用 LLM
                        raw_response = translator.translate(user_text, timeout=timeout)
                        if self._dump:
                            self._log(f"[{fmt}] 第 {i + 1} 部分: {str(raw_response)[:200]}...")

                        # 解析
                        parsed = stage_strategy.parse_stage_1_result(raw_response, prompt_format=fmt)
                        if not parsed:
                            raise ValueError(f"{fmt}: 解析结果为空")

                        # 提取翻译文本
                        part_result = [
                            t.get("translation", "") if isinstance(t, dict) else str(t)
                            for t in parsed
                        ]
                        break  # 成功，退出格式回退循环

                    except (json.JSONDecodeError, ValueError) as e:
                        if self._dump:
                            self._log(f"[{fmt}] 解析失败 ({e})，回退到下一格式")
                        continue

                if part_result is None:
                    # 全部格式失败 → 无条件 warning + 标记降级
                    logging.warning(
                        f"[{self.file_name}] 全部格式 ({', '.join(tried_formats)}) "
                        f"解析失败，第 {i + 1}/{len(builder.split_requests)} 部分回退为 KR 原文"
                    )
                    had_fallback = True
                    text_blocks = part_data.get("text_blocks", [])
                    part_result = [b.get("kr", "") for b in text_blocks]

                result.extend(part_result)

            # ====== 阶段 2：自校验（仅主格式，阶段 1 全部成功时执行） ======
            if stage_strategy.needs_self_check() and not had_fallback:
                logging.debug(f"[{self.file_name}] 阶段 2: 自校验")
                try:
                    # 收集原文块（从 builder.unified_request 中）
                    original_blocks = builder.unified_request.get("text_blocks", [])
                    # 构建译文 dict 列表（格式与 parse_stage_1_result 输出一致）
                    translations_for_check = [
                        {"id": i + 1, "translation": t}
                        for i, t in enumerate(result)
                    ]

                    s2_prompt = stage_strategy.build_stage_2_prompt(
                        self.file_type,
                        prompt_format=user_format,
                        original_blocks=original_blocks,
                        translations=translations_for_check,
                    )
                    s2_translator = self._build_translator_for_format(s2_prompt, user_format)
                    # 阶段 2 的 user prompt 为空字符串（全部在 system prompt 中）
                    raw_response = s2_translator.translate("", timeout=120)
                    checked = stage_strategy.parse_stage_2_result(raw_response, prompt_format=user_format)

                    if checked:
                        result = self._apply_corrections(result, checked)
                    elif self._dump:
                        self._log("阶段 2 自校验：解析结果为空，保留阶段 1 翻译")
                except Exception as e:
                    logging.warning(
                        f"[{self.file_name}] 阶段 2 自校验失败 ({e})，使用未校验的翻译结果"
                    )

            return builder.deBuild(result), had_fallback
        else:
            # 非 LLM 路径：不存在格式回退
            simple_builder = _SimpleRequestBuilder(request_text)
            simple_builder.build()
            request_texts = simple_builder.get_request_text(from_lang=self._config.from_lang)
            result = self._translator.translate(request_texts)
            return simple_builder.deBuild(result), False

    def _build_format_chain(self) -> list[str]:
        """构建格式回退链：[用户选择] + fallback? [xml_json, json_json, xml_xml] : [].

        用户选择的格式排在最前，回退格式按 xml_json → json_json → xml_xml
        顺序追加（跳过重复）。当 fallback=False 时仅返回用户格式。
        """
        user_format = self._config.prompt_format
        chain = [user_format]
        if self._config.fallback:
            fallback_order = ["xml_json", "json_json", "xml_xml"]
            for f in fallback_order:
                if f not in chain:
                    chain.append(f)
        return chain

    def _build_translator_for_format(self, system_prompt: str, prompt_format: str = "xml_json"):
        """为指定格式创建独立的 translator 实例。"""
        from translateFunc.translate_request import TRANSLATOR_TRANS
        from translatekit import TranslationConfig as TKitConfig

        from translateFunc.config import inject_thinking_mode

        translator_cls = TRANSLATOR_TRANS[self._config.translator_name]
        api_settings = dict(self._config.translator_api)
        api_settings = inject_thinking_mode(api_settings, self._config.enable_thinking)
        api_settings["system_prompt"] = system_prompt
        if prompt_format in ("xml_json", "json_json"):
            api_settings["response_format"] = "json_object"
        elif prompt_format == "xml_xml":
            api_settings["response_format"] = "text"

        tkit_config = TKitConfig(
            api_setting=api_settings,
            debug_mode=self._config.debug_mode,
            enable_cache=True,
            enable_metrics=True,
        )
        tkit_config.text_max_length = 20000
        tkit_config.max_workers = 1

        with _suppress_translatekit_log(self._config.debug_mode):
            translator = translator_cls(tkit_config)

        return translator

    # ========== 阶段 0：消歧 ==========

    def _collect_ambiguous_terms(
        self, builder: "RequestBuilder"
    ) -> list[dict]:
        """收集需要 LLM 消歧的术语-文本块关联。

        遍历 unified_request["text_blocks"]，收集其中 proper_refs 引用的术语。
        disambiguation_mode="llm" 时全部匹配参与消歧；
        disambiguation_mode="hybrid" 时也收集全部（confidence 过滤依赖 ProperAnalyzer 集成）。

        Returns:
            [{term, cn, note, text_block_indices: [int, ...]}, ...]
        """
        text_blocks = builder.unified_request.get("text_blocks", [])
        proper_terms = {
            t.get("term", ""): t
            for t in builder.unified_request.get("reference", {}).get("proper_terms", [])
        }

        # term_key → 出现它的 text_block 索引列表
        term_block_map: dict[str, list[int]] = {}
        for i, block in enumerate(text_blocks):
            refs = block.get("proper_refs", [])
            for ref in refs:
                if ref not in term_block_map:
                    term_block_map[ref] = []
                term_block_map[ref].append(i)

        if not term_block_map:
            return []

        # disambiguation_mode 判断
        mode = self._config.disambiguation_mode
        if mode == "similarity":
            return []  # 不需要 LLM 消歧

        # llm / hybrid 模式：收集所有匹配术语
        # 注：hybrid 模式理想行为是仅收集 LOW/UNKNOWN 置信度术语，
        # 但 confidence 数据需要 ProperAnalyzer 集成，当前暂全部收集
        if mode == "hybrid" and self._dump:
            self._log("hybrid 消歧模式：confidence 过滤需要 ProperAnalyzer 集成，当前收集全部匹配术语")

        result = []
        for term_key, block_indices in term_block_map.items():
            term_data = proper_terms.get(term_key, {"term": term_key, "translation": ""})
            result.append({
                "kr": term_data.get("term", term_key),
                "cn": term_data.get("translation", ""),
                "note": term_data.get("note", ""),
                "text_block_indices": block_indices,
            })
        return result

    def _apply_disambiguation(
        self, builder: "RequestBuilder", disambiguated: list[dict]
    ) -> None:
        """将消歧结果应用到 builder 的术语表。

        对 applies=false 的术语，从 unified_request["reference"]["proper_terms"] 中移除，
        并通过 unified_request["text_blocks"] 中对应的 proper_refs 清除引用。
        """
        if not disambiguated:
            return

        excluded_terms: set[str] = set()
        for item in disambiguated:
            if not item.get("applies", True):
                excluded_terms.add(item.get("term", ""))

        if not excluded_terms:
            return

        # 从 reference 中移除不适用的术语
        proper_terms = builder.unified_request.get("reference", {}).get("proper_terms", [])
        builder.unified_request["reference"]["proper_terms"] = [
            t for t in proper_terms
            if t.get("term", "") not in excluded_terms
        ]

        # 从 text_blocks 中清除对应引用
        text_blocks = builder.unified_request.get("text_blocks", [])
        for block in text_blocks:
            refs = block.get("proper_refs", [])
            if refs:
                block["proper_refs"] = [r for r in refs if r not in excluded_terms]
                if not block["proper_refs"]:
                    del block["proper_refs"]

        logging.info(
            f"[{self.file_name}] 阶段 0 消歧：排除了 {len(excluded_terms)} 个不适用的术语: "
            f"{', '.join(sorted(excluded_terms))}"
        )

    # ========== 阶段 2：自校验 ==========

    def _apply_corrections(
        self, translations: list[str], checked: list[dict]
    ) -> list[str]:
        """应用阶段 2 自校验修正。

        仅对 checked 中 changed=true 的条目替换对应索引的翻译文本。
        checked 中的 id 字段为 1-based 序号，对应 translations 的索引。

        Args:
            translations: 阶段 1 的翻译文本列表
            checked: 阶段 2 的校验结果 [{id, translation, changed, change_reason}, ...]

        Returns:
            修正后的翻译文本列表
        """
        result = list(translations)  # 浅拷贝
        corrections = 0
        for item in checked:
            if item.get("changed", False):
                idx = int(item.get("id", 0)) - 1  # 1-based → 0-based
                if 0 <= idx < len(result):
                    result[idx] = item.get("translation", result[idx])
                    corrections += 1

        if corrections > 0:
            logging.info(
                f"[{self.file_name}] 阶段 2 自校验：修正了 {corrections}/{len(checked)} 条翻译"
            )
        return result

    # ========== 加载与检查 ==========

    def _load_jsons(self) -> ProcessOutcome | None:
        """加载 KR/EN/JP/LLC JSON 文件。出错时返回 ProcessOutcome。"""
        try:
            with open(self.path_config.KR_path, "r", encoding="utf-8-sig") as f:
                self.kr_json = json.load(f)
            try:
                with open(self.path_config.EN_path, "r", encoding="utf-8-sig") as f:
                    self.en_json = json.load(f)
            except FileNotFoundError:
                self.en_json = deepcopy(self.kr_json)
            try:
                with open(self.path_config.JP_path, "r", encoding="utf-8-sig") as f:
                    self.jp_json = json.load(f)
            except FileNotFoundError:
                self.jp_json = deepcopy(self.kr_json)
            try:
                with open(self.path_config.LLC_path, "r", encoding="utf-8-sig") as f:
                    self.llc_json = json.load(f)
            except FileNotFoundError:
                self.llc_json = {}
        except json.JSONDecodeError:
            self._save_except()
            return ProcessOutcome(ProcessResult.JSON_DECODE_ERROR, self.file_name)
        return None

    def _check_empty(self) -> ProcessOutcome | None:
        """检查 KR 数据是否为空。为空时返回 ProcessOutcome。"""
        if self.kr_json in EMPTY_DATA or self.kr_json.get("dataList", []) in EMPTY_DATA_LIST:
            if self.path_config.LLC_path.exists():
                self._save_llc()
                return ProcessOutcome(ProcessResult.EMPTY_WITH_LLC, self.file_name)
            else:
                return ProcessOutcome(ProcessResult.EMPTY_SKIPPED, self.file_name)
        return None

    def _check_translated(self) -> ProcessOutcome | None:
        """检查是否已翻译。已翻译时返回 ProcessOutcome。"""
        if not len(self.jp_index) == len(self.kr_index) == len(self.en_index):
            def _align(d: dict, ref: dict) -> dict:
                return {k: d.get(k, ref[k]) for k in ref}
            self.en_index = _align(self.en_index, self.kr_index)
            self.jp_index = _align(self.jp_index, self.kr_index)
            self.llc_index = _align(self.llc_index, self.kr_index)

        if list(self.kr_index) == list(self.llc_index):
            self._save_llc()
            return ProcessOutcome(ProcessResult.ALREADY_TRANSLATED, self.file_name)
        return None

    # ========== 初始化 ==========

    def _init_base_data(self) -> None:
        self.en_data = self.en_json.get("dataList", [])
        self.kr_data = self.kr_json.get("dataList", [])
        self.jp_data = self.jp_json.get("dataList", [])
        self.llc_data = self.llc_json.get("dataList", [])
        self.is_story = (self.path_config.rel_path.parent.name == "StoryData")
        self.is_skill = self.path_config.real_name.startswith("Skills_")

    def _make_data_index(self) -> None:
        if self.is_story:
            self.en_index = {i: d for i, d in enumerate(self.en_data)}
            self.kr_index = {i: d for i, d in enumerate(self.kr_data)}
            self.jp_index = {i: d for i, d in enumerate(self.jp_data)}
            self.llc_index = {i: d for i, d in enumerate(self.llc_data)}
        else:
            self.en_index = {i["id"]: i for i in self.en_data}
            self.kr_index = {i["id"]: i for i in self.kr_data}
            self.jp_index = {i["id"]: i for i in self.jp_data}
            self.llc_index = {i["id"]: i for i in self.llc_data}

    def _get_translating(self) -> None:
        self.translating_list = [i for i in self.kr_index if i not in self.llc_index]

    # ========== 文本提取 / 重建 ==========

    def _get_translating_text(self, lang: str = "kr") -> dict:
        lang_index = {"kr": self.kr_index, "jp": self.jp_index, "en": self.en_index}[lang]
        translating_text = {}
        for i in self.translating_list:
            flat = flatten_dict_enhanced(lang_index[i], ignore_types=[None, int, float])
            to_delete = [k for k in flat if k[-1] in AVOID_PATH]
            for k in to_delete:
                del flat[k]
            translating_text[i] = flat
        return translating_text

    def _de_get_translating_text(self, translated_text: dict) -> dict:
        self._base_index = deepcopy(self.kr_index)
        for i in self.translating_list:
            trans_item = self._base_index[i]
            translated_item = translated_text[i]
            update_dict_with_flattened(trans_item, translated_item)
        return self._base_index

    def _de_get_translating(self) -> dict:
        result = []
        for i in self.kr_index:
            if i in self.llc_index:
                result.append(self.llc_index[i])
            else:
                result.append(self._base_index[i])
        return {"dataList": result}

    # ========== 保存 ==========

    def _save_result(self, data: dict) -> None:
        if not self._config.save_result:
            return
        self.path_config.target_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path_config.target_file, "w", encoding="utf-8-sig") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def _save_llc(self) -> None:
        shutil.copy2(self.path_config.LLC_path, self.path_config.target_file)

    def _save_except(self) -> None:
        """回退保存：依次尝试 LLC → EN → JP → KR。"""
        for path_attr in ("LLC_path", "EN_path", "JP_path", "KR_path"):
            try:
                src = getattr(self.path_config, path_attr)
                if src.exists():
                    shutil.copy2(src, self.path_config.target_file)
                    return
            except Exception:
                continue


# ============================================================
# _SimpleRequestBuilder —— 非 LLM 翻译器使用
# ============================================================

class _SimpleRequestBuilder:
    """非 LLM 翻译器的轻量请求构建器（保留原有行为）。"""

    def __init__(self, request_text: dict):
        self.en_texts = request_text["en"]
        self.kr_texts = request_text["kr"]
        self.jp_texts = request_text.get("jp", {})

    def build(self) -> list:
        EN_result, KR_result, JP_result = [], [], []
        for idx in self.kr_texts:
            for text in self.kr_texts[idx].values():
                KR_result.append(text)
            for text in self.jp_texts.get(idx, {}).values():
                JP_result.append(text)
            for text in self.en_texts.get(idx, {}).values():
                EN_result.append(text)

        if not (len(KR_result) == len(EN_result) == len(JP_result)):
            raise ValueError(
                f"语言文本长度不一致: KR={len(KR_result)}, "
                f"EN={len(EN_result)}, JP={len(JP_result)}"
            )

        empty_idxs = {
            i for i, (kr, en, jp) in enumerate(zip(KR_result, EN_result, JP_result))
            if kr in EMPTY_TEXT and en in EMPTY_TEXT and jp in EMPTY_TEXT
        }
        self.KR_build = [t for i, t in enumerate(KR_result) if i not in empty_idxs]
        self.EN_build = [t for i, t in enumerate(EN_result) if i not in empty_idxs]
        self.JP_build = [t for i, t in enumerate(JP_result) if i not in empty_idxs]

    def get_request_text(self, from_lang: str = "KR") -> list[str]:
        return getattr(self, f"{from_lang}_build")

    def deBuild(self, translated_texts: list[str], from_lang: str = "kr") -> dict:
        original = deepcopy(getattr(self, f"{from_lang}_texts"))
        it = iter(translated_texts)
        for idx in original:
            kr_item = self.kr_texts.get(idx, {})
            jp_item = self.jp_texts.get(idx, {})
            en_item = self.en_texts.get(idx, {})
            for path_tuple in kr_item:
                jp_val = jp_item.get(path_tuple, "")
                en_val = en_item.get(path_tuple, "")
                kr_val = kr_item[path_tuple]
                if not (jp_val in EMPTY_TEXT and en_val in EMPTY_TEXT and kr_val in EMPTY_TEXT):
                    original[idx][path_tuple] = next(it)
        try:
            next(it)
        except StopIteration:
            pass  # 正常 —— 没有多余的翻译结果
        else:
            raise ValueError("译文数量多于预期")
        return original
