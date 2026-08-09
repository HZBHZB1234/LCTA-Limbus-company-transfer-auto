"""launcher/pipeline.py 与 gui_progress.py 单元测试。

由于 gui_progress.py 依赖 clr/pythonnet + WinForms，无法在无桌面环境的 CI 中
直接创建控件，故采用 mock _safe_invoke 同/异步调度 + mock WinForms 部件的方式
验证窗口逻辑。
"""

import logging
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from launcher.pipeline import (
    LaunchPipeline,
    PHASE_INIT,
    PHASE_CHECK_UPDATE,
    PHASE_RESOURCE_UPDATE,
    PHASE_CDN,
    PHASE_PREPARE_MOD,
    PHASE_LAUNCH,
    PHASE_RUNNING,
    PHASE_EXIT,
)

_PHASE_LABELS_LOOKUP = {
    PHASE_INIT: "初始化",
    PHASE_CHECK_UPDATE: "检查更新",
    PHASE_RESOURCE_UPDATE: "游戏资源更新",
    PHASE_CDN: "CDN优选",
    PHASE_PREPARE_MOD: "模组准备",
    PHASE_LAUNCH: "启动游戏",
    PHASE_RUNNING: "游戏运行中",
    PHASE_EXIT: "游戏已退出",
}


# ═══════════════════════════════════════════════════════════════════
# LaunchPipeline 测试
# ═══════════════════════════════════════════════════════════════════

class TestLaunchPipeline:
    def test_on_registers_callback(self):
        pipeline = LaunchPipeline()
        cb = MagicMock()
        pipeline.on(PHASE_INIT, cb)
        pipeline.emit(PHASE_INIT)
        cb.assert_called_once()

    def test_emit_triggers_multiple_callbacks_in_order(self):
        pipeline = LaunchPipeline()
        results = []
        pipeline.on(PHASE_INIT, lambda **kw: results.append(1))
        pipeline.on(PHASE_INIT, lambda **kw: results.append(2))
        pipeline.emit(PHASE_INIT)
        assert results == [1, 2]

    def test_emit_passes_kwargs(self):
        pipeline = LaunchPipeline()
        cb = MagicMock()
        pipeline.on(PHASE_LAUNCH, cb)
        pipeline.emit(PHASE_LAUNCH, pid=1234)
        cb.assert_called_once_with(pid=1234)

    def test_emit_returns_false_when_cancelled(self):
        pipeline = LaunchPipeline()
        cb = MagicMock()
        pipeline.on(PHASE_INIT, cb)
        pipeline.cancel()
        result = pipeline.emit(PHASE_INIT)
        assert result is False
        cb.assert_not_called()

    def test_cancel_sets_event(self):
        pipeline = LaunchPipeline()
        assert pipeline.is_cancelled is False
        pipeline.cancel()
        assert pipeline.is_cancelled is True
        assert pipeline.cancel_event.is_set()

    def test_unknown_phase_emits_without_error(self):
        pipeline = LaunchPipeline()
        result = pipeline.emit("no_such_phase")
        assert result is True

    def test_callback_exception_does_not_block_siblings(self):
        pipeline = LaunchPipeline()
        good = MagicMock()

        def bad(**kw):
            raise RuntimeError("boom")

        pipeline.on(PHASE_INIT, bad)
        pipeline.on(PHASE_INIT, good)
        pipeline.emit(PHASE_INIT)
        good.assert_called_once()

    def test_context_dict_shared_across_callbacks(self):
        pipeline = LaunchPipeline()

        def writer(**kw):
            pipeline.context["key"] = "written"

        def reader(**kw):
            assert pipeline.context.get("key") == "written"

        pipeline.on(PHASE_INIT, writer)
        pipeline.on(PHASE_LAUNCH, reader)
        pipeline.emit(PHASE_INIT)
        pipeline.emit(PHASE_LAUNCH)

    def test_all_phase_constants_are_unique_strings(self):
        phases = [
            PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_RESOURCE_UPDATE, PHASE_CDN,
            PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING, PHASE_EXIT,
        ]
        assert len(set(phases)) == 8
        assert all(isinstance(p, str) for p in phases)


# ═══════════════════════════════════════════════════════════════════
# ProgressLogHandler 测试
# ═══════════════════════════════════════════════════════════════════

class TestProgressLogHandler:
    def test_formats_and_forwards_record(self):
        from launcher.gui_progress import ProgressLogHandler

        mock_window = MagicMock()
        handler = ProgressLogHandler(mock_window)

        record = logging.LogRecord(
            "LCTA", logging.INFO, "", 0, "hello world", (), None,
        )
        handler.emit(record)

        mock_window.append_log.assert_called_once()
        logged = mock_window.append_log.call_args[0][0]
        assert "hello world" in logged

    def test_reentrancy_guard_prevents_recursion(self):
        from launcher.gui_progress import ProgressLogHandler

        mock_window = MagicMock()
        handler = ProgressLogHandler(mock_window)

        calls = []

        def side_effect(msg):
            calls.append(msg)
            # 在 append_log 内部再次 emit —— 应被 _active 防护跳过
            inner = logging.LogRecord(
                "LCTA", logging.INFO, "", 0, "inner", (), None,
            )
            handler.emit(inner)

        mock_window.append_log.side_effect = side_effect

        outer = logging.LogRecord(
            "LCTA", logging.INFO, "", 0, "outer", (), None,
        )
        handler.emit(outer)

        assert len(calls) == 1
        assert "outer" in calls[0]

    def test_formatter_includes_levelname_and_timestamp(self):
        from launcher.gui_progress import ProgressLogHandler

        mock_window = MagicMock()
        handler = ProgressLogHandler(mock_window)

        record = logging.LogRecord(
            "LCTA", logging.WARNING, "", 0, "warning msg", (), None,
        )
        handler.emit(record)

        logged = mock_window.append_log.call_args[0][0]
        assert "WARNING" in logged
        assert "warning msg" in logged


