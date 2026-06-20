# LCTA Build Script
# 参照 .github/workflows/release.yml 的打包逻辑
# 产物输出到 dist/ 目录

$ErrorActionPreference = "Continue"
$APP_NAME = "LCTA"
$PYTHON_VERSION = "3.9.6"

Set-Location -Path $PSScriptRoot
$ProjectRoot = (Get-Location).Path
$ParentDir = Split-Path -Parent $ProjectRoot

# 构建缓存目录
$BuildCacheDir = "$ProjectRoot\.build_cache"
$PythonZipCache = "$BuildCacheDir\python-$PYTHON_VERSION-embed-amd64.zip"
$PythonEmbedCache = "$BuildCacheDir\python-embed"
$CCompileCache = "$BuildCacheDir\c"
$WebuiBuildCache = "$BuildCacheDir\webui-build"

foreach ($d in @($BuildCacheDir, $PythonEmbedCache, $CCompileCache)) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LCTA Build Script" -ForegroundColor Cyan
Write-Host "  Project: $ProjectRoot" -ForegroundColor Cyan
Write-Host "  Output:  $ProjectRoot\dist" -ForegroundColor Cyan
Write-Host "  Cache:   $BuildCacheDir" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ============================================================
# Step 1: InitCode（含缓存）
# ============================================================
Write-Host "`n[1/6] 初始化代码..." -ForegroundColor Yellow

$initScript = "$ProjectRoot\.github\InitCode.py"
$indexHtmlPath = "$ProjectRoot\webui\index.html"
$initCodeHashFile = "$BuildCacheDir\initcode.hash"
$initCodeCSourcesCache = "$BuildCacheDir\initcode-c-sources"

if (Test-Path $initScript) {
    # 计算缓存键：InitCode.py 读取的所有输入文件的 MD5（与 InitCode.py 的读取逻辑同步）
    # InitCode.py 读取的文件: InitCode.py 自身, launcher.c, webui/index.html,
    #   webui/assets/update.md, favicon.ico, README.md
    $initInputFiles = @(
        @{Path=$initScript;                              Label="InitCode.py"},
        @{Path="$ProjectRoot\launcher.c";                Label="launcher.c"},
        @{Path=$indexHtmlPath;                           Label="index.html"},
        @{Path="$ProjectRoot\webui\assets\update.md";    Label="update.md"},
        @{Path="$ProjectRoot\favicon.ico";              Label="favicon.ico"},
        @{Path="$ProjectRoot\README.md";                 Label="README.md"}
    )

    $hashParts = [System.Collections.Generic.List[string]]::new()
    foreach ($f in $initInputFiles) {
        if (Test-Path $f.Path) {
            $h = (Get-FileHash -Path $f.Path -Algorithm MD5).Hash
            $hashParts.Add("$($f.Label)=$h")
        } else {
            $hashParts.Add("$($f.Label)=MISSING")
        }
    }
    $currentInitHash = $hashParts -join "|"

    $initCacheHit = $false
    if ((Test-Path $WebuiBuildCache) -and (Test-Path $initCodeHashFile) -and (Test-Path $initCodeCSourcesCache)) {
        $cachedInitHash = (Get-Content $initCodeHashFile -Raw).Trim()
        if ($cachedInitHash -eq $currentInitHash) {
            Write-Host "  InitCode 缓存命中，跳过" -ForegroundColor Green
            $initCacheHit = $true
        }
    }

    if (-not $initCacheHit) {
        # 备份 webui/index.html
        $originalIndexHtml = $null
        if (Test-Path $indexHtmlPath) {
            $originalIndexHtml = Get-Content -Path $indexHtmlPath -Raw -Encoding UTF8
        }

        # 执行 InitCode（会修改源码目录下的 webui/ 并在 ParentDir 写入 C 源码）
        $initOutput = & python $initScript 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ERROR: InitCode 执行失败" -ForegroundColor Red
            Write-Host $initOutput
            exit 1
        }
        Write-Host "  InitCode 完成" -ForegroundColor Green

        # 保存 InitCode 修改后的 webui 到缓存
        if (Test-Path $WebuiBuildCache) {
            Remove-Item $WebuiBuildCache -Recurse -Force
        }
        Copy-Item "$ProjectRoot\webui" $WebuiBuildCache -Recurse -Force

        # 保存 InitCode 生成的 C 源文件到缓存
        if (Test-Path $initCodeCSourcesCache) {
            Remove-Item $initCodeCSourcesCache -Recurse -Force
        }
        New-Item -ItemType Directory -Path $initCodeCSourcesCache -Force | Out-Null
        $generatedCSources = @("launcher.c", "launcher_debug.c", "launcher_qt.c",
                               "launcher_qt_debug.c", "test.c")
        foreach ($cf in $generatedCSources) {
            $srcPath = "$ParentDir\$cf"
            if (Test-Path $srcPath) {
                Copy-Item $srcPath "$initCodeCSourcesCache\$cf" -Force
            }
        }
        Write-Host "  C 源文件已缓存" -ForegroundColor Green

        # 还原 webui/index.html
        if ($originalIndexHtml) {
            [System.IO.File]::WriteAllText($indexHtmlPath, $originalIndexHtml, [System.Text.UTF8Encoding]::new($false))
            Write-Host "  已还原 webui/index.html" -ForegroundColor Green
        }

        # 清理 InitCode 在源码目录产生的下载产物
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
        Get-ChildItem "$ProjectRoot\webui\nexus\*.js" -Exclude "simulation.js" -ErrorAction SilentlyContinue |
            Remove-Item -Force

        # 写入缓存键
        $currentInitHash | Out-File -FilePath $initCodeHashFile -Encoding ASCII
        Write-Host "  InitCode 缓存已更新" -ForegroundColor Green
    } else {
        # 从缓存恢复 C 源文件到父目录（供 Step 2 编译使用）
        Get-ChildItem "$initCodeCSourcesCache\*" -ErrorAction SilentlyContinue | ForEach-Object {
            Copy-Item $_.FullName "$ParentDir\$($_.Name)" -Force
        }
        Write-Host "  已从缓存恢复 C 源文件到父目录" -ForegroundColor Green
    }
} else {
    Write-Host "  WARNING: InitCode.py 未找到，跳过" -ForegroundColor Yellow
}

