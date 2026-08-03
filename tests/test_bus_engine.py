import json
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

from webutils.fancy.bus import (
    IndexToken,
    KeyToken,
    SelectorToken,
    WildcardToken,
    apply_bus,
    compile_bus_ruleset,
    convert_edits_to_bus_ruleset,
    convert_fl_config,
    convert_lcje_config,
    convert_tiaozhua_config,
    is_fl_config,
    is_lcje_config,
    is_tiaozhua_config,
    parse_bus_path,
)
from webutils.fancy.engine import RuleValidationError
from webutils.function_fancy import fancy_main, load_fancy_folder_rules, save_ruleset_to_folder
from webutils.drop import evalJson
from webutils import function_fancy
from webutils.rule_editor import quick as function_quick_editor
from webutils.rule_editor import browser as function_rule_editor


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


def test_glob_pattern_backslashes_are_normalized():
    ruleset = make_ruleset([
        {
            "files": ["Config\\Skills\\*.json"],
            "path": "name",
            "replacements": [{"from": "A", "to": "B"}],
        }
    ])
    compiled = compile_bus_ruleset(ruleset)

    matched = apply_bus({"name": "A"}, compiled, "Config/Skills/Skills.json")
    excluded = apply_bus({"name": "A"}, compiled, "Config/Other/Skills.json")

    assert matched.data["name"] == "B"
    assert excluded.data["name"] == "A"


def test_regex_pattern_backslashes_keep_escape_semantics():
    ruleset = make_ruleset([
        {
            "files": [{"regex": r"^Skills\.json$"}],
            "path": "name",
            "replacements": [{"from": "A", "to": "B"}],
        }
    ])
    compiled = compile_bus_ruleset(ruleset)

    matched = apply_bus({"name": "A"}, compiled, "Skills.json")
    escaped = apply_bus({"name": "A"}, compiled, "SkillsXjson")

    assert matched.data["name"] == "B"
    assert escaped.data["name"] == "A"


def test_tiaozhua_empty_rules_is_not_detected():
    assert not is_tiaozhua_config({"rules": []})
    assert not is_tiaozhua_config({"rules": [], "name": "empty"})


def test_lcje_config_detection():
    source = {
        "LLC_zh-CN\\Skills_personality-12.json": {
            "dataList[47].levelList[0].flavor": "天将拂晓",
        },
        "LLC_zh-CN\\PersonalityVoiceDlg\\Voice_Faust_Dawn_10216.json": {
            "dataList[14].dlg": "锋刃，齐射。",
        },
    }
    assert is_lcje_config(source)
    assert not is_lcje_config({})
    assert not is_lcje_config({"dataList": [{"name": "x"}]})
    assert not is_lcje_config({"Skills.json": "not a map"})
    assert not is_lcje_config({
        "format": "lcta-bus",
        "version": 1,
        "name": "bus",
        "rules": [],
    })
    assert not is_lcje_config({"rules": [{"action": []}]})
    assert not is_lcje_config({"LLC_zh-CN\\Skills.json": {}})


def test_lcje_conversion_preserves_paths_and_sets():
    source = {
        "LLC_zh-CN\\Skills_personality-12.json": {
            "dataList[47].levelList[0].flavor": "天将拂晓",
            "dataList[45].levelList[1].desc": "撕开黎明之剑",
        },
        "LLC_zh-CN\\PersonalityVoiceDlg\\Voice_Faust_Dawn_10216.json": {
            "dataList[14].dlg": "锋刃，齐射。",
        },
    }

    ruleset, stats = convert_lcje_config(source, name="converted")

    assert ruleset["desc"] == "由LCJE补丁配置机械转换导入"
    assert ruleset["files"] == ["*.json"]
    assert ruleset["exclude_dirs"] == []
    assert stats["source_rules"] == 3
    assert stats["converted_rules"] == 3
    assert stats["converted_actions"] == 3
    assert stats["skipped"] == 0
    assert ruleset["rules"][0]["files"] == [{"exact": "Skills_personality-12.json"}]
    assert ruleset["rules"][0]["path"] == "dataList[47].levelList[0].flavor"
    assert ruleset["rules"][0]["replacements"] == [{"set": "天将拂晓"}]
    assert ruleset["rules"][2]["files"] == [
        {"exact": "PersonalityVoiceDlg/Voice_Faust_Dawn_10216.json"}
    ]


