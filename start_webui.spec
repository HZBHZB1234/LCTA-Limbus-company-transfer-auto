# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

block_cipher = None

# 获取项目根目录
project_root = Path(os.path.dirname(__file__))

# 定义需要收集的资源文件
datas = [
    # 收集webui目录下的所有文件
    (str(project_root / 'webui' / 'index.html'), 'webui'),
    (str(project_root / 'webui' / 'script.js'), 'webui'),
    (str(project_root / 'webui' / 'style.css'), 'webui'),
    
    # 收集配置文件
    (str(project_root / 'config_default.json'), '.'),
    (str(project_root / 'config_check.json'), '.'),
]

# 如果还有其他需要打包的目录或文件，可以继续添加到datas列表中

a = Analysis(
    ['start_webui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='start_webui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)