# LCTA Build Script
# 参照 .github/workflows/release.yml 的打包逻辑
# 产物输出到 dist/ 目录

$ErrorActionPreference = "Continue"
$APP_NAME = "LCTA"
$PYTHON_VERSION = "3.9.6"

# 切换到脚本所在目录（项目根目录）
Set-Location -Path $PSScriptRoot
$ProjectRoot = (Get-Location).Path
$ParentDir = Split-Path -Parent $ProjectRoot

# 构建缓存目录（不修改源代码）
$BuildCacheDir = "$ProjectRoot\.build_cache"
$PythonZipCache = "$BuildCacheDir\python-$PYTHON_VERSION-embed-amd64.zip"
$PythonEmbedCache = "$BuildCacheDir\python-embed"
$CCompileCache = "$BuildCacheDir\c"
$WebuiBuildCache = "$BuildCacheDir\webui-build"

# 确保缓存目录存在
foreach ($d in @($BuildCacheDir, $PythonEmbedCache, $CCompileCache)) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LCTA Build Script" -ForegroundColor Cyan
Write-Host "  Project: $ProjectRoot" -ForegroundColor Cyan
Write-Host "  Output:  $ProjectRoot\dist" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ============================================================
# Step 1: 初始化代码 (InitCode.py)
# 注意：InitCode 会修改 webui/index.html 并下载资源到源码目录
# 我们在运行后立即将修改版复制到缓存，然后还原源码，确保不污染工作树
# ============================================================
Write-Host "`n[1/6] 初始化代码..." -ForegroundColor Yellow

$initScript = "$ProjectRoot\.github\InitCode.py"
if (Test-Path $initScript) {
    # 备份 webui/index.html 原始内容
    $indexHtmlPath = "$ProjectRoot\webui\index.html"
    $originalIndexHtml = $null
    if (Test-Path $indexHtmlPath) {
        $originalIndexHtml = Get-Content -Path $indexHtmlPath -Raw -Encoding UTF8
    }

    python $initScript
    Write-Host "  InitCode 完成" -ForegroundColor Green

    # 将修改后的 webui/ 复制到缓存
    Write-Host "  保存 InitCode 产物到缓存..."
    if (Test-Path $WebuiBuildCache) {
        Remove-Item $WebuiBuildCache -Recurse -Force
    }
    Copy-Item "$ProjectRoot\webui" $WebuiBuildCache -Recurse -Force

    # 还原源码：恢复 index.html
    if ($originalIndexHtml) {
        [System.IO.File]::WriteAllText($indexHtmlPath, $originalIndexHtml, [System.Text.UTF8Encoding]::new($false))
        Write-Host "  已还原 webui/index.html" -ForegroundColor Green
    }

    # 清理 InitCode 在源码目录产生的产物
    $cleanupPaths = @(
        "$ProjectRoot\webui\favicon.ico",
        "$ProjectRoot\webui\assets\README.md",
        "$ProjectRoot\update.md"
    )
    $cleanupDirs = @(
        "$ProjectRoot\webui\css",
        "$ProjectRoot\webui\webfonts",
        "$ProjectRoot\webui\marked"
    )
    foreach ($p in $cleanupPaths) {
        Remove-Item $p -ErrorAction SilentlyContinue
    }
    foreach ($d in $cleanupDirs) {
        if (Test-Path $d) { Remove-Item $d -Recurse -Force }
    }
    # 清理下载的 nexus/*.js（排除 simulation.js）
    Get-ChildItem "$ProjectRoot\webui\nexus\*.js" -Exclude "simulation.js" -ErrorAction SilentlyContinue |
        Remove-Item -Force
    Write-Host "  源码目录已清理完毕" -ForegroundColor Green
} else {
    Write-Host "  WARNING: InitCode.py 未找到，跳过" -ForegroundColor Yellow
}

# ============================================================
# Step 2: 编译 C 启动器
# ============================================================
Write-Host "`n[2/6] 编译 C 启动器..." -ForegroundColor Yellow

# 检查 gcc 和 windres
$gcc = Get-Command gcc -ErrorAction SilentlyContinue
$windres = Get-Command windres -ErrorAction SilentlyContinue

