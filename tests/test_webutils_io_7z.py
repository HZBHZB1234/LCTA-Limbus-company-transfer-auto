"""webutils/utils/io.py 的 7z 自动获取逻辑测试

覆盖：
- 环境已有 7z（PATH/已下载缓存/系统安装路径）时不触发下载
- 环境无 7z 时自动从官网下载到 code 目录 tools/7z/7zr.exe
- 幂等：已存在时不会重复下载
- 下载失败 / 文件损坏（过小、非 MZ 头）时清理并报错，解压返回 False
"""
from pathlib import Path

import pytest

import webutils.utils.io as io_mod


def _make_7zr(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ" + b"\x00" * (600 * 1024))


@pytest.fixture
def fake_download(monkeypatch):
    """拦截 download_with：写入一个有效大小的 MZ 文件并记录调用。"""
    calls = []

    def _download(url, save_path, *args, **kwargs):
        calls.append((url, str(save_path)))
        _make_7zr(Path(save_path))
        return True

    monkeypatch.setattr(io_mod, "download_with", _download)
    return calls


@pytest.fixture
def force_download_branch(monkeypatch):
    """屏蔽 PATH 与系统安装路径，强制走自动下载分支（真实文件系统）。"""
    monkeypatch.setattr(io_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(io_mod, "_SYSTEM_7Z_PATHS", ())


def test_system_7z_avoids_download(monkeypatch, fake_download):
    """系统 PATH 存在 7z 时，不触发自动下载。"""
    monkeypatch.setattr(io_mod.shutil, "which", lambda name: "C:/system/7z.exe")

    assert io_mod._find_7z_exe() == "C:/system/7z.exe"
    assert fake_download == []


def test_cached_7z_avoids_download(tmp_path, monkeypatch, fake_download):
    """已下载的 tools/7z/7zr.exe 存在时直接复用，不重复下载。"""
    exe = tmp_path / "tools" / "7z" / "7zr.exe"
    _make_7zr(exe)
    monkeypatch.setenv("path_", str(tmp_path))
    monkeypatch.setattr(io_mod.shutil, "which", lambda name: None)

    assert io_mod._find_7z_exe() == str(exe)
    assert fake_download == []


def test_auto_download_to_code_dir(tmp_path, monkeypatch, fake_download,
                                   force_download_branch):
    """环境无 7z 时自动下载 7zr.exe 到 code 目录 tools/7z/ 并返回路径。"""
    monkeypatch.setenv("path_", str(tmp_path))

    exe = io_mod._find_7z_exe()

    assert exe == str(tmp_path / "tools" / "7z" / "7zr.exe")
    assert (tmp_path / "tools" / "7z" / "7zr.exe").exists()
    assert fake_download == [(io_mod._7ZR_DOWNLOAD_URL, exe)]


def test_ensure_7z_idempotent(tmp_path, monkeypatch, fake_download):
    """已下载成功后再次调用不会重复下载。"""
    monkeypatch.setenv("path_", str(tmp_path))

    first = io_mod._ensure_7z_exe()
    second = io_mod._ensure_7z_exe()

    assert first == second
    assert len(fake_download) == 1


def test_download_failure_raises(tmp_path, monkeypatch):
    """下载失败时清理残留文件并抛出 FileNotFoundError。"""
    monkeypatch.setenv("path_", str(tmp_path))
    monkeypatch.setattr(io_mod, "download_with", lambda *a, **k: False)

    with pytest.raises(FileNotFoundError):
        io_mod._ensure_7z_exe()
    assert not (tmp_path / "tools" / "7z" / "7zr.exe").exists()


@pytest.mark.parametrize("header,payload,min_size", [
    (b"MZ", 100, 600 * 1024),          # 大小不足
    (b"XX", 600 * 1024, 100),          # 非有效 PE 头
], ids=["too-small", "bad-header"])
def test_download_invalid_file_cleaned_up(tmp_path, monkeypatch,
                                          header, payload, min_size):
    """下载结果过小或非 MZ 头时清理文件并抛出 FileNotFoundError。"""
    monkeypatch.setenv("path_", str(tmp_path))
    monkeypatch.setattr(io_mod, "_7Z_MIN_SIZE", min_size)

    def _bad(url, save_path, *args, **kwargs):
        Path(save_path).write_bytes(header + b"\x00" * payload)
        return True

    monkeypatch.setattr(io_mod, "download_with", _bad)

    with pytest.raises(FileNotFoundError):
        io_mod._ensure_7z_exe()
    assert not (tmp_path / "tools" / "7z" / "7zr.exe").exists()


def test_extract_7z_returns_false_when_download_fails(tmp_path, monkeypatch,
                                                      force_download_branch):
    """解压时自动下载失败，_extract_7z 返回 False（提示后返回失败）。"""
    archive = tmp_path / "pkg.7z"
    archive.write_bytes(b"7z archive placeholder")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)

    monkeypatch.setenv("path_", str(tmp_path))
    monkeypatch.setattr(io_mod, "download_with", lambda *a, **k: False)

    assert io_mod._extract_7z(str(archive), str(out)) is False
