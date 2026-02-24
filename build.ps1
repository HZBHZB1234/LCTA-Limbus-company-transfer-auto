function askYesNo {
    param($question)
    $answer = Read-Host -Prompt "$question (y/n)"
    while (($answer -ne 'y') -and ($answer -ne 'n')) {
        Write-Output '当前输入非法'
        $answer = Read-Host -Prompt "$question (y/n)"
    }
    return ($answer -eq 'y')
}

function Insert-Line {
    param(
        [string]$FilePath,
        [int]$LineNumber,
        [string]$Text,
        [switch]$Before
    )
    $lines = Get-Content $FilePath
    $index = if ($Before) { $LineNumber - 1 } else { $LineNumber }
    $lines = $lines[0..($index-1)] + $Text + $lines[$index..($lines.Length-1)]
    $lines | Set-Content $FilePath
}

function main{
    if (askYesNo '是否立刻从git更新') {
        try {
            git pull -f
        }
        catch {
            Write-Output '拉取失败'
            return 1
        }
    }

    if (-not (Test-Path -Path 'venv')) {
        try {
            if (askYesNo '创建虚拟环境？') {
                python -m venv venv
                .\venv\Scripts\activate
                python -m pip install .\requirements.txt
            }
        }
        catch {
            Write-Output '创建失败'
            return 1
        }
    } 
    else {
        try {
            .\venv\Scripts\activate
        }
        catch {
            Write-Output '激活虚拟环境失败'
            return 1
        }
    }

    if (askYesNo '格式化代码?') {
        try {
            python .\.github\InitCode.py
            Insert-Line .\start_webui.py 16 'debug = True'
        }
        catch {
            Write-Output '格式化失败'
            return 1
        }
    }
}

main
Read-Host -Prompt '回车键以退出...'