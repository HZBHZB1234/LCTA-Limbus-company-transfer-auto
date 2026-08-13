import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from webutils.clr_bootstrap import ensure_clr


def _ensure_clr_with_log():
    """初始化 CLR(netfx);失败时把真实异常与修复指引写入 logs/app.log 后继续抛出。

    LogManager 的实例化在本模块中位于 ensure_clr 之后,失败时不可用,
    因此这里局部导入并兜底,保证日志写入失败也不会掩盖原始异常。
    """
    try:
        return ensure_clr()
    except Exception as exc:
        try:
            from globalManagers.LogManager import LogManager
            LogManager().log_error(exc)
        except Exception:
            pass
        raise


clr = _ensure_clr_with_log()

clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')
import System.Windows.Forms as WinForms
from System import EventHandler
from System.Drawing import (
    Point, Size, Color, Font, FontStyle, ContentAlignment,
)
from System.Windows.Forms import (
    FlatStyle, BorderStyle,
)

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager
from launcher.pipeline import (
    PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_RESOURCE_UPDATE, PHASE_CDN,
    PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING, PHASE_EXIT,
)

_window: Optional["LauncherProgressWindow"] = None

_log_manager = LogManager()

_PHASE_LABELS = {
    PHASE_INIT: "初始化",
    PHASE_CHECK_UPDATE: "检查更新",
    PHASE_CDN: "CDN优选",
    PHASE_RESOURCE_UPDATE: "游戏资源更新",
    PHASE_PREPARE_MOD: "模组准备",
    PHASE_LAUNCH: "启动游戏",
    PHASE_RUNNING: "游戏运行中",
    PHASE_EXIT: "游戏已退出",
}
_PHASE_ORDER = [PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN, PHASE_RESOURCE_UPDATE, PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING]