# ============================================================
# Step 2: 编译 C 启动器
# ============================================================
Write-Host "`n[2/6] 编译 C 启动器..." -ForegroundColor Yellow

$gcc = Get-Command gcc -ErrorAction SilentlyContinue
$windres = Get-Command windres -ErrorAction SilentlyContinue

if (-not $gcc -or -not $windres) {
    Write-Host "  WARNING: gcc/windres 不可用，跳过 C 编译" -ForegroundColor Yellow
    Write-Host "  请安装 MinGW-w64 (可通过 msys2 或 scoop 安装)" -ForegroundColor Yellow
} else {
    Copy-Item "$ProjectRoot\favicon.ico" "$ParentDir\launcher.ico" -Force

    Set-Location $ParentDir
    '1 ICON "launcher.ico"' | Out-File -FilePath "launcher.rc" -Encoding ASCII
    windres launcher.rc -o launcher_res.o

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

        $srcHash = (Get-FileHash -Path $t.Src -Algorithm MD5).Hash
        $hashFile = "$CCompileCache\$($t.Out).hash"
        $cachedExe = "$CCompileCache\$($t.Out)"

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
            # -mwindows: 编译为GUI子系统，双击启动时不显示控制台窗口
            # tester.exe 不加 -mwindows，因其为诊断工具需要控制台
            $guiFlag = if ($t.Out -eq "tester.exe") { "" } else { "-mwindows" }
            gcc -O2 $guiFlag -o $t.Out $t.Src launcher_res.o -lshlwapi
            strip $t.Out
            Copy-Item $t.Out $cachedExe -Force
            $srcHash | Out-File -FilePath $hashFile -Encoding ASCII
            Write-Host "    $($t.Out) 完成" -ForegroundColor Green
        }
    }

    Set-Location $ProjectRoot
    Write-Host "  C 编译完成" -ForegroundColor Green
}

# ============================================================
# Step 3: 嵌入式 Python + pip 依赖
# ============================================================
Write-Host "`n[3/6] 准备嵌入式 Python..." -ForegroundColor Yellow

$binsDir = "$PythonEmbedCache\Bins"
$siteDir = "$PythonEmbedCache\Lib\site-packages"