# ═══════════════════════════════════════════════════════════════════
# LauncherProgressWindow 测试（mock WinForms）
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_safe_window():
    """创建一个 mock 了 _safe_invoke（同步执行）和所有 UI 控件的窗口。"""
    from launcher.gui_progress import LauncherProgressWindow

    w = LauncherProgressWindow()

    # 将 _safe_invoke 替换为同步执行
    w._safe_invoke = lambda action: action()

    # Mock 控件
    w._form = MagicMock()
    w._form.IsDisposed = False
    w._form.IsHandleCreated = True
    w._status_label = MagicMock()
    w._status_label.IsDisposed = False
    w._activity_label = MagicMock()
    w._activity_label.IsDisposed = False
    w._progress_bar = MagicMock()
    w._progress_bar.IsDisposed = False
    w._phase_percent_label = MagicMock()
    w._phase_percent_label.IsDisposed = False
    w._overall_progress_bar = MagicMock()
    w._overall_progress_bar.IsDisposed = False
    w._overall_progress_label = MagicMock()
    w._overall_progress_label.IsDisposed = False
    w._log_box = MagicMock()
    w._log_box.IsDisposed = False
    w._log_toggle_btn = MagicMock()
    w._log_toggle_btn.IsDisposed = False
    w._info_label = MagicMock()
    w._info_label.IsDisposed = False

    for ph in [PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN,
                PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING]:
        lbl = MagicMock()
        lbl.IsDisposed = False
        lbl.Text = f"\u25cb {_PHASE_LABELS_LOOKUP[ph]}"
        w._phase_labels[ph] = lbl

    w._visible_phases = [
        PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN,
        PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING,
    ]
    w._current_phase = None
    return w


class TestWindowPhaseDisplay:
    def test_show_phase_sets_current_and_updates_labels(self, mock_safe_window):
        mock_safe_window._show_phase(PHASE_CHECK_UPDATE)

        assert mock_safe_window._current_phase == PHASE_CHECK_UPDATE

        # PHASE_INIT 应该被标记为已完成（绿色 ✓）
        init_lbl = mock_safe_window._phase_labels[PHASE_INIT]
        assert "\u2713" in init_lbl.Text
        assert init_lbl.ForeColor is not None

        # PHASE_CHECK_UPDATE 应该是当前（蓝色 ●）
        cur_lbl = mock_safe_window._phase_labels[PHASE_CHECK_UPDATE]
        assert "\u25cf" in cur_lbl.Text
        assert cur_lbl.ForeColor is not None

        # PHASE_CDN 应该是待处理（灰色 ○）
        next_lbl = mock_safe_window._phase_labels[PHASE_CDN]
        assert "\u25cb" in next_lbl.Text

    def test_show_last_phase_marks_all_done(self, mock_safe_window):
        mock_safe_window._show_phase(PHASE_RUNNING)

        for ph in [PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN, PHASE_PREPARE_MOD]:
            lbl = mock_safe_window._phase_labels[ph]
            assert "\u2713" in lbl.Text

        running_lbl = mock_safe_window._phase_labels[PHASE_RUNNING]
        assert "\u25cf" in running_lbl.Text

    def test_progress_bar_hidden_when_running(self, mock_safe_window):
        mock_safe_window._show_phase(PHASE_RUNNING)
        assert mock_safe_window._progress_bar.Visible is False

    def test_progress_bar_visible_for_other_phases(self, mock_safe_window):
        mock_safe_window._show_phase(PHASE_INIT)
        assert mock_safe_window._progress_bar.Visible is True

    def test_form_title_updates(self, mock_safe_window):
        mock_safe_window._show_phase(PHASE_CDN)
        assert "CDN" in mock_safe_window._form.Text

    def test_show_phase_updates_overall_progress(self, mock_safe_window):
        mock_safe_window._show_phase(PHASE_CDN)
        assert mock_safe_window._overall_progress_bar.Value == 40
        assert mock_safe_window._overall_progress_label.Text == "40%"

    def test_unknown_phase_does_not_raise(self, mock_safe_window):
        mock_safe_window._show_phase("nonexistent")
        assert mock_safe_window._current_phase == "nonexistent"


