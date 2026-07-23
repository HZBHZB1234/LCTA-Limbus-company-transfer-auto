"""
translateFunc/validator.py
确定性规则后处理校验器 —— 用于翻译质量验证。

在 Stage 1 翻译完成后、Stage 2 LLM 校验前运行。
处理 LLM 始终无法稳定执行的机械性规则检查：
  - [ID] 格式中误用空格（如 [震颤 ] 应为 [震颤]）
  - 源语言（KR/JP/EN）特殊效果引用在译文中的一致性
"""
from __future__ import annotations
from dataclasses import dataclass, field
import re
import logging
from typing import Any

_logger = logging.getLogger("LCTA")


@dataclass
class ValidationViolation:
    """单条校验违规记录。"""
    block_id: int          # 1-based 文本块索引
    rule: str              # "buff_spacing" | "effect_ref"
    severity: str          # "error" (可自动修复) | "warning" (需人工复核)
    message: str           # 人类可读的描述
    auto_fixable: bool     # 是否可以安全自动修复
    fix_fn: str | None     # "replace" | None
    fix_params: dict | None  # 修复函数的参数


@dataclass
class ValidationReport:
    """一次校验运行的聚合报告。"""
    violations: list[ValidationViolation] = field(default_factory=list)
    auto_fixes_applied: int = 0
    warnings_remaining: int = 0


