"""launcher/crash_export.py：游戏异常退出日志导出测试"""
import zipfile
from pathlib import Path

import pytest

from launcher import crash_export


@pytest.fixture(autouse=True, scope="module")
def _restore_global_log_state():
    """crash_export 导入时会实例化 LogManager 单例并把 LCTA logger 设为
    propagate=False，破坏后续测试模块的 caplog 捕获，模块结束后还原。"""
    yield
    import logging
    from globalManagers.LogManager import LogManager
    LogManager._instance = None
    LogManager._initialized = False
    logging.getLogger("LCTA").propagate = True


@pytest.fixture(autouse=True)
def _no_explorer(monkeypatch):
    """测试中不真正打开资源管理器。"""
    monkeypatch.setattr(crash_export, "_open_in_explorer", lambda path: None)


@pytest.fixture(autouse=True)
def dirs(tmp_path, monkeypatch):
    """把日志目录指到临时目录，避免读真实用户日志。"""
    game_dir = tmp_path / "LocalLow" / "ProjectMoon" / "LimbusCompany"
    crash_dir = tmp_path / "Temp" / "ProjectMoon" / "LimbusCompany" / "Crashes"
    launcher_log_dir = tmp_path / "logs"
    game_dir.mkdir(parents=True)
    crash_dir.mkdir(parents=True)
    launcher_log_dir.mkdir(parents=True)
    monkeypatch.setattr(crash_export, "GAME_LOG_DIR", game_dir)
    monkeypatch.setattr(crash_export, "CRASH_DIR", crash_dir)
    monkeypatch.setattr(crash_export, "LAUNCHER_LOG_DIR", launcher_log_dir)
    return {
        "game_dir": game_dir,
        "crash_dir": crash_dir,
        "launcher_log_dir": launcher_log_dir,
    }


class _FakeConfigManager:
    """内存版 ConfigManager 替身，避免测试读写真实用户配置。"""

    def __init__(self):
        self.store = {}
        self.writes = []

    def get(self, key_path, default=None):
        return self.store.get(key_path, default)

    def set(self, key_path, value, auto_save=True):
        self.store[key_path] = value
        self.writes.append((key_path, value))


@pytest.fixture(autouse=True)
def fake_cm(monkeypatch):
    """把 crash_export 内的 ConfigManager 换成内存替身（忽略退出码功能）。"""
    cm = _FakeConfigManager()
    monkeypatch.setattr(crash_export, "ConfigManager", lambda: cm)
    return cm


def _make_logs(dirs):
    (dirs["game_dir"] / crash_export.LOG_FILE_NAME).write_text("player log line\n", encoding="utf-8", newline="")
    (dirs["game_dir"] / crash_export.PREV_LOG_FILE_NAME).write_text("prev log\n", encoding="utf-8", newline="")


def _make_launcher_log(dirs, text="launcher log line\n"):
    path = dirs["launcher_log_dir"] / crash_export.LAUNCHER_LOG_FILE_NAME
    path.write_text(text, encoding="utf-8", newline="")
    return path


def test_is_abnormal_exit():
    class _P:
        pass
    proc = _P()
    assert crash_export.is_abnormal_exit(1, proc) is True
    assert crash_export.is_abnormal_exit(0, proc) is False
    assert crash_export.is_abnormal_exit(1, None) is False
    class _Cancel:
        def is_set(self):
            return True
    assert crash_export.is_abnormal_exit(1, proc, _Cancel()) is False


