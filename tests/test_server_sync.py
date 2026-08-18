import json
from pathlib import Path

import pytest

import resource_updater.server_sync as server_sync
from resource_updater.server_sync import (
    ServerSync,
    ServerSyncError,
    _s_token_from_settings,
    create_lethe_shortcut,
    get_server_switch_config,
    run_server_sync,
    save_server_switch_options,
)


def make_settings(aa_dir: Path, token: str) -> None:
    settings = {
        "m_CatalogLocations": [
            {
                "m_InternalId": (
                    "https://download.limbuscompanycdn.org/{}/catalog_S1.hash".format(token)
                )
            }
        ]
    }
    (aa_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")


def make_catalog(aa_dir: Path, bundles: list) -> None:
    """构造 catalog.bin：每个 bundle 名后跟外层 32-hex 缓存键，条目间以 \\x00 分隔。"""
    data = b""
    for name in bundles:
        data += name.encode("ascii") + b"\x00" + b"c" * 32 + b"\x00"
    (aa_dir / "catalog.bin").write_bytes(data)


def make_game(tmp_path: Path, name: str, token: str, bundles: list) -> Path:
    game_dir = tmp_path / name
    aa_dir = game_dir / "LimbusCompany_Data" / "StreamingAssets" / "aa"
    aa_dir.mkdir(parents=True)
    make_settings(aa_dir, token)
    make_catalog(aa_dir, bundles)
    (game_dir / "LimbusCompany.exe").write_bytes(b"exe")
    return game_dir


def bundle(name: str, inner: str) -> str:
    return "{}_{}.bundle".format(name, inner)


def test_s_token_from_settings(tmp_path):
    aa = tmp_path / "aa"
    aa.mkdir()
    make_settings(aa, "s20260805_example")
    assert _s_token_from_settings(aa / "settings.json") == "s20260805_example"
    assert _s_token_from_settings(aa / "missing.json") is None


def test_analyze_classifies_shared_and_only(tmp_path):
    inner = "a" * 32
    shared = bundle("s1_shared", inner)
    only_l = bundle("s1_lethe_only", "b" * 32)
    only_o = bundle("s1_official_only", "d" * 32)

    lethe = make_game(tmp_path, "lethe", "s20260801_lethe", [shared, only_l])
    official = make_game(tmp_path, "official", "s20260805_official", [shared, only_o])

    sync = ServerSync(lethe, official, cache_dir=tmp_path / "cache", engine="builtin")
    report = sync.analyze()

    assert report["shared"] == [shared]
    assert report["only_lethe"] == [only_l]
    assert report["only_official"] == [only_o]
    assert report["lethe_token"] == "s20260801_lethe"
    assert report["official_token"] == "s20260805_official"


def test_plan_add_removes_only_differing_bundles(tmp_path):
    inner = "a" * 32
    shared = bundle("s1_shared", inner)
    only_l = bundle("s1_lethe_only", "b" * 32)
    only_o = bundle("s1_official_only", "d" * 32)

    lethe = make_game(tmp_path, "lethe", "s20260801_lethe", [shared, only_l])
    official = make_game(tmp_path, "official", "s20260805_official", [shared, only_o])
    cache = tmp_path / "cache"

    # 缓存中已有共享 + lethe 独有（模拟当前处于 lethe 状态）
    cache.mkdir()
    (cache / ("c" * 32) / inner).mkdir(parents=True)
    (cache / ("c" * 32) / inner / "__data").write_bytes(b"shared")
    (cache / ("c" * 32) / ("b" * 32)).mkdir(parents=True)
    (cache / ("c" * 32) / ("b" * 32) / "__data").write_bytes(b"lethe-only")

    sync = ServerSync(lethe, official, cache_dir=cache, engine="builtin")
    analysis = sync.analyze()
    plan = sync.plan("official", analysis)

    # 切回官服：ADD 官服独有（缺失）、REMOVE lethe 独有（存在）
    assert len(plan["add"]) == 1
    assert plan["add"][0]["name"] == only_o
    assert plan["add"][0]["url"].startswith("https://download.limbuscompanycdn.org/s20260805_official/")
    assert len(plan["remove"]) == 1
    assert plan["remove"][0]["name"] == only_l
    # 共享 bundle 不在任何计划内
    assert all(item["name"] != shared for item in plan["add"])
    assert all(item["name"] != shared for item in plan["remove"])


def test_plan_keep_other_skips_removal(tmp_path):
    inner = "a" * 32
    only_l = bundle("s1_lethe_only", "b" * 32)
    only_o = bundle("s1_official_only", "d" * 32)

    lethe = make_game(tmp_path, "lethe", "s20260801_lethe", [only_l])
    official = make_game(tmp_path, "official", "s20260805_official", [only_o])
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / ("c" * 32) / ("b" * 32)).mkdir(parents=True)
    (cache / ("c" * 32) / ("b" * 32) / "__data").write_bytes(b"lethe-only")

    sync = ServerSync(lethe, official, cache_dir=cache, engine="builtin", keep_other=True)
    analysis = sync.analyze()
    plan = sync.plan("official", analysis)

    assert len(plan["add"]) == 1
    assert len(plan["remove"]) == 0  # keep_other 不移除


