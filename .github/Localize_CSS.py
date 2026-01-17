import requests
import os
import shutil
from pathlib import Path 

projext_path = Path(__file__).parent.parent

print('开始复制图标文件')
os.chdir(projext_path)
shutil.copy2("favicon.ico", "webui/favicon.ico")
print('复制图标文件完成')

print("开始本地化CSS资源...")
os.chdir(projext_path / "webui")
print(f"切换工作目录至: {os.getcwd()}")

BASE_URL = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/"

FILES = {
    "css": ["all.min.css"],
    "webfonts": ["fa-brands-400.woff2", "fa-solid-900.woff2"]
}

TARGET_CSS = "css/all.min.css"

print("修改index.html文件，替换CDN链接为本地链接...")
with open('index.html', 'r', encoding='utf-8') as f:
    html_content = f.read()
    html_content = html_content.replace(BASE_URL, "")
    print("已完成替换CDN链接")

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
    print("已保存修改后的index.html文件")
    
print("开始下载本地化资源文件...")
for key, items in FILES.items():
    os.makedirs(key, exist_ok=True)
    print(f"创建目录: {key}")
    for i in items:
        print(f"正在下载文件: {key}/{i}")
        with open(os.path.join(key, i), 'wb') as f:
            url = f'{BASE_URL}{key}/{i}'
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            f.write(r.content)
            print(f"已成功下载: {key}/{i}")
            
print("所有资源文件下载完成！")