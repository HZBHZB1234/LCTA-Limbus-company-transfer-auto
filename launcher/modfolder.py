import os
from pathlib import Path
from globalManagers.ConfigManager import ConfigManager

def get_mod_folder():
    mod_path = ConfigManager().get('ui_default.manage.mod_path', '')
    if not mod_path or not os.path.exists(mod_path):
        mod_path = Path.home() / 'AppData' /  'Roaming' / 'LimbusCompanyMods'
    mod_path = str(mod_path)
    os.environ['mod_path'] = mod_path