if (-not (Test-Path "$binsDir\python.exe")) {
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
    "done" | Out-File -FilePath "$binsDir\.pth_modified" -Encoding ASCII
} else {
    Write-Host "  ._pth 已修改，跳过" -ForegroundColor Green
}

New-Item -ItemType Directory -Path $siteDir -Force | Out-Null

# 查找系统 Python 3.9.6（需与嵌入式 Python 版本一致）
Write-Host "  查找系统 Python 3.9.6..."
$python396 = $null
$candidatePaths = @(
    "$env:LOCALAPPDATA\Programs\Python\Python39\python.exe",
    "C:\Python39\python.exe",
    "C:\Program Files\Python39\python.exe"
)

foreach ($p in $candidatePaths) {
    if (Test-Path $p) {
        $ver = & $p --version 2>&1
        if ($ver -match "3\.9\.6") {
            $python396 = $p
            Write-Host "  找到 Python 3.9.6: $p" -ForegroundColor Green
            break
        }
    }
}

if (-not $python396) {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $py39Path = & py -3.9 -c "import sys; print(sys.executable)" 2>$null
        if ($py39Path) {
            $ver = & $py39Path --version 2>&1
            if ($ver -match "3\.9\.6") {
                $python396 = $py39Path
                Write-Host "  通过 py launcher 找到 Python 3.9.6: $python396" -ForegroundColor Green
            }
        }
    }
}

if (-not $python396) {
    Write-Host "  ERROR: 未找到 Python 3.9.6" -ForegroundColor Red
    Write-Host ""
    Write-Host "  构建需要系统安装 Python 3.9.6 来创建虚拟环境和安装依赖。" -ForegroundColor Yellow
    Write-Host "  Python 3.9.6 下载地址:" -ForegroundColor Yellow
    Write-Host "    https://www.python.org/ftp/python/3.9.6/python-3.9.6-amd64.exe" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  已检查的路径:" -ForegroundColor Yellow
    foreach ($p in $candidatePaths) {
        Write-Host "    $p" -ForegroundColor DarkGray
    }
    Write-Host "  也尝试了 py -3.9 启动器" -ForegroundColor DarkGray
    exit 1
}

# 安装 pip 依赖到本地 venv（输出仅在错误时显示）
Write-Host "  检查 pip 依赖..."
$localVenv = "$ProjectRoot\venv"
$localSitePackages = "$localVenv\Lib\site-packages"
$requirementsFile = "$ProjectRoot\requirements.txt"

$venvPythonExe = "$localVenv\Scripts\python.exe"
$needCreate = -not (Test-Path $venvPythonExe)
if (-not $needCreate) {
    $existingVer = & $venvPythonExe --version 2>&1
    if ($existingVer -notmatch "3\.9\.6") {
        Write-Host "  已有 venv 版本不匹配 ($existingVer)，重建..." -ForegroundColor Yellow
        Remove-Item $localVenv -Recurse -Force
        $needCreate = $true
    }
}
if ($needCreate) {
    Write-Host "  使用 Python 3.9.6 创建本地 venv..."
    if (Test-Path $localVenv) {
        Remove-Item $localVenv -Recurse -Force
    }
    & $python396 -m venv $localVenv
    if (-not (Test-Path $venvPythonExe)) {
        Write-Host "  ERROR: 创建 venv 失败" -ForegroundColor Red
        exit 1
    }
}

$localPip = "$localVenv\Scripts\pip.exe"
if (-not (Test-Path $localPip)) {
    Write-Host "  venv 中缺少 pip，使用 ensurepip 引导安装..." -ForegroundColor Yellow
    & $venvPythonExe -m ensurepip --upgrade
    if (-not (Test-Path $localPip)) {
        Write-Host "  ERROR: 无法在 venv 中安装 pip" -ForegroundColor Red
        exit 1
    }
}

# 安装/更新依赖（隐藏正常输出）
Write-Host "  安装 pip 依赖（Python 3.9.6）..."
$pipOutput = & $venvPythonExe -m pip install --upgrade pip 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: pip 升级失败" -ForegroundColor Red
    Write-Host $pipOutput
    exit 1
}
$pipOutput = & $localPip install -r $requirementsFile 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: pip 依赖安装失败，请检查网络连接或 requirements.txt" -ForegroundColor Red
    Write-Host $pipOutput
    exit 1
}

