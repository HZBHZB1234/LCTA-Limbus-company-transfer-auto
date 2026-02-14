import os
from pathlib import Path

def get_mod_folder(config):
    mod_path = config.get('manage', {}).get('mod_path', '')
    if not mod_path or not os.path.exists(mod_path):
        mod_path = Path.home() / 'AppData' /  'Roaming' / 'LimbusCompanyMods'
    mod_path = str(mod_path)
    os.environ['mod_path'] = mod_path