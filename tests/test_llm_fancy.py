"""LLM 文本美化（webutils/llm_fancy）测试。"""

import json
import sys
import types
from pathlib import Path

import pytest

if "openspeedy" not in sys.modules:
    openspeedy = types.ModuleType("openspeedy")
    openspeedy.SpeedController = type("SpeedController", (), {})
    openspeedy.ProcessInfo = type("ProcessInfo", (), {})
    for exception_name in (
        "OpenSpeedyError",
        "PlatformNotSupportedError",
        "DLLNotFoundError",
        "ProcessAccessDeniedError",
        "ProcessNotFoundError",
        "ProcessArchitectureMismatch",
        "InjectionError",
        "EjectionError",
        "SpeedRangeError",
        "SpeedControlError",
    ):
        setattr(openspeedy, exception_name, type(exception_name, (Exception,), {}))
    sys.modules["openspeedy"] = openspeedy

from webutils.fancy.bus import apply_bus, compile_bus_ruleset
from webutils.fancy.engine import RuleValidationError
from webutils.llm_fancy import (
    build_ruleset,
    build_system_prompt,
    compile_selection,
    dedup_candidates,
    parse_batch_response,
    scan_data,
    split_items,
    strip_code_fence,
    validate_selection,
)
from webutils.llm_fancy.config import LLMFancyConfig
from webutils.llm_fancy.runner import resolve_lang_dir


SAMPLE_DATA = {
    "dataList": [
        {"id": "101", "name": "旧文本A", "desc": "描述A"},
        {"id": "102", "name": "旧文本B", "desc": "-"},
        {"id": "103", "name": "", "desc": "描述C"},
    ],
    "meta": {"title": "标题"},
    "nested": {"list": ["一", "二", "三"]},
}


def make_selection(rules, **extra):
    return {
        "name": "测试选择",
        "files": ["*.json"],
        "rules": rules,
        **extra,
    }


# ============ scanner ============

def test_compile_selection_valid():
    compiled = compile_selection(make_selection([
        {"path": "dataList[*].name"},
        {"files": [{"regex": r"Skill.*"}], "path": "dataList[?id=101].desc"},
        {"path": ""},
    ]))
    assert compiled.name == "测试选择"
    assert len(compiled.rules) == 3


def test_compile_selection_rejects_invalid():
    errors = validate_selection({"name": "x", "rules": [{"path": "a..b"}]})
    assert errors
    errors = validate_selection({"name": "x", "rules": []})
    assert errors
    errors = validate_selection("not-a-dict")
    assert errors


def test_scan_data_wildcard_and_empty_skips():
    selection = compile_selection(make_selection([
        {"path": "dataList[*].name"},
    ]))
    candidates = scan_data(SAMPLE_DATA, "Skills.json", selection)
    values = [c.value for c in candidates]
    assert values == ["旧文本A", "旧文本B"]
    assert all(c.file == "Skills.json" for c in candidates)
    paths = [c.bus_path for c in candidates]
    assert "dataList[0].name" in paths


def test_scan_data_selector_and_desc():
    selection = compile_selection(make_selection([
        {"path": "dataList[?id=101].desc"},
    ]))
    candidates = scan_data(SAMPLE_DATA, "Skills.json", selection)
    assert [c.value for c in candidates] == ["描述A"]


def test_scan_data_index_token():
    selection = compile_selection(make_selection([
        {"path": "dataList[1].name"},
    ]))
    candidates = scan_data(SAMPLE_DATA, "Skills.json", selection)
    assert [c.value for c in candidates] == ["旧文本B"]


def test_scan_data_all_string_leaves():
    selection = compile_selection(make_selection([
        {"path": ""},
    ]))
    candidates = scan_data(SAMPLE_DATA, "Skills.json", selection)
    values = {c.value for c in candidates}
    assert "旧文本A" in values
    assert "标题" in values
    assert "一" in values
    assert "-" not in values
    assert "" not in values