class RuleBasedValidator:
    """确定性后处理校验器，用于技能文件翻译。

    通过已知的 Buff/状态效果名称数据（affects），执行规则检查：
    - [ID] 格式中是否误用了空格
    - 特殊效果引用是否在译文中完整保留
    """

    # 匹配 [Anything] 格式的括号引用（包含中文名称和英文 ID）
    _BRACKET_REF_RE = re.compile(r'\[([^\]]*)\]')

    # 匹配 [Alphanumeric_ID] 格式的特殊效果引用
    _EFFECT_ID_RE = re.compile(r'\[([A-Za-z][A-Za-z0-9_]*)\]')

    def __init__(self, affects_data: list[dict]):
        """初始化校验器。

        Args:
            affects_data: 状态效果列表，每项含 id/kr/cn/desc 字段。
                          来自 BattleKeywords.json 翻译后的配对数据。
        """
        self._affect_cn_names: set[str] = set()
        self._affect_id_to_cn: dict[str, str] = {}
        self._affect_kr_to_cn: dict[str, str] = {}

        for a in affects_data:
            cn = a.get("cn", "")
            aid = a.get("id", "")
            kr = a.get("kr", "")
            if cn:
                self._affect_cn_names.add(cn)
            if aid and cn:
                self._affect_id_to_cn[aid] = cn
            if kr and cn:
                self._affect_kr_to_cn[kr] = cn

        # 按长度降序排列，确保匹配时长名称优先
        self._sorted_cn_names = sorted(
            self._affect_cn_names, key=len, reverse=True
        )

    # ---- 公开 API ----

    def run_all_checks(
        self,
        text_blocks: list[dict],
        translations: list[str],
    ) -> ValidationReport:
        """运行所有校验，返回聚合报告。"""
        report = ValidationReport()
        report.violations.extend(
            self.validate_buff_spacing(translations)
        )
        report.violations.extend(
            self.validate_effect_refs(text_blocks, translations)
        )

        report.warnings_remaining = sum(
            1 for v in report.violations if v.severity == "warning"
        )
        report.auto_fixes_applied = sum(
            1 for v in report.violations
            if v.auto_fixable and v.severity == "error"
        )
        return report

    @staticmethod
    def apply_auto_fixes(
        translations: list[str],
        violations: list[ValidationViolation],
    ) -> list[str]:
        """对 translations 的副本应用所有可自动修复的违规修正。

        按 block 分组，按位置倒序应用修复，以确保多次修改不会
        导致后续修复的位置偏移。

        Returns:
            修正后的翻译文本列表（新列表，不修改原列表）。
        """
        result = list(translations)

        # 按 block_id 分组
        by_block: dict[int, list[ValidationViolation]] = {}
        for v in violations:
            if v.auto_fixable and v.fix_fn:
                by_block.setdefault(v.block_id - 1, []).append(v)

        for idx, violations_for_block in by_block.items():
            if idx < 0 or idx >= len(result):
                continue
            text = result[idx]

            # 按位置倒序排序，保证多次修改位置正确
            sorted_v = sorted(
                violations_for_block,
                key=lambda v: v.fix_params.get("position", 0) if v.fix_params else 0,
                reverse=True,
            )

            for v in sorted_v:
                if v.fix_fn == "replace" and v.fix_params:
                    old = v.fix_params.get("old", "")
                    new = v.fix_params.get("new", "")
                    pos = v.fix_params.get("position", 0)
                    radius = v.fix_params.get("radius", 40)
                    search_start = max(0, pos - radius)
                    search_end = min(len(text), pos + radius)
                    sub = text[search_start:search_end]
                    if old in sub:
                        text = (
                            text[:search_start]
                            + sub.replace(old, new, 1)
                            + text[search_end:]
                        )

            result[idx] = text

        return result

    # ---- 单项校验 ----

    def validate_buff_spacing(
        self, translations: list[str],
    ) -> list[ValidationViolation]:
        """校验 [ID] 格式中是否误用了空格。

        规则：中括号内的 ID 引用不应包含多余空格。
        - ❌ 错误：`[震颤 ]`、`[ 震颤]`、`[ 震颤 ]`
        - ✅ 正确：`[震颤]`、`[Combustion]`

        检测 [ ] 内部内容的前导空格和尾部空格，自动修复为无空格版本。

        Returns:
            违规列表，误用空格的标记为可自动修复。
        """
        violations: list[ValidationViolation] = []

        for block_idx, cn_text in enumerate(translations):
            if not cn_text:
                continue

            for m in self._BRACKET_REF_RE.finditer(cn_text):
                inner = m.group(1)
                full = m.group(0)  # 含括号的完整匹配

                # 检查内部内容是否有多余空格
                stripped = inner.strip()
                if stripped == inner:
                    continue  # 无多余空格，正常

                if not stripped:
                    continue  # 空括号 []，跳过

                # 构建修正后的版本
                fixed = f"[{stripped}]"
                abs_pos = m.start()
                snippet = cn_text[max(0, abs_pos - 5):min(len(cn_text), m.end() + 5)]

                violations.append(ValidationViolation(
                    block_id=block_idx + 1,
                    rule="buff_spacing",
                    severity="error",
                    message=(
                        f"[ID] 格式误用空格：'{full}' 应为 '{fixed}'"
                        f"（上下文: ...{snippet}...）"
                    ),
                    auto_fixable=True,
                    fix_fn="replace",
                    fix_params={
                        "position": abs_pos,
                        "radius": max(len(full) + 10, 20),
                        "old": full,
                        "new": fixed,
                    },
                ))

        return violations

    def validate_effect_refs(
        self, text_blocks: list[dict], translations: list[str],
    ) -> list[ValidationViolation]:
        """校验源语言中的特殊效果引用在译文中是否完整保留。

        检查两项：
        1. KR/JP/EN 原文中的 [EffectID] 在 CN 译文中是否存在
        2. AC 自动机匹配到的 affect_refs 对应的 CN 名称是否出现在译文中

        此类违规无法可靠自动修复，标记为 warning。

        Returns:
            违规列表，均为 auto_fixable=False。
        """
        violations: list[ValidationViolation] = []

        for block_idx, (block, cn_text) in enumerate(
            zip(text_blocks, translations)
        ):
            if not cn_text:
                continue

            # 1. 收集源语言（KR/JP/EN）中的所有 [EffectID]
            source_ids: set[str] = set()
            for lang in ("kr", "jp", "en"):
                text = block.get(lang, "")
                if text:
                    for m in self._EFFECT_ID_RE.finditer(text):
                        source_ids.add(m.group(1))

            # 2. 收集 CN 译文中的所有 [EffectID]
            cn_ids: set[str] = set()
            for m in self._EFFECT_ID_RE.finditer(cn_text):
                cn_ids.add(m.group(1))

            # 3. 检测缺失的 ID
            missing_ids = source_ids - cn_ids
            for mid in sorted(missing_ids):
                cn_name = self._affect_id_to_cn.get(mid, mid)
                violations.append(ValidationViolation(
                    block_id=block_idx + 1,
                    rule="effect_ref",
                    severity="warning",
                    message=(
                        f"源语言中的特殊效果引用 [{mid}]"
                        f"（{cn_name}）在译文中缺失"
                    ),
                    auto_fixable=False,
                    fix_fn=None,
                    fix_params=None,
                ))

            # 4. 检查 affect_refs 对应的 CN 名称是否出现
            affect_refs = block.get("affect_refs", [])
            for ref in affect_refs:
                aff_id = ref.strip("[]")
                cn_name = self._affect_id_to_cn.get(aff_id, "")
                if cn_name and cn_name not in cn_text:
                    violations.append(ValidationViolation(
                        block_id=block_idx + 1,
                        rule="effect_ref",
                        severity="warning",
                        message=(
                            f"KR原文中检测到特殊效果 '{cn_name}'"
                            f" ([{aff_id}])，但译文中未找到对应中文名称"
                        ),
                        auto_fixable=False,
                        fix_fn=None,
                        fix_params=None,
                    ))

        return violations
