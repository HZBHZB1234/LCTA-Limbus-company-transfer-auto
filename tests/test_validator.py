"""
tests/test_validator.py
确定性规则校验器单元测试。
覆盖：[ID] 空格误用检测、特殊效果引用、自动修复。
"""
import pytest
from translateFunc.validator import (
    RuleBasedValidator,
    ValidationViolation,
    ValidationReport,
)


# 模拟 BattleKeywords 数据
SAMPLE_AFFECTS = [
    {"id": "Combustion",  "kr": "화상",       "cn": "燃烧",     "desc": ""},
    {"id": "Burst",       "kr": "파열",       "cn": "破裂",     "desc": ""},
    {"id": "Tremor",      "kr": "진동",       "cn": "震颤",     "desc": ""},
    {"id": "Charge",      "kr": "충전",       "cn": "充能",     "desc": ""},
    {"id": "SlashWeak",   "kr": "참격 취약",   "cn": "斩击易损",  "desc": ""},
    {"id": "Poise",       "kr": "호흡",       "cn": "呼吸法",   "desc": ""},
    {"id": "Sinking",     "kr": "침잠",       "cn": "沉没",     "desc": ""},
]


# ========== [ID] 空格误用校验 ==========

class TestBuffSpacing:
    """validate_buff_spacing 测试 —— 检测 [ID] 中误用空格。"""

    def test_clean_id_no_violation(self):
        """正常的 [ID] 不应产生违规。"""
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "[震颤]",
        ])
        assert len(violations) == 0

    def test_english_id_no_violation(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "[Combustion] 强度增加",
        ])
        assert len(violations) == 0

    def test_trailing_space_in_brackets(self):
        """[震颤 ] — 尾部空格应被检测。"""
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "[震颤 ]",
        ])
        v_buff = [x for x in violations if x.rule == "buff_spacing"]
        assert len(v_buff) >= 1
        assert v_buff[0].auto_fixable is True
        assert v_buff[0].fix_fn == "replace"
        assert v_buff[0].fix_params["old"] == "[震颤 ]"
        assert v_buff[0].fix_params["new"] == "[震颤]"

    def test_leading_space_in_brackets(self):
        """[ 震颤] — 前导空格应被检测。"""
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "[ 震颤]",
        ])
        v_buff = [x for x in violations if x.rule == "buff_spacing"]
        assert len(v_buff) >= 1
        assert v_buff[0].fix_params["old"] == "[ 震颤]"
        assert v_buff[0].fix_params["new"] == "[震颤]"

    def test_both_spaces_in_brackets(self):
        """[ 震颤 ] — 前后空格都应被修复。"""
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "[ 震颤 ]",
        ])
        v_buff = [x for x in violations if x.rule == "buff_spacing"]
        assert len(v_buff) >= 1
        assert v_buff[0].fix_params["new"] == "[震颤]"

    def test_multiple_bracket_refs(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "[震颤] 和 [破裂 ] 效果",
        ])
        v_buff = [x for x in violations if x.rule == "buff_spacing"]
        assert len(v_buff) == 1  # 只有 [破裂 ] 有问题

    def test_multiple_violations(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "[ 震颤 ] 和 [破裂 ]",
        ])
        v_buff = [x for x in violations if x.rule == "buff_spacing"]
        assert len(v_buff) == 2

    def test_id_with_space_in_sentence(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "使目标增加4级[破裂 ]强度",
        ])
        v_buff = [x for x in violations if x.rule == "buff_spacing"]
        assert len(v_buff) >= 1
        assert "[破裂 ]" in v_buff[0].fix_params["old"]
        assert v_buff[0].fix_params["new"] == "[破裂]"

    def test_no_bracket_refs_returns_empty(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "施加2层震颤 并使目标增加4级破裂 强度。",
        ])
        assert len(violations) == 0

    def test_empty_brackets_skipped(self):
        """空括号 [] 应被跳过。"""
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "[]",
        ])
        assert len(violations) == 0

    def test_english_id_with_trailing_space(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "[Combustion ] 强度增加",
        ])
        v_buff = [x for x in violations if x.rule == "buff_spacing"]
        assert len(v_buff) >= 1
        assert v_buff[0].fix_params["old"] == "[Combustion ]"

    def test_on_skill_event_bracket(self):
        """事件括号如 [OnSucceedAttack] 也不应有空格。"""
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        violations = v.validate_buff_spacing([
            "[OnSucceedAttack ] 施加2层震颤 。",
        ])
        v_buff = [x for x in violations if x.rule == "buff_spacing"]
        assert len(v_buff) >= 1


# ========== 特殊效果引用校验 ==========

