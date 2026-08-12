__version__ = "5.0.2"

import sys
import os
from pathlib import Path

os.environ["__version__"] = __version__

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
print(project_root)
sys.path.insert(0, str(project_root))

debug = False

# 缺少 WebView2 Runtime 时打开官方下载页
WEBVIEW2_DOWNLOAD_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"


def check_webview2_environment():
    """预检 WebView2 Runtime；缺失时弹窗提示并打开下载页。返回 False 表示应终止启动。"""
    if os.getenv('PYWEBVIEW_GUI') == 'qt':
        return True
    try:
        import platform
        import winreg
    except Exception:
        return True

    def _is_new_version(current_version, new_version):
        """与 pywebview winforms._is_new_version 相同的版本比较逻辑。"""
        new_range = new_version.split('.')
        cur_range = current_version.split('.')
        for index, _ in enumerate(new_range):
            if len(cur_range) > index:
                return int(new_range[index]) >= int(cur_range[index])
        return False

    # 与 pywebview winforms._is_chromium 保持一致：.NET Framework >= 4.6.2（Release >= 394802）
    # 注：注册表读取失败/版本过低仅记录警告，不阻断启动（旧版本这些环境只依赖 WebView2 GUID 即可启动）
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full'
        ) as net_key:
            release, _ = winreg.QueryValueEx(net_key, 'Release')
        if release < 394802:  # .NET 4.6.2
            print("警告: .NET Framework 版本低于 4.6.2，pywebview 可能无法正常渲染界面")
    except Exception:
        print("警告: 无法读取 .NET Framework 4.6.2 注册表信息，跳过 .NET 版本预检")

    webview2_guids = (
        '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',   # WebView2 Runtime
        '{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}',   # WebView2 Beta
        '{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}',   # WebView2 Developer
        '{65C35B14-6C1D-4122-AC46-7148CC9D6497}',   # WebView2 Canary
    )

    # 与 pywebview 的 edgechromium 探测保持一致（64 位机器上 HKLM 走 WOW6432Node 视图）
    def edge_build(key_type, guid):
        try:
            if platform.machine() == 'x86' or key_type == 'HKEY_CURRENT_USER':
                path = r'Microsoft\EdgeUpdate\Clients\%s' % guid
            else:
                path = r'WOW6432Node\Microsoft\EdgeUpdate\Clients\%s' % guid
            with winreg.OpenKey(getattr(winreg, key_type), r'SOFTWARE\%s' % path) as key:
                build, _ = winreg.QueryValueEx(key, 'pv')
                # 版本号必须可解析（首个段为数字），否则视为不可用，避免 int() 抛错误阻断启动
                build_str = str(build)
                if not build_str.split('.')[0].isdigit():
                    return '0'
                return build_str
        except Exception:
            return '0'

    try:
        for guid in webview2_guids:
            for key_type in ('HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE'):
                if _is_new_version('86.0.622.0', edge_build(key_type, guid)):  # WebView2 86.0.622.0
                    return True
    except Exception:
        return False

    try:
        import ctypes
        import webbrowser
        ctypes.windll.user32.MessageBoxW(
            0,
            '检测到系统缺少 Microsoft Edge WebView2 Runtime 或 .NET Framework 4.6.2+，LCTA 界面将无法正常显示。\n\n'
            '即将打开下载页面，请安装 WebView2 Runtime 后重新启动 LCTA。',
            'LCTA - 缺少运行环境',
            0x10 | 0x1000
        )
        webbrowser.open(WEBVIEW2_DOWNLOAD_URL)
    except Exception:
        pass
    return False



def get_resource_path():
    """
    获取资源文件的绝对路径
    在PyInstaller打包后，资源文件会被打包进可执行文件，需要特殊处理
    """
    try:
        # PyInstaller创建的临时文件夹
        base_path = Path(sys._MEIPASS)
    except Exception:
        # 未打包时直接使用项目根目录
        base_path = project_root
    
    return base_path