class TestWindowGameRunning:
    def test_marks_all_previous_complete(self, mock_safe_window):
        pipeline = LaunchPipeline()
        pipeline.context["game_pid"] = 9999
        mock_safe_window._pipeline = pipeline

        mock_safe_window._show_game_running()

        for ph in [PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN,
                    PHASE_PREPARE_MOD, PHASE_LAUNCH]:
            lbl = mock_safe_window._phase_labels[ph]
            assert "\u2713" in lbl.Text

        running_lbl = mock_safe_window._phase_labels[PHASE_RUNNING]
        assert "\u25cf" in running_lbl.Text

    def test_displays_pid_and_hotkey_hints(self, mock_safe_window):
        pipeline = LaunchPipeline()
        pipeline.context["game_pid"] = 5678
        mock_safe_window._pipeline = pipeline

        mock_safe_window._show_game_running()

        assert mock_safe_window._info_label.Visible is True
        assert "5678" in mock_safe_window._info_label.Text
        assert "Ctrl+S" in mock_safe_window._info_label.Text

    def test_progress_bar_hidden(self, mock_safe_window):
        mock_safe_window._show_game_running()
        assert mock_safe_window._progress_bar.Visible is False

    def test_status_label_shows_running(self, mock_safe_window):
        mock_safe_window._show_game_running()
        assert mock_safe_window._status_label.Text == "游戏运行中"

    def test_uptime_timer_started(self, mock_safe_window):
        mock_safe_window._show_game_running()
        assert mock_safe_window._uptime_timer is not None

    def test_no_pipeline_context_fallback(self, mock_safe_window):
        mock_safe_window._show_game_running()
        assert mock_safe_window._info_label.Visible is True


class TestWindowGameExited:
    def test_phase_set_to_exit(self, mock_safe_window):
        mock_safe_window._show_game_exited(exit_code=0)
        assert mock_safe_window._current_phase == PHASE_EXIT

    def test_displays_exit_code(self, mock_safe_window):
        mock_safe_window._show_game_exited(exit_code=42)
        assert "42" in mock_safe_window._status_label.Text

    def test_progress_bar_hidden(self, mock_safe_window):
        mock_safe_window._show_game_exited(exit_code=0)
        assert mock_safe_window._progress_bar.Visible is False

    def test_info_label_visible(self, mock_safe_window):
        mock_safe_window._show_game_exited(exit_code=0)
        assert mock_safe_window._info_label.Visible is True

    def test_stops_uptime_timer(self, mock_safe_window):
        timer_mock = MagicMock()
        mock_safe_window._uptime_timer = timer_mock
        mock_safe_window._show_game_exited(exit_code=0)
        timer_mock.Stop.assert_called_once()

    def test_runtime_display(self, mock_safe_window):
        mock_safe_window._game_start_time = 0  # epoch
        with patch("launcher.gui_progress.time") as mock_time:
            mock_time.time.return_value = 3661  # 1h 1m 1s
            mock_safe_window._show_game_exited(exit_code=0)

        assert "运行时长" in mock_safe_window._info_label.Text
        assert "1时1分1秒" in mock_safe_window._info_label.Text


class _MockEventArgs:
    """模拟 FormClosingEventArgs，支持 Cancel 属性。"""
    def __init__(self):
        self.Cancel = False


class TestWindowCloseConfirmation:
    def test_allow_close_in_exit_phase(self, mock_safe_window):
        mock_safe_window._current_phase = PHASE_EXIT
        mock_e = _MockEventArgs()

        mock_safe_window._on_form_closing(None, mock_e)

        assert mock_e.Cancel is False

    @patch("launcher.gui_progress.WinForms")
    def test_confirm_yes_during_running_sets_cancel(self, mock_winforms,
                                                     mock_safe_window):
        mock_safe_window._current_phase = PHASE_RUNNING
        mock_safe_window._pipeline = LaunchPipeline()

        mock_winforms.MessageBox.Show.return_value = mock_winforms.DialogResult.Yes
        mock_e = _MockEventArgs()

        mock_safe_window._on_form_closing(None, mock_e)

        assert mock_safe_window._pipeline.is_cancelled is True
        assert mock_e.Cancel is False

    @patch("launcher.gui_progress.WinForms")
    def test_confirm_no_cancels_close(self, mock_winforms, mock_safe_window):
        mock_safe_window._current_phase = PHASE_INIT
        mock_winforms.MessageBox.Show.return_value = mock_winforms.DialogResult.No
        mock_e = _MockEventArgs()

        mock_safe_window._on_form_closing(None, mock_e)

        assert mock_e.Cancel is True

    @patch("launcher.gui_progress.WinForms")
    def test_confirm_message_during_running_mentions_game(self, mock_winforms,
                                                           mock_safe_window):
        mock_safe_window._current_phase = PHASE_RUNNING
        mock_winforms.MessageBox.Show.return_value = mock_winforms.DialogResult.No

        mock_safe_window._on_form_closing(None, MagicMock())

        msg = mock_winforms.MessageBox.Show.call_args[0][1]
        assert "游戏正在运行" in msg
        assert "终止游戏" in msg

    @patch("launcher.gui_progress.WinForms")
    def test_confirm_message_during_launch_mentions_in_progress(self, mock_winforms,
                                                                 mock_safe_window):
        mock_safe_window._current_phase = PHASE_LAUNCH
        mock_winforms.MessageBox.Show.return_value = mock_winforms.DialogResult.No

        mock_safe_window._on_form_closing(None, MagicMock())

        msg = mock_winforms.MessageBox.Show.call_args[0][1]
        assert "启动流程" in msg


