import re

FILE_PREFIX_RULES = [
    ('BattleSpeechBubbleDlg', '战斗气泡'), ('BattleResultHint', '战斗结果提示'),
    ('BattleKeywords', '战斗关键词'), ('BattlePass', '通行证'),
    ('BattleUIText', '战斗UI'), ('BossRaidUI', '战斗映射UI'),
    ('BattleHint', '战斗提示'), ('BuffAbilities', '战斗Buff'),
    ('Bufs_Mirror', '镜牢Buff'), ('MirrorDungeon', '镜牢'),
    ('DailyLoginEvent', '签到'), ('CultivationEvent', '惜春养成'),
    ('CouponUIText', '兑换码UI'), ('ChoiceEvent', '事件选择'),
    ('DanteAbility', '但丁能力'), ('ActionEvents', '镜牢事件'),
    ('AbEventsResultLog', '事件效果'), ('AbnormalityGuides', '异想体线索/提示'),
    ('AttributeText', '七大罪'), ('AbEvents', '异想体事件'),
    ('AbDlg', '事件判定'), ('Announcer', '播报相关内容'),
    ('Assist', '援助相关'), ('ErrorCodeMsg', '错误代码'),
    ('UnitKeyword', '关键词'), ('Personalities', '人格'),
    ('Characters', '角色'), ('EGOgift', 'EGO饰品'),
    ('Dungeon', '地牢'), ('Enemies', '敌人'),
    ('PanicInfo', '效果'), ('Passives', '被动'),
    ('Railway', '轨道线'), ('Egos', '角色EGO'),
    ('Skill', '技能'), ('Stage', '舞台'),
    ('Story', '故事'), ('Event', '活动'), ('Bufs', '通用Buff'),
]

CATEGORY_FILE_PATTERNS = {
    'Skill': r'Skill.*\.json$', 'Bufs': r'Bufs.*\.json$',
    'BattleSpeechBubbleDlg': r'BattleSpeechBubbleDlg.*\.json$',
    'Egos': r'(Skills_Ego_Personality|Egos).*\.json$',
    'Passives': r'Passives.*\.json$', 'Personalities': r'Personalities.*\.json$',
    'Enemies': r'Enemies.*\.json$', 'EGOgift': r'EGOgift.*\.json$',
    'Railway': r'Railway.*\.json$', 'MirrorDungeon': r'MirrorDungeon.*\.json$',
    'Dungeon': r'Dungeon.*\.json$', 'Stage': r'Stage.*\.json$',
    'Story': r'Story.*\.json$', 'Event': r'Event.*\.json$',
    'BattleUIText': r'BattleUIText.*\.json$', 'BattleKeywords': r'BattleKeywords.*\.json$',
    'AbEvents': r'AbEvents.*\.json$', 'Announcer': r'Announcer.*\.json$',
    'UnitKeyword': r'UnitKeyword.*\.json$',
}

COMMON_REPLACEMENTS = [
    {"from": "大于", "to": ">"}, {"from": "小于", "to": "<"},
    {"from": "不低于", "to": "≥"}, {"from": "不高于", "to": "≤"},
    {"from": "自身", "to": "<u><color=#7C5738>自身</color></u>"},
    {"from": "目标", "to": "<u><color=#7C5738>目标</color></u>"},
    {"from": "护盾", "to": "<u><color=#81BBE8>护盾</color></u>"},
    {"from": "理智值", "to": "<u><color=#81BBE8>理智值</color></u>"},
    {"from": "体力", "to": "<u><color=#61DA61>体力</color></u>"},
]

TEMPLATES = [
    {"name": "空规则集", "template": {"name": "", "desc": "", "rules": []}},
    {"name": "简单文本替换", "template": {
        "name": "", "desc": "",
        "rules": [{"aimFile": "Skill.*\\.json$",
                   "conditions": [{"aim": "dataList\\.\\d+\\.desc"}],
                   "action": [{"from": "查找", "to": "替换"}]}]
    }},
    {"name": "按ID定位替换", "template": {
        "name": "", "desc": "",
        "rules": [{"aimFile": "Skill.*\\.json$",
                   "conditions": [{"trigger": {"aim": "dataList\\.\\d+\\.id", "re": "^10001$"},
                                   "aim": "[back].desc"}],
                   "action": [{"from": "查找", "to": "替换"}]}]
    }},
    {"name": "颜色渐变", "template": {
        "name": "", "desc": "",
        "rules": [{"aimFile": "BattleSpeechBubbleDlg.*\\.json$",
                   "conditions": [{"aim": "dataList\\.\\d+\\.dlg"}],
                   "action": [{"rate": 0.4}]}]
    }},
]
