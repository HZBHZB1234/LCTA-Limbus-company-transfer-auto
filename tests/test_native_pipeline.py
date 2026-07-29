import json
import sys
from types import SimpleNamespace

from translateFunc.config import TranslateConfig
from translateFunc.native_pipeline import NativeTranslationPipeline, build_native_provider
from translateFunc.provider_config import format_api_settings


class _FakeJob:
    def __init__(self):
        self._finished_checks = 0
        self.cancelled = False

    def is_finished(self):
        self._finished_checks += 1
        return self._finished_checks > 1

    def drain_events(self, max_items=100):
        if self._finished_checks == 1:
            return [
                json.dumps({"type": "phase", "name": "translate"}),
                json.dumps(
                    {
                        "type": "progress",
                        "completed": 1,
                        "total": 2,
                        "file": "a.json",
                    }
                ),
            ]
        return []

    def wait(self):
        return json.dumps(
            {
                "total": 2,
                "saved": ["a.json"],
                "skipped": [],
                "fallback": ["b.json"],
                "errors": [],
            }
        )

    def cancel(self):
        self.cancelled = True


class _ConfigManagerStub:
    def __init__(self, translator, translator_config=None):
        self.translator = translator
        self.translator_config = translator_config or {}

    def get(self, key, default=None):
        if key == "ui_default.translator":
            return {"translator": self.translator, **self.translator_config}
        if key == "game_path":
            return ""
        if key == "debug":
            return False
        return default


def test_native_config_passes_complete_llm_request_settings(tmp_path):
    config = TranslateConfig(
        game_path=tmp_path / "game",
        output_dir=tmp_path / "out",
        translator_api={
            "api_key": "secret",
            "base_url": "https://example.invalid/v1",
            "model_name": "test-model",
            "temperature": "0.2",
            "max_tokens": "4096",
            "extra_body": {"seed": 7},
        },
        file_concurrency=32,
        request_concurrency=24,
        file_io_concurrency=48,
        enable_self_check=True,
        enable_rule_validation=False,
        enable_proper=True,
        enable_role=True,
        enable_skill=True,
        auto_fetch_proper=False,
        proper_path=str(tmp_path / "terms.json"),
        dump=True,
        dump_path=tmp_path / "logs" / "native.jsonl",
    )

    native = NativeTranslationPipeline(config)._build_native_config()

    assert native["provider"]["kind"] == "open_ai_compatible"
    assert native["provider"]["model"] == "test-model"
    assert native["provider"]["temperature"] == 0.2
    assert native["provider"]["max_tokens"] == 4096
    assert native["provider"]["extra_body"] == {"seed": 7}
    assert native["concurrency"] == {"files": 32, "requests": 24, "file_io": 48}
    assert native["pipeline"]["enable_self_check"] is True
    assert native["pipeline"]["enable_rule_validation"] is False
    assert native["rules"] == {
        "enable_proper": True,
        "enable_role": True,
        "enable_skill": True,
        "auto_fetch_proper": False,
        "proper_path": str(tmp_path / "terms.json"),
    }
    assert native["diagnostics"] == {
        "dump_path": str(tmp_path / "logs" / "native.jsonl"),
    }


def test_native_pipeline_dispatches_events_and_decodes_summary(monkeypatch, tmp_path):
    fake_job = _FakeJob()
    captured = {}

    def start_translation(config_json):
        captured["config"] = json.loads(config_json)
        return fake_job

    monkeypatch.setitem(
        sys.modules,
        "_lcta_native",
        SimpleNamespace(start_translation=start_translation),
    )
    config = TranslateConfig(
        game_path=tmp_path / "game",
        output_dir=tmp_path / "out",
        translator_api={"api_key": "secret"},
    )
    pipeline = NativeTranslationPipeline(config)
    logs = []
    progress = []
    pipeline.set_callbacks(
        on_log=logs.append,
        on_progress=lambda percent, message: progress.append((percent, message)),
    )

    summary = pipeline.run()

    assert captured["config"]["provider"]["api_key"] == "secret"
    assert summary.saved == ["a.json"]
    assert summary.fallback == ["b.json"]
    assert progress == [(50, "已处理 1/2: a.json")]
    assert "正在并发翻译" in logs


def test_static_provider_schema_builds_native_openai_config():
    settings = format_api_settings(
        "LLM通用翻译服务",
        {
            "api_key": "secret",
            "temperature": "0.1",
            "top_p": "0.8",
            "extra_body": '{"seed": 9}',
            "timeout": "90",
        },
    )

    provider = build_native_provider("LLM通用翻译服务", settings)

    assert provider["kind"] == "open_ai_compatible"
    assert provider["temperature"] == 0.1
    assert provider["timeout_seconds"] == 90
    assert provider["extra_body"] == {"seed": 9, "top_p": 0.8,
                                      "frequency_penalty": 0.0,
                                      "presence_penalty": 0.0}


def test_static_provider_schema_supports_null_provider():
    assert format_api_settings("空翻译器(使用原文)", {}) == {}
    assert build_native_provider("空翻译器(使用原文)", {}) == {"kind": "null"}


def test_legacy_provider_selection_migrates_to_native_llm():
    config = TranslateConfig.from_config_manager(_ConfigManagerStub("百度翻译服务"))

    assert config.translator_name == "LLM通用翻译服务"


def test_native_concurrency_config_is_parsed_and_bounded():
    config = TranslateConfig.from_config_manager(
        _ConfigManagerStub(
            "LLM通用翻译服务",
            {
                "file_concurrency": "999",
                "request_concurrency": "invalid",
                "file_io_concurrency": "0",
            },
        )
    )

    assert config.file_concurrency == 128
    assert config.request_concurrency == 16
    assert config.file_io_concurrency == 1