def test_run_dry_run_makes_no_changes(tmp_path):
    inner = "a" * 32
    only_l = bundle("s1_lethe_only", "b" * 32)
    only_o = bundle("s1_official_only", "d" * 32)

    lethe = make_game(tmp_path, "lethe", "s20260801_lethe", [only_l])
    official = make_game(tmp_path, "official", "s20260805_official", [only_o])
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / ("c" * 32) / ("b" * 32)).mkdir(parents=True)
    (cache / ("c" * 32) / ("b" * 32) / "__data").write_bytes(b"lethe-only")

    sync = ServerSync(lethe, official, cache_dir=cache, engine="builtin")
    result = sync.run("official", dry_run=True)

    assert result["dry_run"] is True
    assert result["added"] == 0
    assert result["removed"] == 0
    # 未下载官服独有，未移除 lethe 独有
    assert not (cache / ("c" * 32) / ("d" * 32)).exists()
    assert (cache / ("c" * 32) / ("b" * 32) / "__data").read_bytes() == b"lethe-only"


def test_run_adds_and_removes(tmp_path, monkeypatch):
    inner = "a" * 32
    shared = bundle("s1_shared", inner)
    only_l = bundle("s1_lethe_only", "b" * 32)
    only_o = bundle("s1_official_only", "d" * 32)

    lethe = make_game(tmp_path, "lethe", "s20260801_lethe", [shared, only_l])
    official = make_game(tmp_path, "official", "s20260805_official", [shared, only_o])
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / ("c" * 32) / inner).mkdir(parents=True)
    (cache / ("c" * 32) / inner / "__data").write_bytes(b"shared")
    (cache / ("c" * 32) / ("b" * 32)).mkdir(parents=True)
    (cache / ("c" * 32) / ("b" * 32) / "__data").write_bytes(b"lethe-only")

    downloaded = {}

    def fake_http_download(url, destination, include_xrw, cancel_event, progress=None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = b"bundle-content-" + url.encode("ascii")
        destination.write_bytes(content)
        downloaded[destination.name] = content
        if progress:
            progress(1, 1)

    monkeypatch.setattr(server_sync, "http_get", lambda *a, **kw: b"x")
    monkeypatch.setattr(
        "resource_updater.core.http_download", fake_http_download
    )

    sync = ServerSync(lethe, official, cache_dir=cache, engine="builtin")
    result = sync.run("official")

    assert result["added"] == 1
    assert result["removed"] == 1
    assert result["failed"] == 0
    # 官服独有 bundle 已下载进缓存（__data + __info）
    added_entry = cache / ("c" * 32) / ("d" * 32)
    assert (added_entry / "__data").is_file()
    assert (added_entry / "__info").is_file()
    # lethe 独有条目已移除，共享保留
    assert not (cache / ("c" * 32) / ("b" * 32)).exists()
    assert (cache / ("c" * 32) / inner / "__data").read_bytes() == b"shared"


def test_run_builtin_engine_uses_retry(tmp_path, monkeypatch):
    only_o = bundle("s1_official_only", "d" * 32)
    only_l = bundle("s1_lethe_only", "b" * 32)

    lethe = make_game(tmp_path, "lethe", "s20260801_lethe", [only_l])
    official = make_game(tmp_path, "official", "s20260805_official", [only_o])
    cache = tmp_path / "cache"

    def fake_http_download(url, destination, include_xrw, cancel_event, progress=None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"data")
        if progress:
            progress(1, 1)

    monkeypatch.setattr(
        "resource_updater.core.http_download", fake_http_download
    )
    sync = ServerSync(lethe, official, cache_dir=cache, engine="builtin")
    result = sync.run("official")
    assert result["added"] == 1
    assert result["failed"] == 0


def test_validate_raises_on_missing_catalog(tmp_path):
    lethe = tmp_path / "lethe"
    official = tmp_path / "official"
    lethe.mkdir()
    official.mkdir()
    sync = ServerSync(lethe, official, cache_dir=tmp_path / "cache")
    with pytest.raises(ServerSyncError):
        sync.validate()


def test_config_roundtrip(monkeypatch):
    from globalManagers.ConfigManager import ConfigManager
    store = {}

    class FakeConfigManager:
        def get(self, key_path, default=None):
            return store.get(key_path, default)

        def set_batch(self, updates, auto_save=True):
            store.update(updates)
            return len(updates)

    fake = FakeConfigManager()
    monkeypatch.setattr(ConfigManager, "_instance", fake)
    monkeypatch.setattr(ConfigManager, "_initialized", True)

    config = get_server_switch_config()
    assert config["enabled"] is False
    assert config["server"] == "official"
    assert config["lethe_dir"] == ""

    result = save_server_switch_options({
        "enabled": True,
        "server": "lethe",
        "lethe_dir": "E:/lethe",
        "keep_other": True,
        "jobs": 4,
        "engine": "aria2",
    })
    assert result["success"] is True
    config = get_server_switch_config()
    assert config["enabled"] is True
    assert config["server"] == "lethe"
    assert config["lethe_dir"] == "E:/lethe"
    assert config["keep_other"] is True
    assert config["jobs"] == 4


def test_run_server_sync_returns_error_when_dirs_invalid(tmp_path, monkeypatch):
    from globalManagers.ConfigManager import ConfigManager
    monkeypatch.setattr(ConfigManager, "get", lambda self, key, default=None: str(tmp_path))
    result = run_server_sync("official", lethe_dir=tmp_path / "nope")
    assert result["success"] is False


def test_create_shortcut_writes_script(tmp_path, monkeypatch):
    lethe = tmp_path / "lethe"
    lethe.mkdir()
    (lethe / "LimbusCompany.exe").write_bytes(b"exe")
    aa = lethe / "LimbusCompany_Data" / "StreamingAssets" / "aa"
    aa.mkdir(parents=True)
    make_settings(aa, "s20260801_lethe")
    make_catalog(aa, [])

    official = tmp_path / "official"
    official.mkdir()

    work = tmp_path / "work"
    monkeypatch.setattr(server_sync, "default_work_dir", lambda: work)
    monkeypatch.setattr(server_sync, "_desktop_path", lambda: tmp_path / "Desktop")
    monkeypatch.setattr(server_sync, "_create_lnk", lambda *a, **kw: True)
    from globalManagers.ConfigManager import ConfigManager
    monkeypatch.setattr(ConfigManager, "get", lambda self, key, default=None: str(official))

    result = create_lethe_shortcut(lethe)
    assert result["success"] is True
    script = work / "server_switch" / "launch_lethe.cmd"
    assert script.is_file()
    content = script.read_text(encoding="utf-8")
    assert "server_sync --server lethe" in content
    assert str(lethe) in content
    assert "LimbusCompany.exe" in content