def _run_pending_pip_ops_with_prompt():
    """启动早期执行待处理的依赖操作，并以原生消息框展示进度。

    - 导入链必须是纯标准库：globalManagers.pending_pip_ops 不依赖任何第三方
      库，即使上次更新残留"库缺失"状态也不会导入失败，保证 pending 一定能
      执行到（否则将进不去更新流程）。
    - 打包版（CREATE_NO_WINDOW 无控制台）下 print/日志均不可见，pip 操作
      可能耗时数分钟而无任何界面反馈；此处用 ctypes MessageBoxW 弹出原生
      提示窗，后台线程逐项执行并在消息框内实时更新文本，全部完成后自动
      关闭（PostMessage WM_CLOSE）。
    """
    from globalManagers.pending_pip_ops import (
        apply_pending_pip_ops,
        load_pending_ops,
        _pending_ops_default_path,
    )
    pending_path = _pending_ops_default_path()
    ops = load_pending_ops(pending_path)
    if not ops["uninstall"] and not ops["install"]:
        return

    import ctypes
    import threading

    user32 = ctypes.windll.user32
    title = "LCTA 依赖更新"
    state = {
        "text": "正在准备依赖更新…",
        "done": False,
        "ok": None,
    }

    def _refresh_window():
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            user32.SetWindowTextW(hwnd, state["text"])
            if state["done"]:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE 自动关闭

    def _worker():
        def on_progress(text):
            state["text"] = text
            _refresh_window()
        state["ok"] = apply_pending_pip_ops(pending_path, progress_callback=on_progress)
        if state["ok"]:
            state["text"] = "依赖更新完成"
        else:
            state["text"] = "部分依赖更新未完成，将在下次启动时重试（详情见 logs/app.log）"
        state["done"] = True
        _refresh_window()

    threading.Thread(target=_worker, daemon=True).start()
    while not state["done"]:
        # 模态循环：等待消息框关闭（用户点击或完成后自动关闭）；
        # 用户提前点击时若操作尚未完成则重新弹出
        user32.MessageBoxW(
            None,
            state["text"],
            title,
            0x40 | 0x10000  # MB_ICONINFORMATION | MB_SETFOREGROUND
        )
    if state["ok"] is False:
        user32.MessageBoxW(
            None,
            "部分依赖更新未完成，将在下次启动时自动重试。\n\n"
            "详细日志见 logs/app.log。",
            title,
            0x10 | 0x10000  # MB_ICONERROR | MB_SETFOREGROUND
        )


def init_env():
    """初始化环境变量"""
    os.environ['path_'] = str(get_resource_path())
    # 判断是否为打包环境
    is_frozen = hasattr(sys, 'frozen') or hasattr(sys, '_MEIPASS')
    os.environ['is_frozen'] = str(is_frozen).lower()
    if debug:
        os.environ['debug'] = 'true'
    if not is_frozen:
        os.environ['PATH'] += os.pathsep + str(project_root / 'code' / 'venv' / 'Scripts')

    # 在加载任何第三方库之前执行待处理的依赖操作（更新延迟的卸载/升级）。
    # globalManagers.pending_pip_ops 为纯标准库模块，导入链不触发
    # webutils/__init__.py（requests/openspeedy/UnityPy 等），
    # 即使上次更新残留库缺失也不会阻断 pending 执行。
    try:
        _run_pending_pip_ops_with_prompt()
    except Exception as e:
        print(f"执行待处理依赖操作失败，将在下次启动时重试: {e}")

def start_webui():
    """启动PyWebGUI界面"""
    try:
        init_env()
        if not check_webview2_environment():
            return
        if os.getenv('__debug_exe__', 'false') == 'true':
            os.environ['COREHOST_TRACE'] = '1'
            os.environ["COREHOST_TRACEFILE"] = "hostfxr.log"
        try:
            from webutils.clr_bootstrap import ensure_clr
            ensure_clr()
            print('clr导入成功，使用netfx')
        except Exception as e:
            print(f'clr导入失败: {e}')
        
        from webui.app import main
        print("正在启动LCTA WebUI...")
        print("请稍候，界面即将打开...")
        main()
    except Exception as e:
        print(f"启动WebUI时发生错误: {e}")
        import traceback
        exc = traceback.format_exc()
        print(exc)
        print(e)
        _log = Path(os.getcwd()) / 'logs'
        _log.mkdir(exist_ok=True)
        _log = _log / 'app.log'
        # 与 LogManager 文件 handler 保持一致用 UTF-8，避免 GBK 字节混入
        # UTF-8 日志文件导致乱码
        with open(_log, '+a' if _log.exists() else '+w', encoding='utf-8') as f:
            f.write(exc)
        print(os.getenv('__debug_exe__', 'false'))
        if os.getenv('__debug_exe__', 'false') == 'true':
            import webutils.debug_environ_test as test
            try:
                test.main()
            except Exception as e:
                traceback.print_exc()
            input('回车键以退出...')

def start_launcher():
    """启动Launcher界面"""
    try:
        init_env()
        os.environ['steam_argv'] = ' '.join([a for a in sys.argv[1:] if a != '-launcher']) if len(sys.argv) >= 2 else ''
        
        from launcher.main import main
        print("正在启动LCTA Launcher...")
        print("请稍候，界面即将打开...")
        main()
    except ImportError as e:
        print(f"启动Launcher失败: {e}")
        print("请确保项目结构完整")
    except Exception as e:
        print(f"启动Launcher时发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 检查命令行参数
    try:
        if "-launcher" in sys.argv:
            start_launcher()
        else:
            start_webui()
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        input('未知神秘错误')