"""
translateFunc/processor.py
FileProcessor —— 对单个文件执行完整的翻译管线处理。
返回 ProcessOutcome，不再抛出 ProcesserExit 异常。
"""
from __future__ import annotations
from copy import deepcopy
import json
import shutil

from translateFunc.enums import ProcessResult, FileType
from translateFunc.config import ProcessOutcome, TranslateConfig, FilePathConfig
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
        self.formal_flatten_item: dict = {}
        self._removed_keys: list = []
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
            translated_data = self._translate(request_text)
        except StopIteration:
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

        return ProcessOutcome(ProcessResult.SUCCESS_SAVED, self.file_name)

    # ========== 翻译执行 ==========

    def _translate(self, request_text: dict) -> dict:
        """通过配置的管线阶段执行翻译，支持格式回退。"""
        # 构建请求
        builder = RequestBuilder(
            request_text,
            self._engine,
            is_story=self.is_story,
            is_skill=self.is_skill,
            is_text_format=False,  # 废弃，由 prompt_format 控制
            max_length=20000,
            file_type=self.file_type,
        )

        if self._config.is_llm:
            builder.build(prompt_format=self._config.prompt_format)
            stage_strategy = StageStrategy(self._config)

            # 确定格式回退链
            formats_chain = self._build_format_chain()

            result: list[str] = []
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
                    # 全部格式失败，回退为原文
                    if self._dump:
                        self._log(f"全部格式 ({', '.join(tried_formats)}) 失败，回退为原文")
                    text_blocks = part_data.get("text_blocks", [])
                    part_result = [b.get("kr", "") for b in text_blocks]

                result.extend(part_result)

            return builder.deBuild(result)
        else:
            # 非 LLM 路径：保持不变
            simple_builder = _SimpleRequestBuilder(request_text)
            simple_builder.build()
            request_texts = simple_builder.get_request_text(from_lang=self._config.from_lang)
            result = self._translator.translate(request_texts)
            return simple_builder.deBuild(result)

    def _build_format_chain(self) -> list[str]:
        """构建格式回退链：[用户选择] + fallback? [xml_json, json_json, xml_xml] : []"""
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
        import logging

        translator_cls = TRANSLATOR_TRANS[self._config.translator_name]
        api_settings = dict(self._config.translator_api)
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

        if not self._config.debug_mode:
            logging.getLogger("translatekit").setLevel(logging.INFO)

        translator = translator_cls(tkit_config)

        if not self._config.debug_mode:
            logging.getLogger("translatekit").setLevel(logging.DEBUG)

        return translator

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
            self.formal_flatten_item = deepcopy(flat)
            to_delete = [k for k in flat if k[-1] in AVOID_PATH]
            self._removed_keys = to_delete
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
            raise StopIteration("译文数量多于预期")
        return original
