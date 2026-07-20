"""游戏加速热键与倍率选择窗口（从 launcher/main.py 拆分而来）"""
import ctypes
import os
import threading

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager

_log_manager = LogManager()

# -- 前台进程检测（与 webutils/function_speed.py 相同的 PID 缓存模式） --
_kernel32 = ctypes.windll.kernel32
_user32 = ctypes.windll.user32
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_game_pid = None


def _pid_alive(pid: int) -> bool:
    """用 OpenProcess 快速检查 PID 是否仍然存在。"""
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        _kernel32.CloseHandle(handle)
        return True
    return False


def _find_game_pid():
    """查找 LimbusCompany.exe 的 PID（带缓存，与 function_speed.py 相同模式）。"""
    global _game_pid

    # 快速路径：验证缓存的 PID
    if _game_pid is not None and _pid_alive(_game_pid):
        return _game_pid

    # 慢速路径：通过 SpeedController 枚举进程
    _game_pid = None
    try:
        from openspeedy import SpeedController
        with SpeedController() as sc:
            processes = sc.list_processes(fast=False)
        for p in processes:
            if p.name == "LimbusCompany.exe":
                _game_pid = p.pid
                return _game_pid
    except Exception as e:
        _log_manager.log_error(e)
        return None

    return None


def _is_game_foreground() -> bool:
    """检查当前前台窗口是否属于 LimbusCompany.exe。"""
    game_pid = _find_game_pid()
    if game_pid is None:
        return False

    hwnd = _user32.GetForegroundWindow()
    if hwnd == 0:
        return False

    fg_pid = ctypes.c_ulong()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(fg_pid))
    return fg_pid.value == game_pid

def _start_speed_hotkeys(speed_factor: float, exit_event: threading.Event):
    """游戏加速热键线程入口。

    注册全局热键并阻塞直到 exit_event 被设置：
    - ctrl+s: 切换 1.0x / speed_factor
    - ctrl+shift+s: 弹出速度选择窗口

    DLL 延迟注入：首次触发热键时才注入。
    """
    import keyboard
    from webutils.function_speed import SpeedManager

    speed_enabled = [False]  # 用列表实现闭包可变引用

    def toggle_speed():
        if not _is_game_foreground():
            _log_manager.log("热键 ctrl+s 按下但前台窗口不是 LimbusCompany.exe，跳过加速切换")
            return
        _log_manager.log("热键 ctrl+s 按下，正在切换加速状态...")
        try:
            if not SpeedManager.is_injected():
                _log_manager.log("正在注入加速 DLL...")
                SpeedManager.inject()
            speed_enabled[0] = not speed_enabled[0]
            _log_manager.log(f"设置游戏速度为 {speed_factor if speed_enabled[0] else 1.0}x")
            SpeedManager.set_speed(speed_factor if speed_enabled[0] else 1.0)
            _log_manager.log(
                f"加速 {'开启' if speed_enabled[0] else '关闭'} "
                f"({speed_factor if speed_enabled[0] else 1.0}x)"
            )
        except Exception as e:
            _log_manager.log_error(e)

    def open_selector():
        if not _is_game_foreground():
            _log_manager.log("热键 ctrl+shift+s 按下但前台窗口不是 LimbusCompany.exe，跳过打开倍率选择窗口")
            return
        _log_manager.log("热键 ctrl+shift+s 按下，正在打开倍率选择窗口...")
        try:
            if not SpeedManager.is_injected():
                _log_manager.log("正在注入加速 DLL...")
                SpeedManager.inject()
            _show_speed_slider_window()
        except Exception as e:
            _log_manager.log_error(e)

    keyboard.add_hotkey('ctrl+s', toggle_speed)
    keyboard.add_hotkey('ctrl+shift+s', open_selector)
    _log_manager.log(f"游戏加速热键已注册: ctrl+s / ctrl+shift+s (目标倍率: {speed_factor}x)")

    exit_event.wait()

    keyboard.remove_all_hotkeys()
    _log_manager.log("正在卸载加速 DLL...")
    try:
        SpeedManager.close()
        _log_manager.log("加速 DLL 已卸载")
    except Exception as e:
        _log_manager.log_error(e)
    _log_manager.log("游戏加速热键已注销")


