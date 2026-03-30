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
    'textFile': '文本内容替换包',
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
        
def evalFile(file_path):
    if Path(file_path).is_dir():
        return evalFolder(file_path)
    if file_path.endswith('.zip'):
        return evalZip(file_path)
    if file_path.endswith('.7z'):
        return eval7zip(file_path)[0]
    if file_path.endswith('.json'):
        return evalJson(file_path)
    return 'invalid'

def makeMessage(content):
    message = '<div>'
    count = {key: 0 for key in NAMEREFER}
    for i in content.values():
        count[i] += 1
    for key, value in count.items():
        if value > 0:
            message += f"<p>{NAMEREFER.get(key, key)}: {value}个</p>"
    message += '<br/><hr /><br/>'
    message += '<details><summary>点击展开完整列表</summary><br />'

    for i, t in content.items():
        message += f'<p><strong>{Path(i).name}</strong>: {NAMEREFER.get(t, t)}</p>'
    message += '</details><br /><hr /><br />'
    message += '<p>点击确认以安装</p>'
    message += '</div>'
    if count['update'] and not all(count[key] == 0 for key in count if key != 'update'):
        return 'invalid'
    if all(count[key] == 0 for key in count if key != 'invalid') and count['invalid'] > 0:
        return 'none'
    return message

def evalFiles(files_data, config, logger, modal_id="false"):
    pass

if __name__ == '__main__':
    evalZip(r'E:\desktop\limbus transfer\LCTA-Limbus-company-transfer-auto\LimbusLocalize_2026032001.zip')