class TestIgnoredExitCodes:
    """「忽略此种异常退出码」：解析、写入与 is_abnormal_exit 联动。"""

    def test_default_empty_means_no_ignored(self, fake_cm):
        assert crash_export.get_ignored_exit_codes() == []
        class _P:
            pass
        assert crash_export.is_abnormal_exit(-1073741819, _P()) is True

    def test_ignored_code_not_abnormal(self, fake_cm):
        fake_cm.store[crash_export.IGNORED_CODES_CONFIG_KEY] = "-1073741819,1"
        class _P:
            pass
        proc = _P()
        assert crash_export.is_abnormal_exit(-1073741819, proc) is False
        assert crash_export.is_abnormal_exit(1, proc) is False
        # 忽略列表外的退出码照常视为异常
        assert crash_export.is_abnormal_exit(2, proc) is True

    def test_zero_and_cancelled_bypass_ignore_list(self, fake_cm):
        """退出码 0 与用户取消本来就不算异常，忽略列表不改变其语义。"""
        fake_cm.store[crash_export.IGNORED_CODES_CONFIG_KEY] = "0"
        class _P:
            pass
        class _Cancel:
            def is_set(self):
                return True
        assert crash_export.is_abnormal_exit(0, _P()) is False
        assert crash_export.is_abnormal_exit(0, _P(), _Cancel()) is False

    def test_tolerates_garbage_entries(self, fake_cm):
        """空串/垃圾项/多余逗号跳过，可解析项保留。"""
        fake_cm.store[crash_export.IGNORED_CODES_CONFIG_KEY] = "abc,, 12 ,-3,x"
        assert crash_export.get_ignored_exit_codes() == [12, -3]
        fake_cm.store[crash_export.IGNORED_CODES_CONFIG_KEY] = ""
        assert crash_export.get_ignored_exit_codes() == []

    def test_add_ignored_exit_code_persists_and_dedupes(self, fake_cm):
        assert crash_export.add_ignored_exit_code(-1073741819) is True
        assert crash_export.get_ignored_exit_codes() == [-1073741819]
        assert fake_cm.writes == [
            (crash_export.IGNORED_CODES_CONFIG_KEY, "-1073741819")
        ]
        # 幂等：重复添加不重复写盘
        assert crash_export.add_ignored_exit_code(-1073741819) is False
        assert len(fake_cm.writes) == 1
        # 追加时保留既有条目
        assert crash_export.add_ignored_exit_code(1) is True
        assert crash_export.get_ignored_exit_codes() == [-1073741819, 1]

    def test_is_abnormal_exit_after_add(self, fake_cm):
        class _P:
            pass
        proc = _P()
        assert crash_export.is_abnormal_exit(3221225786, proc) is True
        crash_export.add_ignored_exit_code(3221225786)
        assert crash_export.is_abnormal_exit(3221225786, proc) is False


def test_collect_log_sources(dirs):
    _make_logs(dirs)
    (dirs["crash_dir"] / "nested").mkdir()
    (dirs["crash_dir"] / "nested" / "error.log").write_text("crash\n", encoding="utf-8")
    (dirs["crash_dir"] / "error.log").write_text("crash\n", encoding="utf-8")

    sources = crash_export.collect_log_sources()
    arcs = {arc for _, arc in sources}
    assert arcs == {"Player.log", "Player-prev.log", "Crashes/error.log", "Crashes/nested/error.log"}
    for src, _ in sources:
        assert Path(src).is_file()


def test_collect_log_sources_empty(dirs):
    assert crash_export.collect_log_sources() == []