def test_scan_data_file_matchers():
    selection = compile_selection(make_selection(
        [{"path": "meta.title"}],
        files=[{"exact": "Skills.json"}],
    ))
    assert len(scan_data(SAMPLE_DATA, "Skills.json", selection)) == 1
    assert len(scan_data(SAMPLE_DATA, "Story.json", selection)) == 0


def test_scan_data_rule_specific_files():
    selection = compile_selection(make_selection([
        {"files": [{"regex": r"Story.*"}], "path": "meta.title"},
    ]))
    assert len(scan_data(SAMPLE_DATA, "Skills.json", selection)) == 0
    assert len(scan_data(SAMPLE_DATA, "Story1.json", selection)) == 1


# ============ splitter ============

def test_split_items_respects_max_length():
    items = [("a", 300), ("b", 300), ("c", 300)]
    batches = split_items(items, lambda item: item[1], max_length=700)
    assert batches == [[("a", 300), ("b", 300)], [("c", 300)]]


def test_split_items_oversize_single():
    items = [("a", 5000), ("b", 10)]
    batches = split_items(items, lambda item: item[1], max_length=1000)
    assert batches == [[("a", 5000)], [("b", 10)]]


def test_split_items_empty():
    assert split_items([], lambda item: 1, max_length=1000) == []


# ============ dedup ============

def test_dedup_candidates_merges_identical_text():
    from webutils.llm_fancy.scanner import Candidate

    candidates = [
        Candidate(file="Skills.json", path=("dataList", 0, "name"), bus_path="dataList[0].name", value="相同文本"),
        Candidate(file="Skills.json", path=("dataList", 1, "name"), bus_path="dataList[1].name", value="相同文本"),
        Candidate(file="Characters.json", path=("dataList", 0, "name"), bus_path="dataList[0].name", value="相同文本"),
    ]
    representatives, groups = dedup_candidates(candidates)
    assert len(representatives) == 1
    assert representatives[0] is candidates[0]
    assert len(groups[0]) == 3


def test_dedup_candidates_preserves_distinct_text():
    from webutils.llm_fancy.scanner import Candidate

    candidates = [
        Candidate(file="Skills.json", path=("dataList", 0, "name"), bus_path="dataList[0].name", value="文本A"),
        Candidate(file="Skills.json", path=("dataList", 0, "desc"), bus_path="dataList[0].desc", value="文本B"),
    ]
    representatives, groups = dedup_candidates(candidates)
    assert len(representatives) == 2
    assert all(len(group) == 1 for group in groups.values())


# ============ llm parsing ============

def test_strip_code_fence():
    assert strip_code_fence("```json\n[1, 2]\n```") == "[1, 2]"
    assert strip_code_fence("```\n[1, 2]```") == "[1, 2]"
    assert strip_code_fence("[1, 2]") == "[1, 2]"


def test_parse_batch_response_aligned():
    response = json.dumps([{"id": 1, "text": "美化A"}, {"id": 2, "text": "美化B"}])
    assert parse_batch_response(response, 2) == ["美化A", "美化B"]


def test_parse_batch_response_missing_ids_filled_with_none():
    response = json.dumps([{"id": 1, "text": "美化A"}])
    assert parse_batch_response(response, 2) == ["美化A", None]


def test_parse_batch_response_rejects_non_array():
    with pytest.raises(ValueError):
        parse_batch_response("{\"foo\": 1}", 1)


def test_build_system_prompt_default_and_custom():
    assert "JSON 数组" in build_system_prompt()
    merged = build_system_prompt("请使用更文艺的风格", enabled=True)
    assert "更文艺" in merged
    assert build_system_prompt("忽略我", enabled=False) == build_system_prompt()


# ============ builder ============

