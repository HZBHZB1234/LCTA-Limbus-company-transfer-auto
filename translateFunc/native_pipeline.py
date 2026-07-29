"""PyO3 bridge for the Rust-native translation engine."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from translateFunc.config import (
    PipelineSummary,
    ProcessOutcome,
    TranslateConfig,
    inject_thinking_mode,
)
from translateFunc.enums import ProcessResult


class NativeEngineUnavailable(RuntimeError):
    pass


def native_engine_available() -> bool:
    try:
        import _lcta_native  # noqa: F401
    except ImportError:
        return False
    return True


class NativeTranslationPipeline:
    """Compatibility adapter around the Rust TranslationJob API."""

    def __init__(self, config: TranslateConfig):
        self._config = config
        self._on_log: Callable[[str], None] = lambda message: None
        self._on_status: Callable[[str], None] = lambda message: None
        self._on_progress: Callable[[int, str], None] = lambda percent, message: None
        self._on_check_running: Callable[[], None] = lambda: None

    def set_callbacks(
        self,
        *,
        on_log: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_progress: Callable[[int, str], None] | None = None,
        on_check_running: Callable[[], None] | None = None,
    ) -> None:
        if on_log:
            self._on_log = on_log
        if on_status:
            self._on_status = on_status
        if on_progress:
            self._on_progress = on_progress
        if on_check_running:
            self._on_check_running = on_check_running

    def run(self) -> PipelineSummary:
        try:
            import _lcta_native
        except ImportError as exc:
            raise NativeEngineUnavailable(
                "未找到 _lcta_native 原生模块，请先构建 Rust 翻译引擎"
            ) from exc

        job = _lcta_native.start_translation(
            json.dumps(self._build_native_config(), ensure_ascii=False)
        )
        self._on_status("Rust 翻译引擎正在初始化")
        try:
            while not job.is_finished():
                self._dispatch_events(job.drain_events(200))
                self._on_check_running()
                time.sleep(0.05)
            self._dispatch_events(job.drain_events(1000))
            return self._decode_summary(job.wait())
        except BaseException:
            job.cancel()
            raise

    def _build_native_config(self) -> dict[str, Any]:
        api_settings = inject_thinking_mode(
            dict(self._config.translator_api), self._config.enable_thinking
        )
        provider = build_native_provider(self._config.translator_name, api_settings)

        files = max(1, int(self._config.file_concurrency))
        requests = max(1, int(self._config.request_concurrency))
        file_io = max(1, int(self._config.file_io_concurrency))
        return {
            "game_path": str(self._config.game_path),
            "output_dir": str(self._config.output_dir),
            "paths": {
                "kr": _optional_path(self._config.kr_path),
                "jp": _optional_path(self._config.jp_path),
                "en": _optional_path(self._config.en_path),
                "llc": _optional_path(self._config.llc_path),
            },
            "provider": provider,
            "concurrency": {
                "files": files if self._config.enable_concurrent else 1,
                "requests": requests if self._config.enable_concurrent else 1,
                "file_io": file_io if self._config.enable_concurrent else 1,
            },
            "pipeline": {
                "has_prefix": self._config.has_prefix,
                "save_result": self._config.save_result,
                "max_prompt_chars": 18000,
                "enable_self_check": self._config.enable_self_check,
                "enable_rule_validation": self._config.enable_rule_validation,
            },
            "rules": {
                "enable_proper": self._config.enable_proper,
                "enable_role": self._config.enable_role,
                "enable_skill": self._config.enable_skill,
                "auto_fetch_proper": self._config.auto_fetch_proper,
                "proper_path": _optional_path(self._config.proper_path),
            },
            "diagnostics": {
                "dump_path": _optional_path(self._config.dump_path) if self._config.dump else None,
            },
        }

    def _dispatch_events(self, raw_events: list[str]) -> None:
        for raw_event in raw_events:
            try:
                event = json.loads(raw_event)
            except (TypeError, json.JSONDecodeError):
                continue
            event_type = event.get("type")
            if event_type == "phase":
                phase = {
                    "scan": "正在扫描翻译文件",
                    "rules": "正在构建原生翻译规则快照",
                    "translate": "正在并发翻译",
                    "complete": "翻译处理完成",
                }.get(event.get("name"), str(event.get("name", "")))
                self._on_status(phase)
                self._on_log(phase)
            elif event_type == "progress":
                total = max(1, int(event.get("total", 1)))
                completed = int(event.get("completed", 0))
                file_name = str(event.get("file", ""))
                self._on_progress(
                    min(99, int(completed * 100 / total)),
                    f"已处理 {completed}/{total}: {file_name}",
                )
            elif event_type == "request_retry":
                self._on_log(
                    f"[{event.get('file', '')}] 网络请求重试 "
                    f"{event.get('attempt', '')}: {event.get('reason', '')}"
                )
            elif event_type == "log":
                self._on_log(str(event.get("message", "")))

    @staticmethod
    def _decode_summary(raw_summary: str) -> PipelineSummary:
        data = json.loads(raw_summary)
        summary = PipelineSummary(
            saved=list(data.get("saved", [])),
            skipped=list(data.get("skipped", [])),
            fallback=list(data.get("fallback", [])),
        )
        for error in data.get("errors", []):
            summary.errors.append(
                ProcessOutcome(
                    ProcessResult.SAVE_ERROR,
                    str(error.get("file", "<unknown>")),
                    {"reason": str(error.get("message", "Rust 翻译引擎错误"))},
                )
            )
        return summary


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def build_native_provider(
    translator_name: str, api_settings: dict[str, Any]
) -> dict[str, Any]:
    if translator_name == "空翻译器(使用原文)":
        return {"kind": "null"}
    if translator_name != "LLM通用翻译服务":
        raise ValueError(f"Rust 翻译引擎不支持服务: {translator_name}")

    extra_body = _dict_value(api_settings.get("extra_body"))
    for key in ("top_p", "frequency_penalty", "presence_penalty"):
        if api_settings.get(key) not in (None, ""):
            extra_body[key] = float(api_settings[key])
    return {
        "kind": "open_ai_compatible",
        "api_key": str(api_settings.get("api_key", "")),
        "base_url": str(
            api_settings.get("base_url") or "https://api.openai.com/v1"
        ),
        "model": str(
            api_settings.get("model_name")
            or api_settings.get("model")
            or "gpt-4o-mini"
        ),
        "temperature": float(api_settings.get("temperature", 0.0)),
        "max_tokens": _optional_int(api_settings.get("max_tokens")),
        "extra_body": extra_body,
        "timeout_seconds": int(api_settings.get("timeout", 120)),
        "max_retries": int(api_settings.get("max_retries", 3)),
    }


def _dict_value(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _optional_path(value: str | Path | None) -> str | None:
    if not value:
        return None
    return str(value)