def _show_speed_slider_window():
    """弹出 WinForms 倍率选择窗口（置顶、不抢夺焦点）。"""
    from webutils.function_speed import SpeedManager

    # 初始化 clr（参照 start_webui.py 的回退链）
    try:
        import clr
    except Exception:
        try:
            os.environ['PYTHONNET_RUNTIME'] = 'coreclr'
            import clr
        except Exception:
            os.environ['PYTHONNET_RUNTIME'] = 'mono'
            import clr

    clr.AddReference('System.Windows.Forms')
    clr.AddReference('System.Drawing')
    import System.Windows.Forms as WinForms
    from System.Drawing import Point, Size

    current = SpeedManager.get_speed() or 1.0
    slider_val = [int(max(1, min(100, current * 10)))]  # 0.1x-10.0x -> 1-100

    def run_form():
        WinForms.Application.EnableVisualStyles()

        form = WinForms.Form()
        form.Text = "游戏加速"
        form.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        form.StartPosition = WinForms.FormStartPosition.CenterScreen
        form.Size = Size(320, 170)
        form.TopMost = True
        form.MaximizeBox = False
        form.MinimizeBox = False
        form.Activate()

        # 标题标签
        title = WinForms.Label()
        title.Text = "选择游戏速度倍率"
        title.Location = Point(16, 12)
        title.AutoSize = True
        form.Controls.Add(title)

        # 滑块
        trackbar = WinForms.TrackBar()
        trackbar.Minimum = 1
        trackbar.Maximum = 100
        trackbar.Value = slider_val[0]
        trackbar.TickFrequency = 10
        trackbar.Size = Size(270, 45)
        trackbar.Location = Point(16, 35)
        form.Controls.Add(trackbar)

        # 当前值标签
        val_label = WinForms.Label()
        val_label.Text = f"当前: {trackbar.Value / 10.0:.1f}x"
        val_label.Location = Point(16, 80)
        val_label.AutoSize = True
        form.Controls.Add(val_label)

        def on_scroll(sender, args):
            val_label.Text = f"当前: {trackbar.Value / 10.0:.1f}x"

        trackbar.Scroll += on_scroll

        # 应用按钮
        apply_btn = WinForms.Button()
        apply_btn.Text = "应用"
        apply_btn.Size = Size(75, 28)
        apply_btn.Location = Point(210, 95)

        def on_apply(sender, args):
            try:
                _log_manager.log(f"设置游戏速度为 {trackbar.Value / 10.0:.1f}x")
                SpeedManager.set_speed(trackbar.Value / 10.0)
            except Exception as e:
                _log_manager.log_error(e)
            form.Close()

        apply_btn.Click += on_apply
        form.Controls.Add(apply_btn)

        # 取消按钮
        cancel_btn = WinForms.Button()
        cancel_btn.Text = "取消"
        cancel_btn.Size = Size(75, 28)
        cancel_btn.Location = Point(125, 95)

        def on_cancel(sender, args):
            form.Close()

        cancel_btn.Click += on_cancel
        form.Controls.Add(cancel_btn)

        form.ShowDialog()

    import System.Threading as NetThreading
    t = NetThreading.Thread(NetThreading.ThreadStart(run_form))
    t.SetApartmentState(NetThreading.ApartmentState.STA)
    t.Start()
    t.Join()


def run_speed_hotkey_if_enabled():
    """如果配置允许，启动热键线程并返回 exit_event 或 None。"""
    if not ConfigManager().get("launcher.work.speed", False):
        return None
    if not ConfigManager().get("speed.disclaimer_accepted", False):
        _log_manager.log("游戏加速已配置但未同意免责声明，跳过热键注册")
        return None

    speed_factor = float(ConfigManager().get("launcher.work.speed_factor", "2.0"))
    exit_event = threading.Event()
    t = threading.Thread(
        target=_start_speed_hotkeys,
        args=(speed_factor, exit_event),
        daemon=True,
    )
    t.start()
    _log_manager.log(f"启动游戏加速热键线程 (目标倍率: {speed_factor}x)")
    return exit_event
