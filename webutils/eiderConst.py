updateList = {
    'main': '415',
    'character': '415',
    'base': '415',
    'launcher': '415',
    'mod': '415',
    'bubble': '415',
}

bindRefer = {
    'main': {},
    'character': {
        'elder-character-base': [
            '--elder-character-base', 'elder.character.base',
        ],
        'elder-character-launcher': [
            '--elder-character-launcher', 'elder.character.launcher',
        ],
        'elder-character-translate': [
            '--elder-character-translate', 'elder.character.translate',
        ],
        'elder-character-manage': [
            '--elder-character-manage', 'elder.character.manage',
        ],
    },
    'base': {
        'elder-auto-update': [
            'auto-check-update', 'auto_check_update',
        ]
    },
    'launcher': {
        'elder-launcher-mod': [
            'launcher-work-mod', 'launcher.work.mod',
        ],
        'elder-launcher-bubble': [
            'launcher-work-bubble', 'launcher.work.bubble',
        ],
        'elder-launcher-fancy': [
            'launcher-work-fancy', 'launcher.work.fancy',
        ],
    },
    'mod': {},
    'bubble': {
        'elder-bubble-color': [
            'bubble-color', 'ui_default.bubble.color',
        ],
        'elder-bubble-llc': [
            'bubble-llc', 'ui_default.bubble.llc',
        ],
    },
}

relyList = {
    'main': [],
    'character': [],
    'base': ['elder.character.base'],
    'launcher': ['elder.character.launcher'],
    'mod': ['elder.character.launcher',
            'elder.launcher.mod'],
    'bubble': ['elder.character.launcher',
               'elder.launcher.bubble'],
}