def test_build_ruleset_validates_and_shapes():
    from webutils.llm_fancy.scanner import Candidate

    candidates = [
        (Candidate("Skills.json", ("dataList", 0, "name"), "dataList[0].name", "旧"), "新A"),
        (Candidate("Skills.json", ("dataList", 1, "desc"), "dataList[1].desc", "旧"), "新B"),
    ]
    ruleset = build_ruleset(candidates, name="LLM 文本美化 2026080601")
    assert ruleset["format"] == "lcta-bus"
    assert ruleset["version"] == 1
    assert ruleset["name"] == "LLM 文本美化 2026080601"
    assert len(ruleset["rules"]) == 2
    first = ruleset["rules"][0]
    assert first["files"] == [{"exact": "Skills.json"}]
    assert first["path"] == "dataList[0].name"
    assert first["replacements"] == [{"set": "新A"}]
    # 必须能通过 bus 引擎编译（最终会被 fancy_main 加载）
    compile_bus_ruleset(ruleset)


def test_build_ruleset_output_applies_via_bus_engine():
    from webutils.llm_fancy.scanner import Candidate

    candidates = [
        (Candidate("Skills.json", ("dataList", 0, "name"), "dataList[0].name", "旧文本A"), "新文本A"),
    ]
    ruleset = build_ruleset(candidates, name="测试应用")
    compiled = compile_bus_ruleset(ruleset)
    data = {"dataList": [{"name": "旧文本A"}]}
    result = apply_bus(data, compiled, "Skills.json")
    assert result.changed_count == 1
    assert data["dataList"][0]["name"] == "新文本A"


# ============ exclusion 集成 ============

def test_exclusion_skips_paths_handled_by_bus_rules(monkeypatch):
    from webutils.llm_fancy.exclude import compile_exclusion_rulesets, excluded_paths
    from webutils.fancy.bus import BUS_FORMAT

    exclusion = {
        "format": BUS_FORMAT,
        "version": 1,
        "name": "已有规则",
        "files": ["*.json"],
        "exclude_dirs": [],
        "rules": [{
            "name": "旧规则",
            "files": ["Skills.json"],
            "path": "dataList[*].name",
            "replacements": [{"from": "旧文本", "to": "已替换"}],
        }],
    }
    monkeypatch.setattr(
        "webutils.llm_fancy.exclude.load_fancy_folder_rules",
        lambda: [exclusion],
    )
    compiled, missing = compile_exclusion_rulesets(["已有规则"])
    assert missing == []
    data = {"dataList": [{"name": "旧文本A", "desc": "描述A"}, {"name": "旧文本B", "desc": "描述B"}]}
    excluded = excluded_paths(data, "Skills.json", compiled)
    assert excluded == {("dataList", 0, "name"), ("dataList", 1, "name")}

    # 扫描 + 排除联调：两个 name 都被排除，desc 不受影响
    selection = compile_selection(make_selection([{"path": "dataList[*].name"}, {"path": "dataList[*].desc"}]))
    candidates = scan_data(data, "Skills.json", selection)
    kept = [c for c in candidates if c.path not in excluded]
    assert [c.bus_path for c in kept] == ["dataList[0].desc", "dataList[1].desc"]


def test_compile_exclusion_rulesets_missing_name(monkeypatch):
    from webutils.llm_fancy.exclude import compile_exclusion_rulesets

    monkeypatch.setattr(
        "webutils.llm_fancy.exclude.load_fancy_folder_rules",
        lambda: [],
    )
    compiled, missing = compile_exclusion_rulesets(["不存在的规则集"])
    assert compiled == ()
    assert missing == ["不存在的规则集"]


# ============ config ============

def test_config_roundtrip():
    from webutils.llm_fancy.config import load_config, save_config

    from globalManagers.ConfigManager import ConfigManager

    cfg = LLMFancyConfig(
        selection=make_selection([{"path": "dataList[*].name"}]),
        exclusions=["已有规则"],
        custom_prompt="文艺一些",
        custom_prompt_enabled=True,
        max_length=9999,
        max_workers=2,
        dedup_enabled=False,
    )
    mgr = ConfigManager()
    save_config(mgr, cfg)
    loaded = load_config(mgr)
    assert loaded.selection["name"] == "测试选择"
    assert loaded.exclusions == ["已有规则"]
    assert loaded.custom_prompt == "文艺一些"
    assert loaded.custom_prompt_enabled is True
    assert loaded.max_length == 9999
    assert loaded.max_workers == 2
    assert loaded.dedup_enabled is False