class TestLauncherLogSources:
    """启动器自身日志（logs/app.log）纳入导出。"""

    def test_collect_launcher_log_sources(self, dirs):
        path = _make_launcher_log(dirs)
        sources = crash_export.collect_launcher_log_sources()
        assert sources == [(str(path), "LauncherLogs/app.log")]

    def test_collect_launcher_log_sources_empty(self, dirs):
        """app.log 不存在时不产出来源（不阻塞导出其余内容）。"""
        assert crash_export.collect_launcher_log_sources() == []

    def test_rotation_backups_are_not_collected(self, dirs):
        """只收当前 app.log：轮转备份（app.log.2026-01-01 等）不纳入。"""
        _make_launcher_log(dirs, text="current\n")
        (dirs["launcher_log_dir"] / "app.log.2026-01-01").write_text(
            "rotated\n", encoding="utf-8"
        )
        arcs = {arc for _, arc in crash_export.collect_launcher_log_sources()}
        assert arcs == {"LauncherLogs/app.log"}

    def test_combined_sources_include_launcher_log(self, dirs):
        """默认收集时启动器日志与游戏日志同时出现在来源里。"""
        _make_logs(dirs)
        _make_launcher_log(dirs)
        arcs = {arc for _, arc in crash_export.collect_log_sources()}
        assert arcs == {
            "Player.log", "Player-prev.log", "LauncherLogs/app.log"
        }

    def test_opt_out_excludes_launcher_log(self, dirs):
        """include_launcher_logs=False 时行为与改动前一致。"""
        _make_logs(dirs)
        _make_launcher_log(dirs)
        arcs = {
            arc for _, arc in crash_export.collect_log_sources(
                include_launcher_logs=False
            )
        }
        assert arcs == {"Player.log", "Player-prev.log"}

    def test_export_zip_contains_launcher_log(self, dirs, tmp_path):
        _make_logs(dirs)
        _make_launcher_log(dirs, text="launcher line\n")
        out_dir = tmp_path / "out"
        result = crash_export.export_game_logs(output_dir=str(out_dir))
        assert result is not None
        with zipfile.ZipFile(result) as zf:
            names = set(zf.namelist())
            assert "LauncherLogs/app.log" in names
            assert names == {
                "Player.log", "Player-prev.log", "LauncherLogs/app.log"
            }
            assert zf.read("LauncherLogs/app.log") == b"launcher line\n"

    def test_export_launcher_log_only(self, dirs, tmp_path):
        """游戏侧日志全部缺失时，仅启动器日志也应能成功导出。"""
        _make_launcher_log(dirs)
        out_dir = tmp_path / "out"
        result = crash_export.export_game_logs(output_dir=str(out_dir))
        assert result is not None
        with zipfile.ZipFile(result) as zf:
            assert set(zf.namelist()) == {"LauncherLogs/app.log"}

    def test_export_tolerates_launcher_log_failure(self, dirs, tmp_path, monkeypatch):
        """app.log 读取失败（被占用/损坏）只跳过该文件，游戏日志照常导出。"""
        _make_logs(dirs)
        _make_launcher_log(dirs)
        out_dir = tmp_path / "out"

        real_write = zipfile.ZipFile.write

        def fake_write(self, filename, arcname=None, compress_type=None, compresslevel=None):
            if arcname == "LauncherLogs/app.log":
                raise OSError("file locked")
            return real_write(self, filename, arcname, compress_type, compresslevel)

        monkeypatch.setattr(zipfile.ZipFile, "write", fake_write)
        result = crash_export.export_game_logs(output_dir=str(out_dir))
        assert result is not None
        with zipfile.ZipFile(result) as zf:
            names = set(zf.namelist())
            assert names == {"Player.log", "Player-prev.log"}


def test_export_game_logs_creates_zip(dirs, tmp_path):
    _make_logs(dirs)
    (dirs["crash_dir"] / "error.log").write_text("crash\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    result = crash_export.export_game_logs(output_dir=str(out_dir))
    assert result is not None
    result_path = Path(result)
    assert result_path.parent == out_dir
    assert result_path.name.startswith("LCTA_游戏日志导出_")
    with zipfile.ZipFile(result) as zf:
        assert set(zf.namelist()) == {
            "Player.log", "Player-prev.log", "Crashes/error.log"
        }
        assert zf.read("Player.log") == b"player log line\n"


def test_export_game_logs_nothing_to_export(dirs, tmp_path):
    out_dir = tmp_path / "out"
    assert crash_export.export_game_logs(output_dir=str(out_dir)) is None
    assert not out_dir.exists()


def test_export_game_logs_default_downloads_dir(dirs, tmp_path, monkeypatch):
    _make_logs(dirs)
    downloads = tmp_path / "Downloads"
    monkeypatch.setattr(
        crash_export, "get_downloads_dir", lambda: str(downloads)
    )
    result = crash_export.export_game_logs()
    assert result is not None
    assert Path(result).parent == downloads
    with zipfile.ZipFile(result) as zf:
        assert "Player.log" in zf.namelist()


def test_export_tolerates_single_file_failure(dirs, tmp_path, monkeypatch):
    _make_logs(dirs)
    (dirs["crash_dir"] / "error.log").write_text("crash\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    real_write = zipfile.ZipFile.write

    def fake_write(self, filename, arcname=None, compress_type=None, compresslevel=None):
        if arcname == "Crashes/error.log":
            raise OSError("file locked")
        return real_write(self, filename, arcname, compress_type, compresslevel)

    monkeypatch.setattr(zipfile.ZipFile, "write", fake_write)
    result = crash_export.export_game_logs(output_dir=str(out_dir))
    assert result is not None
    with zipfile.ZipFile(result) as zf:
        names = set(zf.namelist())
        assert "Player.log" in names
        assert "Player-prev.log" in names
        assert "Crashes/error.log" not in names


def test_export_zip_failure_returns_none(dirs, tmp_path, monkeypatch):
    _make_logs(dirs)
    out_dir = tmp_path / "out"

    def fake_zip_init(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(zipfile.ZipFile, "__init__", fake_zip_init)
    assert crash_export.export_game_logs(output_dir=str(out_dir)) is None
