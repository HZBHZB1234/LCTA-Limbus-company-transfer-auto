TEXT_REPLACEMENTS = [
    {"type": "replace", "mode": "literal", "from": "大于", "to": ">"},
    {"type": "replace", "mode": "literal", "from": "小于", "to": "<"},
    {"type": "replace", "mode": "literal", "from": "不低于", "to": "≥"},
    {"type": "replace", "mode": "literal", "from": "不高于", "to": "≤"},
    {"type": "replace", "mode": "literal", "from": "自身", "to": "<u><color=#7C5738>自身</color></u>"},
    {"type": "replace", "mode": "literal", "from": "目标", "to": "<u><color=#7C5738>目标</color></u>"},
    {"type": "replace", "mode": "literal", "from": "行动槽", "to": "<u><color=#7C5738>行动槽</color></u>"},
    {"type": "replace", "mode": "literal", "from": "重复使用", "to": "<u><color=#7C5738>重复使用</color></u>"},
    {"type": "replace", "mode": "literal", "from": "基础威力", "to": "<u><color=#7C5738>基础威力</color></u>"},
    {"type": "replace", "mode": "literal", "from": "最终威力", "to": "<u><color=#7C5738>最终威力</color></u>"},
    {"type": "replace", "mode": "literal", "from": "硬币威力", "to": "<u><color=#7C5738>硬币威力</color></u>"},
    {"type": "replace", "mode": "literal", "from": "拼点威力", "to": "<u><color=#7C5738>拼点威力</color></u>"},
    {"type": "replace", "mode": "literal", "from": "护盾", "to": "<u><color=#81BBE8>护盾</color></u>"},
    {"type": "replace", "mode": "literal", "from": "理智值", "to": "<u><color=#81BBE8>理智值</color></u>"},
    {"type": "replace", "mode": "literal", "from": "体力", "to": "<u><color=#61DA61>体力</color></u>"},
]

EGO_WARNING_ACTIONS = [
    {"type": "wrap", "prefix": "<color=#ff0000>⚠️", "suffix": "⚠️</color>"},
    {"type": "gradient", "rate": 0.5},
    {"type": "wrap", "prefix": "<b><i>", "suffix": "</i></b>"},
]

EGO_NORMAL_ACTIONS = [
    {"type": "wrap", "prefix": "<b><i>", "suffix": "</i></b>"},
]

SKILL_COLOR_ACTIONS = [
    {"type": "skill_color", "idPath": "id"},
    {"type": "gradient", "rate": 0.3},
]


fancy = [
    {
        "version": 2,
        "name": "技能文本美化(FL Like)",
        "desc": "替换部分文本为符号，同时为部分文本着色",
        "rules": [
            {
                "files": ["Skill*.json"],
                "scope": "dataList[*].levelList[*]",
                "targets": ["desc"],
                "where": [],
                "actions": TEXT_REPLACEMENTS,
            },
            {
                "files": ["Skill*.json"],
                "scope": "dataList[*].levelList[*].coinlist[*].coindescs[*]",
                "targets": ["desc"],
                "where": [],
                "actions": TEXT_REPLACEMENTS,
            },
        ],
    },
    {
        "version": 2,
        "name": "气泡文本渐变(FL Like)",
        "desc": "为气泡文本添加渐变色",
        "rules": [
            {
                "files": ["BattleSpeechBubbleDlg*.json"],
                "scope": "dataList[*]",
                "targets": ["dlg"],
                "where": [],
                "actions": [{"type": "gradient", "rate": 0.4}],
            }
        ],
    },
    {
        "version": 2,
        "name": "EGO文本渐变(FL Like)",
        "desc": "为EGO文本添加渐变色，与人格技能冲突",
        "conflict": ["EGO名称渐变(FL Like)"],
        "rules": [
            {
                "files": ["Skills_Ego_Personality-*.json"],
                "scope": "dataList[*].levelList[*]",
                "targets": ["name", "abName"],
                "where": [{"path": "desc", "operator": "contains", "value": "指定"}],
                "actions": EGO_WARNING_ACTIONS,
            },
            {
                "files": ["Skills_Ego_Personality-*.json"],
                "scope": "dataList[*].levelList[*]",
                "targets": ["name", "abName"],
                "where": [{"path": "desc", "operator": "regex", "value": "^(?!.*指定).*$"}],
                "actions": EGO_NORMAL_ACTIONS,
            },
        ],
    },
    {
        "version": 2,
        "name": "技能名称渐变(FL Like)",
        "desc": "为技能名称添加渐变色",
        "rules": [
            {
                "files": ["Skills_personality-*.json"],
                "scope": "dataList[*]",
                "targets": ["levelList[*].name"],
                "where": [],
                "actions": SKILL_COLOR_ACTIONS,
            }
        ],
    },
    {
        "version": 2,
        "name": "EGO名称渐变(FL Like)",
        "desc": "为EGO名称添加渐变色，与EGO文本美化冲突",
        "conflict": ["EGO文本渐变(FL Like)"],
        "rules": [
            {
                "files": ["Skills_Ego_Personality-*.json"],
                "scope": "dataList[*]",
                "targets": ["levelList[*].name", "levelList[*].adName"],
                "where": [],
                "actions": SKILL_COLOR_ACTIONS,
            }
        ],
    },
]