class TestWindowPipelineRegistration:
    def test_register_wires_all_phase_callbacks(self, mock_safe_window):
        pipeline = LaunchPipeline()
        mock_safe_window.register_to_pipeline(pipeline)

        pipeline.emit(PHASE_INIT)
        assert mock_safe_window._current_phase == PHASE_INIT

        pipeline.emit(PHASE_CHECK_UPDATE)
        assert mock_safe_window._current_phase == PHASE_CHECK_UPDATE

        pipeline.emit(PHASE_CDN)
        assert mock_safe_window._current_phase == PHASE_CDN

        pipeline.emit(PHASE_PREPARE_MOD)
        assert mock_safe_window._current_phase == PHASE_PREPARE_MOD

        pipeline.emit(PHASE_LAUNCH)
        assert mock_safe_window._current_phase == PHASE_LAUNCH

    def test_register_stores_pipeline_reference(self, mock_safe_window):
        pipeline = LaunchPipeline()
        mock_safe_window.register_to_pipeline(pipeline)
        assert mock_safe_window._pipeline is pipeline


class TestWindowMethods:
    def test_update_status_sets_label(self, mock_safe_window):
        mock_safe_window.update_status("测试状态")
        assert mock_safe_window._status_label.Text == "测试状态"

    def test_set_progress_blocks_mode(self, mock_safe_window):
        mock_safe_window.set_progress(75, 100)
        assert mock_safe_window._progress_bar.Style is not None
        assert mock_safe_window._progress_bar.Maximum == 100
        assert mock_safe_window._progress_bar.Value == 75

    def test_set_progress_clamps_negative(self, mock_safe_window):
        mock_safe_window.set_progress(-5, 100)
        assert mock_safe_window._progress_bar.Value == 0

    def test_set_progress_clamps_overflow(self, mock_safe_window):
        mock_safe_window.set_progress(200, 100)
        assert mock_safe_window._progress_bar.Value == 100

    def test_set_progress_marquee_mode(self, mock_safe_window):
        mock_safe_window.set_progress_marquee()
        assert mock_safe_window._progress_bar.Style is not None

    def test_resource_progress_updates_detail_and_percent(self, mock_safe_window):
        mock_safe_window.update_resource_progress("Bundle", "已完成 2/4", 0.5)
        assert mock_safe_window._progress_bar.Value == 50
        assert mock_safe_window._phase_percent_label.Text == "50%"
        assert "Bundle" in mock_safe_window._activity_label.Text

    def test_resource_progress_without_fraction_uses_marquee(self, mock_safe_window):
        mock_safe_window.update_resource_progress("Localize", "正在解析目录", None)
        assert mock_safe_window._progress_bar.Style is not None
        assert "Localize" in mock_safe_window._activity_label.Text

    def test_append_log_calls_log_box(self, mock_safe_window):
        mock_safe_window.append_log("line 1")
        mock_safe_window._log_box.AppendText.assert_called_once_with("line 1\n")

    def test_toggle_log_expands_and_collapses(self, mock_safe_window):
        assert mock_safe_window._log_expanded is False

        mock_safe_window._toggle_log(None, None)
        assert mock_safe_window._log_expanded is True
        mock_safe_window._log_box.Show.assert_called_once()

        mock_safe_window._toggle_log(None, None)
        assert mock_safe_window._log_expanded is False
        mock_safe_window._log_box.Hide.assert_called_once()

    def test_close_dispatches_form_close(self, mock_safe_window):
        mock_safe_window.close()
        mock_safe_window._form.Close.assert_called_once()

    def test_is_alive_no_thread(self, mock_safe_window):
        mock_safe_window._thread = None
        mock_safe_window._closed.clear()
        assert mock_safe_window.is_alive() is False

    def test_is_alive_with_closed_event(self, mock_safe_window):
        mock_safe_window._thread = MagicMock()
        mock_safe_window._thread.IsAlive = True
        mock_safe_window._closed.set()
        assert mock_safe_window.is_alive() is False


class TestSafeInvokeEdgeCases:
    def test_returns_silently_when_form_is_none(self):
        from launcher.gui_progress import LauncherProgressWindow
        w = LauncherProgressWindow()
        w._form = None
        w._safe_invoke(lambda: 1 / 0)

    def test_returns_silently_when_form_disposed(self):
        from launcher.gui_progress import LauncherProgressWindow
        w = LauncherProgressWindow()
        w._form = MagicMock()
        w._form.IsDisposed = True
        w._safe_invoke(lambda: 1 / 0)

    def test_returns_silently_when_no_handle(self):
        from launcher.gui_progress import LauncherProgressWindow
        w = LauncherProgressWindow()
        w._form = MagicMock()
        w._form.IsDisposed = False
        w._form.IsHandleCreated = False
        w._safe_invoke(lambda: 1 / 0)

    def test_returns_silently_on_begininvoke_exception(self):
        from launcher.gui_progress import LauncherProgressWindow
        w = LauncherProgressWindow()
        w._form = MagicMock()
        w._form.IsDisposed = False
        w._form.IsHandleCreated = True
        w._form.BeginInvoke.side_effect = RuntimeError("disposed in the middle")
        w._safe_invoke(lambda: None)


