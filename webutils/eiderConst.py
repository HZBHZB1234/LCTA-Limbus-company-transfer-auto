updateList = {
    'main': '415',
    'gamepath': '415',
    'character': '415',
    'base': '415',
    'network': '415',
    'launcher': '415',
    'launcher-source': '415',
    'translate': '415',
    'download': '415',
    'bubble': '415',
    'mod': '415',
    'manage': '415',
}

bindRefer = {
    'main': {},

    'gamepath': {
        'elder-game-path': ['game-path', 'game_path'],
    },

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
        ],
        'elder-theme': [
            '--theme', 'theme',
        ],
    },

    'network': {
        'elder-update-use-proxy': [
            'update-use-proxy', 'update_use_proxy',
        ],
        'elder-update-only-stable': [
            'update-only-stable', 'update_only_stable',
        ],
        'elder-delete-updating': [
            'delete-updating', 'delete_updating',
        ],
        'elder-github-max-workers': [
            'github-max-workers', 'github_max_workers',
        ],
        'elder-github-timeout': [
            'github-timeout', 'github_timeout',
        ],
        'elder-debug-mode': [
            'debug-mode', 'debug',
        ],
    },

    'launcher': {
        'elder-launcher-update': [
            'launcher-work-update', 'launcher.work.update',
        ],
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

    'launcher-source': {
        # 启动器 - LLC
        'elder-l-zero-zip-type': [
            'launcher-zero-zip-type', 'launcher.zero.zip_type',
        ],
        'elder-l-zero-download-source': [
            'launcher-zero-download-source', 'launcher.zero.download_source',
        ],
        'elder-l-zero-use-proxy': [
            'launcher-zero-use-proxy', 'launcher.zero.use_proxy',
        ],
        'elder-l-zero-use-cache': [
            'launcher-zero-use-cache', 'launcher.zero.use_cache',
        ],
        # 启动器 - LCTA-AU
        'elder-l-machine-download-source': [
            'machine-zero-download-source', 'launcher.machine.download_source',
        ],
        'elder-l-machine-use-proxy': [
            'machine-zero-use-proxy', 'launcher.machine.use_proxy',
        ],
        # 启动器 - OurPlay
        'elder-l-ourplay-font-option': [
            'launcher-ourplay-font-option', 'launcher.ourplay.font_option',
        ],
        'elder-l-ourplay-use-api': [
            'launcher-ourplay-use-api', 'launcher.ourplay.use_api',
        ],
    },

    'translate': {
        'elder-translator-service': [
            'translator-service-select', 'ui_default.translator.translator',
        ],
        'elder-from-lang': [
            'from-lang', 'ui_default.translator.from_lang',
        ],
        'elder-enable-proper': [
            'enable-proper', 'ui_default.translator.enable_proper',
        ],
        'elder-enable-role': [
            'enable-role', 'ui_default.translator.enable_role',
        ],
        'elder-enable-skill': [
            'enable-skill', 'ui_default.translator.enable_skill',
        ],
        'elder-fallback': [
            'fallback', 'ui_default.translator.fallback',
        ],
        'elder-enable-rule-validation': [
            'enable-rule-validation', 'ui_default.translator.enable_rule_validation',
        ],
    },

    'download': {
        # LLC
        'elder-d-zero-download-source': [
            'llc-download-source', 'ui_default.zero.download_source',
        ],
        'elder-d-zero-zip-type': [
            'llc-zip-type', 'ui_default.zero.zip_type',
        ],
        'elder-d-zero-use-proxy': [
            'llc-use-proxy', 'ui_default.zero.use_proxy',
        ],
        'elder-d-zero-use-cache': [
            'llc-use-cache', 'ui_default.zero.use_cache',
        ],
        'elder-d-zero-dump-default': [
            'llc-dump-default', 'ui_default.zero.dump_default',
        ],
        # LCTA-AU
        'elder-d-machine-download-source': [
            'machine-download-source', 'ui_default.machine.download_source',
        ],
        'elder-d-machine-use-proxy': [
            'machine-use-proxy', 'ui_default.machine.use_proxy',
        ],
        # OurPlay
        'elder-d-ourplay-font-option': [
            'ourplay-font-option', 'ui_default.ourplay.font_option',
        ],
        'elder-d-ourplay-check-hash': [
            'ourplay-check-hash', 'ui_default.ourplay.check_hash',
        ],
        'elder-d-ourplay-use-api': [
            'ourplay-use-api', 'ui_default.ourplay.use_api',
        ],
    },

    'bubble': {
        'elder-bubble-color': [
            'bubble-color', 'ui_default.bubble.color',
        ],
        'elder-bubble-llc': [
            'bubble-llc', 'ui_default.bubble.llc',
        ],
        'elder-bubble-install': [
            'bubble-install', 'ui_default.bubble.install',
        ],
    },

    'mod': {},

    'manage': {
        'elder-package-directory': [
            'install-package-directory', 'ui_default.install.package_directory',
        ],
        'elder-mod-path': [
            'installed-mod-directory', 'ui_default.manage.mod_path',
        ],
        'elder-enable-cache': [
            'enable-cache', 'enable_cache',
        ],
        'elder-enable-storage': [
            'enable-storage', 'enable_storage',
        ],
        'elder-clean-progress': [
            'clean-progress', 'ui_default.clean.clean_progress',
        ],
        'elder-clean-notice': [
            'clean-notice', 'ui_default.clean.clean_notice',
        ],
        'elder-clean-mods': [
            'clean-mods', 'ui_default.clean.clean_mods',
        ],
    },
}

relyList = {
    'main': [],
    'gamepath': [],
    'character': [],
    'base': ['elder.character.base'],
    'network': [],
    'launcher': ['elder.character.launcher'],
    'launcher-source': ['elder.character.launcher'],
    'translate': ['elder.character.translate'],
    'download': [],
    'bubble': ['elder.character.launcher',
               'elder.launcher.bubble'],
    'mod': ['elder.character.launcher',
            'elder.launcher.mod'],
    'manage': ['elder.character.manage'],
}
