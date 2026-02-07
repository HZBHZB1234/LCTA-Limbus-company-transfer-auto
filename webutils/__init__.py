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
from .function_LCTA_auto import function_LCTA_auto_main
from webutils.function_clean import clean_config_main

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
    'clean_config_main'
]