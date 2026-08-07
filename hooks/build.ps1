# hooks/build.ps1
# 独立编译 rawinput hook DLL。产物：$(本项目根)\hooks\rawinput_hook.dll
# 说明：完整构建流程请使用项目根目录的 build.ps1（本文件不参与该流程，
#       根 build.ps1 使用 .NET 兼容的缓存机制独立编译同名 DLL）。

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$HookSrc = Join-Path $PSScriptRoot "rawinput_hook.c"
$HookOut = Join-Path $PSScriptRoot "rawinput_hook.dll"

$gcc = Get-Command gcc -ErrorAction SilentlyContinue
if (-not $gcc) {
    Write-Host "ERROR: gcc 不可用，请安装 MinGW-w64 (msys2 / scoop mingw)" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $HookSrc)) {
    Write-Host "ERROR: 源码不存在: $HookSrc" -ForegroundColor Red
    exit 1
}

Write-Host "编译 $HookSrc -> $HookOut..."
gcc -shared -O2 -s -static-libgcc -o $HookOut $HookSrc -lpsapi
if ($LASTEXITCODE -ne 0) {
    Write-Host "编译失败" -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "完成: $HookOut" -ForegroundColor Green