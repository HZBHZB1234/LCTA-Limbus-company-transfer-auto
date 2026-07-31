import sys
import time
import types

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

from webutils.bus_engine import (
    IndexToken,
    KeyToken,
    SelectorToken,
    WildcardToken,
    apply_bus,
    compile_bus_ruleset,
    convert_edits_to_bus_ruleset,
    convert_tiaozhua_config,
    parse_bus_path,
)
from webutils.fancy_engine import RuleValidationError
from webutils.function_fancy import fancy_main, load_fancy_folder_rules, save_ruleset_to_folder
from webutils.function_drop import evalJson
from webutils import function_fancy, function_quick_editor, function_rule_editor


def make_ruleset(rules, **extra):
    return {
        "format": "lcta-bus",
        "version": 1,
        "name": "test",
        "files": ["*.json"],
        "exclude_dirs": [],
        "rules": rules,
        **extra,
    }


def test_parse_bus_path_supports_all_token_types():
    tokens = parse_bus_path("dataList[?id=101].levelList[*].coinlist[2].name")

    assert tokens == (
        KeyToken("dataList"),
        SelectorToken("id", "101"),
        KeyToken("levelList"),
        WildcardToken(),
        KeyToken("coinlist"),
        IndexToken(2),
        KeyToken("name"),
    )


@pytest.mark.parametrize("path", ["dataList..name", "dataList[?=1]", "dataList[abc]"])
def test_parse_bus_path_rejects_invalid_syntax(path):
    with pytest.raises(RuleValidationError):
        parse_bus_path(path)


def test_tiaozhua_conversion_preserves_regex_and_path_semantics():
    source = {
        "blacklist": ["Config"],
        "rules": [{
            "aimFile": "Skills.*\\.json$",
            "aim": "dataList.id[101].levelList.*.name",
            "action": [{"from": "肉斩", "to": "舍吾皮肉"}],
        }],
    }

    ruleset, stats = convert_tiaozhua_config(source, name="converted")

    assert ruleset["rules"][0]["files"] == [{"regex": "Skills.*\\.json$"}]
    assert ruleset["rules"][0]["path"] == "dataList[?id=101].levelList[*].name"
    assert ruleset["exclude_dirs"] == ["Config"]
    assert stats["converted_rules"] == 1


def test_rule_order_is_global_not_trie_node_order():
    ruleset = make_ruleset([
        {
            "path": "dataList.name",
            "replacements": [{"from": "A", "to": "B"}],
        },
        {
            "path": "dataList[0].name",
            "replacements": [{"from": "B", "to": "C"}],
        },
        {
            "path": "dataList[?id=1].name",
            "replacements": [{"from": "C", "to": "D"}],
        },
    ])
    data = {"dataList": [{"id": 1, "name": "A"}, {"id": 2, "name": "A"}]}

    result = apply_bus(data, compile_bus_ruleset(ruleset), "Skills.json")

    assert result.data["dataList"][0]["name"] == "D"
    assert result.data["dataList"][1]["name"] == "B"
    assert result.changed_count == 2


def test_global_rule_runs_in_converted_specificity_order():
    source = {
        "rules": [
            {"aimFile": "", "aim": "", "action": [{"from": "B", "to": "C"}]},
            {"aimFile": "Skills.*\\.json$", "aim": "dataList.name", "action": [{"from": "A", "to": "B"}]},
        ]
    }
    ruleset, _ = convert_tiaozhua_config(source, name="converted")

    result = apply_bus(
        {"dataList": [{"name": "A"}]},
        compile_bus_ruleset(ruleset),
        "Skills.json",
    )

    assert result.data["dataList"][0]["name"] == "C"


def test_empty_from_matches_reference_modes():
    ruleset = make_ruleset([
        {"path": "literal", "replacements": [{"from": "", "to": "-"}]},
        {"path": "regex", "replacements": [{"from": "", "to": "-", "mode": "regex"}]},
        {"path": "end", "replacements": [{"from": "", "to": "end", "mode": "end"}]},
    ])

    result = apply_bus(
        {"literal": "ab", "regex": "ab", "end": "ab"},
        compile_bus_ruleset(ruleset),
        "Any.json",
    )

    assert result.data == {
        "literal": "-a-b-",
        "regex": "-a-b-",
        "end": "end",
    }


def test_safe_replace_does_not_expand_existing_target_text():
    ruleset = make_ruleset([{
        "path": "name",
        "replacements": [{"from": "X", "to": "XX", "safe": True}],
    }])

    result = apply_bus({"name": "XX X"}, compile_bus_ruleset(ruleset), "Any.json")

    assert result.data["name"] == "XX XX"


def test_quick_edits_use_exact_set_and_can_create_dict_key():
    ruleset, report = convert_edits_to_bus_ruleset([
        {"file": "Skills.json", "path": "dataList.0.name", "old": "old", "new": "new"},
        {"file": "Skills.json", "path": "dataList.0.added", "old": None, "new": 3},
    ])

    result = apply_bus(
        {"dataList": [{"name": "package changed"}]},
        compile_bus_ruleset(ruleset),
        "Skills.json",
    )

    assert result.data == {"dataList": [{"name": "new", "added": 3}]}
    assert result.matched_rules == 2
    assert result.failed_rules == 0
    assert report["skipped"] == 0


def test_required_quick_edit_reports_missing_parent_path():
    ruleset, _ = convert_edits_to_bus_ruleset([
        {"file": "Skills.json", "path": "missing.0.name", "old": "old", "new": "new"},
    ])

    result = apply_bus({}, compile_bus_ruleset(ruleset), "Skills.json")

    assert result.matched_rules == 0
    assert result.failed_rules == 1
    assert "路径未命中" in result.errors[0]


