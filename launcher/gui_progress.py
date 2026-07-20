import logging
import threading
from typing import Optional

try:
    import clr
except Exception:
    try:
        import os
        os.environ['PYTHONNET_RUNTIME'] = 'coreclr'
        import clr
    except Exception:
        os.environ['PYTHONNET_RUNTIME'] = 'mono'
        import clr

clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')
import System.Windows.Forms as WinForms
from System.Drawing import Point, Size, Color, Font, FontStyle

# 模块级窗口实例引用
_window: Optional["LauncherProgressWindow"] = None


class LauncherProgressWindow:

    def __init__(self):
        self._form: Optional[WinForms.Form] = None
        self._status_label: Optional[WinForms.Label] = None
        self._progress_bar: Optional[WinForms.ProgressBar] = None
        self._log_box: Optional[WinForms.RichTextBox] = None
        self._thread: Optional = None
        self._ready = threading.Event()
        self._closed = threading.Event()

    def _create_form(self):
        WinForms.Application.EnableVisualStyles()

        form = WinForms.Form()
        form.Text = "LCTA 启动器"
        form.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        form.StartPosition = WinForms.FormStartPosition.CenterScreen
        form.Size = Size(520, 380)
        form.TopMost = False
        form.MaximizeBox = False
        form.MinimizeBox = True

        # ---- 状态标签 ----
        status_label = WinForms.Label()
        status_label.Text = "正在初始化..."
        status_label.Location = Point(12, 12)
        status_label.AutoSize = True
        status_label.Font = Font("Microsoft YaHei", 10, FontStyle.Bold)
        form.Controls.Add(status_label)

        # ---- 进度条 ----
        progress_bar = WinForms.ProgressBar()
        progress_bar.Location = Point(12, 36)
        progress_bar.Size = Size(480, 20)
        progress_bar.Minimum = 0
        progress_bar.Maximum = 100
        progress_bar.Value = 0
        progress_bar.Style = WinForms.ProgressBarStyle.Marquee
        form.Controls.Add(progress_bar)

        # ---- 日志文本框 ----
        log_box = WinForms.RichTextBox()
        log_box.Location = Point(12, 65)
        log_box.Size = Size(480, 240)
        log_box.ReadOnly = True
        log_box.BackColor = Color.FromArgb(30, 30, 30)
        log_box.ForeColor = Color.FromArgb(220, 220, 220)
        log_box.Font = Font("Consolas", 9)
        log_box.WordWrap = True
        log_box.ScrollBars = WinForms.RichTextBoxScrollBars.Vertical
        log_box.DetectUrls = False
        form.Controls.Add(log_box)

        # ---- 底部提示 ----
        hint = WinForms.Label()
        hint.Text = "游戏启动完成后此窗口将自动关闭"
        hint.Location = Point(12, 315)
        hint.AutoSize = True
        hint.ForeColor = Color.Gray
        hint.Font = Font("Microsoft YaHei", 8)
        form.Controls.Add(hint)

        # 赋值成员变量（仅在STA线程上访问）
        self._form = form
        self._status_label = status_label
        self._progress_bar = progress_bar
        self._log_box = log_box

        # 通知主线程窗体已就绪
        self._ready.set()

        # 启动消息泵（阻塞直到 form.Close()）
        WinForms.Application.Run(form)

        self._closed.set()

    def start(self):
        import System.Threading as NetThreading
        self._thread = NetThreading.Thread(NetThreading.ThreadStart(self._create_form))
        self._thread.SetApartmentState(NetThreading.ApartmentState.STA)
        self._thread.IsBackground = True
        self._thread.Start()
        if not self._ready.wait(10.0):
            raise RuntimeError("GUI窗口创建超时，请确认系统支持WinForms")

    def update_status(self, text: str):
        def _set():
            if self._status_label is not None and not self._status_label.IsDisposed:
                self._status_label.Text = text
        self._safe_invoke(_set)

    def set_progress(self, value: int, max_value: int = 100):
        def _set():
            if self._progress_bar is not None and not self._progress_bar.IsDisposed:
                self._progress_bar.Style = WinForms.ProgressBarStyle.Blocks
                self._progress_bar.Maximum = max_value
                self._progress_bar.Value = max(0, min(value, max_value))
        self._safe_invoke(_set)

    def set_progress_marquee(self):
        def _set():
            if self._progress_bar is not None and not self._progress_bar.IsDisposed:
                self._progress_bar.Style = WinForms.ProgressBarStyle.Marquee
        self._safe_invoke(_set)

    def append_log(self, text: str):
        def _append():
            if self._log_box is not None and not self._log_box.IsDisposed:
                self._log_box.AppendText(text + "\n")
                self._log_box.ScrollToCaret()
        self._safe_invoke(_append)

    def close(self):
        def _close():
            if self._form is not None and not self._form.IsDisposed:
                self._form.Close()
        self._safe_invoke(_close)
        if self._thread is not None:
            self._thread.Join(3000)

    def is_alive(self) -> bool:
        if self._thread is None:
            return False
        if self._closed.is_set():
            return False
        return self._thread.IsAlive

    def _safe_invoke(self, action):
        if self._form is None:
            return
        if not self._form.IsHandleCreated:
            return
        if self._form.IsDisposed:
            return
        try:
            self._form.BeginInvoke(WinForms.MethodInvoker(action))
        except Exception:
            logging.getLogger("LCTA").debug("GUI _safe_invoke 失败，窗口可能已关闭")
            pass


class ProgressLogHandler(logging.Handler):

    def __init__(self, window: LauncherProgressWindow):
        super().__init__()
        self._window = window
        self._active = True
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        self.setFormatter(formatter)
        self.setLevel(logging.INFO)

    def emit(self, record: logging.LogRecord):
        if not self._active:
            return
        self._active = False
        try:
            msg = self.format(record)
            self._window.append_log(msg)
        except Exception:
            logging.getLogger("LCTA").debug("GUI 日志输出失败，窗口可能已关闭")
            pass
        finally:
            self._active = True


def create_progress_window() -> LauncherProgressWindow:
    global _window
    window = LauncherProgressWindow()
    window.start()
    _window = window
    return window


def get_active_window() -> Optional[LauncherProgressWindow]:
    return _window
