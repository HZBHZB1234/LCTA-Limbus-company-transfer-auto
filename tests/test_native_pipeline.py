import json
import sys
from types import SimpleNamespace

from translateFunc.config import TranslateConfig
from translateFunc.native_pipeline import NativeTranslationPipeline


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
        max_workers=8,
    )

    native = NativeTranslationPipeline(config)._build_native_config()

    assert native["provider"]["kind"] == "open_ai_compatible"
    assert native["provider"]["model"] == "test-model"
    assert native["provider"]["temperature"] == 0.2
    assert native["provider"]["max_tokens"] == 4096
    assert native["provider"]["extra_body"] == {"seed": 7}
    assert native["concurrency"] == {"files": 8, "requests": 16}


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