def test_resolve_lang_dir(tmp_path, monkeypatch):
    from webutils.llm_fancy.runner import resolve_lang_dir

    lang = tmp_path / "LimbusCompany_Data" / "Lang"
    (lang / "LLC_zh-CN").mkdir(parents=True)
    (lang / "config.json").write_text(json.dumps({"lang": "LLC_zh-CN"}), encoding="utf-8")
    assert resolve_lang_dir(str(tmp_path)) == (lang / "LLC_zh-CN")

    with pytest.raises(ValueError):
        resolve_lang_dir(str(tmp_path / "missing"))


# ============ runner 端到端（假 translator） ============

def test_run_beautify_end_to_end(tmp_path, monkeypatch):
    from webutils.llm_fancy import runner as runner_module

    lang_dir = tmp_path / "LimbusCompany_Data" / "Lang" / "LLC_zh-CN"
    lang_dir.mkdir(parents=True)
    (tmp_path / "LimbusCompany_Data" / "Lang" / "config.json").write_text(
        json.dumps({"lang": "LLC_zh-CN"}), encoding="utf-8"
    )
    (lang_dir / "Skills.json").write_text(
        json.dumps({"dataList": [{"name": "旧文本A"}, {"name": "旧文本B"}]}, ensure_ascii=False),
        encoding="utf-8-sig",
    )

    class FakeTranslator:
        def __init__(self, *args, **kwargs):
            pass

        def update_config(self, **kwargs):
            pass

        def translate(self, user_prompt, from_lang, to_lang):
            items = json.loads(user_prompt)["items"]
            return json.dumps([
                {"id": item["id"], "text": "美化" + item["text"]}
                for item in items
            ])

    monkeypatch.setattr(runner_module, "build_translator", lambda *a, **k: FakeTranslator())

    # 隔离 fancy 文件夹（避免污染真实 fancy/）
    import webutils.function_fancy as function_fancy
    fake_fancy = tmp_path / "fancy"
    fake_fancy.mkdir()
    monkeypatch.setattr(function_fancy, "_get_fancy_folder", lambda: fake_fancy)

    # 隔离 ConfigManager 的 game_path
    from globalManagers.ConfigManager import ConfigManager
    monkeypatch.setattr(ConfigManager, "get", staticmethod(
        lambda key, default=None: str(tmp_path) if key == "game_path" else default
    ))
    monkeypatch.setattr(ConfigManager, "set", staticmethod(lambda *a, **k: None))

    cfg = LLMFancyConfig(
        selection=make_selection([{"path": "dataList[*].name"}]),
        exclusions=[],
        max_length=20000,
        max_workers=2,
    )
    logs = []
    result = runner_module.run_beautify(
        cfg,
        {"base_url": "https://example.com/v1", "model_name": "m", "api_key": "k"},
        on_log=logs.append,
        name="LLM 文本美化 2026080601",
    )
    assert result.candidates == 2
    assert result.changed == 2
    assert result.llm_failed == 0
    assert result.unchanged == 0
    assert result.ruleset_name == "LLM 文本美化 2026080601"
    assert Path(result.ruleset_path).exists()
    assert logs

    # 产物可被 bus 引擎编译并正确应用
    saved = json.loads(Path(result.ruleset_path).read_text(encoding="utf-8"))
    compiled = compile_bus_ruleset(saved)
    data = {"dataList": [{"name": "旧文本A"}, {"name": "旧文本B"}]}
    applied = apply_bus(data, compiled, "Skills.json")
    assert data["dataList"][0]["name"] == "美化旧文本A"
    assert data["dataList"][1]["name"] == "美化旧文本B"
    assert applied.changed_count == 2


