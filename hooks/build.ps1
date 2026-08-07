# hooks/build.ps1
# 独立编译 hooks DLL。产物：$(本项目根)\hooks\rawinput_hook.dll、$(本项目根)\hooks\damage_hook.dll
# 说明：完整构建流程请使用项目根目录的 build.ps1（本文件不参与该流程，
#       根 build.ps1 使用 .NET 兼容的缓存机制独立编译同名 DLL）。

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$HookSrc = Join-Path $PSScriptRoot "rawinput_hook.c"
$HookOut = Join-Path $PSScriptRoot "rawinput_hook.dll"
$DamageSrc = Join-Path $PSScriptRoot "damage_hook.c"
$DamageOut = Join-Path $PSScriptRoot "damage_hook.dll"
$MinHookInclude = Join-Path $ProjectRoot "vendor\minhook\include"
$MinHookHde = Join-Path $ProjectRoot "vendor\minhook\src\hde"

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

if (-not (Test-Path $DamageSrc)) {
    Write-Host "ERROR: 源码不存在: $DamageSrc" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "$MinHookInclude\MinHook.h")) {
    Write-Host "ERROR: MinHook 头文件缺失: $MinHookInclude\MinHook.h（请先 vendor minhook v1.3.4）" -ForegroundColor Red
    exit 1
}

Write-Host "编译 $DamageSrc -> $DamageOut..."
$minhookSrcs = @(
    "$ProjectRoot\vendor\minhook\src\hook.c",
    "$ProjectRoot\vendor\minhook\src\buffer.c",
    "$ProjectRoot\vendor\minhook\src\trampoline.c",
    "$MinHookHde\hde64.c"
)
gcc -shared -O2 -s -static-libgcc -o $DamageOut $DamageSrc $minhookSrcs -I $MinHookInclude -I $MinHookHde
if ($LASTEXITCODE -ne 0) {
    Write-Host "编译失败" -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "完成: $DamageOut" -ForegroundColor Green