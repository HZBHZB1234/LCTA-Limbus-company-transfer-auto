"""launcher/pipeline.py 与 gui_progress.py 单元测试。

由于 gui_progress.py 依赖 clr/pythonnet + WinForms，无法在无桌面环境的 CI 中
直接创建控件，故采用 mock _safe_invoke 同/异步调度 + mock WinForms 部件的方式
验证窗口逻辑。
"""

import logging
import threading
from unittest.mock import MagicMock, patch

import pytest

from launcher.pipeline import (
    LaunchPipeline,
    PHASE_INIT,
    PHASE_CHECK_UPDATE,
    PHASE_CDN,
    PHASE_PREPARE_MOD,
    PHASE_LAUNCH,
    PHASE_RUNNING,
    PHASE_EXIT,
)


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
            PHASE_INIT, PHASE_CHECK_UPDATE, PHASE_CDN,
            PHASE_PREPARE_MOD, PHASE_LAUNCH, PHASE_RUNNING, PHASE_EXIT,
        ]
        assert len(set(phases)) == 7
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
    w._progress_bar = MagicMock()
    w._progress_bar.IsDisposed = False
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
        w._phase_labels[ph] = lbl

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
        assert "终止游戏进程" in msg

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