def test_quick_edit_rejects_root_replacement():
    ruleset, report = convert_edits_to_bus_ruleset([
        {"file": "Skills.json", "path": "", "old": {}, "new": []},
    ])

    assert ruleset["rules"] == []
    assert report["skipped"] == 1
    assert "根节点" in report["warnings"][0]


def test_file_regex_uses_search_semantics_and_blacklist_is_case_insensitive():
    ruleset = make_ruleset([
        {
            "files": [{"regex": "Skills.*\\.json$"}],
            "path": "name",
            "replacements": [{"from": "A", "to": "B"}],
        }
    ], exclude_dirs=["Config"])
    compiled = compile_bus_ruleset(ruleset)

    matched = apply_bus({"name": "A"}, compiled, "fooSkills_test.json")
    excluded = apply_bus({"name": "A"}, compiled, "myCONFIG/fooSkills_test.json")

    assert matched.data["name"] == "B"
    assert excluded.data["name"] == "A"


def test_selector_workload_growth_is_bounded():
    def run(size):
        data = {"dataList": [{"id": index, "name": "A"} for index in range(size)]}
        rules = [
            {
                "path": f"dataList[?id={index}].name",
                "replacements": [{"from": "A", "to": "B"}],
            }
            for index in range(600)
        ]
        started = time.perf_counter()
        result = apply_bus(data, compile_bus_ruleset(make_ruleset(rules)), "Skills.json")
        return time.perf_counter() - started, result

    small_elapsed, small_result = run(500)
    large_elapsed, large_result = run(1000)

    assert small_result.changed_count == 500
    assert large_result.changed_count == 600
    assert small_elapsed < 2.0
    assert large_elapsed < max(3.0, small_elapsed * 3 + 0.1)


def test_fancy_main_preserves_v2_bus_ruleset_order(tmp_path):
    lang_dir = tmp_path / "LimbusCompany_Data" / "lang" / "LLC_zh-CN"
    lang_dir.mkdir(parents=True)
    target = lang_dir / "Skills.json"
    target.write_text('{"name":"A"}', encoding="utf-8")
    v2 = {
        "version": 2,
        "name": "v2",
        "rules": [{
            "files": ["Skills.json"],
            "scope": "",
            "targets": ["name"],
            "where": [],
            "actions": [{"type": "replace", "mode": "literal", "from": "A", "to": "B"}],
        }],
    }
    bus = make_ruleset([{
        "path": "name",
        "replacements": [{"from": "B", "to": "C"}],
    }])
    bus["name"] = "bus"

    stats = fancy_main(str(tmp_path), "LLC_zh-CN", [v2, bus])

    assert target.read_text(encoding="utf-8-sig").strip().endswith('"C"\n}')
    assert stats.files_changed == 1
    assert stats.values_changed == 1


def test_bus_ruleset_load_and_save_keep_version(monkeypatch, tmp_path):
    monkeypatch.setattr(function_fancy, "_get_fancy_folder", lambda: tmp_path)
    ruleset = make_ruleset([{
        "path": "name",
        "replacements": [{"from": "A", "to": "B"}],
    }])

    saved = save_ruleset_to_folder("bus", ruleset)
    loaded = load_fancy_folder_rules(str(tmp_path))

    assert saved.name == "bus.json"
    assert loaded[0]["format"] == "lcta-bus"
    assert loaded[0]["version"] == 1


def test_quick_editor_persists_bus_and_applies_exact_set(monkeypatch, tmp_path):
    fancy_dir = tmp_path / "fancy"
    lang_dir = tmp_path / "lang"
    lang_dir.mkdir()
    target = lang_dir / "Skills.json"
    target.write_text('{"dataList":[{"name":"package changed"}]}', encoding="utf-8")
    monkeypatch.setattr(function_quick_editor, "_get_fancy_folder", lambda: fancy_dir)
    monkeypatch.setattr(function_rule_editor, "_get_lang_dir", lambda: lang_dir)
    edits = [{
        "file": "Skills.json",
        "path": "dataList.0.name",
        "old": "old",
        "new": "new",
    }]

    saved = function_quick_editor.save_quick_edits(edits)
    applied = function_quick_editor.apply_quick_edits()
    stored = function_quick_editor.load_quick_edits()

    assert saved["success"] is True
    assert stored["format"] == "lcta-bus"
    assert stored["edits"] == edits
    assert applied == {"success": True, "applied": 1, "failed": 0, "errors": []}
    assert '"new"' in target.read_text(encoding="utf-8-sig")


def test_drag_drop_recognizes_bus_and_tiaozhua_json(tmp_path):
    bus_path = tmp_path / "bus.json"
    bus_path.write_text(
        '{"format":"lcta-bus","version":1,"name":"bus","rules":[]}',
        encoding="utf-8",
    )
    source_path = tmp_path / "source.json"
    source_path.write_text(
        '{"rules":[{"aimFile":"","aim":"","action":[]}]}',
        encoding="utf-8",
    )

    assert evalJson(str(bus_path)) == "busimport"
    assert evalJson(str(source_path)) == "busimport"


def test_import_bus_rules_file_uses_shared_conversion(monkeypatch, tmp_path):
    fancy_dir = tmp_path / "fancy"
    source_path = tmp_path / "source.json"
    source_path.write_text(
        '{"rules":[{"aimFile":"Skills.*\\\\.json$","aim":"dataList.name",'
        '"action":[{"from":"A","to":"B"}]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(function_fancy, "_get_fancy_folder", lambda: fancy_dir)

    imported = function_fancy.import_bus_rules_file(str(source_path))
    loaded = load_fancy_folder_rules(str(fancy_dir))

    assert imported["stats"]["converted_rules"] == 1
    assert loaded[0]["format"] == "lcta-bus"
