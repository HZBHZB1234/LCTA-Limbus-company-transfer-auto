import requests
import os
import shutil
from pathlib import Path 
import warnings
from typing import List, Dict, Tuple
import re

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
        if flag:break
        else:flag = True
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
                       ('int is_debug = 0;', 'int is_debug = 1;')])
]
os.chdir(projext_path)
codeC = Path('launcher.c').read_text(encoding='utf-8')
baseDir = projext_path.parent
for outputPath, actions in createC:
    output = baseDir / outputPath
    outputContent = codeC
    for _, __ in actions:
        outputContent = outputContent.replace(_, __)
    output.write_text(outputContent, encoding='utf-8')

print('开始复制图标文件')
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
        'marked/marked.min.js'),
    ("https://web-static-res-edge-speedtest-b1-hk.dahi.edu.eu.org/scripts/556780/1710242/NexusMods%20%E4%B8%AD%E6%96%87%E5%8C%96-%E8%AF%8D%E5%BA%93.js",
        'nexus/dict.js'),
    ("https://update.greasyfork.org.cn/scripts/556781/NexusMods%20%E4%B8%AD%E6%96%87%E5%8C%96%E6%8F%92%E4%BB%B6.user.js",
        'nexus/cn.js'),
    ("https://update.greasyfork.org.cn/scripts/519037/Nexus%20No%20Wait%20%2B%2B.user.js",
        'nexus/skip.js')
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


print("修改marked.js，替换.at()")
def replace_at_with_brackets(code: str) -> str:
    """
    将 JavaScript 代码中的数组 .at() 方法替换为 [] 访问。
    只处理参数为数字字面量的情况（包括负数），对于其他表达式保持原样。
    例如：
        arr.at(0)   -> arr[0]
        arr.at(-1)  -> arr[arr.length - 1]
        arr.at(i)   -> arr.at(i)   (保持不变)
    """
    def repl(match):
        array_name = match.group(1)          # 数组名，可能包含点，如 obj.arr
        arg = match.group(2).strip()         # 参数，去除空格
        # 检查参数是否为整数（允许负号）
        if re.match(r'^-?\d+$', arg):
            num = int(arg)
            if num >= 0:
                return f"{array_name}[{num}]"
            else:
                # 负数转换为 array[array.length - abs(num)]
                return f"{array_name}[{array_name}.length - {abs(num)}]"
        else:
            # 非数字字面量，保持原样
            return match.group(0)

    # 匹配模式：数组名.at(参数)
    pattern = re.compile(r'([\w.]+)\.at\(([^)]+)\)')
    return pattern.sub(repl, code)
with open('marked/marked.min.js', 'r', encoding='utf-8') as f:
    marked = f.read()
    marked = replace_at_with_brackets(marked)

with open('marked/marked.min.js', 'w', encoding='utf-8') as f:
    f.write(marked)
