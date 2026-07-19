import os
import shutil
from pathlib import Path
from typing import List, Tuple

projext_path = Path(__file__).parent.parent

print('开始撰写Release Note')
update_note = projext_path / 'webui' / 'assets' / "update.md"
ABOUT = '''
## 文件下载指导
- LCTA-Portable-Full.zip 正常版本。推荐下载此版本
- LCTA-Portable-Full-Compatible.zip 兼容版，空间占用较大且存在可能出现的UI界面错误，请在无法使用正常版本时使用该版本
- LCTA-update.zip 完整版自动更新功能需求文件，包含项目源码
'''
update_note = update_note.read_text(encoding='utf-8').split('\n')
r = []
flag = False
for i in update_note:
    if i.startswith('##'):
        if flag:
            break
        else:
            flag = True
    r.append(i)
r = '\n'.join(r)
release_note = r + '\n' + ABOUT
Path('update.md').write_text(release_note, encoding='utf-8')
print('生成更新日志成功')

print('开始创建c语言脚本')
createC: List[Tuple[str, List[Tuple[str, str]]]] = [
    ('launcher.c', []),
    ('launcher_debug.c', [('int is_debug = 0;', 'int is_debug = 1;')]),
    ('launcher_qt.c', [('int use_qt = 0;', 'int use_qt = 1;')]),
    ('launcher_qt_debug.c', [('int use_qt = 0;', 'int use_qt = 1;'),
                             ('int is_debug = 0;', 'int is_debug = 1;')]),
    ('test.c', [('char script_name[MAX_PATH] = "code\\start_webui.py";',
                 'char script_name[MAX_PATH] = "code\\webutils\\test.py";'),
                ('int is_debug = 0;', 'int is_debug = 1;')])
]
os.chdir(projext_path)
codeC = Path('launcher.c').read_text(encoding='utf-8')
baseDir = projext_path.parent
for outputPath, actions in createC:
    output = baseDir / outputPath
    outputContent = codeC
    for old, new in actions:
        outputContent = outputContent.replace(old, new)
    output.write_text(outputContent, encoding='utf-8')

print('开始复制图标文件')
shutil.copy2("favicon.ico", "webui/favicon.ico")
print('复制图标文件完成')

print('开始复制README文件')
shutil.copy2("README.md", "webui/assets/README.md")
print('复制README文件完成')

# ---- 下载 CFST (CloudflareSpeedTest) ----
import zipfile
import requests
import warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

CFST_VERSION = "v2.3.5"
CFST_DOWNLOAD_URL = (
    f"https://github.com/XIU2/CloudflareSpeedTest/releases/download/"
    f"{CFST_VERSION}/cfst_windows_amd64.zip"
)
IP_TXT_URL = "https://raw.githubusercontent.com/XIU2/CloudflareSpeedTest/master/ip.txt"

cfst_dir = projext_path / "CFST"
cfst_dir.mkdir(parents=True, exist_ok=True)

print("下载 ip.txt...")
with open(cfst_dir / "ip.txt", "wb") as f:
    r = requests.get(IP_TXT_URL, timeout=10, verify=False)
    r.raise_for_status()
    f.write(r.content)
print("ip.txt 下载完成")

print("下载 cfst.exe...")
cfst_zip_path = cfst_dir / "cfst_windows_amd64.zip"
with open(cfst_zip_path, "wb") as f:
    r = requests.get(CFST_DOWNLOAD_URL, timeout=60, verify=False)
    r.raise_for_status()
    f.write(r.content)

with zipfile.ZipFile(cfst_zip_path, "r") as zf:
    zf.extract("cfst.exe", cfst_dir)
cfst_zip_path.unlink()
print("CFST 下载完成")