# 修补 requests 库：禁用 SSL 验证
$requestsSession = "$localSitePackages\requests\sessions.py"
$sessionContent = Get-Content $requestsSession -Raw -Encoding UTF8
$sessionContent = $sessionContent.Replace('verify=None,', 'verify=False,')
[System.IO.File]::WriteAllText($requestsSession, $sessionContent, [System.Text.UTF8Encoding]::new($false))
Write-Host "  已修补 requests SSL 验证 (verify=None -> verify=False)" -ForegroundColor Green

Write-Host "  pip 依赖准备完成" -ForegroundColor Green

# ============================================================
# Step 4: 组装 dist/ 目录
# ============================================================
Write-Host "`n[4/6] 组装 dist/ 目录..." -ForegroundColor Yellow

$distDir = "$ProjectRoot\dist"
$lctaCode = "$distDir\LCTA\code"
$lctaCompatCode = "$distDir\LCTA-Compatible\code"
$lctaUpdate = "$distDir\LCTA-update"

if (Test-Path $distDir) {
    Remove-Item $distDir -Recurse -Force
    Write-Host "  已清理旧的 dist/"
}

$dirs = @($lctaCode, $lctaCompatCode, $lctaUpdate)
foreach ($d in $dirs) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}
Write-Host "  目录结构已创建" -ForegroundColor Green

# ---- 复制项目源文件 ----
Write-Host "  复制源文件..."

$excludeDirs = @(
    ".git", "__pycache__", "logs", "tmp", "dist", "code",
    ".venv", "node_modules", ".vscode", ".idea", ".workshop",
    "dev_cache", "dev_assets", "translatekit",
    "LLc-CN_LCTA", ".github", "venv", "build", ".build_cache"
)

$excludeFiles = @(
    "*.pyc", "*.pyo", ".rmv", ".lock", ".env", "proper.json", "build.ps1"
)

# 优先使用 git ls-files（自动匹配 .gitignore），与 CI checkout 行为一致
function Copy-ProjectFiles {
    param([string]$Destination)

    Push-Location $ProjectRoot
    $gitFiles = & git ls-files -z --cached --others --exclude-standard 2>$null
    Pop-Location

    if ($gitFiles) {
        $fileList = $gitFiles -split "`0" | Where-Object { $_ -ne '' }
        $count = 0
        foreach ($file in $fileList) {
            $src = Join-Path $ProjectRoot $file
            $dst = Join-Path $Destination $file
            $dstDir = Split-Path -Parent $dst
            if (-not (Test-Path $dstDir)) {
                New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
            }
            if (Test-Path $src) {
                Copy-Item $src $dst -Force
                $count++
            }
        }
        Write-Host "    通过 git ls-files 复制了 $count 个文件 (.gitignore 匹配)" -ForegroundColor Green
    } else {
        Write-Host "    git 不可用，使用手动排除列表" -ForegroundColor Yellow

        Get-ChildItem $ProjectRoot -Force | ForEach-Object {
            $name = $_.Name
            if ($_.PSIsContainer) {
                if ($excludeDirs -contains $name) { return }
                if ($name.StartsWith('.') -and $name -ne '.gitkeep') { return }
                Copy-Item $_.FullName "$Destination\$name" -Recurse -Force
            } else {
                $excluded = $false
                foreach ($pattern in $excludeFiles) {
                    if ($name -like $pattern) { $excluded = $true; break }
                }
                if ($excluded) { return }
                if ($name.StartsWith('.') -and $name -ne '.gitattributes') { return }
                Copy-Item $_.FullName "$Destination\$name" -Force
            }
        }
    }
}

Copy-ProjectFiles $lctaCode
Copy-ProjectFiles $lctaCompatCode
Copy-ProjectFiles $lctaUpdate

Write-Host "  源文件复制完成" -ForegroundColor Green

