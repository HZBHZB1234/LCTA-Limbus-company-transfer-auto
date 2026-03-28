from pathlib import Path
import os
from pyunpack import Archive
import shutil
import tempfile
import json
import zipfile

FOLDERLIST = [
    'BattleAnnouncerDlg',
    'BgmLyrics',
    'EGOVoiceDig',
    'PersonalityVoiceDlg',
    'StoryData',
]

NAMEREFER = {
    'full': '汉化包',
    'nofont': '无字体汉化包',
    'FLmod': '浮士德启动器格式模组',
    'jsononly': '文本内容替换包',
    'update': '更新包',
    'invalid': '无效的文件',
    'carra': '贴图模组',
    'bank': '音效模组',
    'textfile': '文本内容替换包',
    'LCTAchange': 'LCTA文本修改包',
    'FLchange': '浮士德启动器格式文本修改包',
}

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
        if any('requirements.txt' in name for name in notJsonAmount) and any('start_webui.py' in name for name in notJsonAmount):
            return 'update'
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
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if 'dataList' in data:
            return 'textFile'
        if 'patches' in data:
            return 'LCTAchange'
        if isinstance(data, dict) and all('dataList' in i for i in data.values()):
            return 'FLchange'
        return 'invalid'
    except Exception as e:
        return 'invalid'
        

if __name__ == '__main__':
    evalZip(r'E:\desktop\limbus transfer\LCTA-Limbus-company-transfer-auto\LimbusLocalize_2026032001.zip')