_PHASE_STATUS_TEXT = {
    PHASE_INIT: "正在初始化...",
    PHASE_CHECK_UPDATE: "正在检查更新...",
    PHASE_CDN: "正在进行CDN优选...",
    PHASE_RESOURCE_UPDATE: "正在检查游戏资源更新...",
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
        elif ph == PHASE_RESOURCE_UPDATE:
            if config.get("launcher.resource_update.enabled", False):
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
_COLOR_FAILED = Color.FromArgb(239, 83, 80)
_COLOR_WARNING = Color.FromArgb(255, 183, 77)
_COLOR_BG_DARK = Color.FromArgb(15, 18, 26)
_COLOR_BG_FORM = Color.FromArgb(20, 24, 34)
_COLOR_CARD = Color.FromArgb(28, 34, 48)
_COLOR_CARD_ALT = Color.FromArgb(34, 41, 57)
_COLOR_BORDER = Color.FromArgb(55, 65, 84)
_COLOR_FG_LIGHT = Color.FromArgb(238, 241, 247)
_COLOR_FG_MUTED = Color.FromArgb(157, 167, 184)


def _feature_summary(config) -> str:
    features = []
    if config.get("launcher.work.mod", False):
        features.append("模组")
    if config.get("launcher.work.fancy", False):
        features.append("文本美化")
    if config.get("launcher.work.tiaozhua", False):
        features.append("调爪文本")
    tiaozhua_config = config.get("ui_default.tiaozhua", {})
    if any(tiaozhua_config.get(f"replace_{n}", False) for n in (3, 4, 5, 7, 8)):
        features.append("调爪替换文本")
    if config.get("launcher.resource_update.enabled", False):
        features.append("资源预下载")
    if config.get("launcher.work.cdn_optimize", False):
        features.append("CDN 优选")
    if config.get("launcher.work.speed", False):
        features.append("游戏加速")
    return "、".join(features) if features else "仅启动游戏"


class LauncherProgressWindow:

    def __init__(self):
        self._form: Optional[WinForms.Form] = None
        self._status_label: Optional[WinForms.Label] = None
        self._activity_label: Optional[WinForms.Label] = None
        self._status_badge: Optional[WinForms.Label] = None
        self._progress_bar: Optional[WinForms.ProgressBar] = None
        self._phase_progress_label: Optional[WinForms.Label] = None
        self._phase_percent_label: Optional[WinForms.Label] = None
        self._overall_progress_bar: Optional[WinForms.ProgressBar] = None
        self._overall_progress_label: Optional[WinForms.Label] = None
        self._log_box: Optional[WinForms.RichTextBox] = None
        self._log_toggle_btn: Optional[WinForms.Button] = None
        self._log_panel: Optional[WinForms.Panel] = None
        self._action_btn: Optional[WinForms.Button] = None
        self._phase_flow: Optional[WinForms.FlowLayoutPanel] = None
        self._phase_labels: Dict[str, WinForms.Label] = {}
        self._info_label: Optional[WinForms.Label] = None
        self._game_path_value: Optional[WinForms.Label] = None
        self._update_mode_value: Optional[WinForms.Label] = None
        self._features_value: Optional[WinForms.Label] = None
        self._launch_source_value: Optional[WinForms.Label] = None
        self._thread: Optional = None
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._pipeline: Optional = None
        self._visible_phases = list(_PHASE_ORDER)
        self._current_phase = PHASE_INIT
        self._log_expanded = False
        self._collapsed_size = Size(920, 650)
        self._expanded_size = Size(920, 860)
        self._launch_start_time = time.time()
        self._phase_start_time = self._launch_start_time
        self._game_start_time: Optional[float] = None
        self._uptime_timer: Optional = None

    def register_to_pipeline(self, pipeline) -> None:
        self._pipeline = pipeline

        pipeline.on(PHASE_INIT, lambda **kw: self._show_phase(PHASE_INIT))
        pipeline.on(PHASE_CHECK_UPDATE, lambda **kw: self._show_phase(PHASE_CHECK_UPDATE))
        pipeline.on(PHASE_RESOURCE_UPDATE, lambda **kw: self._show_phase(PHASE_RESOURCE_UPDATE))
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
        form.Size = self._collapsed_size
        form.TopMost = False
        form.MaximizeBox = False
        form.MinimizeBox = True
        form.BackColor = _COLOR_BG_FORM
        form.Font = Font("Microsoft YaHei UI", 9)
        form.AutoScaleMode = WinForms.AutoScaleMode.Dpi
        form.add_FormClosing(WinForms.FormClosingEventHandler(self._on_form_closing))

        header = WinForms.Panel()
        header.Location = Point(0, 0)
        header.Size = Size(914, 88)
        header.BackColor = _COLOR_CARD
        form.Controls.Add(header)

        accent = WinForms.Panel()
        accent.Location = Point(0, 0)
        accent.Size = Size(6, 88)
        accent.BackColor = _COLOR_ACTIVE
        header.Controls.Add(accent)

        title = WinForms.Label()
        title.Text = "LCTA 游戏启动中心"
        title.Location = Point(24, 14)
        title.Size = Size(520, 30)
        title.Font = Font("Microsoft YaHei UI", 17, FontStyle.Bold)
        title.ForeColor = _COLOR_FG_LIGHT
        header.Controls.Add(title)

        subtitle = WinForms.Label()
        subtitle.Text = "自动完成汉化更新、资源准备与模组加载，然后启动 Limbus Company"
        subtitle.Location = Point(26, 50)
        subtitle.Size = Size(660, 22)
        subtitle.Font = Font("Microsoft YaHei UI", 9)
        subtitle.ForeColor = _COLOR_FG_MUTED
        header.Controls.Add(subtitle)

        badge = WinForms.Label()
        badge.Text = "准备中"
        badge.Location = Point(748, 25)
        badge.Size = Size(130, 34)
        badge.Font = Font("Microsoft YaHei UI", 10, FontStyle.Bold)
        badge.ForeColor = Color.White
        badge.BackColor = _COLOR_ACTIVE
        badge.TextAlign = ContentAlignment.MiddleCenter
        header.Controls.Add(badge)
        self._status_badge = badge

        stage_card = WinForms.Panel()
        stage_card.Location = Point(18, 106)
        stage_card.Size = Size(224, 430)
        stage_card.BackColor = _COLOR_CARD
        stage_card.BorderStyle = BorderStyle.FixedSingle
        form.Controls.Add(stage_card)

        stage_title = WinForms.Label()
        stage_title.Text = "启动阶段"
        stage_title.Location = Point(16, 14)
        stage_title.Size = Size(180, 24)
        stage_title.Font = Font("Microsoft YaHei UI", 11, FontStyle.Bold)
        stage_title.ForeColor = _COLOR_FG_LIGHT
        stage_card.Controls.Add(stage_title)

        stage_hint = WinForms.Label()
        stage_hint.Text = "按当前配置动态生成"
        stage_hint.Location = Point(16, 40)
        stage_hint.Size = Size(180, 20)
        stage_hint.Font = Font("Microsoft YaHei UI", 8)
        stage_hint.ForeColor = _COLOR_FG_MUTED
        stage_card.Controls.Add(stage_hint)

        flow = WinForms.FlowLayoutPanel()
        flow.Location = Point(12, 72)
        flow.Size = Size(198, 340)
        flow.FlowDirection = WinForms.FlowDirection.TopDown
        flow.WrapContents = False
        flow.BackColor = Color.Transparent
        stage_card.Controls.Add(flow)
        self._phase_flow = flow

        self._visible_phases = _get_visible_phases()
        for ph in self._visible_phases:
            lbl = WinForms.Label()
            lbl.Text = f"\u25cb  {_PHASE_LABELS[ph]}"
            lbl.AutoSize = False
            lbl.Size = Size(192, 39)
            lbl.Font = Font("Microsoft YaHei UI", 9)
            lbl.ForeColor = _COLOR_PENDING
            lbl.BackColor = _COLOR_CARD
            lbl.TextAlign = ContentAlignment.MiddleLeft
            lbl.Padding = WinForms.Padding(10, 0, 0, 0)
            lbl.Margin = WinForms.Padding(0, 0, 0, 5)
            flow.Controls.Add(lbl)
            self._phase_labels[ph] = lbl

        content = WinForms.Panel()
        content.Location = Point(258, 106)
        content.Size = Size(638, 430)
        content.BackColor = _COLOR_BG_FORM
        form.Controls.Add(content)

        progress_card = WinForms.Panel()
        progress_card.Location = Point(0, 0)
        progress_card.Size = Size(638, 224)
        progress_card.BackColor = _COLOR_CARD
        progress_card.BorderStyle = BorderStyle.FixedSingle
        content.Controls.Add(progress_card)

        eyebrow = WinForms.Label()
        eyebrow.Text = "当前任务"
        eyebrow.Location = Point(20, 15)
        eyebrow.Size = Size(130, 18)
        eyebrow.Font = Font("Microsoft YaHei UI", 8, FontStyle.Bold)
        eyebrow.ForeColor = _COLOR_ACTIVE
        progress_card.Controls.Add(eyebrow)

        status = WinForms.Label()
        status.Text = "正在初始化..."
        status.Location = Point(18, 38)
        status.Size = Size(595, 34)
        status.Font = Font("Microsoft YaHei UI", 15, FontStyle.Bold)
        status.ForeColor = _COLOR_FG_LIGHT
        status.TextAlign = ContentAlignment.MiddleLeft
        progress_card.Controls.Add(status)
        self._status_label = status

        activity = WinForms.Label()
        activity.Text = "正在读取 Launcher 配置与启动环境"
        activity.Location = Point(20, 74)
        activity.Size = Size(590, 22)
        activity.Font = Font("Microsoft YaHei UI", 9)
        activity.ForeColor = _COLOR_FG_MUTED
        activity.AutoEllipsis = True
        progress_card.Controls.Add(activity)
        self._activity_label = activity

        phase_caption = WinForms.Label()
        phase_caption.Text = "阶段进度"
        phase_caption.Location = Point(20, 108)
        phase_caption.Size = Size(120, 18)
        phase_caption.Font = Font("Microsoft YaHei UI", 8)
        phase_caption.ForeColor = _COLOR_FG_MUTED
        progress_card.Controls.Add(phase_caption)
        self._phase_progress_label = phase_caption

        phase_percent = WinForms.Label()
        phase_percent.Text = "处理中"
        phase_percent.Location = Point(500, 108)
        phase_percent.Size = Size(110, 18)
        phase_percent.Font = Font("Microsoft YaHei UI", 8, FontStyle.Bold)
        phase_percent.ForeColor = _COLOR_FG_LIGHT
        phase_percent.TextAlign = ContentAlignment.MiddleRight
        progress_card.Controls.Add(phase_percent)
        self._phase_percent_label = phase_percent

        prog = WinForms.ProgressBar()
        prog.Location = Point(20, 130)
        prog.Size = Size(590, 17)
        prog.Minimum = 0
        prog.Maximum = 100
        prog.Value = 0
        prog.Style = WinForms.ProgressBarStyle.Marquee
        prog.MarqueeAnimationSpeed = 28
        progress_card.Controls.Add(prog)
        self._progress_bar = prog

        overall_caption = WinForms.Label()
        overall_caption.Text = "总体进度"
        overall_caption.Location = Point(20, 164)
        overall_caption.Size = Size(120, 18)
        overall_caption.Font = Font("Microsoft YaHei UI", 8)
        overall_caption.ForeColor = _COLOR_FG_MUTED
        progress_card.Controls.Add(overall_caption)

        overall_text = WinForms.Label()
        overall_text.Text = "0%"
        overall_text.Location = Point(500, 164)
        overall_text.Size = Size(110, 18)
        overall_text.Font = Font("Microsoft YaHei UI", 8, FontStyle.Bold)
        overall_text.ForeColor = _COLOR_FG_LIGHT
        overall_text.TextAlign = ContentAlignment.MiddleRight
        progress_card.Controls.Add(overall_text)
        self._overall_progress_label = overall_text

        overall = WinForms.ProgressBar()
        overall.Location = Point(20, 186)
        overall.Size = Size(590, 13)
        overall.Minimum = 0
        overall.Maximum = 100
        overall.Value = 0
        overall.Style = WinForms.ProgressBarStyle.Continuous
        progress_card.Controls.Add(overall)
        self._overall_progress_bar = overall

        summary_card = WinForms.Panel()
        summary_card.Location = Point(0, 236)
        summary_card.Size = Size(638, 194)
        summary_card.BackColor = _COLOR_CARD
        summary_card.BorderStyle = BorderStyle.FixedSingle
        content.Controls.Add(summary_card)

        summary_title = WinForms.Label()
        summary_title.Text = "本次启动信息"
        summary_title.Location = Point(18, 12)
        summary_title.Size = Size(180, 24)
        summary_title.Font = Font("Microsoft YaHei UI", 11, FontStyle.Bold)
        summary_title.ForeColor = _COLOR_FG_LIGHT
        summary_card.Controls.Add(summary_title)

        self._game_path_value = self._add_info_row(summary_card, 42, "游戏目录")
        self._update_mode_value = self._add_info_row(summary_card, 76, "汉化更新")
        self._features_value = self._add_info_row(summary_card, 110, "启用功能")
        self._launch_source_value = self._add_info_row(summary_card, 144, "启动来源")

        info = WinForms.Label()
        info.Location = Point(18, 42)
        info.Size = Size(596, 126)
        info.Font = Font("Microsoft YaHei UI", 10)
        info.ForeColor = _COLOR_FG_LIGHT
        info.BackColor = _COLOR_CARD
        info.Text = ""
        info.TextAlign = ContentAlignment.MiddleLeft
        info.Visible = False
        summary_card.Controls.Add(info)
        self._info_label = info

        btn = WinForms.Button()
        btn.Text = "查看详细日志  ▾"
        btn.Location = Point(18, 550)
        btn.Size = Size(700, 38)
        btn.FlatStyle = FlatStyle.Flat
        btn.BackColor = _COLOR_CARD_ALT
        btn.ForeColor = _COLOR_FG_LIGHT
        btn.Font = Font("Microsoft YaHei UI", 9)
        btn.FlatAppearance.BorderColor = _COLOR_BORDER
        btn.FlatAppearance.BorderSize = 1
        btn.TextAlign = ContentAlignment.MiddleLeft
        btn.add_Click(EventHandler(self._toggle_log))
        form.Controls.Add(btn)
        self._log_toggle_btn = btn

        action = WinForms.Button()
        action.Text = "取消启动"
        action.Location = Point(734, 550)
        action.Size = Size(162, 38)
        action.FlatStyle = FlatStyle.Flat
        action.BackColor = Color.FromArgb(116, 49, 54)
        action.ForeColor = Color.White
        action.Font = Font("Microsoft YaHei UI", 9, FontStyle.Bold)
        action.FlatAppearance.BorderSize = 0
        action.add_Click(EventHandler(self._on_action_click))
        form.Controls.Add(action)
        self._action_btn = action

        footer = WinForms.Label()
        footer.Text = "关闭窗口时会询问是否中止当前任务；游戏运行后可选择仅关闭 Launcher。"
        footer.Location = Point(20, 596)
        footer.Size = Size(870, 20)
        footer.Font = Font("Microsoft YaHei UI", 8)
        footer.ForeColor = _COLOR_FG_MUTED
        form.Controls.Add(footer)

        log_panel = WinForms.Panel()
        log_panel.Location = Point(18, 620)
        log_panel.Size = Size(878, 190)
        log_panel.BackColor = _COLOR_CARD
        log_panel.BorderStyle = BorderStyle.FixedSingle
        log_panel.Visible = False
        form.Controls.Add(log_panel)
        self._log_panel = log_panel

        log_title = WinForms.Label()
        log_title.Text = "实时日志"
        log_title.Location = Point(14, 10)
        log_title.Size = Size(160, 22)
        log_title.Font = Font("Microsoft YaHei UI", 10, FontStyle.Bold)
        log_title.ForeColor = _COLOR_FG_LIGHT
        log_panel.Controls.Add(log_title)

        log = WinForms.RichTextBox()
        log.Location = Point(14, 38)
        log.Size = Size(848, 134)
        log.ReadOnly = True
        log.BackColor = _COLOR_BG_DARK
        log.ForeColor = _COLOR_FG_LIGHT
        log.Font = Font("Consolas", 8.5)
        log.WordWrap = True
        log.ScrollBars = WinForms.RichTextBoxScrollBars.Vertical
        log.DetectUrls = False
        log.BorderStyle = BorderStyle.FixedSingle
        log_panel.Controls.Add(log)
        log.Hide()
        self._log_box = log

        self._refresh_config_summary()

        self._form = form
        form.CreateHandle()
        self._ready.set()
        WinForms.Application.Run(form)
        self._closed.set()

    def _add_info_row(self, parent, y: int, caption: str):
        caption_label = WinForms.Label()
        caption_label.Text = caption
        caption_label.Location = Point(18, y)
        caption_label.Size = Size(86, 24)
        caption_label.Font = Font("Microsoft YaHei UI", 8)
        caption_label.ForeColor = _COLOR_FG_MUTED
        caption_label.TextAlign = ContentAlignment.MiddleLeft
        parent.Controls.Add(caption_label)

        value_label = WinForms.Label()
        value_label.Text = "读取中..."
        value_label.Location = Point(110, y)
        value_label.Size = Size(504, 24)
        value_label.Font = Font("Microsoft YaHei UI", 9)
        value_label.ForeColor = _COLOR_FG_LIGHT
        value_label.TextAlign = ContentAlignment.MiddleLeft
        value_label.AutoEllipsis = True
        parent.Controls.Add(value_label)
        return value_label

    def _refresh_config_summary(self) -> None:
        config = ConfigManager()
        game_path = str(config.get("game_path", "") or "未配置")
        game_exe = Path(game_path) / "LimbusCompany.exe" if game_path != "未配置" else None
        if game_exe is not None and not game_exe.exists():
            game_path = f"{game_path}  （未检测到游戏程序）"

        update_mode = str(config.get("launcher.work.update", "no") or "no")
        if update_mode == "no":
            update_mode = "不自动更新"

        launch_source = "Steam 启动参数" if os.getenv("steam_argv", "") else "配置中的游戏目录"

        if self._game_path_value is not None:
            self._game_path_value.Text = game_path
        if self._update_mode_value is not None:
            self._update_mode_value.Text = update_mode
        if self._features_value is not None:
            self._features_value.Text = _feature_summary(config)
        if self._launch_source_value is not None:
            self._launch_source_value.Text = launch_source

    def _on_action_click(self, sender, e):
        if self._form is None or self._form.IsDisposed:
            return
        self._form.Close()

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
                    if self._form is not None and not self._form.IsDisposed:
                        self._form.Size = self._expanded_size
                    if self._log_panel is not None and not self._log_panel.IsDisposed:
                        self._log_panel.Show()
                    self._log_box.Show()
                    self._log_toggle_btn.Text = "收起详细日志  ▴"
                else:
                    self._log_box.Hide()
                    if self._log_panel is not None and not self._log_panel.IsDisposed:
                        self._log_panel.Hide()
                    if self._form is not None and not self._form.IsDisposed:
                        self._form.Size = self._collapsed_size
                    self._log_toggle_btn.Text = "查看详细日志  ▾"
        self._safe_invoke(_do)

    def _show_phase(self, phase: str) -> None:
        self._current_phase = phase
        self._phase_start_time = time.time()

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
                    lbl.BackColor = _COLOR_CARD
                    lbl.Text = f"\u2713  {_PHASE_LABELS[ph]}"
                    lbl.Font = Font("Microsoft YaHei UI", 9)
                elif i == idx:
                    lbl.ForeColor = _COLOR_FG_LIGHT
                    lbl.BackColor = Color.FromArgb(42, 67, 98)
                    lbl.Text = f"\u25cf  {_PHASE_LABELS[ph]}"
                    lbl.Font = Font("Microsoft YaHei UI", 9, FontStyle.Bold)
                else:
                    lbl.ForeColor = _COLOR_PENDING
                    lbl.BackColor = _COLOR_CARD
                    lbl.Text = f"\u25cb  {_PHASE_LABELS[ph]}"
                    lbl.Font = Font("Microsoft YaHei UI", 9)

            if self._form is not None and not self._form.IsDisposed:
                self._form.Text = f"LCTA 启动器 \u2014 {_PHASE_LABELS.get(phase, phase)}"

            if phase == PHASE_RUNNING:
                self._progress_bar.Visible = False
            else:
                self._progress_bar.Visible = True
                self._progress_bar.Style = WinForms.ProgressBarStyle.Marquee
                self._progress_bar.MarqueeAnimationSpeed = 28

            overall = 100 if phase == PHASE_RUNNING else int(
                idx * 100 / max(1, len(self._visible_phases) - 1)
            )
            self._set_overall_progress_ui(overall)

            if self._phase_percent_label is not None and not self._phase_percent_label.IsDisposed:
                self._phase_percent_label.Text = "处理中"
            if self._activity_label is not None and not self._activity_label.IsDisposed:
                self._activity_label.Text = _PHASE_STATUS_TEXT.get(phase, "正在处理当前任务...")
            if self._status_badge is not None and not self._status_badge.IsDisposed:
                self._status_badge.Text = "处理中"
                self._status_badge.BackColor = _COLOR_ACTIVE

            status_text = _PHASE_STATUS_TEXT.get(phase)
            if status_text and self._status_label is not None and not self._status_label.IsDisposed:
                self._status_label.Text = status_text

        self._safe_invoke(_do)

    def mark_phase_failed(self, phase: str) -> None:
        def _do():
            lbl = self._phase_labels.get(phase)
            if lbl is None or lbl.IsDisposed:
                return
            lbl.ForeColor = Color.White
            lbl.BackColor = Color.FromArgb(104, 47, 52)
            lbl.Text = f"\u2717  {_PHASE_LABELS[phase]}"
            if self._status_badge is not None and not self._status_badge.IsDisposed:
                self._status_badge.Text = "存在问题"
                self._status_badge.BackColor = _COLOR_FAILED
        self._safe_invoke(_do)

    def _show_game_running(self, **kw) -> None:
        self._current_phase = PHASE_RUNNING

        def _do():
            for i, ph in enumerate(self._visible_phases):
                lbl = self._phase_labels.get(ph)
                if lbl is None or lbl.IsDisposed:
                    continue
                if ph == PHASE_RUNNING:
                    lbl.ForeColor = _COLOR_FG_LIGHT
                    lbl.BackColor = Color.FromArgb(40, 82, 68)
                    lbl.Text = f"\u25cf  {_PHASE_LABELS[ph]}"
                    lbl.Font = Font("Microsoft YaHei UI", 9, FontStyle.Bold)
                else:
                    lbl.ForeColor = _COLOR_DONE
                    lbl.BackColor = _COLOR_CARD
                    lbl.Text = f"\u2713  {_PHASE_LABELS[ph]}"
                    lbl.Font = Font("Microsoft YaHei UI", 9)

            if self._form is not None and not self._form.IsDisposed:
                self._form.Text = "LCTA 启动器 \u2014 游戏运行中"

            if self._status_label is not None and not self._status_label.IsDisposed:
                self._status_label.Text = "游戏运行中"
            if self._progress_bar is not None and not self._progress_bar.IsDisposed:
                self._progress_bar.Visible = False
            self._set_overall_progress_ui(100)

            if self._activity_label is not None and not self._activity_label.IsDisposed:
                self._activity_label.Text = "Launcher 正在监控游戏进程与快捷键状态"
            if self._status_badge is not None and not self._status_badge.IsDisposed:
                self._status_badge.Text = "运行中"
                self._status_badge.BackColor = _COLOR_DONE
            if self._phase_percent_label is not None and not self._phase_percent_label.IsDisposed:
                self._phase_percent_label.Text = "已完成"
            if self._action_btn is not None and not self._action_btn.IsDisposed:
                self._action_btn.Text = "退出选项"

            pid = self._pipeline.context.get('game_pid', '?') if self._pipeline else '?'
            if self._info_label is not None and not self._info_label.IsDisposed:
                self._info_label.Text = (
                    f"游戏已成功启动\n\n"
                    f"进程 PID：{pid}\n"
                    f"快捷操作：Ctrl+S 切换加速  |  Ctrl+Shift+S 选择倍率"
                )
                self._info_label.Visible = True
                self._info_label.BringToFront()

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

            if self._progress_bar is not None and not self._progress_bar.IsDisposed:
                self._progress_bar.Visible = False
            self._set_overall_progress_ui(100)

            runtime_str = ""
            if self._game_start_time is not None:
                secs = int(time.time() - self._game_start_time)
                h, m = divmod(secs, 3600)
                m, s = divmod(m, 60)
                runtime_str = f"\n运行时长: {h}时{m}分{s}秒"

            if self._status_label is not None and not self._status_label.IsDisposed:
                self._status_label.Text = f"游戏已退出 (退出码: {exit_code})"
            if self._info_label is not None and not self._info_label.IsDisposed:
                self._info_label.Text = f"游戏进程已结束{runtime_str}"
                self._info_label.Visible = True
                self._info_label.BringToFront()

            success = exit_code == 0
            if self._activity_label is not None and not self._activity_label.IsDisposed:
                self._activity_label.Text = "本次启动流程已结束，可查看日志了解各阶段详情"
            if self._status_badge is not None and not self._status_badge.IsDisposed:
                self._status_badge.Text = "已完成" if success else "异常退出"
                self._status_badge.BackColor = _COLOR_DONE if success else _COLOR_FAILED
            if self._phase_percent_label is not None and not self._phase_percent_label.IsDisposed:
                self._phase_percent_label.Text = "已结束"
            if self._action_btn is not None and not self._action_btn.IsDisposed:
                self._action_btn.Text = "关闭窗口"
                self._action_btn.BackColor = _COLOR_CARD_ALT

        self._safe_invoke(_do)

    def prompt_crash_export(self, exit_code: int) -> None:
        """游戏异常退出时弹窗询问是否导出日志（同步阻塞直到用户响应）。

        在主线程调用；经 form.Invoke 切到 GUI 线程以模态对话框呈现，
        保证弹窗在进程退出前完成交互（GUI 线程为后台线程，main() 返回即进程结束）。
        """
        if self._form is None or self._form.IsDisposed or not self._form.IsHandleCreated:
            return
        try:
            self._form.Invoke(
                WinForms.MethodInvoker(lambda: self._run_crash_export_dialog(exit_code))
            )
        except Exception as e:
            _log_manager.log(f"显示游戏异常退出弹窗失败: {e}")

    def _run_crash_export_dialog(self, exit_code: int) -> None:
        try:
            dlg = self._build_crash_export_dialog(exit_code)
            dlg.ShowDialog(self._form)
            dlg.Dispose()
        except Exception as e:
            _log_manager.log(f"显示游戏异常退出弹窗失败: {e}")

    def _build_crash_export_dialog(self, exit_code: int):
        dlg = WinForms.Form()
        dlg.Text = "游戏异常退出"
        dlg.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        dlg.StartPosition = WinForms.FormStartPosition.CenterParent
        dlg.Size = Size(440, 208)
        dlg.MaximizeBox = False
        dlg.MinimizeBox = False
        dlg.ShowInTaskbar = False
        dlg.BackColor = _COLOR_BG_FORM
        dlg.Font = Font("Microsoft YaHei UI", 9)
        dlg.AutoScaleMode = WinForms.AutoScaleMode.Dpi

        title = WinForms.Label()
        title.Text = "游戏异常退出"
        title.Location = Point(20, 14)
        title.Size = Size(400, 26)
        title.Font = Font("Microsoft YaHei UI", 13, FontStyle.Bold)
        title.ForeColor = Color.FromArgb(239, 83, 80)
        dlg.Controls.Add(title)

        desc = WinForms.Label()
        desc.Text = (
            f"游戏进程非正常退出（退出码: {exit_code}）。\n"
            "可导出游戏日志与崩溃报告，便于排查问题。"
        )
        desc.Location = Point(20, 50)
        desc.Size = Size(400, 44)
        desc.Font = Font("Microsoft YaHei UI", 9)
        desc.ForeColor = _COLOR_FG_LIGHT
        dlg.Controls.Add(desc)

        hint = WinForms.Label()
        hint.Text = "导出内容：Player.log、Player-prev.log 及崩溃报告（如有）"
        hint.Location = Point(20, 96)
        hint.Size = Size(400, 20)
        hint.Font = Font("Microsoft YaHei UI", 8)
        hint.ForeColor = _COLOR_FG_MUTED
        dlg.Controls.Add(hint)

        export_btn = WinForms.Button()
        export_btn.Text = "导出日志"
        export_btn.Location = Point(130, 132)
        export_btn.Size = Size(120, 36)
        export_btn.FlatStyle = FlatStyle.Flat
        export_btn.BackColor = Color.FromArgb(56, 94, 128)
        export_btn.ForeColor = Color.White
        export_btn.Font = Font("Microsoft YaHei UI", 9, FontStyle.Bold)
        export_btn.FlatAppearance.BorderSize = 0
        export_btn.add_Click(EventHandler(lambda s, e: self._on_crash_export_click(dlg)))
        dlg.Controls.Add(export_btn)
        dlg.AcceptButton = export_btn

        ignore_btn = WinForms.Button()
        ignore_btn.Text = "忽略"
        ignore_btn.Location = Point(268, 132)
        ignore_btn.Size = Size(90, 36)
        ignore_btn.FlatStyle = FlatStyle.Flat
        ignore_btn.BackColor = _COLOR_CARD_ALT
        ignore_btn.ForeColor = _COLOR_FG_LIGHT
        ignore_btn.Font = Font("Microsoft YaHei UI", 9)
        ignore_btn.FlatAppearance.BorderColor = _COLOR_BORDER
        ignore_btn.FlatAppearance.BorderSize = 1
        ignore_btn.add_Click(EventHandler(lambda s, e: dlg.Close()))
        dlg.Controls.Add(ignore_btn)
        dlg.CancelButton = ignore_btn

        return dlg

    def _on_crash_export_click(self, dlg) -> None:
        dlg.Cursor = WinForms.Cursors.WaitCursor
        try:
            from launcher.crash_export import export_game_logs
            result = export_game_logs()
            if result:
                WinForms.MessageBox.Show(
                    dlg,
                    f"日志已导出到：\n{result}\n\n已自动打开所在文件夹。",
                    "导出完成",
                    WinForms.MessageBoxButtons.OK,
                    WinForms.MessageBoxIcon.Information,
                )
                dlg.Close()
            else:
                WinForms.MessageBox.Show(
                    dlg,
                    "导出失败：未找到可导出的日志文件，或打包过程中发生错误（详情见 Launcher 日志）。",
                    "导出失败",
                    WinForms.MessageBoxButtons.OK,
                    WinForms.MessageBoxIcon.Warning,
                )
        except Exception as e:
            WinForms.MessageBox.Show(
                dlg,
                f"导出日志失败：{e}",
                "导出失败",
                WinForms.MessageBoxButtons.OK,
                WinForms.MessageBoxIcon.Error,
            )
        finally:
            dlg.Cursor = WinForms.Cursors.Default

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

    def _set_overall_progress_ui(self, value: int) -> None:
        normalized = max(0, min(int(value), 100))
        if self._overall_progress_bar is not None and not self._overall_progress_bar.IsDisposed:
            self._overall_progress_bar.Value = normalized
        if self._overall_progress_label is not None and not self._overall_progress_label.IsDisposed:
            self._overall_progress_label.Text = f"{normalized}%"

    def start(self):
        import System.Threading as NetThreading
        self._thread = NetThreading.Thread(NetThreading.ThreadStart(self._create_form))
        self._thread.SetApartmentState(NetThreading.ApartmentState.STA)
        self._thread.IsBackground = True
        self._thread.Start()
        if not self._ready.wait(10.0):
            raise RuntimeError("GUI窗口创建超时，请确认系统支持WinForms")

    def update_status(self, text: str, modal_id=None):
        def _set():
            if self._status_label is not None and not self._status_label.IsDisposed:
                self._status_label.Text = text
            if self._activity_label is not None and not self._activity_label.IsDisposed:
                self._activity_label.Text = text
        self._safe_invoke(_set)

    def update_activity(self, text: str):
        def _set():
            if self._activity_label is not None and not self._activity_label.IsDisposed:
                self._activity_label.Text = text
        self._safe_invoke(_set)

    def set_progress(self, value: int, max_value: int = 100):
        def _set():
            if self._progress_bar is not None and not self._progress_bar.IsDisposed:
                safe_max = max(1, int(max_value))
                safe_value = max(0, min(int(value), safe_max))
                self._progress_bar.Style = WinForms.ProgressBarStyle.Blocks
                self._progress_bar.MarqueeAnimationSpeed = 0
                self._progress_bar.Maximum = safe_max
                self._progress_bar.Value = safe_value
                self._progress_bar.Visible = True
                if self._phase_percent_label is not None and not self._phase_percent_label.IsDisposed:
                    percent = int(safe_value * 100 / safe_max)
                    self._phase_percent_label.Text = f"{percent}%"
        self._safe_invoke(_set)

    def set_progress_marquee(self, text: str = ""):
        def _set():
            if self._progress_bar is not None and not self._progress_bar.IsDisposed:
                self._progress_bar.Style = WinForms.ProgressBarStyle.Marquee
                self._progress_bar.MarqueeAnimationSpeed = 28
                self._progress_bar.Visible = True
            if self._phase_percent_label is not None and not self._phase_percent_label.IsDisposed:
                self._phase_percent_label.Text = "处理中"
            if text and self._activity_label is not None and not self._activity_label.IsDisposed:
                self._activity_label.Text = text
        self._safe_invoke(_set)

    def update_phase_progress(self, percent: int, text: str = "") -> None:
        self.set_progress(percent, 100)
        if text:
            self.update_activity(text)

    def update_modal_progress(self, percent: int, text: str = "", modal_id=None, log=True) -> None:
        self.update_phase_progress(percent, text)

    def update_resource_progress(self, channel: str, message: str, fraction) -> None:
        display = f"{channel}：{message}" if channel else message
        if fraction is None:
            self.set_progress_marquee(display)
            return
        self.update_phase_progress(int(max(0.0, min(1.0, fraction)) * 100), display)

    def update_cdn_progress(self, percent, message: str) -> None:
        self.update_phase_progress(int(percent), message)

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