if (-not $gcc -or -not $windres) {
    Write-Host "  WARNING: gcc/windres 不可用，跳过 C 编译" -ForegroundColor Yellow
    Write-Host "  请安装 MinGW-w64 (可通过 msys2 或 scoop 安装)" -ForegroundColor Yellow
} else {
    # 复制图标
    Copy-Item "$ProjectRoot\favicon.ico" "$ParentDir\launcher.ico" -Force

    # 生成资源文件
    Set-Location $ParentDir
    '1 ICON "launcher.ico"' | Out-File -FilePath "launcher.rc" -Encoding ASCII
    windres launcher.rc -o launcher_res.o

    # 编译各变体（支持 hash 缓存：源文件未变则跳过编译）
    $targets = @(
        @{Src="launcher.c";            Out="launcher.exe"},
        @{Src="launcher_debug.c";      Out="launcher_debug.exe"},
        @{Src="launcher_qt.c";         Out="launcher_qt.exe"},
        @{Src="launcher_qt_debug.c";   Out="launcher_qt_debug.exe"},
        @{Src="test.c";                Out="tester.exe"}
    )

    foreach ($t in $targets) {
        if (-not (Test-Path $t.Src)) {
            Write-Host "  WARNING: $($t.Src) 未找到（可能 InitCode 未生成），跳过" -ForegroundColor Yellow
            continue
        }

        # 计算源文件 hash
        $srcHash = (Get-FileHash -Path $t.Src -Algorithm MD5).Hash
        $hashFile = "$CCompileCache\$($t.Out).hash"
        $cachedExe = "$CCompileCache\$($t.Out)"

        # 检查缓存是否命中
        $cacheHit = $false
        if ((Test-Path $cachedExe) -and (Test-Path $hashFile)) {
            $cachedHash = (Get-Content $hashFile -Raw).Trim()
            if ($cachedHash -eq $srcHash) {
                Write-Host "  使用缓存: $($t.Out)" -ForegroundColor Green
                Copy-Item $cachedExe "$ParentDir\$($t.Out)" -Force
                $cacheHit = $true
            }
        }

        if (-not $cacheHit) {
            Write-Host "  编译 $($t.Src) -> $($t.Out)..."
            gcc -O2 -o $t.Out $t.Src launcher_res.o -lshlwapi
            strip $t.Out
            # 存入缓存
            Copy-Item $t.Out $cachedExe -Force
            $srcHash | Out-File -FilePath $hashFile -Encoding ASCII
            Write-Host "    $($t.Out) 完成" -ForegroundColor Green
        }
    }

    Set-Location $ProjectRoot
    Write-Host "  C 编译完成" -ForegroundColor Green
}

# ============================================================
# Step 3: 准备嵌入式 Python + pip 依赖
# 所有产物写入 .build_cache/，不修改源码目录
# ============================================================
Write-Host "`n[3/6] 准备嵌入式 Python..." -ForegroundColor Yellow

$binsDir = "$PythonEmbedCache\Bins"
$siteDir = "$PythonEmbedCache\Lib\site-packages"

