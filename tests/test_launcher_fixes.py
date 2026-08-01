"""launcher 修复回归测试：shlex 路径解析、wait_for_validation 超时、退出等待。"""

import os
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class _FakeLogManager:
    def log(self, msg, *args):
        pass

    def log_error(self, e):
        pass


@pytest.fixture(autouse=True, scope="module")
def _restore_global_log_state():
    """launcher.sound/changes 导入时会实例化 LogManager 单例并把 LCTA logger
    设为 propagate=False，破坏后续测试模块的 caplog 捕获，模块结束后还原。"""
    yield
    import logging
    from globalManagers.LogManager import LogManager
    LogManager._instance = None
    LogManager._initialized = False
    logging.getLogger("LCTA").propagate = True


# ═══════════════════════════════════════════════════════════════════
# Bug 2: extract_exe_path（Windows 命令行解析，替代 shlex.split）
# ═══════════════════════════════════════════════════════════════════

class TestExtractExePath:
    def test_quoted_path_with_spaces(self):
        from launcher.changes import extract_exe_path
        cmdline = r'"C:\SteamLibrary\steamapps\common\Limbus Company\LimbusCompany.exe" -arg'
        assert extract_exe_path(cmdline) == r'C:\SteamLibrary\steamapps\common\Limbus Company\LimbusCompany.exe'

    def test_unquoted_path_preserves_backslashes(self):
        from launcher.changes import extract_exe_path
        cmdline = r'D:\Games\Limbus\LimbusCompany.exe -arg'
        assert extract_exe_path(cmdline) == r'D:\Games\Limbus\LimbusCompany.exe'

    def test_quoted_path_without_args(self):
        from launcher.changes import extract_exe_path
        cmdline = r'"D:\Games\Limbus Company\LimbusCompany.exe"'
        assert extract_exe_path(cmdline) == r'D:\Games\Limbus Company\LimbusCompany.exe'

    def test_empty_and_blank(self):
        from launcher.changes import extract_exe_path
        assert extract_exe_path("") == ""
        assert extract_exe_path("   ") == ""

    def test_surrounding_whitespace(self):
        from launcher.changes import extract_exe_path
        cmdline = '  "C:\\Games\\Limbus Company\\LimbusCompany.exe"  -x  '
        assert extract_exe_path(cmdline) == r'C:\Games\Limbus Company\LimbusCompany.exe'


# ═══════════════════════════════════════════════════════════════════
# Bug 1: wait_for_validation 超时 + 备份恢复
# ═══════════════════════════════════════════════════════════════════

class TestWaitForValidation:
    def test_no_bank_files_returns_immediately(self, tmp_path, monkeypatch):
        import launcher.sound as sound
        monkeypatch.setattr(sound, "sound_data_paths", lambda: iter([]))
        monkeypatch.setattr(sound.time, "sleep", lambda s: None)
        sound.wait_for_validation(timeout=0.05)

    def test_timeout_restores_backup(self, tmp_path, monkeypatch):
        import launcher.sound as sound
        bank = tmp_path / "min.bank"
        original = b"BANK_DATA_123"
        bank.write_bytes(original)
        monkeypatch.setattr(sound, "sound_data_paths", lambda: iter([str(bank)]))
        monkeypatch.setattr(sound.time, "sleep", lambda s: None)

        sound.wait_for_validation(timeout=0.05)

        assert bank.read_bytes() == original

    def test_returns_early_when_file_recreated(self, tmp_path, monkeypatch):
        import launcher.sound as sound
        bank = tmp_path / "min.bank"
        bank.write_bytes(b"ORIGINAL")
        monkeypatch.setattr(sound, "sound_data_paths", lambda: iter([str(bank)]))
        monkeypatch.setattr(sound.time, "sleep", lambda s: None)

        real_remove = os.remove

        def fake_remove(path):
            real_remove(path)
            # 模拟游戏校验重新生成该文件
            Path(path).write_bytes(b"REGENERATED")

        monkeypatch.setattr(sound.os, "remove", fake_remove)

        sound.wait_for_validation(timeout=0.05)

        assert bank.read_bytes() == b"REGENERATED"

    def test_replace_sound_starts_daemon_thread(self, tmp_path, monkeypatch):
        import launcher.sound as sound
        (tmp_path / "x.bank").write_bytes(b"x")
        captured = {}

        def fake_thread(*args, **kwargs):
            captured["daemon"] = kwargs.get("daemon")
            return MagicMock()

        monkeypatch.setattr(sound, "Thread", fake_thread)
        monkeypatch.setattr(sound, "get_mod_folder", lambda: str(tmp_path))
        sound.replace_sound("mod_folder")
        assert captured.get("daemon") is True


