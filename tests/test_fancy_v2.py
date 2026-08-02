import json
from pathlib import Path

from webutils.rule_editor import browser as rule_editor
from webutils.rule_editor import generate as rule_editor_generate
from webutils.fancy.builtin_func import SkillColorHandler
from webutils.function_fancy import fancy_main, load_fancy_folder_rules
from webutils.rule_editor import (
    apply_ruleset_to_content,
    build_rule_from_form,
    validate_rule,
)


def make_ruleset(rule):
    return {"version": 2, "name": "test", "desc": "", "rules": [rule]}


def test_rule_editor_builds_v2_rule():
    rule = build_rule_from_form({
        "file_pattern": "Skill",
        "scope": "dataList[*]",
        "target_paths": ["desc"],
        "item_ids": [10001, 10002],
        "extra_conditions": [{"path": "name", "operator": "contains", "value": "斩"}],
        "operations": [{"type": "replace", "mode": "literal", "from": "大于", "to": ">"}],
    })

    assert rule["files"] == ["Skill*.json"]
    assert rule["scope"] == "dataList[*]"
    assert rule["targets"] == ["desc"]
    assert rule["where"][0] == {"path": "id", "operator": "in", "value": [10001, 10002]}
    assert validate_rule(json.dumps(rule, ensure_ascii=False))["valid"]


def test_rule_editor_rejects_invalid_v2_regex():
    ruleset = make_ruleset({
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["desc"],
        "where": [{"path": "id", "operator": "regex", "value": "("}],
        "actions": [{"type": "replace", "mode": "literal", "from": "a", "to": "b"}],
    })

    result = validate_rule(json.dumps(ruleset, ensure_ascii=False))

    assert not result["valid"]
    assert "正则错误" in result["errors"][0]


def test_fancy_main_skips_unchanged_files(tmp_path):
    package_dir = tmp_path / "LimbusCompany_Data" / "lang" / "LLC_zh-CN"
    package_dir.mkdir(parents=True)
    target_file = package_dir / "Skills.json"
    target_file.write_text(json.dumps({"dataList": [{"desc": "没有命中"}]}, ensure_ascii=False), encoding="utf-8-sig")
    original_mtime = target_file.stat().st_mtime_ns
    ruleset = make_ruleset({
        "files": ["Skill*.json"],
        "scope": "dataList[*]",
        "targets": ["desc"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "大于", "to": ">"}],
    })

    stats = fancy_main(str(tmp_path), "LLC_zh-CN", [ruleset])

    assert stats.files_matched == 1
    assert stats.files_changed == 0
    assert stats.values_changed == 0
    assert target_file.stat().st_mtime_ns == original_mtime


def test_fancy_main_writes_changed_files(tmp_path):
    package_dir = tmp_path / "LimbusCompany_Data" / "lang" / "LLC_zh-CN"
    package_dir.mkdir(parents=True)
    target_file = package_dir / "Skills.json"
    target_file.write_text(json.dumps({"dataList": [{"desc": "大于目标"}]}, ensure_ascii=False), encoding="utf-8-sig")
    ruleset = make_ruleset({
        "files": ["Skill*.json"],
        "scope": "dataList[*]",
        "targets": ["desc"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "大于", "to": ">"}],
    })

    stats = fancy_main(str(tmp_path), "LLC_zh-CN", [ruleset])

    saved = json.loads(target_file.read_text(encoding="utf-8-sig"))
    assert saved["dataList"][0]["desc"] == ">目标"
    assert stats.files_changed == 1
    assert stats.values_changed == 1


def test_fancy_main_only_prepares_skill_cache_for_enabled_rulesets(monkeypatch, tmp_path):
    package_dir = tmp_path / "LimbusCompany_Data" / "lang" / "LLC_zh-CN"
    package_dir.mkdir(parents=True)
    skill_ruleset = {
        "version": 2,
        "name": "skill-cache",
        "rules": [{
            "files": ["Skill*.json"],
            "scope": "dataList[*]",
            "targets": ["name"],
            "where": [],
            "actions": [{"type": "skill_color", "idPath": "id"}],
        }],
    }
    plain_ruleset = make_ruleset({
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["desc"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "a", "to": "b"}],
    })
    plain_ruleset["name"] = "plain"
    calls = {"count": 0}

    def prepare():
        calls["count"] += 1
        return True

    monkeypatch.setattr("webutils.fancy.builtin_func.skillColorHandler.prepare", prepare)

    fancy_main(
        str(tmp_path),
        "LLC_zh-CN",
        [skill_ruleset, plain_ruleset],
        {"skill-cache": False, "plain": True},
    )
    assert calls["count"] == 0

    fancy_main(
        str(tmp_path),
        "LLC_zh-CN",
        [skill_ruleset, plain_ruleset],
        {"skill-cache": True, "plain": False},
    )
    assert calls["count"] == 1