def test_run_beautify_no_candidates_no_ruleset(tmp_path, monkeypatch):
    from webutils.llm_fancy import runner as runner_module

    lang_dir = tmp_path / "LimbusCompany_Data" / "Lang" / "LLC_zh-CN"
    lang_dir.mkdir(parents=True)
    (tmp_path / "LimbusCompany_Data" / "Lang" / "config.json").write_text(
        json.dumps({"lang": "LLC_zh-CN"}), encoding="utf-8"
    )
    (lang_dir / "Skills.json").write_text(
        json.dumps({"dataList": [{"name": "AAA"}, {"name": "BBB"}]}, ensure_ascii=False),
        encoding="utf-8-sig",
    )

    from globalManagers.ConfigManager import ConfigManager
    monkeypatch.setattr(ConfigManager, "get", staticmethod(
        lambda key, default=None: str(tmp_path) if key == "game_path" else default
    ))

    cfg = LLMFancyConfig(
        selection=make_selection([{"path": "dataList[*].zzz"}]),
        exclusions=[],
    )
    result = runner_module.run_beautify(cfg, {})
    assert result.candidates == 0
    assert result.ruleset_path == ""


def test_run_beautify_dedup_sends_identical_text_once(tmp_path, monkeypatch):
    from webutils.llm_fancy import runner as runner_module

    lang_dir = tmp_path / "LimbusCompany_Data" / "Lang" / "LLC_zh-CN"
    lang_dir.mkdir(parents=True)
    (tmp_path / "LimbusCompany_Data" / "Lang" / "config.json").write_text(
        json.dumps({"lang": "LLC_zh-CN"}), encoding="utf-8"
    )
    (lang_dir / "Skills.json").write_text(
        json.dumps({"dataList": [{"name": "相同文本"}, {"name": "相同文本"}]}, ensure_ascii=False),
        encoding="utf-8-sig",
    )
    (lang_dir / "Characters.json").write_text(
        json.dumps({"dataList": [{"name": "相同文本"}]}, ensure_ascii=False),
        encoding="utf-8-sig",
    )

    class FakeTranslator:
        def __init__(self, *args, **kwargs):
            self.total_items = 0

        def update_config(self, **kwargs):
            pass

        def translate(self, user_prompt, from_lang, to_lang):
            items = json.loads(user_prompt)["items"]
            self.total_items += len(items)
            return json.dumps([
                {"id": item["id"], "text": "美化" + item["text"]}
                for item in items
            ])

    fake = FakeTranslator()
    monkeypatch.setattr(runner_module, "build_translator", lambda *a, **k: fake)

    import webutils.function_fancy as function_fancy
    fake_fancy = tmp_path / "fancy"
    fake_fancy.mkdir()
    monkeypatch.setattr(function_fancy, "_get_fancy_folder", lambda: fake_fancy)

    from globalManagers.ConfigManager import ConfigManager
    monkeypatch.setattr(ConfigManager, "get", staticmethod(
        lambda key, default=None: str(tmp_path) if key == "game_path" else default
    ))
    monkeypatch.setattr(ConfigManager, "set", staticmethod(lambda *a, **k: None))

    cfg = LLMFancyConfig(
        selection=make_selection([{"path": "dataList[*].name"}]),
        exclusions=[],
        max_length=20000,
        max_workers=2,
        dedup_enabled=True,
    )
    result = runner_module.run_beautify(cfg, {"base_url": "x", "model_name": "m", "api_key": "k"})
    assert result.candidates == 3
    assert result.deduped == 2
    assert result.changed == 3
    assert result.llm_failed == 0
    assert fake.total_items == 1

    saved = json.loads(Path(result.ruleset_path).read_text(encoding="utf-8"))
    assert len(saved["rules"]) == 3
    compiled = compile_bus_ruleset(saved)
    data = {"dataList": [{"name": "相同文本"}, {"name": "相同文本"}]}
    applied = apply_bus(data, compiled, "Skills.json")
    assert data["dataList"][0]["name"] == "美化相同文本"
    assert data["dataList"][1]["name"] == "美化相同文本"
    assert applied.changed_count == 2