# ---- 替换 webui 为 InitCode 修改版 ----
if (Test-Path $WebuiBuildCache) {
    Write-Host "  使用 InitCode 修改版 webui..."
    foreach ($dest in @($lctaCode, $lctaCompatCode, $lctaUpdate)) {
        $destWebui = "$dest\webui"
        if (Test-Path $destWebui) { Remove-Item $destWebui -Recurse -Force }
        Copy-Item $WebuiBuildCache $destWebui -Recurse -Force
    }
    Write-Host "  webui 已替换为 InitCode 修改版" -ForegroundColor Green
}

# ---- 复制 venv（嵌入式 Python + site-packages + Scripts） ----
Write-Host "  复制嵌入式 Python venv..."

$targetVenvLcta = "$lctaCode\venv"
$targetVenvCompat = "$lctaCompatCode\venv"
if (Test-Path $targetVenvLcta) { Remove-Item $targetVenvLcta -Recurse -Force }
if (Test-Path $targetVenvCompat) { Remove-Item $targetVenvCompat -Recurse -Force }

Copy-Item $PythonEmbedCache $targetVenvLcta -Recurse -Force
Copy-Item $PythonEmbedCache $targetVenvCompat -Recurse -Force

foreach ($targetVenv in @($targetVenvLcta, $targetVenvCompat)) {
    Copy-Item "$localVenv\Scripts" "$targetVenv\Scripts" -Recurse -Force
    Copy-Item "$localVenv\pyvenv.cfg" "$targetVenv\pyvenv.cfg" -Force
    if (Test-Path "$localVenv\Include") {
        Copy-Item "$localVenv\Include" "$targetVenv\Include" -Recurse -Force
    }
}

Write-Host "  复制 pip 依赖到 dist..."
Copy-Item "$localSitePackages\*" "$targetVenvLcta\Lib\site-packages" -Recurse -Force
Copy-Item "$localSitePackages\*" "$targetVenvCompat\Lib\site-packages" -Recurse -Force
Write-Host "  pip 依赖复制完成" -ForegroundColor Green

# ---- 兼容版额外安装 PyQt ----
Write-Host "  为兼容版安装 PyQt..."
$compatPython = "$lctaCompatCode\venv\Bins\python.exe"

if (Test-Path $compatPython) {
    $pyqtOutput = & $compatPython -m pip install PyQt5 qtpy PyQtWebEngine 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  WARNING: PyQt 安装失败" -ForegroundColor Yellow
        Write-Host $pyqtOutput
    } else {
        Write-Host "  PyQt 安装完成" -ForegroundColor Green
    }
} else {
    Write-Host "  WARNING: 嵌入式 Python 不可用，跳过 PyQt 安装" -ForegroundColor Yellow
}

Write-Host "  venv 复制完成" -ForegroundColor Green

# ---- 复制 C 启动器 ----
Write-Host "  复制 C 启动器..."

$testerName = "无法打开？运行环境检测.exe"

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

Remove-Item "$ParentDir\launcher.ico" -ErrorAction SilentlyContinue
Remove-Item "$ParentDir\launcher.rc" -ErrorAction SilentlyContinue
Remove-Item "$ParentDir\launcher_res.o" -ErrorAction SilentlyContinue

Write-Host "  启动器复制完成" -ForegroundColor Green
Write-Host "  dist/ 组装完成" -ForegroundColor Green

# ============================================================
# Step 5: 处理 update 包
# ============================================================
Write-Host "`n[5/6] 处理 update 包..." -ForegroundColor Yellow

$updateGit = "$lctaUpdate\.git"
$updateGithub = "$lctaUpdate\.github"
if (Test-Path $updateGit) { Remove-Item $updateGit -Recurse -Force }
if (Test-Path $updateGithub) { Remove-Item $updateGithub -Recurse -Force }
Write-Host "  update 包处理完成" -ForegroundColor Green

# ============================================================
# Step 6: ZIP 打包
# ============================================================
Write-Host "`n[6/6] ZIP 打包..." -ForegroundColor Yellow

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

# 显示 dist 目录下直接产物（非递归）
Write-Host "`n产物:" -ForegroundColor Yellow
Get-ChildItem $distDir | ForEach-Object {
    if ($_.PSIsContainer) {
        Write-Host "  [$($_.Name)]"
    } else {
        $sizeMB = [math]::Round($_.Length / 1MB, 2)
        Write-Host "  $($_.Name): $sizeMB MB"
    }
}

Write-Host "`nDone." -ForegroundColor Green
