from .function_llc import function_llc_main, check_ver_github
from .function_ourplay import function_ourplay_main, check_ver_ourplay, function_ourplay_api
from .function_install import (
    find_translation_packages,
    delete_translation_package,
    change_font_for_package,
    install_translation_package,
    get_system_fonts,
    export_system_font
)
from .function_fetch import function_fetch_main
from .function_LCTA_auto import function_LCTA_auto_main, check_ver_github_M
from .function_bubble import function_bubble_main
from .function_clean import clean_config_main
from .function_manage import (find_installed_packages,
                              use_translation_package,
                              delete_installed_package,
                              check_lang_enabled,
                              toggle_install_package,
                              fing_mod, toggle_mod, delete_mod,
                              open_mod_path)

__all__ = [
    'function_llc_main',
    'function_ourplay_main',
    'find_translation_packages',
    'delete_translation_package',
    'change_font_for_package',
    'install_translation_package',
    'get_system_fonts',
    'export_system_font',
    'check_ver_github',
    'check_ver_ourplay',
    'function_ourplay_api',
    'function_fetch_main',
    'function_LCTA_auto_main',
    'check_ver_github_M',
    'clean_config_main',
    'function_bubble_main',
    'find_installed_packages',
    'use_translation_package',
    'delete_installed_package',
    'check_lang_enabled',
    'toggle_install_package',
    'fing_mod',
    'toggle_mod',
    'delete_mod',
    'open_mod_path'
]