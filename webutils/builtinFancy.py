fancy = [
    {
        "name": "技能文本美化(FL Like)",
        "desc": "替换部分文本为符号，同时为部分文本着色",
        "rules": [
            {
                "aimFile": "Skill.*\\.json$",
                "aim": "dataList\\.\\d+\\.levelList\\.\\d+\\.desc",
                "action": [
                    { "from": "大于", "to": ">" },
                    { "from": "小于", "to": "<" },
                    { "from": "不低于", "to": "≥" },
                    { "from": "不高于", "to": "≤" },
                    { "from": "自身", "to": "<u><color=#7C5738>自身</color></u>" },
                    { "from": "目标", "to": "<u><color=#7C5738>目标</color></u>" },
                    { "from": "行动槽", "to": "<u><color=#7C5738>行动槽</color></u>" },
                    { "from": "重复使用", "to": "<u><color=#7C5738>重复使用</color></u>" },
                    { "from": "基础威力", "to": "<u><color=#7C5738>基础威力</color></u>" },
                    { "from": "最终威力", "to": "<u><color=#7C5738>最终威力</color></u>" },
                    { "from": "硬币威力", "to": "<u><color=#7C5738>硬币威力</color></u>" },
                    { "from": "拼点威力", "to": "<u><color=#7C5738>拼点威力</color></u>" },
                    { "from": "护盾", "to": "<u><color=#81BBE8>护盾</color></u>" },
                    { "from": "理智值", "to": "<u><color=#81BBE8>理智值</color></u>" },
                    { "from": "体力", "to": "<u><color=#61DA61>体力</color></u>" }
                ]
            },
            {
                "aimFile": "Skill.*\\.json$",
                "aim": "dataList\\.\\d+\\.levelList\\.\\d+\\.coinlist\\.\\d+\\.coindescs\\.\\d+\\.desc",
                "action": [
                    { "from": "大于", "to": ">" },
                    { "from": "小于", "to": "<" },
                    { "from": "不低于", "to": "≥" },
                    { "from": "不高于", "to": "≤" },
                    { "from": "自身", "to": "<u><color=#7C5738>自身</color></u>" },
                    { "from": "目标", "to": "<u><color=#7C5738>目标</color></u>" },
                    { "from": "行动槽", "to": "<u><color=#7C5738>行动槽</color></u>" },
                    { "from": "重复使用", "to": "<u><color=#7C5738>重复使用</color></u>" },
                    { "from": "基础威力", "to": "<u><color=#7C5738>基础威力</color></u>" },
                    { "from": "最终威力", "to": "<u><color=#7C5738>最终威力</color></u>" },
                    { "from": "硬币威力", "to": "<u><color=#7C5738>硬币威力</color></u>" },
                    { "from": "拼点威力", "to": "<u><color=#7C5738>拼点威力</color></u>" },
                    { "from": "护盾", "to": "<u><color=#81BBE8>护盾</color></u>" },
                    { "from": "理智值", "to": "<u><color=#81BBE8>理智值</color></u>" },
                    { "from": "体力", "to": "<u><color=#61DA61>体力</color></u>" }
                ]
            }
        ]
    },
    {
        "name": "气泡文本渐变(FL Like)",
        "desc": "为气泡文本添加渐变色",
        "rules": [
            {
                "aimFile": "BattleSpeechBubbleDlg.*\\.json$",
                "aim": "dataList\\.\\d+\\.dlg",
                "action": [
                    {
                        "rate": 1.0
                    }
                ]
            }
        ]
    },
    {
        "name": "EGO文本渐变(FL Like)",
        "desc": "为EGO文本添加渐变色",
        "rules": [
            {
                "aimFile": "Skills_Ego_Personality-.*\\.json$",
                "trigger": {
                    "aim": "dataList\\.\\d+\\.levelList\\.\\d+\\.desc",
                    "re": "指定"
                },
                "aim": "[back].name",
                "action": [
                    { "from": "^(.*)$", "to": "<color=#ff0000>⚠️\\1⚠️</color>" },
                    { "rate": 0.5 },
                    { "from": "^(.*)$", "to": "<b><i>\\1</i></b>" }
                ]
            },
            {
                "aimFile": "Skills_Ego_Personality-.*\\.json$",
                "trigger": {
                    "aim": "dataList\\.\\d+\\.levelList\\.\\d+\\.desc",
                    "re": "^(?!.*指定).*$"
                },
                "aim": "[back].name",
                "action": [
                    { "from": "^(.*)$", "to": "<b><i>\\1</i></b>" }
                ]
            },
            {
                "aimFile": "Skills_Ego_Personality-.*\\.json$",
                "trigger": {
                    "aim": "dataList\\.\\d+\\.levelList\\.\\d+\\.desc",
                    "re": "指定"
                },
                "aim": "[back].abName",
                "action": [
                    { "from": "^(.*)$", "to": "<color=#ff0000>⚠️\\1⚠️</color>" },
                    { "rate": 0.5 },
                    { "from": "^(.*)$", "to": "<b><i>\\1</i></b>" }
                ]
            },
            {
                "aimFile": "Skills_Ego_Personality-.*\\.json$",
                "trigger": {
                    "aim": "dataList\\.\\d+\\.levelList\\.\\d+\\.desc",
                    "re": "^(?!.*指定).*$"
                },
                "aim": "[back].abName",
                "action": [
                    { "from": "^(.*)$", "to": "<b><i>\\1</i></b>" }
                ]
            }
        ]
    },
    {
        "name": "技能名称渐变(FL Like)",
        "desc": "为技能名称添加渐变色",
        "rules": [
            {
                "aimFile": "Skills_personality-.*\\.json$",
                "aim": "dataList\\.\\d+\\.levelList\\.name",
                "action": [
                    {
                        "builtIn": "skillColor",
                        "rate": 1.0
                    }
                ]
            }
        ]
    },
]