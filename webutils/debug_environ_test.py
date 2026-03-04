#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Python.NET 环境诊断脚本
检查 .NET Framework / .NET Core 版本、clr_loader 文件及 VC++ 运行时。
适用于 Windows 系统。

修改：使用 logging 将日志同时输出到控制台和文件。
"""

import os
import sys
import subprocess
import platform
import logging
from pathlib import Path

# 尝试导入 winreg，若失败则说明非 Windows 环境
try:
    import winreg
except ImportError:
    winreg = None


def setup_logging():
    """配置日志：同时输出到控制台和文件"""
    logger = logging.getLogger('PythonNETDiagnostic')
    logger.setLevel(logging.DEBUG)

    # 移除已有的处理器，避免重复
    if logger.hasHandlers():
        logger.handlers.clear()

    # 文件处理器：记录所有级别，带时间、级别、消息
    file_handler = logging.FileHandler('logs/pythonnet_diagnostic.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    # 控制台处理器：只输出消息（类似 print），级别 INFO 及以上
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# 全局 logger 对象，在 main 中初始化
logger = None


def print_header(title):
    """打印带分隔线的标题（使用 logging）"""
    logger.info("")
    logger.info("=" * 60)
    logger.info(title)
    logger.info("=" * 60)


def check_python():
    """显示当前 Python 环境信息"""
    print_header("Python 环境")
    logger.info(f"Python 版本: {sys.version}")
    logger.info(f"可执行路径: {sys.executable}")
    logger.info(f"平台: {platform.platform()}")
    logger.info(f"系统: {platform.system()} {platform.release()}")


def check_dotnet_cli():
    """检测 dotnet CLI 是否可用，并列出已安装的运行时"""
    print_header(".NET Core / .NET 5+ 运行时")
    dotnet_path = None
    # 尝试从 PATH 查找 dotnet
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(path) / "dotnet.exe"
        if candidate.exists():
            dotnet_path = candidate
            break

    if dotnet_path:
        logger.info(f"找到 dotnet CLI: {dotnet_path}")
        try:
            result = subprocess.run(
                [str(dotnet_path), "--list-runtimes"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
            )
            if result.returncode == 0:
                runtimes = result.stdout.strip()
                if runtimes:
                    logger.info("已安装的运行时：")
                    logger.info(runtimes)
                else:
                    logger.info("未找到任何 .NET 运行时。")
            else:
                logger.error("dotnet --list-runtimes 执行失败：")
                logger.error(result.stderr)
        except Exception as e:
            logger.error(f"执行 dotnet --list-runtimes 时出错：{e}")
    else:
        logger.info("未在 PATH 中找到 dotnet.exe，无法检查 .NET Core 运行时。")
        logger.info("如果已安装，请将 dotnet 目录添加到 PATH。")


def check_netfx_version():
    """检查 .NET Framework 版本（Windows 注册表）"""
    print_header(".NET Framework 版本")
    if not winreg:
        logger.info("非 Windows 环境，跳过 .NET Framework 检查。")
        return

    # 参考 Microsoft 官方文档：检测 .NET Framework 4.x 版本
    try:
        key_path = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            release = winreg.QueryValueEx(key, "Release")[0]
            # 映射 Release 值到版本号
            version_map = {
                528040: "4.8",
                461808: "4.7.2",
                461308: "4.7.1",
                460798: "4.7",
                394802: "4.6.2",
                394254: "4.6.1",
                393295: "4.6",
                379893: "4.5.2",
                378675: "4.5.1",
                378389: "4.5",
            }
            version = version_map.get(release, f"未知版本 (Release={release})")
            logger.info(f".NET Framework 版本: {version}")
            if release < 461808:  # 4.7.2
                logger.warning("Python.NET 3.x 需要 .NET Framework 4.7.2 或更高。")
    except FileNotFoundError:
        logger.info("未找到 .NET Framework 4.x 安装。")
    except Exception as e:
        logger.error(f"读取注册表时出错：{e}")


def check_clr_loader_files():
    """检查 clr_loader 的辅助 DLL 文件是否存在"""
    print_header("clr_loader 辅助 DLL 文件")
    # 定位 site-packages 目录
    try:
        import clr_loader
        pkg_dir = Path(clr_loader.__file__).parent
        logger.info(f"clr_loader 安装路径: {pkg_dir}")

        # 检查 ffi/dlls 下的文件
        dll_dir = pkg_dir / "ffi" / "dlls"
        if dll_dir.exists():
            for arch in ["x86", "amd64"]:
                clrloader = dll_dir / arch / "ClrLoader.dll"
                if clrloader.exists():
                    logger.info(f"找到 {arch} 版本的 ClrLoader.dll: {clrloader}")
                else:
                    logger.warning(f"缺失 {arch} 版本的 ClrLoader.dll")
        else:
            logger.warning("未找到 ffi/dlls 目录，clr_loader 安装可能不完整。")
    except ImportError:
        logger.info("clr_loader 未安装。")
    except Exception as e:
        logger.error(f"检查 clr_loader 文件时出错：{e}")


def check_vc_redist():
    """检查 Visual C++ Redistributable 是否安装"""
    print_header("Visual C++ Redistributable")
    if not winreg:
        logger.info("非 Windows 环境，跳过 VC++ 检查。")
        return

    # 常见的 VC++ 运行时注册表路径
    # 查询已安装程序列表
    vc_versions = []
    try:
        # 对于 64 位系统，查看两个注册表视图
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, subkey in reg_paths:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as sub:
                                try:
                                    display_name = winreg.QueryValueEx(sub, "DisplayName")[0]
                                    if "Visual C++" in display_name:
                                        vc_versions.append(display_name)
                                except FileNotFoundError:
                                    pass
                            i += 1
                        except OSError:
                            break
            except FileNotFoundError:
                continue
    except Exception as e:
        logger.error(f"检查 VC++ 时出错：{e}")

    if vc_versions:
        logger.info("找到以下 Visual C++ Redistributable 版本：")
        for v in sorted(vc_versions):
            logger.info(f"  - {v}")
    else:
        logger.info("未在已安装程序列表中找到 Visual C++ Redistributable。")
        logger.info("这可能导致 clr_loader 依赖的 DLL 无法加载。")


def main():
    global logger
    logger = setup_logging()

    logger.info("=" * 60)
    logger.info(" Python.NET 环境诊断脚本")
    logger.info("=" * 60)

    check_python()
    check_netfx_version()
    check_dotnet_cli()
    check_clr_loader_files()
    check_vc_redist()

    logger.info("\n诊断完成。请根据上述输出排查问题。")
    logger.info("如果仍有疑问，请将输出提供给支持人员。")
    logger.info(f"详细日志已保存至: {os.path.abspath('logs/pythonnet_diagnostic.log')}")


if __name__ == "__main__":
    main()