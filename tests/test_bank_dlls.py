import os

import pytest

from webutils.bank.dlls import (
    DLL_NAMES, FmodDlls, default_dll_candidates, find_dll_dir, missing_dlls,
)
from webutils.bank.errors import BankDllMissingError
from globalManagers.ConfigManager import ConfigManager


def _fake_dir(tmp_path, names=DLL_NAMES):
    d = tmp_path / "dlls"
    d.mkdir()
    for n in names:
        (d / n).write_bytes(b"x")
    return str(d)


def test_missing_dlls(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert missing_dlls(None) == list(DLL_NAMES)
    assert missing_dlls(str(empty)) == list(DLL_NAMES)
    assert missing_dlls(_fake_dir(tmp_path)) == []
    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "fmod64.dll").write_bytes(b"x")
    assert missing_dlls(str(partial)) == ["fsbank64.dll", "libfsbvorbis64.dll"]


def test_find_dll_dir(tmp_path):
    good = _fake_dir(tmp_path)
    assert find_dll_dir([str(tmp_path / "nope"), good]) == good
    assert find_dll_dir(["C:/definitely/missing"]) is None
    assert find_dll_dir([]) is None


def test_default_dll_candidates_uses_env_and_config(tmp_path, monkeypatch):
    cfg_dir = _fake_dir(tmp_path)
    env_dir = str(tmp_path / "env_dir")
    os.makedirs(env_dir)
    monkeypatch.setenv("LCTA_FMOD_DLL_DIR", env_dir)
    monkeypatch.setattr(ConfigManager, "get", lambda self, key, default=None: cfg_dir)
    cands = default_dll_candidates()
    assert cands[0] == cfg_dir
    assert cands[1] == env_dir


def test_fmod_dlls_init_raises_when_missing(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(BankDllMissingError):
        FmodDlls(str(empty))