class TestEffectRefs:
    """validate_effect_refs 测试。"""

    def test_all_ids_preserved(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        blocks = [{"kr": "[Combustion] 위력", "jp": "", "en": "[Combustion] Power"}]
        translations = ["[Combustion] 强度"]
        violations = v.validate_effect_refs(blocks, translations)
        assert len(violations) == 0

    def test_missing_effect_id(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        blocks = [{"kr": "[Combustion] 위력", "jp": "", "en": "[Combustion] Power"}]
        translations = ["燃烧 强度"]  # 缺少 [Combustion]
        violations = v.validate_effect_refs(blocks, translations)
        v_found = [x for x in violations if x.rule == "effect_ref"]
        assert len(v_found) >= 1
        assert v_found[0].severity == "warning"
        assert v_found[0].auto_fixable is False
        assert "Combustion" in v_found[0].message

    def test_multiple_source_ids(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        blocks = [{
            "kr": "[Combustion] [Burst]",
            "jp": "[Combustion] [Burst]",
            "en": "[Combustion] [Burst]",
        }]
        translations = ["[Combustion] [Burst] 效果"]
        violations = v.validate_effect_refs(blocks, translations)
        assert len(violations) == 0

    def test_partial_missing_ids(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        blocks = [{
            "kr": "[Combustion] [Burst]",
            "jp": "",
            "en": "[Combustion] [Burst]",
        }]
        translations = ["[Combustion] 效果"]  # 缺少 [Burst]
        violations = v.validate_effect_refs(blocks, translations)
        v_found = [x for x in violations if x.rule == "effect_ref"]
        assert len(v_found) >= 1
        assert any("Burst" in x.message for x in v_found)

    def test_affect_refs_cn_name_present(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        blocks = [{"kr": "화상", "jp": "", "en": "", "affect_refs": ["[Combustion]"]}]
        translations = ["[Combustion] 燃烧 效果"]
        violations = v.validate_effect_refs(blocks, translations)
        v_found = [x for x in violations if x.rule == "effect_ref"]
        assert len(v_found) == 0

    def test_affect_refs_cn_name_missing(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        blocks = [{"kr": "화상", "jp": "", "en": "", "affect_refs": ["[Combustion]"]}]
        translations = ["火焰 效果"]  # 未使用正确的 CN 名称"燃烧"
        violations = v.validate_effect_refs(blocks, translations)
        v_found = [x for x in violations if x.rule == "effect_ref"]
        assert len(v_found) >= 1
        assert "燃烧" in v_found[0].message


# ========== 自动修复 ==========

class TestApplyAutoFixes:
    """apply_auto_fixes 测试。"""

    def test_fix_trailing_space_in_brackets(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        translations = ["[震颤 ]"]
        violations = v.validate_buff_spacing(translations)
        fixed = v.apply_auto_fixes(translations, violations)
        assert fixed[0] == "[震颤]"

    def test_fix_leading_space_in_brackets(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        translations = ["[ 震颤]"]
        violations = v.validate_buff_spacing(translations)
        fixed = v.apply_auto_fixes(translations, violations)
        assert fixed[0] == "[震颤]"

    def test_fix_both_spaces(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        translations = ["[ 震颤 ]"]
        violations = v.validate_buff_spacing(translations)
        fixed = v.apply_auto_fixes(translations, violations)
        assert fixed[0] == "[震颤]"

    def test_fix_multiple_in_same_text(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        translations = ["[ 震颤 ] 和 [破裂 ]"]
        violations = v.validate_buff_spacing(translations)
        fixed = v.apply_auto_fixes(translations, violations)
        assert "[震颤]" in fixed[0]
        assert "[破裂]" in fixed[0]
        assert "[ 震颤 ]" not in fixed[0]
        assert "[破裂 ]" not in fixed[0]

    def test_fix_in_sentence(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        translations = ["使目标增加4级[破裂 ]强度"]
        violations = v.validate_buff_spacing(translations)
        fixed = v.apply_auto_fixes(translations, violations)
        assert "[破裂]" in fixed[0]
        assert "[破裂 ]" not in fixed[0]

    def test_no_fix_when_correct(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        translations = ["[震颤] 效果正确"]
        violations = v.validate_buff_spacing(translations)
        fixed = v.apply_auto_fixes(translations, violations)
        assert fixed == translations

    def test_original_not_mutated(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        original = ["[震颤 ]"]
        translations = list(original)
        violations = v.validate_buff_spacing(translations)
        _ = v.apply_auto_fixes(translations, violations)
        assert translations[0] == "[震颤 ]"  # 原列表未被修改

    def test_fix_english_id(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        translations = ["[Combustion ] 强度增加"]
        violations = v.validate_buff_spacing(translations)
        fixed = v.apply_auto_fixes(translations, violations)
        assert "[Combustion]" in fixed[0]
        assert "[Combustion ]" not in fixed[0]


# ========== 集成：run_all_checks ==========

class TestRunAllChecks:
    """run_all_checks 集成测试。"""

    def test_multiple_issue_types(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        blocks = [{
            "kr": "[Burst] 위력 4 증가. [Combustion]",
            "jp": "",
            "en": "[Burst] Power +4. [Combustion]",
            "affect_refs": ["[Burst]", "[Combustion]"],
        }]
        translations = ["[Burst ] 增加4级破裂 强度。燃烧 "]  # [Burst ] 有空格 + 缺 [Combustion] ID
        report = v.run_all_checks(blocks, translations)

        # buff_spacing 错误可修复，effect_ref 警告不可修复
        assert report.auto_fixes_applied >= 1
        assert report.warnings_remaining >= 1

    def test_perfect_translation_no_violations(self):
        v = RuleBasedValidator(SAMPLE_AFFECTS)
        blocks = [{
            "kr": "[Tremor] 위력 2 증가 [Charge] 횟수 3 부여",
            "jp": "",
            "en": "[Tremor] Potency +2. Inflict 3 [Charge].",
            "affect_refs": ["[Tremor]", "[Charge]"],
        }]
        translations = ["[Tremor] 增加2级震颤 强度 [Charge] 施加3层充能 。"]
        report = v.run_all_checks(blocks, translations)
        assert len(report.violations) == 0
        assert report.auto_fixes_applied == 0
        assert report.warnings_remaining == 0