# ═══════════════════════════════════════════════════════════════════
# VisiblePhaseFiltering 测试
# ═══════════════════════════════════════════════════════════════════

class TestGetVisiblePhases:
    def test_default_config_shows_four_phases(self):
        from launcher.gui_progress import _get_visible_phases

        with patch("launcher.gui_progress.ConfigManager") as mock_cm:
            instance = mock_cm.return_value
            def _mock_get(key, default):
                if key == "launcher.work.update":
                    return "LM-G"
                return default
            instance.get.side_effect = _mock_get
            result = _get_visible_phases()

        assert len(result) == 4
        assert result == [PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_LAUNCH, PHASE_RUNNING]

    def test_update_no_removes_check_update(self):
        from launcher.gui_progress import _get_visible_phases

        with patch("launcher.gui_progress.ConfigManager") as mock_cm:
            instance = mock_cm.return_value
            def _mock_get(key, default):
                if key == "launcher.work.update":
                    return "no"
                return default
            instance.get.side_effect = _mock_get
            result = _get_visible_phases()

        assert len(result) == 3
        assert result == [PHASE_INIT, PHASE_LAUNCH, PHASE_RUNNING]

    def test_cdn_enabled_includes_cdn(self):
        from launcher.gui_progress import _get_visible_phases

        with patch("launcher.gui_progress.ConfigManager") as mock_cm:
            instance = mock_cm.return_value
            def _mock_get(key, default):
                if key == "launcher.work.update":
                    return "LM-G"
                if key == "launcher.work.cdn_optimize":
                    return True
                return default
            instance.get.side_effect = _mock_get
            result = _get_visible_phases()

        assert PHASE_CDN in result
        assert result.index(PHASE_CDN) > result.index(PHASE_CHECK_UPDATE)
        assert result.index(PHASE_CDN) < result.index(PHASE_LAUNCH)

    def test_mod_enabled_includes_prepare_mod(self):
        from launcher.gui_progress import _get_visible_phases

        with patch("launcher.gui_progress.ConfigManager") as mock_cm:
            instance = mock_cm.return_value
            def _mock_get(key, default):
                if key == "launcher.work.update":
                    return "LM-G"
                if key == "launcher.work.cdn_optimize":
                    return True
                if key == "launcher.work.mod":
                    return True
                return default
            instance.get.side_effect = _mock_get
            result = _get_visible_phases()

        assert PHASE_PREPARE_MOD in result
        assert result.index(PHASE_PREPARE_MOD) > result.index(PHASE_CDN)
        assert result.index(PHASE_PREPARE_MOD) < result.index(PHASE_LAUNCH)

    def test_resource_update_enabled_includes_phase(self):
        from launcher.gui_progress import _get_visible_phases

        with patch("launcher.gui_progress.ConfigManager") as mock_cm:
            instance = mock_cm.return_value
            def _mock_get(key, default):
                if key == "launcher.work.update":
                    return "LM-G"
                if key == "launcher.work.cdn_optimize":
                    return True
                if key == "launcher.resource_update.enabled":
                    return True
                return default
            instance.get.side_effect = _mock_get
            result = _get_visible_phases()

        assert PHASE_RESOURCE_UPDATE in result
        assert result.index(PHASE_RESOURCE_UPDATE) > result.index(PHASE_CHECK_UPDATE)
        assert result.index(PHASE_RESOURCE_UPDATE) > result.index(PHASE_CDN)

    def test_resource_update_disabled_excludes_phase(self):
        from launcher.gui_progress import _get_visible_phases

        with patch("launcher.gui_progress.ConfigManager") as mock_cm:
            instance = mock_cm.return_value
            def _mock_get(key, default):
                if key == "launcher.work.update":
                    return "LM-G"
                return default
            instance.get.side_effect = _mock_get
            result = _get_visible_phases()

        assert PHASE_RESOURCE_UPDATE not in result

    def test_all_enabled_shows_all_seven(self):
        from launcher.gui_progress import _get_visible_phases

        with patch("launcher.gui_progress.ConfigManager") as mock_cm:
            instance = mock_cm.return_value
            def _mock_get(key, default):
                if key == "launcher.work.update":
                    return "LM-G"
                if key in ("launcher.work.cdn_optimize", "launcher.work.mod"):
                    return True
                if key == "launcher.resource_update.enabled":
                    return True
                return default
            instance.get.side_effect = _mock_get
            result = _get_visible_phases()

        assert len(result) == 7
        assert result == [
            PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN, PHASE_RESOURCE_UPDATE,
            PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING,
        ]

    def test_all_enabled_shows_all_six(self):
        from launcher.gui_progress import _get_visible_phases

        with patch("launcher.gui_progress.ConfigManager") as mock_cm:
            instance = mock_cm.return_value
            def _mock_get(key, default):
                if key == "launcher.work.update":
                    return "LM-G"
                if key in ("launcher.work.cdn_optimize", "launcher.work.mod"):
                    return True
                return default
            instance.get.side_effect = _mock_get
            result = _get_visible_phases()

        assert len(result) == 6
        assert result == [
            PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN,
            PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING,
        ]