# 检查嵌入式 Python 是否已缓存
if (-not (Test-Path "$binsDir\python.exe")) {
    # 下载 zip（缓存下载）
    if (-not (Test-Path $PythonZipCache)) {
        Write-Host "  下载 Python $PYTHON_VERSION embed..."
        $pythonUrl = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-embed-amd64.zip"
        try {
            Invoke-WebRequest -Uri $pythonUrl -OutFile $PythonZipCache -UseBasicParsing
            Write-Host "  下载完成" -ForegroundColor Green
        } catch {
            Write-Host "  ERROR: 下载嵌入式 Python 失败: $_" -ForegroundColor Red
            Write-Host "  请手动下载并解压到: $binsDir" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "  使用已缓存的 Python zip" -ForegroundColor Green
    }

    New-Item -ItemType Directory -Path $binsDir -Force | Out-Null
    Expand-Archive -Path $PythonZipCache -DestinationPath $binsDir -Force
    Write-Host "  嵌入式 Python 解压完成" -ForegroundColor Green
} else {
    Write-Host "  嵌入式 Python 已缓存，跳过" -ForegroundColor Green
}

# 修改 ._pth 文件以启用 site-packages（仅首次）
if (-not (Test-Path "$binsDir\.pth_modified")) {
    Get-ChildItem "$binsDir\*._pth" | ForEach-Object {
        Add-Content -Path $_.FullName -Value "import site"
        Write-Host "  已修改 $($_.Name) 添加 'import site'"
    }
    # 标记已修改，避免重复
    "done" | Out-File -FilePath "$binsDir\.pth_modified" -Encoding ASCII
} else {
    Write-Host "  ._pth 已修改，跳过" -ForegroundColor Green
}

# 确保 site-packages 目录存在
New-Item -ItemType Directory -Path $siteDir -Force | Out-Null

# 安装 pip 依赖到本地 venv
Write-Host "  检查 pip 依赖..."
$localVenv = "$ProjectRoot\venv"
$localSitePackages = "$localVenv\Lib\site-packages"
$requirementsFile = "$ProjectRoot\requirements.txt"

# 检查本地 venv 是否就绪
if (-not (Test-Path "$localVenv\Scripts\python.exe")) {
    Write-Host "  创建本地 venv..."
    if (Test-Path $localVenv) {
        Remove-Item $localVenv -Recurse -Force
    }
    python -m venv $localVenv
}

$localPython = "$localVenv\Scripts\python.exe"
$localPip = "$localVenv\Scripts\pip.exe"

# 安装/更新依赖
$null = & $localPip install --upgrade pip 2>&1
$null = & $localPip install -r $requirementsFile 2>&1

if (-not (Test-Path $localSitePackages)) {
    Write-Host "  ERROR: pip 依赖安装失败，请检查 requirements.txt" -ForegroundColor Red
    exit 1
}

Write-Host "  pip 依赖准备完成" -ForegroundColor Green

# ============================================================
# Step 4: 组装 dist/ 目录
# ============================================================
Write-Host "`n[4/6] 组装 dist/ 目录..." -ForegroundColor Yellow

$distDir = "$ProjectRoot\dist"
$lctaCode = "$distDir\LCTA\code"
$lctaCompatCode = "$distDir\LCTA-Compatible\code"
$lctaUpdate = "$distDir\LCTA-update"

# 清理旧的 dist
if (Test-Path $distDir) {
    Remove-Item $distDir -Recurse -Force
    Write-Host "  已清理旧的 dist/"
}

# 创建目录结构
$dirs = @(
    $lctaCode,
    "$lctaCode\logs",
    "$lctaCode\tmp",
    $lctaCompatCode,
    "$lctaCompatCode\logs",
    "$lctaCompatCode\tmp",
    $lctaUpdate
)
foreach ($d in $dirs) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}

Write-Host "  目录结构已创建" -ForegroundColor Green

# ---- 复制项目源文件 ----
Write-Host "  复制源文件..."

# 排除列表
$excludeDirs = @(
    ".git",
    "__pycache__",
    "logs",
    "tmp",
    "dist",
    "code",
    ".venv",
    "node_modules",
    ".vscode",
    ".idea",
    ".workshop",
    "dev_cache",
    "dev_assets",
    "translatekit",
    "LLc-CN_LCTA",
    ".github",
    "venv",
    "build",
    ".build_cache"
)

$excludeFiles = @(
    "*.pyc",
    "*.pyo",
    ".rmv",
    ".lock",
    ".env",
    "proper.json",
    "build.ps1"
)

function Copy-ProjectFiles {
    param([string]$Destination)

    Get-ChildItem $ProjectRoot -Force | ForEach-Object {
        $name = $_.Name

        # 检查目录排除
        if ($_.PSIsContainer) {
            if ($excludeDirs -contains $name) { return }
            # 排除隐藏文件夹（除了必须的）
            if ($name.StartsWith('.') -and $name -ne '.gitkeep') { return }
            Copy-Item $_.FullName "$Destination\$name" -Recurse -Force
            Write-Host "    目录: $name"
        } else {
            # 检查文件排除
            $excluded = $false
            foreach ($pattern in $excludeFiles) {
                if ($name -like $pattern) {
                    $excluded = $true
                    break
                }
            }
            if ($excluded) { return }
            if ($name.StartsWith('.') -and $name -ne '.gitattributes') { return }

            Copy-Item $_.FullName "$Destination\$name" -Force
        }
    }
}

# 复制到 LCTA/code/
Copy-ProjectFiles $lctaCode