# ═══════════════════════════════════════════════════════════════════
# Bug 2: resolve_steam_argv 回退路径（引号包裹空格路径）
# ═══════════════════════════════════════════════════════════════════

class TestResolveSteamArgv:
    def test_env_present_passthrough(self, monkeypatch):
        from launcher.main import resolve_steam_argv
        monkeypatch.setenv("steam_argv", r'"C:\Steam\LimbusCompany.exe" -x')
        monkeypatch.setattr("launcher.main._log_manager", _FakeLogManager())
        assert resolve_steam_argv() == r'"C:\Steam\LimbusCompany.exe" -x'

    def test_fallback_quotes_path_with_spaces(self, monkeypatch):
        from launcher.main import resolve_steam_argv
        monkeypatch.delenv("steam_argv", raising=False)
        monkeypatch.setattr("launcher.main._log_manager", _FakeLogManager())

        class _FakeCM:
            def get(self, key, default=None):
                return "C:\\SteamLibrary\\steamapps\\common\\Limbus Company\\"

        monkeypatch.setattr("launcher.main.ConfigManager", lambda: _FakeCM())
        assert resolve_steam_argv() == r'"C:\SteamLibrary\steamapps\common\Limbus Company\LimbusCompany.exe"'

    def test_fallback_no_spaces_no_quotes(self, monkeypatch):
        from launcher.main import resolve_steam_argv
        monkeypatch.delenv("steam_argv", raising=False)
        monkeypatch.setattr("launcher.main._log_manager", _FakeLogManager())

        class _FakeCM:
            def get(self, key, default=None):
                return "D:\\Games\\Limbus\\"

        monkeypatch.setattr("launcher.main.ConfigManager", lambda: _FakeCM())
        assert resolve_steam_argv() == r"D:\Games\Limbus\LimbusCompany.exe"


# ═══════════════════════════════════════════════════════════════════
# Bug 3: 退出等待（游戏已退出立即关闭，否则可配置延迟）
# ═══════════════════════════════════════════════════════════════════

class TestCloseProgressWindow:
    def test_no_progress_returns(self):
        from launcher.main import _close_progress_window
        _close_progress_window(None, MagicMock(), 0, threading.Event())

    def test_game_never_launched_closes_immediately(self, monkeypatch):
        from launcher.main import _close_progress_window
        progress = MagicMock()
        progress.is_alive.return_value = True
        sleeps = []
        monkeypatch.setattr("launcher.main.time.sleep", lambda s: sleeps.append(s))
        _close_progress_window(progress, None, -1, threading.Event())
        progress.close.assert_called_once()
        assert sleeps == []

    def test_game_exited_closes_immediately(self, monkeypatch):
        from launcher.main import _close_progress_window
        progress = MagicMock()
        progress.is_alive.return_value = True
        sleeps = []
        monkeypatch.setattr("launcher.main.time.sleep", lambda s: sleeps.append(s))
        game_process = MagicMock()
        _close_progress_window(progress, game_process, 0, threading.Event())
        progress.close.assert_called_once()
        assert sleeps == []

    def test_cancelled_closes_immediately(self, monkeypatch):
        from launcher.main import _close_progress_window
        progress = MagicMock()
        progress.is_alive.return_value = True
        sleeps = []
        monkeypatch.setattr("launcher.main.time.sleep", lambda s: sleeps.append(s))
        cancel_event = threading.Event()
        cancel_event.set()
        _close_progress_window(progress, MagicMock(), -1, cancel_event)
        progress.close.assert_called_once()
        assert sleeps == []

    def test_ambiguous_case_uses_configured_delay(self, monkeypatch):
        from launcher.main import _close_progress_window
        progress = MagicMock()
        progress.is_alive.return_value = True
        sleeps = []
        monkeypatch.setattr("launcher.main.time.sleep", lambda s: sleeps.append(s))

        class _FakeCM:
            def get(self, key, default=None):
                return 1.5

        monkeypatch.setattr("launcher.main.ConfigManager", lambda: _FakeCM())
        _close_progress_window(progress, MagicMock(), -1, threading.Event())
        progress.close.assert_called_once()
        assert sleeps == [1.5]
