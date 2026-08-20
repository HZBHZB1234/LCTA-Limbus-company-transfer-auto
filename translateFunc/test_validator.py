"""
translateFunc/test_validator.py
RuleBasedValidator 中关于 buff id 格式（[中文名] → [EnglishId]）的回归测试。
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from translateFunc.validator import RuleBasedValidator  # noqa: E402


_AFFECTS = [
    {"id": "Bleed", "kr": "출혈", "cn": "出血", "desc": ""},
    {"id": "Combustion", "kr": "연소", "cn": "燃烧", "desc": ""},
    {"id": "Tremor", "kr": "진동", "cn": "震颤", "desc": ""},
]


def _apply(v: RuleBasedValidator, translations: list[str]) -> list[str]:
    report = v.run_all_checks([{"kr": ""} for _ in translations], translations)
    fixable = [x for x in report.violations if x.auto_fixable]
    return RuleBasedValidator.apply_auto_fixes(translations, fixable)


def test_bracketed_cn_no_space():
    v = RuleBasedValidator(_AFFECTS)
    out = _apply(v, ["对目标施加2层[出血]"])
    assert out[0] == "对目标施加2层[Bleed]", out


def test_bracketed_cn_with_trailing_space():
    v = RuleBasedValidator(_AFFECTS)
    out = _apply(v, ["对目标施加2层[出血 ]"])
    assert out[0] == "对目标施加2层[Bleed]", out


def test_known_id_preserved():
    v = RuleBasedValidator(_AFFECTS)
    out = _apply(v, ["[OnSucceedAttack] 使目标增加2级[Combustion]强度"])
    assert out[0] == "[OnSucceedAttack] 使目标增加2级[Combustion]强度", out


def test_display_name_form_untouched():
    # 正确的中文显示名（无括号+尾随空格）不应被改动
    v = RuleBasedValidator(_AFFECTS)
    out = _apply(v, ["施加2层出血 。"])
    assert out[0] == "施加2层出血 。", out


def test_unknown_cn_bracket_is_warning_not_autofixed():
    v = RuleBasedValidator(_AFFECTS)
    report = v.run_all_checks([{"kr": ""}], ["获得[目标]效果"])
    viol = [x for x in report.violations if x.rule == "bracketed_cn_buff"]
    assert viol, "应检测到未知中文括号"
    assert all(not x.auto_fixable for x in viol), "未知中文名不应自动修复"
    out = _apply(v, ["获得[目标]效果"])
    assert out[0] == "获得[目标]效果", "未知中文名不应被改动"


def test_non_skill_no_false_positive():
    # 无状态效果数据时（非技能文件）不应误报
    v = RuleBasedValidator([])
    report = v.run_all_checks([{"kr": ""}], ["请选择[目标]进行攻击"])
    assert not any(x.rule == "bracketed_cn_buff" for x in report.violations)


if __name__ == "__main__":
    test_bracketed_cn_no_space()
    test_bracketed_cn_with_trailing_space()
    test_known_id_preserved()
    test_display_name_form_untouched()
    test_unknown_cn_bracket_is_warning_not_autofixed()
    test_non_skill_no_false_positive()
    print("All validator buff-id tests passed.")
