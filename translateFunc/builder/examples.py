"""
translateFunc/builder/examples.py
Few-shot 翻译示例，按文件类型分类。
在提示词 v2 中用于帮助 LLM 理解输出格式和翻译风格。
"""
from __future__ import annotations

# ---- STORY 文件示例 (剧情对话) ----

STORY_EXAMPLES: list[dict] = [
    {
        "in": "KR: 그래, 모두 준비됐나?\nJP: よし、準備はいいか？\nEN: Alright, is everyone ready?",
        "reasoning": "口语化短句，使用中文自然口语表达。保持疑问语气。",
        "translation": "好了，大家都准备好了吗？",
        "confidence": "high",
    },
    {
        "in": "KR: ……그런가.\nJP: ……そうか。\nEN: ...I see.",
        "reasoning": "省略开头的短句，保留……。角色为简洁性格，翻译需简短。",
        "translation": "……是吗。",
        "confidence": "high",
    },
]

# ---- SKILL 文件示例 (技能描述) ----

SKILL_EXAMPLES: list[dict] = [
    {
        "in": "KR: 적에게 <0> 피해를 입힙니다\nJP: 敵に<0>ダメージを与える\nEN: Deals <0> damage to enemy",
        "reasoning": "技能描述需精炼。保护<0>占位符位置。",
        "translation": "对敌方造成<0>伤害",
        "confidence": "high",
    },
    {
        "in": "KR: 턴 종료 시 체력이 가장 낮은 아군 <0> 회복\nJP: ターン終了時、体力が最も低い味方を<0>回復\nEN: At turn end, heals the ally with the lowest HP by <0>",
        "reasoning": "技能效果描述。保护<0>参数。遵循半角括号惯例。",
        "translation": "回合结束时，为体力最低的友方恢复<0>",
        "confidence": "high",
    },
]

# ---- UI 文件示例 (界面文本) ----

UI_EXAMPLES: list[dict] = [
    {
        "in": "KR: 확인\nJP: 確認\nEN: Confirm",
        "reasoning": "UI按钮文本，极短，不加标点。",
        "translation": "确认",
        "confidence": "high",
    },
    {
        "in": "KR: 전투 시작\nJP: 戦闘開始\nEN: Battle Start",
        "reasoning": "UI标签。简洁直接。",
        "translation": "战斗开始",
        "confidence": "high",
    },
]

# ---- OTHER 文件示例 (通用) ----

OTHER_EXAMPLES: list[dict] = [
    {
        "in": "KR: 효과: {{0}}% 확률로 {{1}} 부여\nJP: 効果: {{0}}%の確率で{{1}}付与\nEN: Effect: {{0}}% chance to apply {{1}}",
        "reasoning": "通用模板文本。保护{{0}}和{{1}}模板变量。",
        "translation": "效果：{{0}}%概率赋予{{1}}",
        "confidence": "high",
    },
]


def get_examples(file_type_name: str) -> list[dict] | None:
    """根据 FileType 名称获取对应的 few-shot 示例列表。"""
    mapping = {
        "STORY": STORY_EXAMPLES,
        "SKILL": SKILL_EXAMPLES,
        "UI": UI_EXAMPLES,
        "OTHER": OTHER_EXAMPLES,
    }
    return mapping.get(file_type_name)