class TestVisiblePhaseShowPhase:
    def test_hidden_phase_skips_ui_updates(self, mock_safe_window):
        mock_safe_window._visible_phases = [PHASE_INIT, PHASE_LAUNCH, PHASE_RUNNING]

        mock_safe_window._show_phase(PHASE_CDN)

        assert mock_safe_window._current_phase == PHASE_CDN
        init_lbl = mock_safe_window._phase_labels[PHASE_INIT]
        assert "\u25cb" in init_lbl.Text

    def test_visible_phase_updates_labels(self, mock_safe_window):
        mock_safe_window._visible_phases = [PHASE_INIT, PHASE_LAUNCH, PHASE_RUNNING]

        mock_safe_window._show_phase(PHASE_LAUNCH)

        init_lbl = mock_safe_window._phase_labels[PHASE_INIT]
        assert "\u2713" in init_lbl.Text
        launch_lbl = mock_safe_window._phase_labels[PHASE_LAUNCH]
        assert "\u25cf" in launch_lbl.Text

    def test_hidden_phase_does_not_update_hidden_label(self, mock_safe_window):
        mock_safe_window._visible_phases = [PHASE_INIT, PHASE_LAUNCH, PHASE_RUNNING]

        mock_safe_window._show_phase(PHASE_LAUNCH)

        cdn_lbl = mock_safe_window._phase_labels[PHASE_CDN]
        assert "\u25cb" in cdn_lbl.Text


class TestVisiblePhaseGameRunning:
    def test_marks_only_visible_phases_complete(self, mock_safe_window):
        mock_safe_window._visible_phases = [PHASE_INIT, PHASE_LAUNCH, PHASE_RUNNING]

        mock_safe_window._show_game_running()

        for ph in [PHASE_INIT, PHASE_LAUNCH]:
            lbl = mock_safe_window._phase_labels[ph]
            assert "\u2713" in lbl.Text
        running_lbl = mock_safe_window._phase_labels[PHASE_RUNNING]
        assert "\u25cf" in running_lbl.Text

    def test_hidden_phases_not_touched(self, mock_safe_window):
        mock_safe_window._visible_phases = [PHASE_INIT, PHASE_LAUNCH, PHASE_RUNNING]

        mock_safe_window._show_game_running()

        for ph in [PHASE_CHECK_UPDATE, PHASE_CDN, PHASE_PREPARE_MOD]:
            lbl = mock_safe_window._phase_labels[ph]
            assert "\u25cb" in lbl.Text


# ═══════════════════════════════════════════════════════════════════
# webui/app.py LCTA_API 修复回归测试
# ═══════════════════════════════════════════════════════════════════

class _EventHolder:
    """模拟 pywebview 事件对象，支持 += 注册处理器。"""

    def __init__(self):
        self._handlers = []

    def __iadd__(self, handler):
        self._handlers.append(handler)
        return self


def _make_api():
    from webui.app import LCTA_API

    api = object.__new__(LCTA_API)
    api._window = MagicMock()
    api.log = MagicMock()
    api.log_error = MagicMock()
    api.log_manager = MagicMock()
    return api


class TestModalJsEscaping:
    """JS 字符串拼接转义：含反斜杠/单引号的文本必须生成合法 JS 字面量。"""

    def test_log_ui_escapes_backslash_and_quote(self):
        api = _make_api()
        api.log_ui(r"C:\tmp\new it's")
        js = api._window.run_js.call_args[0][0]
        assert js.startswith("addLogMessage(")
        assert r"C:\\tmp\\new it's" in js

    def test_log_ui_trailing_backslash_keeps_string_closed(self):
        api = _make_api()
        api.log_ui("path\\to\\")
        js = api._window.run_js.call_args[0][0]
        assert js.rstrip().endswith(");")

    def test_add_modal_log_escapes_path(self):
        api = _make_api()
        api.add_modal_log(r"解压到 C:\tmp\mods", "m1")
        js = api._window.evaluate_js.call_args[0][0]
        assert 'modalWindows.find(m => m.id === "m1")' in js
        assert r"C:\\tmp\\mods" in js

    def test_add_modal_log_false_routes_to_log_ui_raw(self):
        api = _make_api()
        api.log_ui = MagicMock()
        api.add_modal_log(r"C:\tmp\note", "false")
        api.log_ui.assert_called_once_with(r"C:\tmp\note")

    def test_set_modal_status_escapes(self):
        api = _make_api()
        api.set_modal_status("done\n已'完成'", "m2")
        js = api._window.evaluate_js.call_args[0][0]
        assert 'modal.setStatus("done\\n已\'完成\'")' in js

    def test_update_modal_progress_escapes(self):
        api = _make_api()
        api.update_modal_progress(42, r"进度 C:\dir", "m3")
        js = api._window.evaluate_js.call_args[0][0]
        assert 'modal.updateProgress(42, "进度 C:\\\\dir")' in js


