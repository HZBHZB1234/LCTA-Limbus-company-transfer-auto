import logging
import threading
import time
from typing import Callable, Dict, Optional

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
from System import EventHandler
from System.Drawing import (
    Point, Size, Color, Font, FontStyle, ContentAlignment,
)
from System.Windows.Forms import (
    FlatStyle, BorderStyle, AnchorStyles,
)

from globalManagers.ConfigManager import ConfigManager
from launcher.pipeline import (
    PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN,
    PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING, PHASE_EXIT,
)

_window: Optional["LauncherProgressWindow"] = None

_PHASE_LABELS = {
    PHASE_INIT: "初始化",
    PHASE_CHECK_UPDATE: "检查更新",
    PHASE_CDN: "CDN优选",
    PHASE_PREPARE_MOD: "模组准备",
    PHASE_LAUNCH: "启动游戏",
    PHASE_RUNNING: "游戏运行中",
    PHASE_EXIT: "游戏已退出",
}
_PHASE_ORDER = [PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN, PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING]

_PHASE_STATUS_TEXT = {
    PHASE_INIT: "正在初始化...",
    PHASE_CHECK_UPDATE: "正在检查更新...",
    PHASE_CDN: "正在进行CDN优选...",
    PHASE_PREPARE_MOD: "正在准备模组...",
    PHASE_LAUNCH: "正在启动游戏...",
    PHASE_RUNNING: "游戏运行中",
    PHASE_EXIT: "游戏已退出",
}


def _get_visible_phases() -> list:
    config = ConfigManager()
    visible = []
    for ph in _PHASE_ORDER:
        if ph in (PHASE_INIT, PHASE_LAUNCH, PHASE_RUNNING):
            visible.append(ph)
        elif ph == PHASE_CHECK_UPDATE:
            if config.get("launcher.work.update", "no") != "no":
                visible.append(ph)
        elif ph == PHASE_CDN:
            if config.get("launcher.work.cdn_optimize", False):
                visible.append(ph)
        elif ph == PHASE_PREPARE_MOD:
            if config.get("launcher.work.mod", False):
                visible.append(ph)
    return visible

_COLOR_DONE = Color.FromArgb(76, 175, 80)
_COLOR_ACTIVE = Color.FromArgb(33, 150, 243)
_COLOR_PENDING = Color.FromArgb(158, 158, 158)
_COLOR_BG_DARK = Color.FromArgb(30, 30, 30)
_COLOR_FG_LIGHT = Color.FromArgb(220, 220, 220)
_COLOR_BG_FORM = Color.FromArgb(45, 45, 48)


