"""
文件处理器模块
负责单个翻译文件的完整处理流程：
加载JSON → 检查空文件 → 初始化数据 → 创建索引 → 检查翻译状态
→ 获取待翻译条目 → 构建请求文本 → 执行翻译 → 还原结果 → 保存

增强改进：
- 详细的错误上下文日志记录
- ProcessExitType 枚举替代字符串退出码
- Fallback机制内聚（JSON↔TEXT格式切换）
"""

import json
import logging
import os
import shutil
import re
from typing import Dict, List, Tuple
from copy import deepcopy
from contextlib import suppress

from .data_structures import (
    FilePathConfig, RequestConfig,
    EMPTY_DATA, EMPTY_DATA_LIST, EMPTY_TEXT, AVOID_PATH,
    ProcessExitType, ProcesserExit
)
from .matcher import MatcherOrganizer
from .builder import RequestTextBuilder, SimpleRequestTextBuilder

from translateFunc.proper.flat import flatten_dict_enhanced, update_dict_with_flattened

logger = logging.getLogger(__name__)


class FileProcessor:
    """
    文件处理器
    负责单个文件的完整翻译处理流水线

    处理流程：
    1. _load_json - 加载所有语言的JSON文件
    2. _check_empty - 检查是否为空文件
    3. _init_base_data - 提取dataList并判断文件类型
    4. _make_data_index - 创建数据索引
    5. _check_translated - 检查是否已翻译
    6. _get_translating - 确定待翻译条目
    7. _get_translating_text - 提取待翻译文本
    8. _execute_translation - 执行翻译（含fallback）
    9. _de_get_translating_text - 还原翻译结果
    10. _save_result - 保存结果文件
    """

    def __init__(
        self,
        path_config: FilePathConfig,
        matcher: MatcherOrganizer,
        request_config: RequestConfig = None,
    ):
        self.path_config = path_config
        self.matcher = matcher
        self.request_config = request_config or RequestConfig()
        self._dump = os.getenv('DUMP', 'False').lower() == 'true'

        # 运行时状态
        self.kr_json = None
        self.en_json = None
        self.jp_json = None
        self.llc_json = None
        self.is_story = False
        self.is_skill = False
        self.translating_list = []
        self.formal_flatten_item = None
        self.get_translating_removement = []
        self._base_index = None

    def dump(self, content):
        """调试输出（仅在DUMP环境变量启用时）"""
        if self._dump:
            logger.debug(str(content)[:2000])

    def process_file(self):
        """执行完整的文件处理流水线"""
        self._log_processing_state("开始处理")

        try:
            self._load_json()
            self._check_empty()
            self._init_base_data()
            self._make_data_index()
            self._check_translated()
            self._get_translating()

            request_text = {
                "kr": self._get_translating_text('kr'),
                "jp": self._get_translating_text('jp'),
                "en": self._get_translating_text('en')
            }
            self.dump(request_text)

            translated = self._execute_translation(request_text)
            self._de_get_translating_text(translated)
            result = self._de_get_translating()
            self._save_result(result)

        except ProcesserExit:
            raise
        except Exception as e:
            self._log_error_context(e)
            raise

    # ========== 步骤1: 加载JSON ==========

    def _load_json(self):
        """加载所有语言版本的JSON文件"""
        try:
            with open(self.path_config.KR_path, 'r', encoding='utf-8-sig') as f:
                self.kr_json = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"{self.path_config.real_name} 文件解析错误")
            logger.exception(e)
            self._save_except()
            raise ProcesserExit(ProcessExitType.JSON_DECODE_ERROR)

        # 英文文件
        try:
            with open(self.path_config.EN_path, 'r', encoding='utf-8-sig') as f:
                self.en_json = json.load(f)
        except FileNotFoundError:
            logger.warning(f"{self.path_config.real_name} 不存在EN文件，使用KR替代")
            self.en_json = deepcopy(self.kr_json)

        # 日文文件
        try:
            with open(self.path_config.JP_path, 'r', encoding='utf-8-sig') as f:
                self.jp_json = json.load(f)
        except FileNotFoundError:
            logger.warning(f"{self.path_config.real_name} 不存在JP文件，使用KR替代")
            self.jp_json = deepcopy(self.kr_json)

        # 已有汉化文件
        try:
            with open(self.path_config.LLC_path, 'r', encoding='utf-8-sig') as f:
                self.llc_json = json.load(f)
        except FileNotFoundError:
            logger.info(f"{self.path_config.real_name} 无已有汉化，从头翻译")
            self.llc_json = {}

    # ========== 步骤2: 检查空文件 ==========

    def _check_empty(self):
        """检查是否为空数据"""
        if self.kr_json in EMPTY_DATA or self.kr_json.get('dataList', []) in EMPTY_DATA_LIST:
            logger.warning(f"{self.path_config.real_name} 文件为空")
            if self.path_config.LLC_path.exists():
                self._save_llc()
                raise ProcesserExit(ProcessExitType.EMPTY_WITH_LLC)
            else:
                raise ProcesserExit(ProcessExitType.EMPTY_NO_LLC)

    # ========== 步骤3: 初始化基础数据 ==========

    def _init_base_data(self):
        """提取dataList并判断文件类型（故事/技能/通用）"""
        self.en_data = self.en_json.get('dataList', [])
        self.kr_data = self.kr_json.get('dataList', [])
        self.jp_data = self.jp_json.get('dataList', [])
        self.llc_data = self.llc_json.get('dataList', [])

        self.is_story = (self.path_config.rel_dir.name == 'StoryData')
        self.is_skill = self.path_config.real_name.startswith('Skills_')

        self.request_config.is_story = self.is_story
        self.request_config.is_skill = self.is_skill

    # ========== 步骤4: 创建数据索引 ==========

    def _make_data_index(self):
        """根据文件类型建立数据索引"""
        if self.is_story:
            self._make_data_index_story()
        else:
            self._make_data_index_default()

    def _make_data_index_default(self):
        self.en_index = {i['id']: i for i in self.en_data}
        self.kr_index = {i['id']: i for i in self.kr_data}
        self.jp_index = {i['id']: i for i in self.jp_data}
        self.llc_index = {i['id']: i for i in self.llc_data}

    def _make_data_index_story(self):
        self.en_index = {i: d for i, d in enumerate(self.en_data)}
        self.kr_index = {i: d for i, d in enumerate(self.kr_data)}
        self.jp_index = {i: d for i, d in enumerate(self.jp_data)}
        self.llc_index = {i: d for i, d in enumerate(self.llc_data)}

    # ========== 步骤5: 检查翻译状态 ==========

    def _check_translated(self):
        """检查三语长度一致性，判断是否已翻译"""
        if not (len(self.jp_index) == len(self.kr_index) == len(self.en_index)):
            logger.warning(
                f"{self.path_config.real_name} 三语长度不一致 "
                f"jp:{len(self.jp_index)} kr:{len(self.kr_index)} en:{len(self.en_index)}，自动对齐"
            )

            def align_length(dict_: dict, dict_kr: dict) -> dict:
                result = {}
                for i in dict_kr:
                    result[i] = dict_.get(i, dict_kr[i])
                return result

            self.en_index = align_length(self.en_index, self.kr_index)
            self.jp_index = align_length(self.jp_index, self.kr_index)
            self.llc_index = align_length(self.llc_index, self.kr_index)

        if list(self.kr_index) == list(self.llc_index):
            self._save_llc()
            raise ProcesserExit(ProcessExitType.ALREADY_TRANSLATED)

    # ========== 步骤6: 获取待翻译条目 ==========

    def _get_translating(self):
        """确定需要翻译的条目列表"""
        self.translating_list = [
            i for i in self.kr_index if i not in self.llc_index
        ]

    # ========== 步骤7: 提取待翻译文本 ==========

    def _get_translating_text(self, lang: str = 'kr') -> Dict[str, Dict[Tuple, str]]:
        """提取待翻译条目的文本内容（扁平化）"""
        lang_map = {'kr': self.kr_index, 'jp': self.jp_index, 'en': self.en_index}
        lang_index = lang_map.get(lang, self.kr_index)

        translating_text = {}
        for i in self.translating_list:
            flatten_item = flatten_dict_enhanced(
                lang_index[i], ignore_types=[None, int, float]
            )
            self.formal_flatten_item = deepcopy(flatten_item)

            # 移除无需翻译的字段
            keys_to_delete = [k for k in flatten_item if k[-1] in AVOID_PATH]
            self.get_translating_removement = keys_to_delete
            for key in keys_to_delete:
                del flatten_item[key]

            translating_text[i] = flatten_item

        return translating_text

    def _de_get_translating_text(self, translated_text: Dict[str, Dict[Tuple, str]]):
        """将翻译结果还原到数据结构中"""
        self._base_index = deepcopy(self.kr_index)
        for i in self.translating_list:
            trans_item = self._base_index[i]
            translated_item = translated_text[i]
            update_dict_with_flattened(trans_item, translated_item)

    def _de_get_translating(self):
        """合并已翻译和待翻译数据"""
        result = []
        for i in self.kr_index:
            if i in self.llc_index:
                result.append(self.llc_index[i])
            else:
                result.append(self._base_index[i])
        return {"dataList": result}

    # ========== 步骤8: 执行翻译 ==========

    def _execute_translation(self, request_text: dict) -> Dict:
        """执行翻译（含fallback机制）"""
        try:
            return self._do_translate(request_text)
        except ProcesserExit:
            raise
        except Exception as e:
            # 仅对LLM翻译器尝试fallback
            if not self.request_config.is_llm:
                raise
            return self._fallback_translate(request_text, e)

    def _do_translate(self, request_text: dict) -> Dict:
        """执行实际翻译"""
        if self.request_config.is_llm:
            builder = RequestTextBuilder(
                request_text, self.matcher, self.request_config,
                self.formal_flatten_item
            )
            builder.build()
            self.dump(builder.unified_request)

            request_texts = builder.get_request_text()
            result = []

            for i, request_part in enumerate(request_texts):
                timeout = max(len(request_part) // 200 + 1, 40)
                result_part = self.request_config.translator.translate(
                    request_part, timeout=timeout
                )
                self.dump(result_part)

                if self.request_config.is_text_format:
                    result_list = result_part.split('\n\n')
                    result_list = [
                        re.sub(
                            r'^\s?【文本块\s?\d+】[\s\n]?', '',
                            item.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
                        )
                        for item in result_list
                    ]
                else:
                    result_list = json.loads(result_part).get('translations', [])

                result.extend(result_list)
                logger.info(
                    f"第 {i+1} 部分翻译完成，"
                    f"获得 {len(result_list)} 条结果"
                )
        else:
            builder = SimpleRequestTextBuilder(request_text)
            builder.build()
            request_texts = builder.get_request_text(
                from_lang=self.request_config.from_lang
            )
            result = self.request_config.translator.translate(request_texts)
            self.dump(result)
            logger.info(f"获得 {len(result)} 条翻译结果")

        try:
            return builder.deBuild(result)
        except StopIteration:
            logger.warning(f"{self.path_config.real_name} 翻译结果数量不匹配")
            self._save_except()
            raise ProcesserExit(ProcessExitType.TRANSLATION_LENGTH_ERROR)

    def _fallback_translate(self, request_text: dict, original_error: Exception) -> Dict:
        """
        翻译失败时的fallback处理
        切换JSON↔TEXT请求格式后重试
        """
        logger.warning(
            f"{self.path_config.real_name} 翻译失败: {original_error}，"
            f"尝试切换请求格式(is_text={self.request_config.is_text_format}→"
            f"{not self.request_config.is_text_format})"
        )

        if self._dump:
            self._dump_failed_request(request_text, original_error)

        # 切换格式
        self.request_config.is_text_format = not self.request_config.is_text_format

        try:
            result = self._do_translate(request_text)
            logger.info(f"{self.path_config.real_name} fallback成功")
            return result
        except Exception as e:
            logger.error(
                f"{self.path_config.real_name} fallback也失败: {e}"
            )
            raise

    # ========== 步骤9: 保存 ==========

    def _save_result(self, json_data):
        """保存翻译结果"""
        if not self.request_config.save_result:
            raise ProcesserExit(ProcessExitType.NO_SAVE_SUCCESS)
        try:
            with open(self.path_config.target_file, 'w', encoding='utf-8-sig') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.exception(e)
            raise ProcesserExit(ProcessExitType.SUCCESS_SAVE)

    # ========== 备份保存 ==========

    def _save_llc(self):
        shutil.copy2(self.path_config.LLC_path, self.path_config.target_file)

    def _save_en(self):
        shutil.copy2(self.path_config.EN_path, self.path_config.target_file)

    def _save_jp(self):
        shutil.copy2(self.path_config.JP_path, self.path_config.target_file)

    def _save_kr(self):
        shutil.copy2(self.path_config.KR_path, self.path_config.target_file)

    def _save_except(self):
        """依次尝试备份各种语言版本"""
        for saver in [self._save_llc, self._save_en, self._save_jp, self._save_kr]:
            try:
                saver()
                return
            except Exception:
                continue
        logger.error(f"无法保存 {self.path_config.real_name}，请检查文件路径")
        raise ProcesserExit(ProcessExitType.SAVE_EXCEPT)

    # ========== 日志增强 ==========

    def _log_processing_state(self, stage: str):
        """记录处理状态快照"""
        logger.info(
            f"[FileProcessor] {self.path_config.real_name} | {stage} | "
            f"rel={self.path_config.rel_path} | "
            f"type={'story' if self.is_story else 'skill' if self.is_skill else 'general'} | "
            f"translator={type(self.request_config.translator).__name__ if self.request_config.translator else 'N/A'}"
        )

    def _log_error_context(self, error: Exception):
        """记录详细的错误上下文"""
        context = {
            "文件相对路径": str(self.path_config.rel_path),
            "韩文源文件": str(self.path_config.KR_path),
            "目标输出": str(self.path_config.target_file),
            "错误类型": type(error).__name__,
            "错误信息": str(error)[:500],
            "文件类型": f"story={self.is_story}, skill={self.is_skill}",
            "翻译配置": (
                f"is_text={self.request_config.is_text_format}, "
                f"is_llm={self.request_config.is_llm}, "
                f"from_lang={self.request_config.from_lang}"
            ),
            "待翻译数量": len(self.translating_list),
        }
        logger.error(
            f"[FileProcessor] 文件处理失败:\n" +
            "\n".join(f"  {k}: {v}" for k, v in context.items())
        )

    def _dump_failed_request(self, request_text: dict, error: Exception):
        """将失败的请求保存到文件用于调试"""
        dump_dir = self.path_config.target_file.parent.parent.parent / "dump"
        dump_dir.mkdir(exist_ok=True)
        dump_file = dump_dir / f"{self.path_config.real_name}_failed_{int(os.times().elapsed)}.json"
        try:
            with open(dump_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "request": request_text,
                    "error": str(error),
                    "config": {
                        "is_text": self.request_config.is_text_format,
                        "is_llm": self.request_config.is_llm,
                        "from_lang": self.request_config.from_lang,
                    }
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"失败请求已保存到: {dump_file}")
        except Exception:
            logger.warning("无法保存失败请求dump")