def test_lcje_conversion_applies_exact_matches():
    source = {
        "LLC_zh-CN\\Skills_personality-12.json": {
            "dataList[47].levelList[0].flavor": "天将拂晓",
        },
    }
    ruleset, _ = convert_lcje_config(source, name="converted")
    compiled = compile_bus_ruleset(ruleset)

    lang_data = {
        "dataList": [
            {"id": index, "levelList": [{"flavor": "旧文本"}]}
            for index in range(48)
        ]
    }
    result = apply_bus(lang_data, compiled, "Skills_personality-12.json")

    assert result.data["dataList"][47]["levelList"][0]["flavor"] == "天将拂晓"
    assert result.data["dataList"][0]["levelList"][0]["flavor"] == "旧文本"
    assert result.changed_count == 1


def test_drag_drop_recognizes_lcje_json(tmp_path):
    source_path = tmp_path / "patch.json"
    source_path.write_text(
        '{"LLC_zh-CN\\\\Skills_personality-12.json":'
        '{"dataList[47].levelList[0].flavor":"天将拂晓"}}',
        encoding="utf-8",
    )

    assert evalJson(str(source_path)) == "busimport"


def test_import_bus_rules_file_accepts_lcje(monkeypatch, tmp_path):
    fancy_dir = tmp_path / "fancy"
    source_path = tmp_path / "source.json"
    source_path.write_text(
        '{"LLC_zh-CN\\\\Skills.json":{"dataList[0].name":"新名字"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(function_fancy, "_get_fancy_folder", lambda: fancy_dir)

    imported = function_fancy.import_bus_rules_file(str(source_path))
    loaded = load_fancy_folder_rules(str(fancy_dir))

    assert imported["stats"]["converted_rules"] == 1
    assert loaded[0]["format"] == "lcta-bus"
    assert loaded[0]["rules"][0]["replacements"] == [{"set": "新名字"}]


FL_SOURCE = {
    "LLC_zh-CN\\Personalities.json": {
        "dataList": [
            {"id": 10212, "changes": {"title": "小 - 黑兽 - 卯 魁首"}},
        ]
    },
    "LLC_zh-CN\\Skills_personality-02.json": {
        "dataList": [
            {"id": 1021201, "changes": {"levelList": [
                {"name": "顺..步?"},
                {"name": "顺..步?"},
                {"name": "顺..步?"},
            ]}},
            {"id": 1021202, "changes": {"levelList": [
                {"name": "窝将开批前路，原长。"},
                {"name": "窝将开批前路，原长。"},
            ]}},
            {"id": 1021206, "changes": {"levelList": [
                {"name": "嗯嗯！", "desc": "[CanDuelGuard]\n[SupportProtect]专用技能"},
                {"name": "嗯嗯！", "desc": "[CanDuelGuard]\n[SupportProtect]专用技能<style=\"highlight\"></style>"},
            ]}},
        ]
    },
}


def test_fl_config_detection():
    assert is_fl_config(FL_SOURCE)
    assert not is_fl_config({})
    assert not is_fl_config({"dataList": [{"name": "x"}]})
    assert not is_fl_config({"Skills.json": "not a map"})
    assert not is_fl_config({
        "format": "lcta-bus",
        "version": 1,
        "name": "bus",
        "rules": [],
    })
    assert not is_fl_config({"rules": [{"action": []}]})
    assert not is_fl_config({"LLC_zh-CN\\Skills.json": {}})
    assert not is_fl_config({
        "LLC_zh-CN\\Skills.json": {"dataList[0].levelList": [{"name": "x"}]},
    })
    assert not is_fl_config({
        "Skills.json": {
            "dataList": [
                {"id": 1, "changes": {"name": "x"}},
                {"name": "未包裹项"},
            ],
        },
    })
    assert not is_lcje_config(FL_SOURCE)


def test_fl_conversion_preserves_paths_and_sets():
    ruleset, stats = convert_fl_config(FL_SOURCE, name="converted")

    assert ruleset["desc"] == "由浮士德启动器自定义汉化补丁机械转换导入"
    assert ruleset["files"] == ["*.json"]
    assert ruleset["exclude_dirs"] == []
    assert stats["source_rules"] == 10
    assert stats["converted_rules"] == 10
    assert stats["converted_actions"] == 10
    assert stats["skipped"] == 0
    assert ruleset["rules"][0]["files"] == [{"exact": "Personalities.json"}]
    assert ruleset["rules"][0]["path"] == "dataList[?id=10212].title"
    assert ruleset["rules"][0]["replacements"] == [{"set": "小 - 黑兽 - 卯 魁首"}]
    assert ruleset["rules"][1]["files"] == [
        {"exact": "Skills_personality-02.json"}
    ]
    assert ruleset["rules"][1]["path"] == "dataList[?id=1021201].levelList[0].name"
    assert ruleset["rules"][3]["path"] == "dataList[?id=1021201].levelList[2].name"
    assert ruleset["rules"][4]["path"] == "dataList[?id=1021202].levelList[0].name"
    assert ruleset["rules"][6]["path"] == "dataList[?id=1021206].levelList[0].name"
    assert ruleset["rules"][9]["path"] == "dataList[?id=1021206].levelList[1].desc"
    assert ruleset["rules"][9]["replacements"] == [
        {"set": "[CanDuelGuard]\n[SupportProtect]专用技能<style=\"highlight\"></style>"}
    ]


def test_fl_conversion_applies_exact_matches():
    ruleset, _ = convert_fl_config(FL_SOURCE, name="converted")
    compiled = compile_bus_ruleset(ruleset)

    lang_data = {
        "dataList": [
            {
                "id": 10212,
                "title": "旧标题",
            },
            {
                "id": 1021206,
                "levelList": [
                    {"name": "旧名", "desc": "旧描述"},
                    {"name": "旧名", "desc": "旧描述"},
                    {"name": "未改动", "desc": "保持"},
                ],
            },
        ]
    }
    result = apply_bus(lang_data, compiled, "Skills_personality-02.json")

    target = next(item for item in result.data["dataList"] if item["id"] == 1021206)
    assert target["levelList"][0]["name"] == "嗯嗯！"
    assert target["levelList"][1]["desc"].endswith("<style=\"highlight\"></style>")
    assert target["levelList"][2]["name"] == "未改动"
    assert result.changed_count == 4
    assert result.data["dataList"][0]["title"] == "旧标题"


def test_drag_drop_recognizes_fl_json(tmp_path):
    source_path = tmp_path / "changes.json"
    source_path.write_text(
        json.dumps(FL_SOURCE, ensure_ascii=False),
        encoding="utf-8",
    )

    assert evalJson(str(source_path)) == "busimport"


def test_import_bus_rules_file_accepts_fl(monkeypatch, tmp_path):
    fancy_dir = tmp_path / "fancy"
    source_path = tmp_path / "changes.json"
    source_path.write_text(
        json.dumps(FL_SOURCE, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(function_fancy, "_get_fancy_folder", lambda: fancy_dir)

    imported = function_fancy.import_bus_rules_file(str(source_path))
    loaded = load_fancy_folder_rules(str(fancy_dir))

    assert imported["stats"]["converted_rules"] == 10
    assert loaded[0]["format"] == "lcta-bus"
    assert loaded[0]["rules"][0]["path"] == "dataList[?id=10212].title"
    assert loaded[0]["rules"][1]["path"] == "dataList[?id=1021201].levelList[0].name"


def test_path_cache_revalidates_after_structural_mutation():
    ruleset = make_ruleset([
        {
            "path": "list[?id=5].name",
            "replacements": [{"from": "A", "to": "A"}],
        },
        {
            "path": "list",
            "replacements": [{"set": [{"id": 1, "name": "A"}, {"id": 5, "name": "B"}]}],
        },
        {
            "path": "list[?id=5].name",
            "replacements": [{"from": "B", "to": "X"}],
        },
    ])

    result = apply_bus(
        {"list": [{"id": 5, "name": "A"}]},
        compile_bus_ruleset(ruleset),
        "Skills.json",
    )

    assert result.data["list"][0]["name"] == "A"
    assert result.data["list"][1]["name"] == "X"


def test_global_rules_share_string_leaf_traversal(monkeypatch):
    from webutils.fancy import bus as bus_engine

    calls = []
    original = bus_engine._iter_string_leaf_paths

    def counting(data):
        calls.append(True)
        return original(data)

    monkeypatch.setattr(bus_engine, "_iter_string_leaf_paths", counting)
    rules = [
        {"path": "", "replacements": [{"from": "x", "to": "y"}]}
        for _ in range(100)
    ]
    data = {"dataList": [{"name": "x"} for _ in range(2000)]}

    result = apply_bus(data, compile_bus_ruleset(make_ruleset(rules)), "Skills.json")

    assert result.changed_count == 2000
    assert len(calls) == 1


def test_identical_path_rules_share_resolution(monkeypatch):
    from webutils.fancy import bus as bus_engine

    calls = []
    original = bus_engine._resolve_paths

    def counting(data, tokens, *, allow_missing_final):
        calls.append(tokens)
        return original(data, tokens, allow_missing_final=allow_missing_final)

    monkeypatch.setattr(bus_engine, "_resolve_paths", counting)
    ruleset = make_ruleset([
        {"path": "dataList[0].name", "replacements": [{"from": "A", "to": "B"}]},
        {"path": "dataList[0].name", "replacements": [{"from": "B", "to": "C"}]},
    ])

    result = apply_bus(
        {"dataList": [{"name": "A"}]},
        compile_bus_ruleset(ruleset),
        "Skills.json",
    )

    assert result.data["dataList"][0]["name"] == "C"
    assert len(calls) == 1


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
        "old": "package changed",
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


def test_quick_editor_applies_matching_edits_and_reports_stale_ones(monkeypatch, tmp_path):
    fancy_dir = tmp_path / "fancy"
    lang_dir = tmp_path / "lang"
    lang_dir.mkdir()
    target = lang_dir / "Skills.json"
    target.write_text('{"dataList":[{"name":"original"}]}', encoding="utf-8")
    monkeypatch.setattr(function_quick_editor, "_get_fancy_folder", lambda: fancy_dir)
    monkeypatch.setattr(function_rule_editor, "_get_lang_dir", lambda: lang_dir)
    edits = [
        {"file": "Skills.json", "path": "dataList.0.name", "old": "original", "new": "patched"},
        {"file": "Skills.json", "path": "dataList.0.added", "old": None, "new": "inserted"},
        {"file": "Skills.json", "path": "dataList.0.name", "old": "stale", "new": "should-not-write"},
    ]

    saved = function_quick_editor.save_quick_edits(edits)
    applied = function_quick_editor.apply_quick_edits()

    assert saved["success"] is True
    assert applied["success"] is False
    assert applied["applied"] == 2
    assert applied["failed"] == 1
    assert "原值不匹配" in applied["errors"][0]
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    assert data["dataList"][0]["name"] == "patched"
    assert data["dataList"][0]["added"] == "inserted"


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
