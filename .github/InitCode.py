import requests
import os
import shutil
from pathlib import Path 
import warnings

projext_path = Path(__file__).parent.parent

print('开始撰写Release Note')
update_note = projext_path / 'webui' / 'assets' / "update.md"
ABOUT = '''
## 文件下载指导  
- LCTA-Portable-Full.zip 完整版全功能，空间占用较大。推荐下载此版本  
- LCTA-Folder.zip 兼容版文件夹版  
- LCTA-Folder-Debug.zip 兼容调试版，显示命令窗口  
- LCTA-OneFile.zip 兼容版单文件版  
- LCTA-OneFile-Debug.zip 兼容调试版，显示命令窗口  
- LCTA-update.zip 完整版自动更新功能需求文件，包含项目源码 
'''
update_note = update_note.read_text(encoding='utf-8').split('\n')
r = []
flag = False
for i in update_note:
    if i.startswith('##'):
        if flag:break
        else:flag = True
    r.append(i)
r = '\n'.join(r)
release_note = r + '\n' + ABOUT
Path('update.md').write_text(release_note, encoding='utf-8')
print('生成更新日志成功')

print('开始复制图标文件')
os.chdir(projext_path)
shutil.copy2("favicon.ico", "webui/favicon.ico")
print('复制图标文件完成')

print('开始复制README文件')
shutil.copy2("README.md", "webui/assets/README.md")
print('复制README文件完成')

print("开始本地化样式资源...")
os.chdir(projext_path / "webui")
print(f"切换工作目录至: {os.getcwd()}")

URL_TRANSFER = [("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
                 'css/all.min.css'),
                ("https://cdn.jsdelivr.net/npm/marked/marked.min.js",'marked/marked.min.js'),
                ("https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.1.0/github-markdown-light.min.css",
                 'css/github-markdown-light.min.css')]

FILES = [
    ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
        'css/all.min.css'),
    ("https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.1.0/github-markdown-light.min.css",
        'css/github-markdown-light.min.css'),
    ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-brands-400.woff2",
        'webfonts/fa-brands-400.woff2'),
    ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.woff2",
        'webfonts/fa-solid-900.woff2'),
    ("https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.1.0/github-markdown-light.min.css",
        'css/github-markdown-light.min.css'),
    ("https://cdn.jsdelivr.net/npm/marked/marked.min.js",
        'marked/marked.min.js')
]

print("修改index.html文件，替换CDN链接为本地链接...")
with open('index.html', 'r', encoding='utf-8') as f:
    html_content = f.read()
    for url, path in URL_TRANSFER:
        html_content = html_content.replace(url, path)
    print("已完成替换CDN链接")

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
    print("已保存修改后的index.html文件")
    
print("开始下载本地化资源文件...")
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
for url, file in FILES:
    file_path = Path(file)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"正在下载文件: {file}")
    with open(file, 'wb') as f:
        r = requests.get(url, timeout=10, verify=False)
        r.raise_for_status()
        f.write(r.content)
        print(f"已成功下载: {file}")
            
print("所有资源文件下载完成！")