# 复制到 LCTA-Compatible/code/
Copy-ProjectFiles $lctaCompatCode

# 复制到 LCTA-update/（纯源码，也排除 .git 已在函数中处理）
Copy-ProjectFiles $lctaUpdate

Write-Host "  源文件复制完成" -ForegroundColor Green

# ---- 覆盖 webui/ 为 InitCode 修改版 ----
if (Test-Path $WebuiBuildCache) {
    Write-Host "  使用 InitCode 修改版 webui..."
    foreach ($dest in @($lctaCode, $lctaCompatCode, $lctaUpdate)) {
        # 移除源码 webui，替换为 InitCode 修改版
        $destWebui = "$dest\webui"
        if (Test-Path $destWebui) { Remove-Item $destWebui -Recurse -Force }
        Copy-Item $WebuiBuildCache $destWebui -Recurse -Force
    }
    Write-Host "  webui 已替换为 InitCode 修改版" -ForegroundColor Green
}

# ---- 复制 venv (Bins + Lib) 从缓存到各版本 ----
Write-Host "  复制嵌入式 Python venv..."

# 确保目标干净（避免嵌套）
$targetVenvLcta = "$lctaCode\venv"
$targetVenvCompat = "$lctaCompatCode\venv"
if (Test-Path $targetVenvLcta) { Remove-Item $targetVenvLcta -Recurse -Force }
if (Test-Path $targetVenvCompat) { Remove-Item $targetVenvCompat -Recurse -Force }

# 从 .build_cache/python-embed/ 复制（而非源码 code/venv/）
Copy-Item $PythonEmbedCache $targetVenvLcta -Recurse -Force
Copy-Item $PythonEmbedCache $targetVenvCompat -Recurse -Force

# 填入 site-packages（从本地 venv 直接复制到 dist）
Write-Host "  复制 pip 依赖到 dist..."
Copy-Item "$localSitePackages\*" "$targetVenvLcta\Lib\site-packages" -Recurse -Force
Copy-Item "$localSitePackages\*" "$targetVenvCompat\Lib\site-packages" -Recurse -Force
Write-Host "  pip 依赖复制完成" -ForegroundColor Green

# ---- 兼容版额外安装 PyQt ----
Write-Host "  为兼容版安装 PyQt..."
$compatPython = "$lctaCompatCode\venv\Bins\python.exe"
$compatSitePackages = "$lctaCompatCode\venv\Lib\site-packages"

if (Test-Path $compatPython) {
    # 先临时安装到本地 venv，再复制过去
    $null = & $localPip install PyQt5 qtpy PyQtWebEngine --target "$lctaCompatCode\venv\Lib\site-packages" 2>&1
} else {
    Write-Host "  WARNING: 嵌入式 Python 不可用，请在 venv/Bins/ 放置 python.exe" -ForegroundColor Yellow
}

Write-Host "  venv 复制完成" -ForegroundColor Green

# ---- 复制 C 启动器 exe ----
Write-Host "  复制 C 启动器..."

$testerName = "无法打开？运行环境检测.exe"

# LCTA（正常版）
if (Test-Path "$ParentDir\launcher.exe") {
    Copy-Item "$ParentDir\launcher.exe" "$distDir\LCTA\launcher.exe" -Force
    Write-Host "    LCTA/launcher.exe" -ForegroundColor Green
}
if (Test-Path "$ParentDir\launcher_debug.exe") {
    Copy-Item "$ParentDir\launcher_debug.exe" "$distDir\LCTA\launcher_debug.exe" -Force
    Write-Host "    LCTA/launcher_debug.exe" -ForegroundColor Green
}
if (Test-Path "$ParentDir\tester.exe") {
    Copy-Item "$ParentDir\tester.exe" "$distDir\LCTA\$testerName" -Force
    Write-Host "    LCTA/$testerName" -ForegroundColor Green
}

