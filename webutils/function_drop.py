from pathlib import Path
import os
from pyunpack import Archive
import shutil
import tempfile
import zipfile

FOLDERLIST = [
    'BattleAnnouncerDlg',
    'BgmLyrics',
    'EGOVoiceDig',
    'PersonalityVoiceDlg',
    'StoryData',
]


def evalZip(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        namelist = zip_ref.namelist()
        notJson = [name for name in namelist if '.json' not in name]
        amount = len(namelist)
        notJsonAmount = len(notJson)
        hasFont = any('Font' in name for name in notJson)
        if all(notJson.count(folder) > 0 for folder in FOLDERLIST) and amount > 1500:
            if hasFont:
                return 'full'
            return 'nofont'
        if any('mod_info.json' in name for name in namelist):
            return 'FLmod'
        if notJsonAmount >= 3:
            return 'jsononly'
        return 'invalid'
        
def evalFolder(folder_path):
    items = os.listdir(folder_path)
    hasFont = any('Font' in item for item in items)
    if all(any(folder in item for item in items) for folder in FOLDERLIST):
        if hasFont:
            return 'full'
        return 'nofont'
    if 'mod_info.json' in items:
        return 'FLmod'
    if len(items) >= 3:
        return 'jsononly'
    
    return 'invalid'

def eval7zip(file_path):
    tmp = tempfile.mkdtemp()
    try:
        Archive(file_path).extractall(tmp)
        return evalFolder(tmp), tmp
    except Exception as e:
        return 'invalid', tmp
    
def evalJson(json_path):
    pass

if __name__ == '__main__':
    evalZip(r'E:\desktop\limbus transfer\LCTA-Limbus-company-transfer-auto\LimbusLocalize_2026032001.zip')