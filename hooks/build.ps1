# hooks/build.ps1
# 独立编译 hooks DLL。产物：$(本项目根)\hooks\rawinput_hook.dll
# 说明：
#   - rawinput_hook.dll（输入反检测）由此脚本编译
#   - 作弊工具箱（含伤害倍率）源码已迁往私有仓库 LCTA_CheatingCore，
#     由根目录 build.ps1 的 "Cheat Core" 步骤从克隆编译（hooks/*.c 逐个）
#     并 XOR 加密打包，不再直接输出到 hooks/ 目录（见 LCTA_CheatingCore/hooks/build.ps1）
# 完整构建流程请使用项目根目录的 build.ps1

$ErrorActionPreference = "Stop"

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
