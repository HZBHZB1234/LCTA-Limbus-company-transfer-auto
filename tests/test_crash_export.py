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
    game_dir.mkdir(parents=True)
    crash_dir.mkdir(parents=True)
    monkeypatch.setattr(crash_export, "GAME_LOG_DIR", game_dir)
    monkeypatch.setattr(crash_export, "CRASH_DIR", crash_dir)
    return {"game_dir": game_dir, "crash_dir": crash_dir}


def _make_logs(dirs):
    (dirs["game_dir"] / crash_export.LOG_FILE_NAME).write_text("player log line\n", encoding="utf-8", newline="")
    (dirs["game_dir"] / crash_export.PREV_LOG_FILE_NAME).write_text("prev log\n", encoding="utf-8", newline="")


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
