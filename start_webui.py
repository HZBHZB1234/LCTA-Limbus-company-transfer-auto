__version__ = "5.0.1"

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
                return str(build)
        except Exception:
            return '0'

    for guid in webview2_guids:
        for key_type in ('HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE'):
            if edge_build(key_type, guid) != '0':
                return True

    try:
        import ctypes
        import webbrowser
        ctypes.windll.user32.MessageBoxW(
            0,
            '检测到系统缺少 Microsoft Edge WebView2 Runtime，LCTA 界面将无法正常显示。\n\n'
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

    # 在加载任何扩展包 DLL（pythonnet/clr_loader/pywebview 等）之前执行待处理的
    # 依赖操作（更新延迟的卸载/升级）。此时扩展包尚未加载进进程，
    # Windows 下可正常卸载/替换。注：导入 webutils 包会带入其他第三方库，
    # 但关键约束是扩展包 DLL 未加载，而非无任何第三方库被导入。
    try:
        from webutils.update import apply_pending_pip_ops
        apply_pending_pip_ops()
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
        with open(_log, '+a' if _log.exists() else '+w') as f:
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