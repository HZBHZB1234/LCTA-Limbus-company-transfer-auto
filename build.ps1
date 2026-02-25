function askYesNo {
    param([string]$question)
    do {
        $answer = Read-Host -Prompt "$question (y/n)"
        if ($answer -eq 'y' -or $answer -eq 'n') {
            return ($answer -eq 'y')
        }
        Write-Output '输入无效，请输入 y 或 n'
    } while ($true)
}

function Insert-Line {
    param(
        [string]$FilePath,
        [int]$LineNumber,
        [string]$Text,
        [switch]$Before
    )
    # 检查文件是否存在
    if (-not (Test-Path $FilePath)) {
        Write-Error "文件 $FilePath 不存在"
        return
    }
    $lines = Get-Content $FilePath -Encoding UTF8
    # 验证行号范围
    if ($LineNumber -lt 1 -or $LineNumber -gt $lines.Count) {
        Write-Error "行号 $LineNumber 超出范围 (1..$($lines.Count))"
        return
    }
    # 计算插入位置索引（0-based）
    $index = if ($Before) { $LineNumber - 1 } else { $LineNumber }
    # 安全地分割数组
    $beforeLines = if ($index -gt 0) { $lines[0..($index-1)] } else { @() }
    $afterLines = if ($index -lt $lines.Count) { $lines[$index..($lines.Count-1)] } else { @() }
    $newLines = $beforeLines + $Text + $afterLines
    # 使用 UTF-8 编码保存，避免中文乱码
    $newLines | Set-Content -Path $FilePath -Encoding UTF8
    Write-Host "已向 $FilePath 的第 $LineNumber 行 $(if($Before){'前'}else{'后'})插入行: $Text"
}

function main {
    Set-Location -Path $PSScriptRoot
    # 询问是否从 Git 更新
    if (askYesNo '是否立刻从 git 更新') {
        try {
            git reset --hard HEAD
            git pull -f
            Write-Host 'Git 更新成功'
        }
        catch {
            Write-Error '拉取失败'
            return 1
        }
    }

    # 检查虚拟环境是否存在
    if (-not (Test-Path -Path 'venv')) {
        if (askYesNo '创建虚拟环境？') {
            try {
                python -m venv venv
                # 在 PowerShell 中正确激活虚拟环境（点源执行 Activate.ps1）
                . .\venv\Scripts\Activate.ps1
                # 修复 pip 安装命令：添加 -r 参数
                Write-Host '开始安装依赖'
                python -m pip install --upgrade pip
                python -m pip install -r requirements.txt
                Write-Host '虚拟环境创建并安装依赖成功'
            }
            catch {
                Write-Error '创建虚拟环境失败'
                return 1
            }
        }
    } else {
        try {
            . .\venv\Scripts\Activate.ps1
            Write-Host '虚拟环境已激活'
        }
        catch {
            Write-Error '激活虚拟环境失败'
            return 1
        }
    }

    # 询问是否格式化代码
    if (askYesNo '格式化代码?') {
        try {
            python .\.github\InitCode.py
            # 在 start_webui.py 的第 16 行后插入 debug = True
            Insert-Line .\start_webui.py 16 'debug = True'
            Write-Host '格式化完成'
        }
        catch {
            Write-Error '格式化失败'
            return 1
        }
    }

    Write-Host '脚本执行完毕'
    return 0
}

# 执行主函数，并捕获退出码
$exitCode = main
Read-Host -Prompt '按回车键退出...'
exit $exitCode