class TestBrowseDialogs:
    """browse_file/browse_folder 的 JS 注入与空 input_id 防御。"""

    def _set_picked(self, api, picked):
        api._window.create_file_dialog.return_value = [picked]
        api.log_ui = MagicMock()

    def test_browse_file_empty_input_id_returns_path_without_js(self):
        api = _make_api()
        self._set_picked(api, r"C:\O'Brien\update.zip")
        result = api.browse_file("")
        assert result == r"C:\O'Brien\update.zip"
        api._window.run_js.assert_not_called()

    def test_browse_file_injects_json_quoted_path(self):
        api = _make_api()
        self._set_picked(api, r"C:\O'Brien\file.txt")
        api.browse_file("input-id")
        js = api._window.run_js.call_args[0][0]
        assert js.startswith('document.getElementById("input-id").value =')
        assert r"O'Brien" in js

    def test_browse_folder_empty_input_id_returns_path_without_js(self):
        api = _make_api()
        self._set_picked(api, r"C:\tmp\dir")
        result = api.browse_folder("")
        assert result == r"C:\tmp\dir"
        api._window.run_js.assert_not_called()

    def test_browse_cancelled_returns_none(self):
        api = _make_api()
        api._window.create_file_dialog.return_value = None
        assert api.browse_file("x") is None
        assert api.browse_folder("x") is None


class TestCleanCache:
    """clean_cache 可变默认参数修复：custom_files 不得跨调用累积。"""

    @patch("webui.app_api.packages.clean_config_main")
    def test_custom_files_not_shared_across_calls(self, mock_clean):
        api = _make_api()
        api.add_modal_log = MagicMock()
        api.clean_cache(modal_id="m", clean_mods=True)
        api.clean_cache(modal_id="m", clean_mods=True)
        assert mock_clean.call_count == 2
        first = mock_clean.call_args_list[0].kwargs["custom_files"]
        second = mock_clean.call_args_list[1].kwargs["custom_files"]
        assert len(first) == 1
        assert len(second) == 1
        assert first is not second

    @patch("webui.app_api.packages.clean_config_main")
    def test_clean_cache_no_mods_passes_empty_list(self, mock_clean):
        api = _make_api()
        api.add_modal_log = MagicMock()
        api.clean_cache(modal_id="m", clean_mods=False)
        assert mock_clean.call_args.kwargs["custom_files"] == []


class TestMoveFolders:
    """move_folders 盘符提取：UNC 不截断、无字母目录名不崩溃。"""

    @patch("webui.app_api.packages.ctypes.windll.user32", create=True)
    @patch("webui.app_api.packages._move_folders")
    def test_drive_paths_preserved_and_no_letter_dir_safe(self, mock_move, fake_user32):
        import tempfile

        fake_user32.FindWindowW.return_value = 0
        api = _make_api()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sub1").mkdir()
            (Path(tmp) / "123").mkdir()
            api.move_folders(tmp, r"C:\dst")
        sources = mock_move.call_args.args[0]
        assert len(sources) == 2
        assert all(os.path.isabs(s) for s in sources)
        assert mock_move.call_args.args[1] == r"C:\dst"

    @patch("webui.app_api.packages.ctypes.windll.user32", create=True)
    @patch("webui.app_api.packages._move_folders")
    def test_unc_paths_not_truncated(self, mock_move, fake_user32):
        import webui.app_api.packages as app_mod

        fake_user32.FindWindowW.return_value = 0
        real_path = Path
        unc_children = [r"\\server\share\base\mods", r"\\server\share\base\123"]

        class _FakePath:
            def iterdir(self):
                return iter(unc_children)

        with patch.object(app_mod, "Path",
                          side_effect=lambda p: _FakePath() if p == r"\\server\share\base" else real_path(p)):
            api = _make_api()
            api.move_folders(r"\\server\share\base", r"C:\dst")
        sources = mock_move.call_args.args[0]
        assert sources == unc_children


class TestUpdateConfigBatch:
    """update_config_batch 应一次批量写入，避免逐项全量写盘。"""

    @patch("webui.app_api.config.ConfigManager")
    def test_uses_set_batch_once(self, mock_cm):
        api = _make_api()
        instance = mock_cm.return_value
        instance.set_batch.return_value = 3
        updates = {"a.b": 1, "c": 2, "d.e": 3}
        result = api.update_config_batch(updates)
        instance.set_batch.assert_called_once_with(updates)
        instance.set.assert_not_called()
        assert result == {"success": True, "updated": 3, "total": 3}

    @patch("webui.app_api.config.ConfigManager")
    def test_empty_updates_skip_write(self, mock_cm):
        api = _make_api()
        result = api.update_config_batch({})
        mock_cm.return_value.set_batch.assert_not_called()
        assert result == {"success": True, "updated": 0, "total": 0}