class LauncherProgressWindow:

    def __init__(self):
        self._form: Optional[WinForms.Form] = None
        self._status_label: Optional[WinForms.Label] = None
        self._progress_bar: Optional[WinForms.ProgressBar] = None
        self._log_box: Optional[WinForms.RichTextBox] = None
        self._log_toggle_btn: Optional[WinForms.Button] = None
        self._phase_flow: Optional[WinForms.FlowLayoutPanel] = None
        self._phase_labels: Dict[str, WinForms.Label] = {}
        self._info_label: Optional[WinForms.Label] = None
        self._thread: Optional = None
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._pipeline: Optional = None
        self._visible_phases = list(_PHASE_ORDER)
        self._current_phase = PHASE_INIT
        self._log_expanded = False
        self._game_start_time: Optional[float] = None
        self._uptime_timer: Optional = None

    def register_to_pipeline(self, pipeline) -> None:
        self._pipeline = pipeline

        pipeline.on(PHASE_INIT, lambda **kw: self._show_phase(PHASE_INIT))
        pipeline.on(PHASE_CHECK_UPDATE, lambda **kw: self._show_phase(PHASE_CHECK_UPDATE))
        pipeline.on(PHASE_CDN, lambda **kw: self._show_phase(PHASE_CDN))
        pipeline.on(PHASE_PREPARE_MOD, lambda **kw: self._show_phase(PHASE_PREPARE_MOD))
        pipeline.on(PHASE_LAUNCH, lambda **kw: self._show_phase(PHASE_LAUNCH))
        pipeline.on(PHASE_RUNNING, lambda **kw: self._show_game_running(**kw))
        pipeline.on(PHASE_EXIT, lambda **kw: self._show_game_exited(**kw))

    def _create_form(self):
        WinForms.Application.EnableVisualStyles()

        form = WinForms.Form()
        form.Text = "LCTA 启动器"
        form.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        form.StartPosition = WinForms.FormStartPosition.CenterScreen
        form.Size = Size(520, 440)
        form.TopMost = False
        form.MaximizeBox = False
        form.MinimizeBox = True
        form.BackColor = _COLOR_BG_FORM
        form.add_FormClosing(WinForms.FormClosingEventHandler(self._on_form_closing))

        # ---- 阶段指示器 ----
        flow = WinForms.FlowLayoutPanel()
        flow.Location = Point(12, 12)
        flow.Size = Size(496, 28)
        flow.FlowDirection = WinForms.FlowDirection.LeftToRight
        flow.WrapContents = False
        flow.BackColor = Color.Transparent
        form.Controls.Add(flow)
        self._phase_flow = flow

        self._visible_phases = _get_visible_phases()
        for ph in self._visible_phases:
            lbl = WinForms.Label()
            lbl.Text = _PHASE_LABELS[ph]
            lbl.AutoSize = True
            lbl.Font = Font("Microsoft YaHei", 8)
            lbl.ForeColor = _COLOR_PENDING
            lbl.Margin = WinForms.Padding(1, 4, 6, 0)
            flow.Controls.Add(lbl)
            self._phase_labels[ph] = lbl

        y = 44

        # ---- 状态标签 ----
        status = WinForms.Label()
        status.Text = "正在初始化..."
        status.Location = Point(12, y)
        status.Size = Size(496, 24)
        status.Font = Font("Microsoft YaHei", 11, FontStyle.Bold)
        status.ForeColor = _COLOR_FG_LIGHT
        status.TextAlign = ContentAlignment.MiddleLeft
        form.Controls.Add(status)
        self._status_label = status
        y += 28

        # ---- 进度条 ----
        prog = WinForms.ProgressBar()
        prog.Location = Point(12, y)
        prog.Size = Size(496, 18)
        prog.Minimum = 0
        prog.Maximum = 100
        prog.Value = 0
        prog.Style = WinForms.ProgressBarStyle.Marquee
        form.Controls.Add(prog)
        self._progress_bar = prog
        y += 24

        # ---- 游戏运行信息区 ----
        info = WinForms.Label()
        info.Location = Point(12, y)
        info.Size = Size(496, 50)
        info.Font = Font("Microsoft YaHei", 9)
        info.ForeColor = Color.FromArgb(180, 180, 180)
        info.Text = ""
        info.Visible = False
        form.Controls.Add(info)
        self._info_label = info

        y += 54

        # ---- 日志折叠按钮 ----
        btn = WinForms.Button()
        btn.Text = "详细日志 ▸"
        btn.Location = Point(12, y)
        btn.Size = Size(496, 22)
        btn.FlatStyle = FlatStyle.Flat
        btn.BackColor = Color.FromArgb(55, 55, 58)
        btn.ForeColor = _COLOR_FG_LIGHT
        btn.Font = Font("Microsoft YaHei", 8)
        btn.FlatAppearance.BorderSize = 0
        btn.TextAlign = ContentAlignment.MiddleLeft
        btn.add_Click(EventHandler(self._toggle_log))
        form.Controls.Add(btn)
        self._log_toggle_btn = btn
        y += 26

        # ---- 日志文本框 ----
        log = WinForms.RichTextBox()
        log.Location = Point(12, y)
        log.Size = Size(496, 200)
        log.ReadOnly = True
        log.BackColor = _COLOR_BG_DARK
        log.ForeColor = _COLOR_FG_LIGHT
        log.Font = Font("Consolas", 8.5)
        log.WordWrap = True
        log.ScrollBars = WinForms.RichTextBoxScrollBars.Vertical
        log.DetectUrls = False
        log.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
        form.Controls.Add(log)
        log.Hide()
        self._log_box = log

        self._form = form
        form.CreateHandle()
        self._ready.set()
        WinForms.Application.Run(form)
        self._closed.set()

    def _on_form_closing(self, sender, e):
        if self._current_phase == PHASE_EXIT:
            return

        if self._current_phase == PHASE_RUNNING:
            msg = "游戏正在运行。\n\n是 - 退出启动器并终止游戏\n否 - 仅退出启动器，游戏继续运行\n取消 - 返回"
        else:
            msg = "启动流程正在进行中，确认退出？"

        buttons = (
            WinForms.MessageBoxButtons.YesNoCancel
            if self._current_phase == PHASE_RUNNING
            else WinForms.MessageBoxButtons.YesNo
        )

        result = WinForms.MessageBox.Show(
            self._form, msg, "LCTA 启动器",
            buttons,
            WinForms.MessageBoxIcon.Warning,
        )

        if result == WinForms.DialogResult.Yes:
            if self._pipeline is not None:
                self._pipeline.cancel()
        elif result == WinForms.DialogResult.No:
            if self._current_phase != PHASE_RUNNING:
                e.Cancel = True
        else:
            e.Cancel = True

    def _toggle_log(self, sender, e):
        self._log_expanded = not self._log_expanded

        def _do():
            if self._log_box is not None and not self._log_box.IsDisposed:
                if self._log_expanded:
                    self._log_box.Show()
                    self._log_toggle_btn.Text = "详细日志 ▾"
                else:
                    self._log_box.Hide()
                    self._log_toggle_btn.Text = "详细日志 ▸"
        self._safe_invoke(_do)

    def _show_phase(self, phase: str) -> None:
        self._current_phase = phase

        if phase not in self._visible_phases:
            return

        def _do():
            idx = self._visible_phases.index(phase)
            for i, ph in enumerate(self._visible_phases):
                lbl = self._phase_labels.get(ph)
                if lbl is None or lbl.IsDisposed:
                    continue
                if i < idx:
                    lbl.ForeColor = _COLOR_DONE
                    lbl.Text = f"\u2713 {_PHASE_LABELS[ph]}"
                elif i == idx:
                    lbl.ForeColor = _COLOR_ACTIVE
                    lbl.Text = f"\u25cf {_PHASE_LABELS[ph]}"
                    lbl.Font = Font("Microsoft YaHei", 8, FontStyle.Bold)
                else:
                    lbl.ForeColor = _COLOR_PENDING
                    lbl.Text = f"\u25cb {_PHASE_LABELS[ph]}"
                    lbl.Font = Font("Microsoft YaHei", 8)

            if self._form is not None and not self._form.IsDisposed:
                self._form.Text = f"LCTA 启动器 \u2014 {_PHASE_LABELS.get(phase, phase)}"

            if phase == PHASE_RUNNING:
                self._progress_bar.Visible = False
            else:
                self._progress_bar.Visible = True

            status_text = _PHASE_STATUS_TEXT.get(phase)
            if status_text and self._status_label is not None and not self._status_label.IsDisposed:
                self._status_label.Text = status_text

        self._safe_invoke(_do)

    def _show_game_running(self, **kw) -> None:
        self._current_phase = PHASE_RUNNING

        def _do():
            for i, ph in enumerate(self._visible_phases):
                lbl = self._phase_labels.get(ph)
                if lbl is None or lbl.IsDisposed:
                    continue
                if ph == PHASE_RUNNING:
                    lbl.ForeColor = _COLOR_ACTIVE
                    lbl.Text = f"\u25cf {_PHASE_LABELS[ph]}"
                    lbl.Font = Font("Microsoft YaHei", 8, FontStyle.Bold)
                else:
                    lbl.ForeColor = _COLOR_DONE
                    lbl.Text = f"\u2713 {_PHASE_LABELS[ph]}"
                    lbl.Font = Font("Microsoft YaHei", 8)

            if self._form is not None and not self._form.IsDisposed:
                self._form.Text = "LCTA 启动器 \u2014 游戏运行中"

            self._status_label.Text = "游戏运行中"
            self._progress_bar.Visible = False

            pid = self._pipeline.context.get('game_pid', '?') if self._pipeline else '?'
            self._info_label.Text = (
                f"游戏进程 PID: {pid}\n"
                f"快捷操作:  Ctrl+S 切换加速  |  Ctrl+Shift+S 倍率选择窗口"
            )
            self._info_label.Visible = True

            self._game_start_time = time.time()
            self._start_uptime_timer()

        self._safe_invoke(_do)

    def _show_game_exited(self, **kw) -> None:
        self._current_phase = PHASE_EXIT
        exit_code = kw.get('exit_code', '?')

        def _do():
            self._stop_uptime_timer()

            if self._form is not None and not self._form.IsDisposed:
                self._form.Text = "LCTA 启动器 \u2014 游戏已退出"

            self._progress_bar.Visible = False

            runtime_str = ""
            if self._game_start_time is not None:
                secs = int(time.time() - self._game_start_time)
                h, m = divmod(secs, 3600)
                m, s = divmod(m, 60)
                runtime_str = f"\n运行时长: {h}时{m}分{s}秒"

            self._status_label.Text = f"游戏已退出 (退出码: {exit_code})"
            self._info_label.Text = f"游戏进程已结束{runtime_str}"
            self._info_label.Visible = True

        self._safe_invoke(_do)

    def _start_uptime_timer(self):
        try:
            import System.Windows.Forms as WFTimer
            self._uptime_timer = WFTimer.Timer()
            self._uptime_timer.Interval = 1000
            self._uptime_timer.add_Tick(EventHandler(self._on_uptime_tick))
            self._uptime_timer.Start()
        except Exception:
            pass

    def _stop_uptime_timer(self):
        if self._uptime_timer is not None:
            try:
                self._uptime_timer.Stop()
                self._uptime_timer.Dispose()
            except Exception:
                pass
            self._uptime_timer = None

    def _on_uptime_tick(self, sender, e):
        if self._game_start_time is None:
            return
        secs = int(time.time() - self._game_start_time)
        h, m = divmod(secs, 3600)
        m, s = divmod(m, 60)
        pid = self._pipeline.context.get('game_pid', '?') if self._pipeline else '?'
        if self._info_label is not None and not self._info_label.IsDisposed:
            self._info_label.Text = (
                f"游戏进程 PID: {pid}    已运行 {h:02d}:{m:02d}:{s:02d}\n"
                f"快捷操作:  Ctrl+S 切换加速  |  Ctrl+Shift+S 倍率选择窗口"
            )

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