# LCTA-Compatible（兼容版 — 用 qt 变体）
if (Test-Path "$ParentDir\launcher_qt.exe") {
    Copy-Item "$ParentDir\launcher_qt.exe" "$distDir\LCTA-Compatible\launcher.exe" -Force
    Write-Host "    LCTA-Compatible/launcher.exe (qt)" -ForegroundColor Green
}
if (Test-Path "$ParentDir\launcher_qt_debug.exe") {
    Copy-Item "$ParentDir\launcher_qt_debug.exe" "$distDir\LCTA-Compatible\launcher_debug.exe" -Force
    Write-Host "    LCTA-Compatible/launcher_debug.exe (qt)" -ForegroundColor Green
}
if (Test-Path "$ParentDir\tester.exe") {
    Copy-Item "$ParentDir\tester.exe" "$distDir\LCTA-Compatible\$testerName" -Force
    Write-Host "    LCTA-Compatible/$testerName" -ForegroundColor Green
}

# 清理编译中间文件
Remove-Item "$ParentDir\launcher.ico" -ErrorAction SilentlyContinue
Remove-Item "$ParentDir\launcher.rc" -ErrorAction SilentlyContinue
Remove-Item "$ParentDir\launcher_res.o" -ErrorAction SilentlyContinue

Write-Host "  启动器复制完成" -ForegroundColor Green

# ---- 创建必要的空目录 ----
foreach ($versionDir in @("$distDir\LCTA\code", "$distDir\LCTA-Compatible\code")) {
    # 确保 logs/ 和 tmp/ 存在
    if (-not (Test-Path "$versionDir\logs")) {
        New-Item -ItemType Directory -Path "$versionDir\logs" -Force | Out-Null
    }
    if (-not (Test-Path "$versionDir\tmp")) {
        New-Item -ItemType Directory -Path "$versionDir\tmp" -Force | Out-Null
    }
}

Write-Host "  dist/ 组装完成" -ForegroundColor Green

# ============================================================
# Step 5: 处理 update 包 — 移除 .git 目录
# ============================================================
Write-Host "`n[5/6] 处理 update 包..." -ForegroundColor Yellow

$updateGit = "$lctaUpdate\.git"
$updateGithub = "$lctaUpdate\.github"
if (Test-Path $updateGit) {
    Remove-Item $updateGit -Recurse -Force
}
if (Test-Path $updateGithub) {
    Remove-Item $updateGithub -Recurse -Force
}
Write-Host "  update 包处理完成" -ForegroundColor Green

# ============================================================
# Step 6: ZIP 打包
# ============================================================
Write-Host "`n[6/6] ZIP 打包..." -ForegroundColor Yellow

# 确保 dist 下没有旧 ZIP
Remove-Item "$distDir\*.zip" -ErrorAction SilentlyContinue

$zipFull = "$distDir\$APP_NAME-Portable-Full.zip"
$zipCompat = "$distDir\$APP_NAME-Portable-Full-Compatible.zip"
$zipUpdate = "$distDir\$APP_NAME-update.zip"

Write-Host "  创建 $APP_NAME-Portable-Full.zip..."
Compress-Archive -Path "$distDir\LCTA\*" -DestinationPath $zipFull -Force

Write-Host "  创建 $APP_NAME-Portable-Full-Compatible.zip..."
Compress-Archive -Path "$distDir\LCTA-Compatible\*" -DestinationPath $zipCompat -Force

Write-Host "  创建 $APP_NAME-update.zip..."
Compress-Archive -Path "$distDir\LCTA-update\*" -DestinationPath $zipUpdate -Force

Write-Host "  ZIP 打包完成" -ForegroundColor Green

# ============================================================
# 完成
# ============================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  构建完成！" -ForegroundColor Green
Write-Host "  产物目录: $distDir" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 显示大小信息
Write-Host "`n产物大小:" -ForegroundColor Yellow
Get-ChildItem $distDir -Recurse -File |
    Group-Object { $_.Directory.Name } |
    ForEach-Object {
        $sizeMB = [math]::Round(($_.Group | Measure-Object Length -Sum).Sum / 1MB, 2)
        Write-Host "  $($_.Name): $sizeMB MB"
    }

$zipFiles = Get-ChildItem "$distDir\*.zip"
if ($zipFiles) {
    Write-Host "`nZIP 包:" -ForegroundColor Yellow
    $zipFiles | ForEach-Object {
        $sizeMB = [math]::Round($_.Length / 1MB, 2)
        Write-Host "  $($_.Name): $sizeMB MB"
    }
}

Write-Host "`nDone." -ForegroundColor Green
