import random
def get_bonus():
    bonus_list=[
        '你知道吗:小镇机器人的名称只在英语中有首字母大写…',
        '你知道吗: \"…\" \"...\" \"···\" \"．．．\" 是不一样的符号…',
        '你知道吗:LCTA版本号第一位指的是重构的次数…',
        '你知道吗:LCTA已经鸽了5个月了…'
    ]
    return random.choice(bonus_list)