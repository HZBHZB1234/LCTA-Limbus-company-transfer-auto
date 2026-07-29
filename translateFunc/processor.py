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
import sys
import threading
import time
import traceback
import uuid

_logger = logging.getLogger("LCTA")  # 与 LogManager 一致的 logger，确保日志正确路由

from datetime import datetime
from translateFunc.enums import ProcessResult, FileType
from translateFunc.config import ProcessOutcome, TranslateConfig, FilePathConfig, _suppress_translatekit_log
from translateFunc.matcher.engine import MatcherEngine
from translateFunc.builder.request import RequestBuilder, EMPTY_TEXT, AVOID_PATH
from translateFunc.builder.stages import StageStrategy
from translateFunc.proper import flatten_dict_enhanced, update_dict_with_flattened
from translateFunc.validator import RuleBasedValidator
from translateFunc.recorder import TranslationRecorder
from translateFunc.diagnostics import (
    HttpResponseObserver,
    safe_json_value,
    serialize_exception,
)

EMPTY_DATA = [{"dataList": []}, {}, []]
EMPTY_DATA_LIST = [[], [{}]]
SUCCESS_CALL_STATUSES = {"success", "recovered"}

# 保护 processing_log.jsonl 的并发写入
_processing_log_lock = threading.Lock()


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
        recorder: "TranslationRecorder" = None,
    ):
        self.path_config = path_config
        self._engine = engine
        self._config = translate_config
        self._translator = translator
        self._recorder = recorder

        self._api_calls: list[dict] = []
        self._input_text_blocks: list[dict] = []
        self._input_reference: dict = {}
        self._last_failed_call: dict | None = None
        self._http_observer = HttpResponseObserver(translator)

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

    # ========== 主处理流程 ==========

    def process(self) -> ProcessOutcome:
        """执行完整的翻译处理。返回 ProcessOutcome。"""
        start_time = time.perf_counter()
        llm_calls = 0
        text_blocks_count = 0
        format_used = None
        formats_tried: list[str] = []
        outcome = None

        try:
            # 1. 加载 JSON 文件
            outcome = self._load_jsons()
            if outcome:
                self._write_processing_log(outcome, start_time)
                return outcome

            # 2. 检查空文件
            outcome = self._check_empty()
            if outcome:
                self._write_processing_log(outcome, start_time)
                return outcome

            # 3. 初始化基础数据
            self._init_base_data()

            # 4. 构建数据索引
            self._make_data_index()

            # 5. 检查是否已翻译
            try:
                outcome = self._check_translated()
                if outcome:
                    self._write_processing_log(outcome, start_time)
                    return outcome
            except Exception as e:
                _logger.exception(f"[{self.file_name}] _check_translated 异常: {e}")
                self._save_except()
                outcome = ProcessOutcome(
                    ProcessResult.SAVE_ERROR,
                    self.file_name,
                    {"reason": f"_check_translated 失败: {e}", "exception_type": type(e).__name__, "traceback": traceback.format_exc()},
                )
                self._write_processing_log(outcome, start_time)
                return outcome

            # 6. 获取待翻译列表
            self._get_translating()
            if not self.translating_list:
                outcome = ProcessOutcome(ProcessResult.ALREADY_TRANSLATED, self.file_name)
                self._write_processing_log(outcome, start_time)
                return outcome

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
                _logger.exception(f"[{self.file_name}] 翻译数量不匹配异常")
                self._save_except()
                outcome = ProcessOutcome(
                    ProcessResult.TRANSLATION_MISMATCH,
                    self.file_name,
                    {"reason": "译文数量与原文不匹配", "traceback": traceback.format_exc()},
                )
                self._write_processing_log(outcome, start_time)
                return outcome
            except Exception as e:
                _logger.exception(f"[{self.file_name}] 翻译处理异常: {e}")
                self._save_except()
                outcome = ProcessOutcome(
                    ProcessResult.SAVE_ERROR,
                    self.file_name,
                    {"reason": str(e), "exception_type": type(e).__name__, "traceback": traceback.format_exc()},
                )
                self._write_processing_log(outcome, start_time)
                return outcome

            # 9. 重建并保存
            self._de_get_translating_text(translated_data)
            result = self._de_get_translating()

            try:
                self._save_result(result)
            except Exception as e:
                _logger.exception(f"[{self.file_name}] 保存结果异常: {e}")
                outcome = ProcessOutcome(
                    ProcessResult.SAVE_ERROR,
                    self.file_name,
                    {"reason": str(e), "exception_type": type(e).__name__, "traceback": traceback.format_exc()},
                )
                self._write_processing_log(outcome, start_time)
                return outcome

            if had_fallback:
                outcome = ProcessOutcome(
                    ProcessResult.FALLBACK_TO_ORIGINAL,
                    self.file_name,
                    {"fallback_parts": "部分文本块回退为 KR 原文"},
                )
            else:
                outcome = ProcessOutcome(ProcessResult.SUCCESS_SAVED, self.file_name)

            self._write_processing_log(outcome, start_time)
            return outcome
        finally:
            if self._recorder is not None:
                active_exception = sys.exc_info()[1]
                try:
                    self._recorder.write_record({
                        "schema_version": 2,
                        "timestamp": datetime.now().isoformat(),
                        "file_name": self.file_name,
                        "text_blocks": self._input_text_blocks,
                        "reference": self._input_reference,
                        "api_calls": self._api_calls,
                        "outcome": outcome.result.name if outcome else "INTERNAL_ERROR",
                        "outcome_extra": outcome.extra if outcome else None,
                        "exception": serialize_exception(active_exception),
                        "call_summary": {
                            "total": len(self._api_calls),
                            "failed": sum(
                                1 for call in self._api_calls
                                if call.get("status") not in SUCCESS_CALL_STATUSES
                            ),
                        },
                        "elapsed_seconds": round(time.perf_counter() - start_time, 3),
                    })
                except Exception:
                    _logger.exception(
                        f"[{self.file_name}] 翻译 dump 写入失败: {self._recorder.file_path}"
                    )

    def _write_processing_log(self, outcome: ProcessOutcome, start_time: float) -> None:
        """将单文件处理结果追加写入 JSONL 日志文件。"""
        try:
            elapsed = time.perf_counter() - start_time
            extra = dict(outcome.extra or {})
            extra["elapsed_seconds"] = round(elapsed, 3)
            if self._last_failed_call is not None:
                extra.setdefault("last_failed_call", self._last_failed_call)
            outcome.extra = extra

            log_entry = {
                "file_name": outcome.file_name,
                "result": outcome.result.name,
                "elapsed_seconds": extra["elapsed_seconds"],
                "extra": safe_json_value(extra),
            }
            log_dir = self.path_config._PathConfig.target_path
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "processing_log.jsonl"
            line = json.dumps(log_entry, ensure_ascii=False) + "\n"
            with _processing_log_lock:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception:
            _logger.exception(f"处理日志写入失败 ({outcome.file_name})，但不影响主流程")

    def _call_ai(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        response_format: str,
        timeout: int,
        parser=None,
        parse_error_provider=None,
        prompt_format: str = "",
        part: int | None = None,
        attempt: int | None = None,
        metadata: dict | None = None,
    ) -> tuple[object, object, dict]:
        """执行一次 AI 调用，并完整记录请求、响应、HTTP 尝试和异常链。"""
        started_at = datetime.now()
        started_perf = time.perf_counter()
        record = {
            "call_id": uuid.uuid4().hex[:16],
            "stage": stage,
            "part": part,
            "attempt": attempt,
            "format": prompt_format,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_format": response_format,
            "timeout": timeout,
            "raw_response": None,
            "parsed_response": None,
            "parse_errors": [],
            "validation_errors": [],
            "http_attempts": [],
            "exception": None,
            "status": "internal_error",
            "failure_kind": None,
            "metadata": metadata or {},
            "started_at": started_at.isoformat(),
        }
        raw_response = None
        parsed_response = None
        caught_exception = None
        self._http_observer.begin()

        try:
            raw_response = self._translator.translate(user_prompt, timeout=timeout)
            record["raw_response"] = str(raw_response)
            parsed_response = parser(raw_response) if parser is not None else raw_response
            record["parsed_response"] = parsed_response
            if parser is not None and not parsed_response:
                record["status"] = "parse_error"
                record["failure_kind"] = "empty_parsed_response"
                parse_errors = (
                    parse_error_provider()
                    if parse_error_provider is not None else []
                )
                record["parse_errors"] = parse_errors or [{
                    "type": "EmptyParseResult",
                    "message": "解析结果为空或响应格式无效",
                }]
            else:
                record["status"] = "success"
            return raw_response, parsed_response, record
        except Exception as exc:
            caught_exception = exc
            record["exception"] = serialize_exception(exc)
            if raw_response is None:
                record["status"] = "api_error"
                record["failure_kind"] = "translator_exception"
            else:
                record["status"] = "parse_error"
                record["failure_kind"] = "parser_exception"
                parse_errors = (
                    parse_error_provider()
                    if parse_error_provider is not None else []
                )
                record["parse_errors"] = parse_errors or [{
                    "type": type(exc).__name__,
                    "message": str(exc),
                }]
            raise
        finally:
            record["http_attempts"] = self._http_observer.finish()
            record["finished_at"] = datetime.now().isoformat()
            record["elapsed_seconds"] = round(time.perf_counter() - started_perf, 3)
            if self._recorder is not None:
                self._api_calls.append(record)
            if record["status"] not in SUCCESS_CALL_STATUSES:
                self._remember_failed_call(record)
                self._log_call_failure(record, caught_exception)

    def _remember_failed_call(self, record: dict) -> None:
        """保存适合 processing_log 的最近失败调用摘要。"""
        http_attempts = record.get("http_attempts") or []
        last_http = http_attempts[-1] if http_attempts else {}
        raw_response = record.get("raw_response") or last_http.get("body") or ""
        self._last_failed_call = safe_json_value({
            "call_id": record.get("call_id"),
            "stage": record.get("stage"),
            "part": record.get("part"),
            "attempt": record.get("attempt"),
            "format": record.get("format"),
            "status": record.get("status"),
            "failure_kind": record.get("failure_kind"),
            "http_status": last_http.get("status_code"),
            "response_excerpt": str(raw_response)[:2000],
            "parse_errors": record.get("parse_errors", []),
            "validation_errors": record.get("validation_errors", []),
            "exception": record.get("exception"),
        })

    def _log_call_failure(self, record: dict, exc: Exception | None = None) -> None:
        """将可读错误摘要写入 app.log；完整内容保存在 dump。"""
        http_attempts = record.get("http_attempts") or []
        last_http = http_attempts[-1] if http_attempts else {}
        response = record.get("raw_response") or last_http.get("body") or ""
        response_excerpt = str(response)[:2000]
        message = (
            f"[{self.file_name}] AI 调用失败 "
            f"call_id={record.get('call_id')} stage={record.get('stage')} "
            f"part={record.get('part')} attempt={record.get('attempt')} "
            f"format={record.get('format')} status={record.get('status')} "
            f"failure={record.get('failure_kind')} "
            f"http_status={last_http.get('status_code')} "
            f"response_excerpt={response_excerpt!r}"
        )
        if exc is not None:
            _logger.error(
                message,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
        else:
            _logger.warning(message)

    def _mark_call_failure(
        self,
        record: dict,
        *,
        status: str,
        failure_kind: str,
        validation_errors: list | None = None,
        parse_errors: list | None = None,
    ) -> None:
        """在调用成功但后续校验失败时更新诊断状态。"""
        record["status"] = status
        record["failure_kind"] = failure_kind
        if validation_errors is not None:
            record.setdefault("validation_errors", []).extend(validation_errors)
        if parse_errors is not None:
            record.setdefault("parse_errors", []).extend(parse_errors)
        self._remember_failed_call(record)
        self._log_call_failure(record)

    def _mark_call_recovered(
        self,
        record: dict | None,
        *,
        recovery_kind: str,
        recovered_by: dict | None = None,
    ) -> None:
        """将已被后续步骤完整恢复的调用从失败状态改为 recovered。"""
        if not record or record.get("status") in SUCCESS_CALL_STATUSES:
            return

        metadata = record.setdefault("metadata", {})
        metadata.setdefault("recovered_status", record.get("status"))
        metadata.setdefault("recovered_failure_kind", record.get("failure_kind"))
        metadata["recovery_kind"] = recovery_kind
        if recovered_by is not None:
            metadata["recovered_by_call_id"] = recovered_by.get("call_id")
        record["status"] = "recovered"
        record["failure_kind"] = None
        self._refresh_last_failed_call()

    def _refresh_last_failed_call(self) -> None:
        """重新计算最近一个尚未恢复的失败调用。"""
        self._last_failed_call = None
        for call in reversed(self._api_calls):
            if call.get("status") not in SUCCESS_CALL_STATUSES:
                self._remember_failed_call(call)
                return

    def _record_diagnostic_event(
        self,
        *,
        stage: str,
        status: str,
        failure_kind: str | None = None,
        prompt_format: str = "",
        part: int | None = None,
        parsed_response=None,
        validation_errors: list | None = None,
        exc: Exception | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """记录不直接发起 HTTP 请求的管线诊断事件。"""
        now = datetime.now().isoformat()
        record = {
            "call_id": uuid.uuid4().hex[:16],
            "stage": stage,
            "part": part,
            "attempt": None,
            "format": prompt_format,
            "system_prompt": "",
            "user_prompt": "",
            "response_format": "",
            "timeout": 0,
            "raw_response": None,
            "parsed_response": parsed_response,
            "parse_errors": [],
            "validation_errors": validation_errors or [],
            "http_attempts": [],
            "exception": serialize_exception(exc),
            "status": status,
            "failure_kind": failure_kind,
            "metadata": metadata or {},
            "started_at": now,
            "finished_at": now,
            "elapsed_seconds": 0,
        }
        if self._recorder is not None:
            self._api_calls.append(record)
        if status not in SUCCESS_CALL_STATUSES:
            self._remember_failed_call(record)
        return record

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

            self._api_calls = []
            self._input_text_blocks = builder.unified_request.get("text_blocks", [])
            self._input_reference = builder.unified_request.get("reference", {})

            # ====== 阶段 0：消歧（仅主格式） ======
            user_format = self._config.prompt_format
            if stage_strategy.needs_disambiguation():
                _logger.debug(f"[{self.file_name}] 阶段 0: 术语消歧 (mode={self._config.disambiguation_mode})")
                ambiguous_terms = self._collect_ambiguous_terms(builder)
                if ambiguous_terms:
                    try:
                        s0_system = stage_strategy.build_stage_0_prompt(prompt_format=user_format)
                        self._update_translator_prompt(s0_system, self._format_to_response_format(user_format))
                        stage_0_parts = stage_strategy.split_stage_0_inputs(
                            ambiguous_terms,
                            builder.unified_request.get("text_blocks", []),
                            prompt_format=user_format,
                            max_length=builder.max_length,
                        )
                        for part_idx, stage_0_part in enumerate(stage_0_parts):
                            s0_call_started = False
                            try:
                                s0_user = stage_strategy.build_stage_0_user_prompt(
                                    stage_0_part["candidate_terms"],
                                    stage_0_part["text_blocks"],
                                    prompt_format=user_format,
                                )
                                s0_call_started = True
                                _, disambiguated, _ = self._call_ai(
                                    stage="stage_0",
                                    system_prompt=s0_system,
                                    user_prompt=s0_user,
                                    response_format=self._format_to_response_format(user_format),
                                    timeout=60,
                                    parser=lambda response: stage_strategy.parse_stage_0_result(
                                        response, prompt_format=user_format,
                                    ),
                                    parse_error_provider=stage_strategy.consume_parse_errors,
                                    prompt_format=user_format,
                                    part=part_idx + 1,
                                    attempt=1,
                                    metadata={
                                        "total_parts": len(stage_0_parts),
                                        "candidate_terms": len(stage_0_part["candidate_terms"]),
                                    },
                                )
                                if disambiguated:
                                    _logger.debug(
                                        f"[{self.file_name}] 阶段 0 消歧 "
                                        f"{part_idx + 1}/{len(stage_0_parts)}："
                                        f"{len(disambiguated)} 个术语被评估"
                                    )
                                    self._apply_disambiguation(builder, disambiguated)
                                else:
                                    _logger.debug(
                                        f"[{self.file_name}] 阶段 0 消歧 "
                                        f"{part_idx + 1}/{len(stage_0_parts)}：解析结果为空"
                                    )
                            except Exception as e:
                                if not s0_call_started:
                                    self._record_diagnostic_event(
                                        stage="stage_0",
                                        status="internal_error",
                                        failure_kind="prompt_or_config_error",
                                        prompt_format=user_format,
                                        part=part_idx + 1,
                                        exc=e,
                                        metadata={"total_parts": len(stage_0_parts)},
                                    )
                                _logger.exception(
                                    f"[{self.file_name}] 阶段 0 消歧 "
                                    f"{part_idx + 1}/{len(stage_0_parts)} 异常 ({e})，跳过该分片"
                                )
                        builder._split_by_length(prompt_format=user_format)
                    except Exception as e:
                        self._record_diagnostic_event(
                            stage="stage_0",
                            status="internal_error",
                            failure_kind="prompt_or_config_error",
                            prompt_format=user_format,
                            exc=e,
                        )
                        _logger.exception(f"[{self.file_name}] 阶段 0 消歧异常 ({e})，使用原始术语表继续")

            # 确定格式回退链
            formats_chain = self._build_format_chain()
            if len(formats_chain) > 1:
                _logger.info(
                    f"[{self.file_name}] 阶段 1: 主翻译 "
                    f"(格式链: {' → '.join(formats_chain)})"
                )
            else:
                _logger.debug(f"[{self.file_name}] 阶段 1: 主翻译 ({formats_chain[0]})")

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
                retry_indices: list[int] = []
                selected_call_record: dict | None = None
                failed_format_calls: list[dict] = []

                for fmt_idx, fmt in enumerate(formats_chain):
                    call_record = None
                    tried_formats.append(fmt)
                    # 按当前格式构建 system prompt
                    system_prompt = stage_strategy.build_stage_1_prompt(
                        self.file_type,
                        prompt_format=fmt,
                    )

                    # 按当前格式构建 user prompt
                    user_prompt = builder.get_request_text(prompt_format=fmt)
                    user_text = user_prompt[i] if i < len(user_prompt) else user_prompt[0]

                    # 自适应超时：基于实际请求长度 + 预期输出长度
                    input_len = len(json.dumps(request_part, ensure_ascii=False))
                    timeout = max(input_len * 3 // 400 + 40, 60)

                    # P0-3: LLM 调用前预检查分片大小，记录详细诊断数据
                    _rendered_len = len(user_text)
                    text_blocks_for_part = part_data.get("text_blocks", [])
                    ref_for_part = part_data.get("reference", {})
                    if _rendered_len > 20000:
                        _logger.warning(
                            f"[{self.file_name}] [{fmt}] 第 {i + 1}/{len(builder.split_requests)} 部分 "
                            f"超限: 渲染长度={_rendered_len} > 限制=20000 | "
                            f"text_blocks={len(text_blocks_for_part)} | "
                            f"proper_terms={len(ref_for_part.get('proper_terms', []))} | "
                            f"affects={len(ref_for_part.get('affects', []))} | "
                            f"models={len(ref_for_part.get('models', []))} | "
                            f"model_docs={len(ref_for_part.get('model_docs', []))} | "
                            f"skill_doc_len={len(ref_for_part.get('skill_doc', ''))}"
                        )

                    # 更新线程本地 translator 的 system_prompt 和 response_format
                    # 放在 try 外：配置更新失败不应被当作解析失败
                    try:
                        self._update_translator_prompt(system_prompt, self._format_to_response_format(fmt))
                    except Exception as exc:
                        self._record_diagnostic_event(
                            stage="stage_1",
                            status="internal_error",
                            failure_kind="translator_config_error",
                            prompt_format=fmt,
                            part=i + 1,
                            exc=exc,
                        )
                        raise

                    # 仅在 xml_json ↔ xml_xml 回退时清除缓存
                    # （两者共用 _make_xml_user_prompt 产生相同 user_text，
                    #  缓存键仅含 user_text hash，不区分 system_prompt/response_format）
                    # 其他格式回退（json_json）user_text 不同，无需清缓存
                    if fmt_idx > 0 and {formats_chain[fmt_idx - 1], fmt} == {"xml_json", "xml_xml"}:
                        self._translator.clear_cache()

                    try:
                        _, parsed, call_record = self._call_ai(
                            stage="stage_1",
                            system_prompt=system_prompt,
                            user_prompt=user_text,
                            response_format=self._format_to_response_format(fmt),
                            timeout=timeout,
                            parser=lambda response, current_format=fmt: (
                                stage_strategy.parse_stage_1_result(
                                    response, prompt_format=current_format,
                                )
                            ),
                            parse_error_provider=stage_strategy.consume_parse_errors,
                            prompt_format=fmt,
                            part=i + 1,
                            attempt=fmt_idx + 1,
                            metadata={
                                "rendered_length": _rendered_len,
                                "text_blocks": len(text_blocks_for_part),
                            },
                        )

                        if not parsed:
                            raise ValueError(f"{fmt}: 解析结果为空")

                        # 按 id 对齐解析结果与文本块（解决 LLM 跳过/重排条目导致的错位）
                        text_blocks = part_data.get("text_blocks", [])
                        expected_count = len(text_blocks)

                        # 构建 id → parsed_item 映射
                        parsed_by_id: dict[int, dict] = {}
                        for t in parsed:
                            if isinstance(t, dict):
                                try:
                                    tid = int(t.get("id", 0))
                                    if tid:
                                        parsed_by_id[tid] = t
                                except (ValueError, TypeError):
                                    continue

                        # 置信度检查准备
                        _CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
                        threshold = _CONFIDENCE_ORDER.get(self._config.min_confidence, 1)
                        low_conf_count = 0
                        low_confidence_ids: list[int] = []
                        missing_ids: list[int] = []

                        # 按 text_block 顺序（1-based id）提取翻译
                        part_result: list[str] = []
                        for idx, block in enumerate(text_blocks):
                            expected_id = idx + 1
                            t = parsed_by_id.get(expected_id)
                            if t is None and idx < len(parsed):
                                # id 未匹配，尝试按顺序回退（LLM 可能未输出 id）
                                fallback_t = parsed[idx]
                                if isinstance(fallback_t, dict):
                                    t = fallback_t

                            if t is not None and isinstance(t, dict):
                                translation = t.get("translation", "")
                                # 置信度检查：低于 min_confidence 的条目回退为 KR 原文
                                conf = str(t.get("confidence", "medium")).lower()
                                if _CONFIDENCE_ORDER.get(conf, 1) < threshold:
                                    reasoning = t.get("reasoning", "")
                                    _logger.warning(
                                        f"[{self.file_name}] [{fmt}] 低置信度条目 #{expected_id}: "
                                        f"confidence={conf}, reasoning={reasoning[:200]}"
                                    )
                                    low_conf_count += 1
                                    low_confidence_ids.append(expected_id)
                                    translation = block.get("kr", "")
                                part_result.append(translation)
                            else:
                                part_result.append(block.get("kr", ""))
                                missing_ids.append(expected_id)

                        # P1-1: 缺失条目时若还有剩余格式则尝试下一格式
                        if missing_ids:
                            if fmt_idx + 1 < len(formats_chain):
                                self._mark_call_failure(
                                    call_record,
                                    status="validation_error",
                                    failure_kind="missing_translation_ids",
                                    validation_errors=[{
                                        "missing_ids": missing_ids,
                                        "expected_count": expected_count,
                                        "action": "try_next_format",
                                    }],
                                )
                                _logger.warning(
                                    f"[{self.file_name}] [{fmt}] {len(missing_ids)} 个文本块缺失翻译 "
                                    f"(id: {missing_ids[:10]}...)，尝试下一格式"
                                )
                                failed_format_calls.append(call_record)
                                continue
                            self._mark_call_failure(
                                call_record,
                                status="fallback",
                                failure_kind="missing_translation_ids",
                                validation_errors=[{
                                    "missing_ids": missing_ids,
                                    "expected_count": expected_count,
                                    "action": "fallback_to_source",
                                }],
                            )
                            _logger.warning(
                                f"[{self.file_name}] [{fmt}] {len(missing_ids)} 个文本块缺失翻译 "
                                f"(id: {missing_ids[:10]}...)，已回退为 KR 原文"
                            )
                        if low_conf_count > 0:
                            self._mark_call_failure(
                                call_record,
                                status="fallback",
                                failure_kind="low_confidence",
                                validation_errors=[{
                                    "count": low_conf_count,
                                    "ids": low_confidence_ids,
                                    "minimum_confidence": self._config.min_confidence,
                                }],
                            )
                            _logger.info(
                                f"[{self.file_name}] [{fmt}] {low_conf_count} 条翻译因低置信度"
                                f" (min={self._config.min_confidence}) 回退为 KR 原文"
                            )

                        retry_indices = sorted({
                            *(expected_id - 1 for expected_id in missing_ids),
                            *(expected_id - 1 for expected_id in low_confidence_ids),
                        })
                        selected_call_record = call_record
                        break  # 翻译完整，退出格式回退循环

                    except (json.JSONDecodeError, ValueError) as e:
                        if call_record is not None:
                            failed_format_calls.append(call_record)
                        _logger.warning(
                            f"[{self.file_name}] [{fmt}] 解析失败 ({e})"
                        )
                        continue

                if part_result is None:
                    # 全部格式失败 → 无条件 warning + 标记降级
                    _logger.warning(
                        f"[{self.file_name}] 全部格式 ({', '.join(tried_formats)}) "
                        f"解析失败，第 {i + 1}/{len(builder.split_requests)} 部分回退为 KR 原文"
                    )
                    had_fallback = True
                    text_blocks = part_data.get("text_blocks", [])
                    part_result = [b.get("kr", "") for b in text_blocks]
                else:
                    # P1-2: 部分格式成功但存在缺失条目 → 补充翻译重试
                    text_blocks = part_data.get("text_blocks", [])
                    unresolved_count = len(retry_indices)
                    supplemental_call = None
                    if retry_indices and len(retry_indices) < len(text_blocks):
                        fixed = self._retry_missing_entries(
                            builder, stage_strategy, part_data, part_result,
                            retry_indices, tried_formats, i,
                        )
                        supplemental_call = self._api_calls[-1] if self._api_calls else None
                        unresolved_count -= fixed

                    if unresolved_count > 0:
                        had_fallback = True
                    else:
                        self._mark_call_recovered(
                            selected_call_record,
                            recovery_kind="supplemental_translation",
                            recovered_by=supplemental_call,
                        )

                    for failed_call in failed_format_calls:
                        self._mark_call_recovered(
                            failed_call,
                            recovery_kind="format_fallback",
                            recovered_by=selected_call_record,
                        )

                result.extend(part_result)

            # ====== 规则化后处理校验（技能文件专用） ======
            if self.is_skill and self._config.enable_rule_validation:
                _logger.debug(f"[{self.file_name}] 规则化后处理校验")
                try:
                    reference = builder.unified_request.get("reference", {})
                    affects_data = reference.get("affects", [])
                    if affects_data:
                        validator = RuleBasedValidator(affects_data)
                        text_blocks_for_check = builder.unified_request.get("text_blocks", [])
                        report = validator.run_all_checks(text_blocks_for_check, result)

                        error_count = sum(
                            1 for v in report.violations if v.severity == "error"
                        )
                        warn_count = report.warnings_remaining
                        if error_count > 0 or warn_count > 0:
                            _logger.info(
                                f"[{self.file_name}] 规则校验: {error_count} 个错误, "
                                f"{warn_count} 个警告"
                            )

                        # 应用自动修正
                        if report.auto_fixes_applied > 0:
                            result = validator.apply_auto_fixes(result, report.violations)
                            _logger.info(
                                f"[{self.file_name}] 规则校验自动修正了 "
                                f"{report.auto_fixes_applied} 处问题"
                            )

                        # 记录不可自动修正的违规
                        for v in report.violations:
                            if not v.auto_fixable:
                                _logger.warning(
                                    f"[{self.file_name}] [规则校验警告] "
                                    f"{v.rule}: {v.message} (block #{v.block_id})"
                                )

                        violations = [
                            {
                                "rule": v.rule,
                                "severity": v.severity,
                                "message": v.message,
                                "block_id": v.block_id,
                                "auto_fixable": v.auto_fixable,
                            }
                            for v in report.violations
                        ]
                        unresolved = [v for v in violations if not v["auto_fixable"]]
                        self._record_diagnostic_event(
                            stage="rule_validation",
                            status="validation_error" if unresolved else "success",
                            failure_kind="rule_validation" if unresolved else None,
                            prompt_format=user_format,
                            parsed_response=violations,
                            validation_errors=unresolved,
                            metadata={
                                "auto_fixes_applied": report.auto_fixes_applied,
                                "warnings_remaining": report.warnings_remaining,
                            },
                        )
                except Exception as e:
                    self._record_diagnostic_event(
                        stage="rule_validation",
                        status="internal_error",
                        failure_kind="validator_exception",
                        prompt_format=user_format,
                        exc=e,
                    )
                    _logger.exception(
                        f"[{self.file_name}] 规则化校验异常 ({e})，使用未校验的翻译结果"
                    )

            # ====== 阶段 2：自校验（仅主格式，阶段 1 全部成功时执行） ======
            if stage_strategy.needs_self_check() and not had_fallback:
                _logger.debug(f"[{self.file_name}] 阶段 2: 自校验")
                try:
                    original_blocks = builder.unified_request.get("text_blocks", [])
                    translations_for_check = [
                        {"id": i + 1, "translation": t}
                        for i, t in enumerate(result)
                    ]

                    s2_system = stage_strategy.build_stage_2_prompt(
                        self.file_type,
                        prompt_format=user_format,
                    )
                    self._update_translator_prompt(s2_system, self._format_to_response_format(user_format))
                    stage_2_parts = stage_strategy.split_stage_2_inputs(
                        original_blocks,
                        translations_for_check,
                        prompt_format=user_format,
                        reference=builder.unified_request.get("reference"),
                        max_length=builder.max_length,
                    )
                    for part_idx, stage_2_part in enumerate(stage_2_parts):
                        s2_call_started = False
                        try:
                            s2_user = stage_strategy.build_stage_2_user_prompt(
                                stage_2_part["original_blocks"],
                                stage_2_part["translations"],
                                prompt_format=user_format,
                                reference=stage_2_part["reference"],
                            )
                            s2_call_started = True
                            _, checked, _ = self._call_ai(
                                stage="stage_2",
                                system_prompt=s2_system,
                                user_prompt=s2_user,
                                response_format=self._format_to_response_format(user_format),
                                timeout=120,
                                parser=lambda response: stage_strategy.parse_stage_2_result(
                                    response, prompt_format=user_format,
                                ),
                                parse_error_provider=stage_strategy.consume_parse_errors,
                                prompt_format=user_format,
                                part=part_idx + 1,
                                attempt=1,
                                metadata={
                                    "total_parts": len(stage_2_parts),
                                    "offset": stage_2_part["offset"],
                                    "pair_count": len(stage_2_part["original_blocks"]),
                                },
                            )
                            if checked:
                                offset = stage_2_part["offset"]
                                global_checked = [
                                    {**item, "id": int(item.get("id", 0)) + offset}
                                    for item in checked
                                ]
                                result = self._apply_corrections(result, global_checked)
                            else:
                                _logger.debug(
                                    f"[{self.file_name}] 阶段 2 自校验 "
                                    f"{part_idx + 1}/{len(stage_2_parts)}：解析结果为空"
                                )
                        except Exception as e:
                            if not s2_call_started:
                                self._record_diagnostic_event(
                                    stage="stage_2",
                                    status="internal_error",
                                    failure_kind="prompt_or_config_error",
                                    prompt_format=user_format,
                                    part=part_idx + 1,
                                    exc=e,
                                    metadata={"total_parts": len(stage_2_parts)},
                                )
                            _logger.exception(
                                f"[{self.file_name}] 阶段 2 自校验 "
                                f"{part_idx + 1}/{len(stage_2_parts)} 异常 ({e})，跳过该分片"
                            )
                except Exception as e:
                    self._record_diagnostic_event(
                        stage="stage_2",
                        status="internal_error",
                        failure_kind="prompt_or_config_error",
                        prompt_format=user_format,
                        exc=e,
                    )
                    _logger.exception(
                        f"[{self.file_name}] 阶段 2 自校验异常 ({e})，使用未校验的翻译结果"
                    )

            return builder.deBuild(result), had_fallback
        else:
            # 非 LLM 路径：不存在格式回退
            simple_builder = _SimpleRequestBuilder(request_text)
            simple_builder.build()
            request_texts = simple_builder.get_request_text(from_lang=self._config.from_lang)
            result = self._translator.translate(request_texts)
            return simple_builder.deBuild(result), False

    def _retry_missing_entries(
        self,
        builder: "RequestBuilder",
        stage_strategy: "StageStrategy",
        part_data: dict,
        part_result: list[str],
        kr_fallback_indices: list[int],
        tried_formats: list[str],
        part_idx: int,
    ) -> int:
        """P1-2: 对全部格式均缺失的条目发起补充翻译重试。

        仅当 part_result 非空且缺失条目数 < 总条目数时调用——部分成功部分
        失败才发起补充翻译（全部失败时补充请求等同于完整重试，无意义）。

        Returns:
            成功修复的条目数。
        """
        text_blocks = part_data.get("text_blocks", [])
        missing_blocks = [text_blocks[idx] for idx in kr_fallback_indices]

        miss_proper_refs: set[str] = set()
        miss_affect_refs: set[str] = set()
        for block in missing_blocks:
            miss_proper_refs.update(block.get("proper_refs", []))
            miss_affect_refs.update(block.get("affect_refs", []))

        ref = builder.unified_request.get("reference", {})
        miss_reference = {
            "proper_terms": [t for t in ref.get("proper_terms", [])
                            if t.get("term", "") in miss_proper_refs],
            "affects": [a for a in ref.get("affects", [])
                       if f'[{a.get("id", "")}]' in miss_affect_refs],
            "models": ref.get("models", []),
            "model_docs": ref.get("model_docs", []),
            "skill_doc": ref.get("skill_doc", ""),
        }
        supp_request = {
            "metadata": {
                **builder.unified_request["metadata"],
                "total_text_blocks": len(missing_blocks),
            },
            "reference": miss_reference,
            "text_blocks": missing_blocks,
        }

        primary_format = tried_formats[0] if tried_formats else "xml_json"
        supp_user_text = builder._get_request_text(supp_request, primary_format)

        _logger.info(
            f"[{self.file_name}] P1-2 补充翻译: {len(kr_fallback_indices)} 个缺失条目 "
            f"(原 id: {[idx + 1 for idx in kr_fallback_indices][:10]}...)"
            f" | 请求长度={len(supp_user_text)}"
        )

        system_prompt = stage_strategy.build_stage_1_prompt(
            self.file_type, prompt_format=primary_format,
        )

        supp_call_started = False
        try:
            self._update_translator_prompt(
                system_prompt, self._format_to_response_format(primary_format),
            )
            timeout = max(len(supp_user_text) * 3 // 400 + 40, 60)
            supp_call_started = True
            _, supp_parsed, call_record = self._call_ai(
                stage="p1_2",
                system_prompt=system_prompt,
                user_prompt=supp_user_text,
                response_format=self._format_to_response_format(primary_format),
                timeout=timeout,
                parser=lambda response: stage_strategy.parse_stage_1_result(
                    response, prompt_format=primary_format,
                ),
                parse_error_provider=stage_strategy.consume_parse_errors,
                prompt_format=primary_format,
                part=part_idx + 1,
                attempt=1,
                metadata={
                    "missing_source_ids": [idx + 1 for idx in kr_fallback_indices],
                },
            )

            if not supp_parsed:
                _logger.info(f"[{self.file_name}] P1-2 补充翻译：解析结果为空，保留 KR 原文")
                return 0

            supp_by_id: dict[int, dict] = {}
            for t in supp_parsed:
                if isinstance(t, dict):
                    try:
                        tid = int(t.get("id", 0))
                        if tid:
                            supp_by_id[tid] = t
                    except (ValueError, TypeError):
                        continue

            fixed = 0
            confidence_order = {"low": 0, "medium": 1, "high": 2}
            confidence_threshold = confidence_order.get(self._config.min_confidence, 1)
            for local_idx, src_idx in enumerate(kr_fallback_indices):
                expected_id = local_idx + 1
                st = supp_by_id.get(expected_id)
                if st is not None and isinstance(st, dict):
                    trans = st.get("translation", "") or ""
                    confidence = str(st.get("confidence", "medium")).lower()
                    if trans and confidence_order.get(confidence, 1) >= confidence_threshold:
                        part_result[src_idx] = trans
                        fixed += 1

            requested = len(kr_fallback_indices)
            if fixed == requested:
                _logger.info(
                    f"[{self.file_name}] P1-2 补充翻译完成: "
                    f"修复 {fixed}/{requested} 条缺失"
                )
            else:
                self._mark_call_failure(
                    call_record,
                    status="fallback",
                    failure_kind="supplemental_translation_unresolved",
                    validation_errors=[{
                        "requested": requested,
                        "fixed": fixed,
                    }],
                )
                _logger.warning(
                    f"[{self.file_name}] P1-2 补充翻译：仍有 "
                    f"{requested - fixed}/{requested} 条未修复，保留 KR 原文"
                )
            return fixed

        except Exception as e:
            if not supp_call_started:
                self._record_diagnostic_event(
                    stage="p1_2",
                    status="internal_error",
                    failure_kind="prompt_or_config_error",
                    prompt_format=primary_format,
                    part=part_idx + 1,
                    exc=e,
                )
            _logger.exception(
                f"[{self.file_name}] P1-2 补充翻译异常 ({e})，保留 KR 原文"
            )
            return 0

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

    @staticmethod
    def _format_to_response_format(prompt_format: str) -> str:
        """prompt_format → response_format 映射。"""
        return "text" if prompt_format == "xml_xml" else "json_object"

    def _update_translator_prompt(self, system_prompt: str, response_format: str):
        """更新线程本地 translator 的 system_prompt 和 response_format，抑制日志。"""
        with _suppress_translatekit_log(self._config.debug_mode):
            self._translator.update_config(
                system_prompt=system_prompt,
                response_format=response_format,
            )

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
        if mode == "hybrid":
            _logger.debug(
                f"[{self.file_name}] hybrid 消歧模式："
                f"confidence 过滤需要 ProperAnalyzer 集成，当前收集全部匹配术语"
            )

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

        _logger.info(
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
            _logger.info(
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
                _logger.debug(f"[{self.file_name}] EN 参考文件缺失: {self.path_config.EN_path}")
                self.en_json = deepcopy(self.kr_json)
            try:
                with open(self.path_config.JP_path, "r", encoding="utf-8-sig") as f:
                    self.jp_json = json.load(f)
            except FileNotFoundError:
                _logger.debug(f"[{self.file_name}] JP 参考文件缺失: {self.path_config.JP_path}")
                self.jp_json = deepcopy(self.kr_json)
            try:
                with open(self.path_config.LLC_path, "r", encoding="utf-8-sig") as f:
                    self.llc_json = json.load(f)
            except FileNotFoundError:
                _logger.debug(f"[{self.file_name}] LLC 参考文件缺失: {self.path_config.LLC_path}")
                self.llc_json = {}
        except json.JSONDecodeError as e:
            _logger.exception(f"[{self.file_name}] JSON 解析失败: {self.path_config.KR_path} (line {e.lineno}, col {e.colno})")
            self._save_except()
            return ProcessOutcome(
                ProcessResult.JSON_DECODE_ERROR,
                self.file_name,
                {"file_path": str(self.path_config.KR_path), "reason": f"line {e.lineno}, col {e.colno}: {e.msg}"},
            )
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
            # 仅当 llc_index 非空时才对齐；空 LLC 意味着没有已翻译数据，不应生成虚假键
            if self.llc_index:
                self.llc_index = _align(self.llc_index, self.kr_index)

        # 验证 LLC 源文件确实存在，且索引键匹配
        if self.llc_index and list(self.kr_index.keys()) == list(self.llc_index.keys()):
            if self.path_config.LLC_path.exists():
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
            # 防御：部分 JSON 的 dataList 元素缺少 "id" 键，回退为 enumerate 索引
            def _make_non_story_index(data: list) -> dict:
                if data and isinstance(data[0], dict) and "id" in data[0]:
                    return {i["id"]: i for i in data}
                return {idx: item for idx, item in enumerate(data)}

            self.en_index = _make_non_story_index(self.en_data)
            self.kr_index = _make_non_story_index(self.kr_data)
            self.jp_index = _make_non_story_index(self.jp_data)
            self.llc_index = _make_non_story_index(self.llc_data)

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
        self.path_config.target_file.parent.mkdir(parents=True, exist_ok=True)
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
        _logger.warning(f"[{self.file_name}] 所有回退路径均不可用，无法保存结果文件")


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
        """将扁平翻译文本列表还原为嵌套字典结构。

        当翻译数量与预期不符时，不再抛出异常：
        - 不足时用 KR 原文填充缺失条目
        - 多余时截断并警告
        """
        original = deepcopy(getattr(self, f"{from_lang}_texts"))

        # 先计算预期数量，同时收集 KR 原文用于可能的回退填充
        expected_count = 0
        kr_fallbacks: list[str] = []
        for idx in original:
            kr_item = self.kr_texts.get(idx, {})
            jp_item = self.jp_texts.get(idx, {})
            en_item = self.en_texts.get(idx, {})
            for path_tuple in kr_item:
                jp_val = jp_item.get(path_tuple, "")
                en_val = en_item.get(path_tuple, "")
                kr_val = kr_item[path_tuple]
                if not (jp_val in EMPTY_TEXT and en_val in EMPTY_TEXT and kr_val in EMPTY_TEXT):
                    expected_count += 1
                    kr_fallbacks.append(kr_val)

        # 韧性处理：数量不匹配时用 KR 原文补齐或截断
        actual_count = len(translated_texts)
        if actual_count < expected_count:
            shortfall = expected_count - actual_count
            _logger.warning(
                f"译文数量不足: 预期 {expected_count}, 实际 {actual_count}"
                f"（{shortfall} 个文本块回退为 KR 原文）"
            )
            translated_texts = list(translated_texts) + kr_fallbacks[-shortfall:]
        elif actual_count > expected_count:
            excess = actual_count - expected_count
            _logger.warning(
                f"译文数量多于预期: 预期 {expected_count}, 实际 {actual_count}"
                f"（截断多余 {excess} 个）"
            )
            translated_texts = translated_texts[:expected_count]

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
        return original
