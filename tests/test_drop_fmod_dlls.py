import zipfile

from webutils.drop.context import FileExecutionContext
from webutils.drop.handlers import REGISTRY
from webutils.drop.handlers.fmod_dlls import FmodDllZipHandler


def _make_zip(tmp_path):
    zpath = tmp_path / "工具.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("fmodbank.py", "# tool")
        z.writestr("rebank.py", "# tool")
        for dll in ("fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll"):
            z.writestr(dll, b"dll")
        z.writestr("使用说明.txt", "readme")
    return str(zpath)


def test_detect(tmp_path, monkeypatch):
    h = FmodDllZipHandler()
    zpath = _make_zip(tmp_path)
    assert h.detect(zpath) == "fmod_dlls"
    assert h.detect(str(tmp_path / "other.zip")) is None
    assert REGISTRY.detect("zip", zpath) == "fmod_dlls"


def test_execute(tmp_path, monkeypatch):
    zpath = _make_zip(tmp_path)
    dest = tmp_path / "imported"
    monkeypatch.setattr("webutils.drop.handlers.fmod_dlls.default_dll_dir",
                        lambda: str(dest))
    writes = []
    monkeypatch.setattr("webutils.drop.handlers.fmod_dlls.ConfigManager.set",
                        lambda self, key, value, **kw: writes.append((key, value)))
    ctx = FileExecutionContext(file_path=zpath, file_type="fmod_dlls", modal_id="0",
                               index=0, total=1, game_path="", mod_path=str(tmp_path))
    h = FmodDllZipHandler()
    result = h.execute(ctx)
    assert result == "imported"
    assert writes == [("ui_default.bank.dll_dir", str(dest))]
    for dll in ("fmod64.dll", "fsbank64.dll", "libfsbvorbis64.dll"):
        assert (dest / dll).read_bytes() == b"dll"


def test_rebank_detect_and_execute(tmp_path):
    from webutils.drop.handlers.copy_mod import RebankHandler

    h = RebankHandler()
    assert h.detect("a.rebank") == "rebank"
    assert h.detect("a.REBANK") == "rebank"
    assert h.detect("a.bank") is None
    assert REGISTRY.detect("path", "a.rebank") == "rebank"

    mod_path = tmp_path / "mods"
    mod_path.mkdir()
    src = tmp_path / "mod.rebank"
    src.write_bytes(b"rebankdata")
    ctx = FileExecutionContext(file_path=str(src), file_type="rebank", modal_id="0",
                               index=0, total=1, game_path="", mod_path=str(mod_path))
    assert h.execute(ctx) == "modded"
    assert (mod_path / "mod.rebank").read_bytes() == b"rebankdata"