def test_load_fancy_folder_rules_accepts_bom(tmp_path):
    ruleset = make_ruleset({
        "files": ["*.json"],
        "scope": "",
        "targets": ["name"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "A", "to": "B"}],
    })
    ruleset["name"] = "bom-rules"
    (tmp_path / "bom_rules.json").write_text(
        json.dumps(ruleset, ensure_ascii=False),
        encoding="utf-8-sig",
    )
    (tmp_path / "plain_rules.json").write_text(
        json.dumps(ruleset, ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = load_fancy_folder_rules(str(tmp_path))

    assert [r["name"] for r in loaded] == ["bom-rules", "bom-rules"]


def test_fancy_main_resets_stale_cache_hit_on_ready_shortcut(tmp_path):
    package_dir = tmp_path / "LimbusCompany_Data" / "lang" / "LLC_zh-CN"
    package_dir.mkdir(parents=True)
    skill_ruleset = {
        "version": 2,
        "name": "skill-cache",
        "rules": [{
            "files": ["Skill*.json"],
            "scope": "dataList[*]",
            "targets": ["name"],
            "where": [],
            "actions": [{"type": "skill_color", "idPath": "id"}],
        }],
    }
    from webutils.fancy.builtin_func import skillColorHandler

    skillColorHandler.state = "ready"
    skillColorHandler.last_cache_hit = True
    try:
        stats = fancy_main(str(tmp_path), "LLC_zh-CN", [skill_ruleset])
        assert stats.resource_cache_hit is False
    finally:
        skillColorHandler.reset()


def test_rule_editor_searches_bom_and_unparseable_file_content(monkeypatch, tmp_path):
    (tmp_path / "Skills_BOM.json").write_text(
        '{"dataList":[{"desc":"目标目标"}]}',
        encoding="utf-8-sig",
    )
    (tmp_path / "Story_raw.json").write_text(
        'not valid json, but contains 目标',
        encoding="utf-8",
    )
    monkeypatch.setattr(rule_editor, "_get_lang_dir", lambda: tmp_path)

    result = rule_editor.search_files("目标")

    assert result["total_matches"] == 3
    assert result["results_by_category"]["技能"] == [("Skills_BOM.json", 2)]
    assert result["results_by_category"]["故事"] == [("Story_raw.json", 1)]


def test_rule_editor_file_content_bom_roundtrip(monkeypatch, tmp_path):
    target = tmp_path / "Skills.json"
    target.write_text('{"dataList":[{"desc":"目标"}]}', encoding="utf-8-sig")
    monkeypatch.setattr(rule_editor, "_get_lang_dir", lambda: tmp_path)

    loaded = rule_editor.get_file_content("Skills.json")

    assert "error" not in loaded
    assert loaded["parsed"] == {"dataList": [{"desc": "目标"}]}
    assert not loaded["raw"].startswith("\ufeff")

    saved = rule_editor.save_file_content("Skills.json", '{"dataList":[{"desc":"新文本"}]}')

    assert saved["success"] is True
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    assert json.loads(target.read_text(encoding="utf-8-sig"))["dataList"][0]["desc"] == "新文本"


def test_rule_editor_rejects_path_traversal(monkeypatch, tmp_path):
    lang_dir = tmp_path / "lang"
    lang_dir.mkdir()
    outside = tmp_path / "evil.json"
    outside.write_text('{"secret": true}', encoding="utf-8")
    monkeypatch.setattr(rule_editor, "_get_lang_dir", lambda: lang_dir)

    read_result = rule_editor.get_file_content("../evil.json")

    assert read_result == {"error": "文件路径超出语言包目录: ../evil.json"}

    save_result = rule_editor.save_file_content("../evil.json", '{"x": 1}')

    assert save_result["success"] is False
    assert "超出" in save_result["error"]

    assert rule_editor.get_file_content(str(outside)).get("error") == "文件路径超出语言包目录: " + str(outside)
    assert json.loads(outside.read_text(encoding="utf-8")) == {"secret": True}


def test_rule_editor_analyze_value_change_classification():
    wrapped = rule_editor_generate._analyze_value_change("123", "<c>123</c>")
    assert wrapped["change_type"] == "PURE_WRAP"
    assert wrapped["prefix_added"] == "<c>"
    assert wrapped["suffix_added"] == "</c>"
    assert wrapped["core_old"] == "123"
    assert wrapped["core_new"] == "<c>123</c>"

    prefixed = rule_editor_generate._analyze_value_change("目标", ">目标")
    assert prefixed["change_type"] == "PREFIX_ONLY"
    assert prefixed["prefix_added"] == ">"
    assert prefixed["suffix_added"] == ""

    suffixed = rule_editor_generate._analyze_value_change("目标", "目标。")
    assert suffixed["change_type"] == "SUFFIX_ONLY"
    assert suffixed["prefix_added"] == ""
    assert suffixed["suffix_added"] == "。"

    replaced = rule_editor_generate._analyze_value_change("大于", ">")
    assert replaced["change_type"] == "PURE_REPLACE"
    assert replaced["prefix_added"] == ""
    assert replaced["suffix_added"] == ""
    assert replaced["core_old"] == "大于"
    assert replaced["core_new"] == ">"

    middle = rule_editor_generate._analyze_value_change("AB目标CD", "AB>CD")
    assert middle["change_type"] == "PURE_REPLACE"
    assert middle["prefix_added"] == ""
    assert middle["suffix_added"] == ""
    assert middle["core_old"] == "目标"
    assert middle["core_new"] == ">"


def test_rule_editor_analyze_changes_clusters_wraps(monkeypatch, tmp_path):
    monkeypatch.setattr(rule_editor, "_get_lang_dir", lambda: tmp_path)
    changes = [
        {"file": "Skill_1.json", "field_path": "desc", "old_val": "123", "new_val": "<c>123</c>"},
        {"file": "Skill_2.json", "field_path": "desc", "old_val": "45", "new_val": "<c>45</c>"},
        {"file": "Skill_3.json", "field_path": "desc", "old_val": "大于", "new_val": ">"},
    ]

    result = rule_editor_generate.analyze_changes(changes)

    assert len(result["groups"]) == 2
    wrap_group = next(g for g in result["groups"] if g["change_type"] == "PURE_WRAP")
    replace_group = next(g for g in result["groups"] if g["change_type"] == "PURE_REPLACE")
    assert wrap_group["occurrence_count"] == 2
    assert wrap_group["action_preview"] == [
        {"from": "123", "to": "<c>123</c>"},
        {"from": "45", "to": "<c>45</c>"},
    ]
    assert replace_group["occurrence_count"] == 1
    assert replace_group["score"]["s2_purity"] == 100
    assert wrap_group["score"]["s2_purity"] == 95


def test_rule_editor_validates_ruleset_payload():
    ruleset = {"version": 2, "name": "t", "rules": [{
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["desc"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "a", "to": "b"}],
    }]}

    assert validate_rule(json.dumps(ruleset, ensure_ascii=False))["valid"]


def test_skill_color_fingerprint_cache(monkeypatch, tmp_path):
    resource_file = tmp_path / "__data"
    resource_file.write_bytes(b"resource")
    cache_file = tmp_path / "cache" / "skill-colors.json"
    asset = json.dumps({
        "list": [{"id": 123, "skillData": [{"attributeType": "CRIMSON"}]}]
    }).encode("utf-8")

    monkeypatch.setattr("webutils.fancy.builtin_func.get_limbus_resource_files", lambda: [resource_file])
    monkeypatch.setattr("webutils.fancy.builtin_func.load_text_assets", lambda *args: ({"personality-skill-01.json": asset}, []))

    first = SkillColorHandler()
    monkeypatch.setattr(first, "_cache_file", lambda: cache_file)
    assert first.prepare()
    assert not first.last_cache_hit
    assert first.apply("技能", 123) == "<color=#ED2525>技能</color>"

    def fail_loader(*args):
        raise AssertionError("cache hit should not reload Unity resources")

    monkeypatch.setattr("webutils.fancy.builtin_func.load_text_assets", fail_loader)
    second = SkillColorHandler()
    monkeypatch.setattr(second, "_cache_file", lambda: cache_file)
    assert second.prepare()
    assert second.last_cache_hit
    assert second.apply("技能", 123) == "<color=#ED2525>技能</color>"


def test_skill_color_failure_is_not_retried(monkeypatch):
    calls = {"count": 0}

    monkeypatch.setattr("webutils.fancy.builtin_func.get_limbus_resource_files", lambda: [])

    def failing_loader(*args):
        calls["count"] += 1
        raise RuntimeError("broken resource")

    monkeypatch.setattr("webutils.fancy.builtin_func.load_text_assets", failing_loader)
    handler = SkillColorHandler()
    monkeypatch.setattr(handler, "_cache_file", lambda: None)

    assert not handler.prepare()
    assert not handler.prepare()
    assert calls["count"] == 1