class TestCheckShow:
    """check_show 版本号归一化：'v5.0.1' 与 '5.0.1' 视为相同，避免首启误弹。"""

    @patch("webui.app_api.core.ConfigManager")
    @patch.dict(os.environ, {"__version__": "5.0.1"}, clear=False)
    def test_v_prefixed_last_version_does_not_show_update(self, mock_cm):
        api = _make_api()
        instance = mock_cm.return_value
        instance.get.return_value = "v5.0.1"
        result = api.check_show()
        assert result == {"show": False}
        instance.set.assert_not_called()

    @patch("webui.app_api.core.ConfigManager")
    @patch.dict(os.environ, {"__version__": "5.0.1"}, clear=False)
    def test_older_version_shows_update(self, mock_cm):
        api = _make_api()
        instance = mock_cm.return_value
        instance.get.return_value = "v4.9.0"
        result = api.check_show()
        assert result["show"] is True
        instance.set.assert_called_once_with("last_version", "5.0.1")


class TestFirstUse:
    """init_config 的 first_use 判定：config.json 不在磁盘（回退默认配置）时视为首次使用。"""

    def _patch_cm(self, from_disk, raw):
        from webui.app_api import core as core_mod

        p_from_disk = patch.object(
            core_mod.ConfigManager, "from_disk", new_callable=PropertyMock
        )
        p_raw = patch.object(
            core_mod.ConfigManager, "raw", new_callable=PropertyMock
        )
        p_use_default = patch.object(core_mod.ConfigManager, "use_default")
        p_validate = patch.object(
            core_mod.ConfigManager, "validate", return_value=(True, [])
        )
        p_get = patch.object(core_mod.ConfigManager, "get", return_value=False)
        m_from_disk = p_from_disk.start()
        m_raw = p_raw.start()
        m_use_default = p_use_default.start()
        p_validate.start()
        p_get.start()
        m_from_disk.return_value = from_disk
        m_raw.return_value = raw
        return _make_api(), m_use_default, (
            p_from_disk, p_raw, p_use_default, p_validate, p_get,
        )

    def test_first_use_true_when_config_missing(self):
        api, m_use_default, patches = self._patch_cm(False, {"debug": False})
        try:
            api.init_config()
            assert api.first_use is True
            m_use_default.assert_called_once()
        finally:
            for p in patches:
                p.stop()

    def test_first_use_false_when_config_exists(self):
        api, m_use_default, patches = self._patch_cm(True, {"debug": False})
        try:
            api.init_config()
            assert api.first_use is False
            m_use_default.assert_not_called()
        finally:
            for p in patches:
                p.stop()


class TestEditorWindowsCleanup:
    """编辑器窗口 closed 后应从句柄列表移除。"""

    def _open_rule_editor(self, api, window):
        import webui.app_api.fancy as app_mod

        with patch.object(app_mod.webview, "create_window", return_value=window), \
             patch.object(app_mod.ConfigManager, "get", return_value="light"), \
             patch.dict(os.environ, {"path_": str(Path(__file__).parent.parent)}, clear=False):
            api.open_rule_editor()
        return window.events.closed._handlers

    def test_rule_editor_window_removed_on_closed(self):
        from webui.app import LCTA_API

        api = _make_api()
        window = MagicMock()
        window.events.closed = _EventHolder()
        self._open_rule_editor(api, window)
        assert api._rule_editor_windows == [window]
        self._open_rule_editor(api, MagicMock(events=MagicMock(closed=_EventHolder())))
        assert len(api._rule_editor_windows) == 2
        handlers = window.events.closed._handlers
        assert handlers
        handlers[0]()
        assert len(api._rule_editor_windows) == 1

    def test_quick_editor_window_removed_on_closed(self):
        api = _make_api()
        window = MagicMock()
        window.events.closed = _EventHolder()
        import webui.app_api.windows as app_mod

        with patch.object(app_mod.webview, "create_window", return_value=window), \
             patch.object(app_mod.ConfigManager, "get", return_value="light"), \
             patch.dict(os.environ, {"path_": str(Path(__file__).parent.parent)}, clear=False):
            api.open_quick_editor()
        assert api._quick_editor_windows == [window]
        window.events.closed._handlers[0]()
        assert api._quick_editor_windows == []

    def test_sync_theme_skips_closed_windows(self):
        api = _make_api()
        window = MagicMock()
        window.events.closed = _EventHolder()
        self._open_rule_editor(api, window)
        window.events.closed._handlers[0]()
        window.evaluate_js.reset_mock()
        api.sync_theme_to_rule_editor("dark")
        window.evaluate_js.assert_not_called()


class TestSaveRulesetExposure:
    """主窗口 LCTA_API 必须暴露 save_ruleset（文本美化 保存当前/保存全部 依赖）。"""

    def test_save_ruleset_is_class_method(self):
        from webui.app import LCTA_API

        assert callable(getattr(LCTA_API, "save_ruleset", None))

    def test_save_ruleset_persists_to_fancy_folder(self, tmp_path, monkeypatch):
        from webutils import function_fancy

        monkeypatch.setattr(function_fancy, "_get_fancy_folder", lambda: tmp_path)
        api = _make_api()
        result = api.save_ruleset(
            "__pytest_save_ruleset__",
            {"name": "__pytest_save_ruleset__", "desc": "测试", "rules": []},
        )
        assert result.get("success") is True
        assert (tmp_path / "__pytest_save_ruleset__.json").exists()
