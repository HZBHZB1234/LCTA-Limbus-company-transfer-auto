@echo off
REM 应用启动脚本

REM 设置Python路径为虚拟环境
set PYTHON_PATH=venv\Scripts\python.exe

REM 检查虚拟环境是否存在
if not exist "%PYTHON_PATH%" (
    echo Python虚拟环境不存在，正在创建...
    python -m venv venv
    if errorlevel 1 (
        echo 创建虚拟环境失败
        pause
        exit /b 1
    )
)

REM 检查依赖是否已安装
echo 检查依赖...
"%PYTHON_PATH%" -c "import tkinter" 2>nul
if errorlevel 1 (
    echo 安装依赖...
    "%PYTHON_PATH%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo 安装依赖失败
        pause
        exit /b 1
    )
)

REM 启动应用
echo 启动应用...
"%PYTHON_PATH%" main.py %*

pause