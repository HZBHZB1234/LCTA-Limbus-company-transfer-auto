import json
from pathlib import Path

from webutils.builtinFancyFunc import SkillColorHandler
from webutils.function_fancy import fancy_main
from webutils.function_rule_editor import (
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


def test_skill_color_fingerprint_cache(monkeypatch, tmp_path):
    resource_file = tmp_path / "__data"
    resource_file.write_bytes(b"resource")
    cache_file = tmp_path / "cache" / "skill-colors.json"
    asset = json.dumps({
        "list": [{"id": 123, "skillData": [{"attributeType": "CRIMSON"}]}]
    }).encode("utf-8")

    monkeypatch.setattr("webutils.builtinFancyFunc.get_limbus_resource_files", lambda: [resource_file])
    monkeypatch.setattr("webutils.builtinFancyFunc.load_text_assets", lambda *args: ({"personality-skill-01.json": asset}, []))

    first = SkillColorHandler()
    monkeypatch.setattr(first, "_cache_file", lambda: cache_file)
    assert first.prepare()
    assert not first.last_cache_hit
    assert first.apply("技能", 123) == "<color=#ED2525>技能</color>"

    def fail_loader(*args):
        raise AssertionError("cache hit should not reload Unity resources")

    monkeypatch.setattr("webutils.builtinFancyFunc.load_text_assets", fail_loader)
    second = SkillColorHandler()
    monkeypatch.setattr(second, "_cache_file", lambda: cache_file)
    assert second.prepare()
    assert second.last_cache_hit
    assert second.apply("技能", 123) == "<color=#ED2525>技能</color>"


def test_skill_color_failure_is_not_retried(monkeypatch):
    calls = {"count": 0}

    monkeypatch.setattr("webutils.builtinFancyFunc.get_limbus_resource_files", lambda: [])

    def failing_loader(*args):
        calls["count"] += 1
        raise RuntimeError("broken resource")

    monkeypatch.setattr("webutils.builtinFancyFunc.load_text_assets", failing_loader)
    handler = SkillColorHandler()
    monkeypatch.setattr(handler, "_cache_file", lambda: None)

    assert not handler.prepare()
    assert not handler.prepare()
    assert calls["count"] == 1

