"""游戏加速热键与倍率选择窗口（从 launcher/main.py 拆分而来）"""
import os
import threading

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager

_log_manager = LogManager()

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
        try:
            if not SpeedManager.is_injected():
                SpeedManager.inject()
            speed_enabled[0] = not speed_enabled[0]
            SpeedManager.set_speed(speed_factor if speed_enabled[0] else 1.0)
            _log_manager.log(
                f"加速 {'开启' if speed_enabled[0] else '关闭'} "
                f"({speed_factor if speed_enabled[0] else 1.0}x)"
            )
        except Exception as e:
            _log_manager.log_error(e)

    def open_selector():
        try:
            if not SpeedManager.is_injected():
                SpeedManager.inject()
            _show_speed_slider_window()
        except Exception as e:
            _log_manager.log_error(e)

    keyboard.add_hotkey('ctrl+s', toggle_speed)
    keyboard.add_hotkey('ctrl+shift+s', open_selector)
    _log_manager.log(f"游戏加速热键已注册: ctrl+s / ctrl+shift+s (目标倍率: {speed_factor}x)")

    exit_event.wait()

    keyboard.remove_all_hotkeys()
    try:
        SpeedManager.close()
    except Exception as e:
        _log_manager.log_error(e)
    _log_manager.log("游戏加速热键已注销")


def _show_speed_slider_window():
    """弹出 WinForms 倍率选择窗口（置顶、不抢夺焦点）。"""
    import threading
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

    t = threading.Thread(target=run_form)
    t.SetApartmentState(3)  # STA
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
    return exit_event
