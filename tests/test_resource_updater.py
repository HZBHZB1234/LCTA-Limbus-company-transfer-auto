import json
import zipfile
from pathlib import Path

import pytest

import resource_updater.core as updater_core
import resource_updater.service as updater_service
from resource_updater.core import (
    DownloadCancelled,
    DownloadError,
    GameInfo,
    ResourceUpdater,
    USER_AGENT,
    X_REQUESTED_WITH,
    _headers,
    build_game_fingerprint,
    parse_catalog,
    resolve_aria2_binary,
)
from resource_updater.service import _state_covers_config


def make_game(tmp_path: Path) -> Path:
    game_dir = tmp_path / "Limbus Company"
    game_dir.mkdir(parents=True)
    (game_dir / "LimbusCompany.exe").write_bytes(b"game-executable")
    data_dir = game_dir / "LimbusCompany_Data"
    aa_dir = data_dir / "StreamingAssets" / "aa"
    aa_dir.mkdir(parents=True)
    settings = {
        "m_CatalogLocations": [
            {
                "m_InternalId": (
                    "https://download.limbuscompanycdn.org/"
                    "s20260805_example/catalog_S1.hash"
                )
            }
        ]
    }
    (aa_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    (data_dir / "resources.assets").write_bytes(
        b"https://downloadcommon.limbuscompanycdn.org/l20260801_old "
        b"https://downloadcommon.limbuscompanycdn.org/l20260805_current "
        b"serverinfos_20260805_example.json"
    )
    (aa_dir / "catalog.bin").write_bytes(b"catalog")
    return game_dir


def test_game_info_extracts_latest_tokens(tmp_path):
    game = GameInfo(make_game(tmp_path))

    assert game.extract_tokens() == {
        "s": "s20260805_example",
        "l": "l20260805_current",
        "serverinfo": "20260805_example",
    }
    assert game.catalog_url() == (
        "https://download.limbuscompanycdn.org/"
        "s20260805_example/catalog_S1.bin"
    )


def test_official_cdn_headers_match_successful_game_client_requests():
    assert _headers(False) == {"User-Agent": USER_AGENT}
    assert _headers(True) == {
        "User-Agent": USER_AGENT,
        "X-Requested-With": X_REQUESTED_WITH,
    }
    assert USER_AGENT.startswith("UnityPlayer/6000.3.12f1")
    assert X_REQUESTED_WITH == "this_is_header_value"


def test_game_fingerprint_only_tracks_executable(tmp_path):
    game_dir = make_game(tmp_path)
    first = build_game_fingerprint(game_dir)

    catalog = game_dir / "LimbusCompany_Data" / "StreamingAssets" / "aa" / "catalog.bin"
    catalog.write_bytes(b"catalog-updated")
    unchanged = build_game_fingerprint(game_dir)
    (game_dir / "LimbusCompany.exe").write_bytes(b"game-executable-updated")
    changed = build_game_fingerprint(game_dir)

    assert first == unchanged
    assert first != changed
    assert set(first) == {"LimbusCompany.exe"}


def test_parse_catalog_extracts_bundle_cache_keys(tmp_path):
    inner = "a" * 32
    outer = "b" * 32
    bundle_name = "characters_{}.bundle".format(inner)
    catalog = tmp_path / "catalog.bin"
    catalog.write_bytes(bundle_name.encode("ascii") + b"\x00" + outer.encode("ascii"))

    names, metadata = parse_catalog(catalog)

    assert names == [bundle_name]
    assert metadata[bundle_name] == {"inner": inner, "outer": outer}


def test_localize_update_uses_token_scoped_zip_and_blocks_traversal(tmp_path):
    game_dir = make_game(tmp_path)
    work_dir = tmp_path / "work"
    token = "l20260805_current"
    zip_dir = work_dir / "downloads" / token
    zip_dir.mkdir(parents=True)
    zip_path = zip_dir / "localize_en.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("LocalizeTemp_en/story/chapter.json", b'{"ok": true}')
        archive.writestr("LocalizeTemp_en/../escaped.txt", b"blocked")
        archive.writestr("LocalizeTemp_en/C:/escaped.txt", b"blocked")

    updater = ResourceUpdater(
        game_dir,
        work_dir=work_dir,
        cache_dir=tmp_path / "unity-cache",
        engine="builtin",
    )
    result = updater.update_localize({"tokens": {"l": token}}, ["en"])

    destination = (
        game_dir
        / "LimbusCompany_Data"
        / "Assets"
        / "Resources_moved"
        / "Localize"
        / "en"
        / "story"
        / "chapter.json"
    )
    assert result == {"updated": 1, "failed": 0, "failed_items": [], "retried": 0}
    assert destination.read_bytes() == b'{"ok": true}'
    assert not (destination.parent.parent / "escaped.txt").exists()


def test_manifest_uses_catalog_url_from_settings(tmp_path, monkeypatch):
    game_dir = make_game(tmp_path)
    inner = "a" * 32
    outer = "b" * 32
    bundle_name = "characters_{}.bundle".format(inner)
    calls = []

    def fake_http_get(url, include_xrw, timeout=60):
        calls.append((url, include_xrw, timeout))
        return bundle_name.encode("ascii") + b"\x00" + outer.encode("ascii")

    monkeypatch.setattr(updater_core, "http_get", fake_http_get)
    updater = ResourceUpdater(
        game_dir,
        work_dir=tmp_path / "work",
        cache_dir=tmp_path / "unity-cache",
        engine="builtin",
    )

    manifest = updater._build_manifest(True)

    assert calls == [(
        "https://download.limbuscompanycdn.org/"
        "s20260805_example/catalog_S1.bin",
        True,
        120,
    )]
    assert manifest["bundles"] == [bundle_name]


def test_failed_bundle_download_removes_cache_entry_folder(tmp_path, monkeypatch):
    game_dir = make_game(tmp_path)
    cache_dir = tmp_path / "unity-cache"
    inner = "a" * 32
    outer = "b" * 32
    bundle_name = "characters_{}.bundle".format(inner)

    def fail_download(url, destination, include_xrw, cancel_event, progress=None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.with_name(destination.name + ".part").write_bytes(b"partial")
        raise DownloadError("HTTP 403")

    monkeypatch.setattr(updater_core, "http_download", fail_download)
    monkeypatch.setattr(
        ResourceUpdater, "_probe_failure", staticmethod(lambda url: "")
    )
    updater = ResourceUpdater(
        game_dir,
        work_dir=tmp_path / "work",
        cache_dir=cache_dir,
        engine="builtin",
    )

    result = updater.update_bundles({
        "tokens": {"s": "s20260805_example"},
        "bundles": [bundle_name],
        "bundle_meta": {
            bundle_name: {"inner": inner, "outer": outer},
        },
    })

    assert result == {
        "updated": 0,
        "skipped": 0,
        "failed": 1,
        "retried": 0,
        "failed_items": [{
            "name": bundle_name,
            "url": "https://download.limbuscompanycdn.org/s20260805_example/{}".format(bundle_name),
            "reason": "HTTP 403",
        }],
    }
    assert not (cache_dir / outer / inner).exists()


def test_failed_aria2_bundle_removes_cache_entry_folder(tmp_path, monkeypatch):
    game_dir = make_game(tmp_path)
    cache_dir = tmp_path / "unity-cache"
    destination = cache_dir / ("b" * 32) / ("a" * 32) / "__data"

    class FakeAria2:
        def add(self, url, target, include_xrw):
            target.parent.mkdir(parents=True, exist_ok=True)
            Path(str(target) + ".aria2").write_bytes(b"partial")
            return "gid"

        def status(self, gid):
            return {
                "status": "error",
                "completedLength": "0",
                "totalLength": "1",
                "downloadSpeed": "0",
                "errorCode": "22",
                "errorMessage": "HTTP 403",
            }

        def remove_all(self):
            pass

    updater = ResourceUpdater(
        game_dir,
        work_dir=tmp_path / "work",
        cache_dir=cache_dir,
        engine="aria2",
    )
    updater.aria2 = FakeAria2()
    monkeypatch.setattr(
        ResourceUpdater, "_probe_failure", staticmethod(lambda url: "")
    )

    result = updater._download_many_aria2(
        "bundle",
        [(
            "https://download.limbuscompanycdn.org/token/example.bundle",
            destination,
            True,
            True,
            updater._write_bundle_info,
            True,
        )],
    )

    assert result == {
        "completed": 0,
        "skipped": 0,
        "failed": 1,
        "retried": 0,
        "failed_items": [{
            "name": "example.bundle",
            "url": "https://download.limbuscompanycdn.org/token/example.bundle",
            "reason": "HTTP 403 (错误码 22)",
        }],
    }
    assert not destination.parent.exists()


def test_bundled_aria2_path_has_priority(tmp_path, monkeypatch):
    resource_root = tmp_path / "package"
    aria2 = resource_root / "tools" / "aria2" / "aria2c.exe"
    aria2.parent.mkdir(parents=True)
    aria2.write_bytes(b"binary")
    monkeypatch.setenv("path_", str(resource_root))

    assert resolve_aria2_binary() == aria2


def test_launcher_state_requires_all_configured_scopes():
    fingerprint = {"settings.json": {"sha256": "abc", "size": 1}}
    state = {
        "fingerprint": fingerprint,
        "resources": {"localize": True, "bundle": False, "languages": ["en"]},
    }
    config = {
        "localize": True,
        "bundle": True,
        "lang_jp": False,
        "lang_en": True,
        "lang_kr": False,
    }

    assert not _state_covers_config(state, fingerprint, config)
    state["resources"]["bundle"] = True
    assert _state_covers_config(state, fingerprint, config)
    config["lang_jp"] = True
    assert not _state_covers_config(state, fingerprint, config)


class RetryAria2:
    def __init__(self, error_statuses=1):
        self.error_statuses = error_statuses
        self.add_count = 0
        self.status_calls = []

    def add(self, url, target, include_xrw):
        self.add_count += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        return "gid-{}".format(self.add_count)

    def status(self, gid):
        self.status_calls.append(gid)
        if len(self.status_calls) <= self.error_statuses:
            return {
                "status": "error",
                "completedLength": "0",
                "totalLength": "1",
                "downloadSpeed": "0",
                "errorCode": "22",
                "errorMessage": "HTTP 403",
            }
        return {
            "status": "complete",
            "completedLength": "1",
            "totalLength": "1",
            "downloadSpeed": "0",
            "errorCode": "0",
            "errorMessage": "",
        }

    def remove_all(self):
        pass


def make_bundle_task(tmp_path):
    destination = tmp_path / ("b" * 32) / ("a" * 32) / "__data"
    return (
        "https://download.limbuscompanycdn.org/token/example.bundle",
        destination,
        True,
        True,
        ResourceUpdater._write_bundle_info,
        True,
    )


def test_aria2_retries_transient_failure_and_recovers(tmp_path):
    updater = ResourceUpdater(
        make_game(tmp_path),
        work_dir=tmp_path / "work",
        cache_dir=tmp_path / "unity-cache",
        engine="aria2",
        retry_max=2,
        retry_delay=0.05,
    )
    updater.aria2 = RetryAria2(error_statuses=1)

    result = updater._download_many_aria2("bundle", [make_bundle_task(tmp_path)])

    assert result == {
        "completed": 1,
        "skipped": 0,
        "failed": 0,
        "retried": 1,
        "failed_items": [],
    }
    assert updater.aria2.add_count == 2
    destination = make_bundle_task(tmp_path)[1]
    assert (destination.parent / "__info").is_file()


def test_aria2_retry_exhausted_records_failure_with_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ResourceUpdater,
        "_probe_failure",
        staticmethod(lambda url: "probe: HTTP 403 (fake)"),
    )
    updater = ResourceUpdater(
        make_game(tmp_path),
        work_dir=tmp_path / "work",
        cache_dir=tmp_path / "unity-cache",
        engine="aria2",
        retry_max=2,
        retry_delay=0.05,
    )
    updater.aria2 = RetryAria2(error_statuses=99)

    result = updater._download_many_aria2("bundle", [make_bundle_task(tmp_path)])

    assert result["completed"] == 0
    assert result["failed"] == 1
    assert result["retried"] == 2
    assert updater.aria2.add_count == 3
    assert result["failed_items"] == [{
        "name": "example.bundle",
        "url": "https://download.limbuscompanycdn.org/token/example.bundle",
        "reason": "HTTP 403 (错误码 22)",
        "diagnostics": "probe: HTTP 403 (fake)",
    }]
    assert not make_bundle_task(tmp_path)[1].parent.exists()


def test_aria2_retry_backoff_accepts_cancel(tmp_path):
    updater = ResourceUpdater(
        make_game(tmp_path),
        work_dir=tmp_path / "work",
        cache_dir=tmp_path / "unity-cache",
        engine="aria2",
        retry_max=2,
        retry_delay=3600,
    )
    client = RetryAria2(error_statuses=1)
    updater.aria2 = client
    original_status = client.status

    def cancel_on_first_status(gid):
        result = original_status(gid)
        if len(client.status_calls) == 1:
            updater.cancel_event.set()
        return result

    client.status = cancel_on_first_status

    with pytest.raises(DownloadCancelled):
        updater._download_many_aria2("bundle", [make_bundle_task(tmp_path)])

    assert client.add_count == 1
    assert client.status_calls == ["gid-1"]


def test_aria2_retry_max_zero_disables_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ResourceUpdater, "_probe_failure", staticmethod(lambda url: "")
    )
    updater = ResourceUpdater(
        make_game(tmp_path),
        work_dir=tmp_path / "work",
        cache_dir=tmp_path / "unity-cache",
        engine="aria2",
        retry_max=0,
    )
    client = RetryAria2(error_statuses=99)
    updater.aria2 = client

    result = updater._download_many_aria2("bundle", [make_bundle_task(tmp_path)])

    assert result == {
        "completed": 0,
        "skipped": 0,
        "failed": 1,
        "retried": 0,
        "failed_items": [{
            "name": "example.bundle",
            "url": "https://download.limbuscompanycdn.org/token/example.bundle",
            "reason": "HTTP 403 (错误码 22)",
        }],
    }
    assert client.add_count == 1


def test_builtin_retries_transient_failure_and_recovers(tmp_path, monkeypatch):
    game_dir = make_game(tmp_path)
    cache_dir = tmp_path / "unity-cache"
    inner = "a" * 32
    outer = "b" * 32
    bundle_name = "characters_{}.bundle".format(inner)
    attempts = {"n": 0}

    def flaky_download(url, destination, include_xrw, cancel_event, progress=None):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise DownloadError("HTTP 403")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"data")

    monkeypatch.setattr(updater_core, "http_download", flaky_download)
    updater = ResourceUpdater(
        game_dir,
        work_dir=tmp_path / "work",
        cache_dir=cache_dir,
        engine="builtin",
        retry_max=2,
        retry_delay=0.05,
    )

    result = updater.update_bundles({
        "tokens": {"s": "s20260805_example"},
        "bundles": [bundle_name],
        "bundle_meta": {bundle_name: {"inner": inner, "outer": outer}},
    })

    assert result == {
        "updated": 1,
        "skipped": 0,
        "failed": 0,
        "retried": 2,
        "failed_items": [],
    }
    assert attempts["n"] == 3
    assert (cache_dir / outer / inner / "__data").read_bytes() == b"data"


def test_builtin_retry_exhausted_records_failure(tmp_path, monkeypatch):
    game_dir = make_game(tmp_path)
    cache_dir = tmp_path / "unity-cache"
    inner = "a" * 32
    outer = "b" * 32
    bundle_name = "characters_{}.bundle".format(inner)
    attempts = {"n": 0}

    def always_fail(url, destination, include_xrw, cancel_event, progress=None):
        attempts["n"] += 1
        raise DownloadError("HTTP 403")

    monkeypatch.setattr(updater_core, "http_download", always_fail)
    monkeypatch.setattr(
        ResourceUpdater,
        "_probe_failure",
        staticmethod(lambda url: "probe: HTTP 403 (fake)"),
    )
    updater = ResourceUpdater(
        game_dir,
        work_dir=tmp_path / "work",
        cache_dir=cache_dir,
        engine="builtin",
        retry_max=1,
        retry_delay=0.05,
    )

    result = updater.update_bundles({
        "tokens": {"s": "s20260805_example"},
        "bundles": [bundle_name],
        "bundle_meta": {bundle_name: {"inner": inner, "outer": outer}},
    })

    assert result["updated"] == 0
    assert result["failed"] == 1
    assert result["retried"] == 0
    assert attempts["n"] == 2
    assert result["failed_items"] == [{
        "name": bundle_name,
        "url": "https://download.limbuscompanycdn.org/s20260805_example/{}".format(bundle_name),
        "reason": "HTTP 403",
        "diagnostics": "probe: HTTP 403 (fake)",
    }]
    assert not (cache_dir / outer / inner).exists()


def test_record_update_result_tracks_scopes_and_last_result(tmp_path, monkeypatch):
    state_file = tmp_path / "launcher-state.json"
    monkeypatch.setattr(updater_service, "_state_path", lambda: state_file)
    fingerprint = {"LimbusCompany.exe": {"sha256": "abc", "size": 1}}
    monkeypatch.setattr(
        updater_service, "build_game_fingerprint", lambda game_path: fingerprint
    )

    partial_failure = {
        "success": False,
        "tokens": {"s": "s1", "l": "l1"},
        "retried": 3,
        "failed": 2,
        "results": {
            "localize": {"updated": 5, "failed": 0, "failed_items": [], "retried": 0},
            "bundle": {
                "updated": 1,
                "failed": 2,
                "retried": 3,
                "failed_items": [
                    {"name": "a.bundle", "reason": "HTTP 403", "diagnostics": "probe: HTTP 403"},
                    {"name": "b.bundle", "reason": "timeout"},
                ],
            },
        },
    }
    updater_service.record_update_result(Path("C:/game"), partial_failure, True, True, ["en"])

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["resources"]["localize"] is True
    assert "bundle" not in state["resources"]
    assert state["resources"]["languages"] == ["en"]
    assert state["last_result"] == {
        "success": False,
        "failed": 2,
        "retried": 3,
        "failed_items": [
            {"name": "a.bundle", "reason": "HTTP 403"},
            {"name": "b.bundle", "reason": "timeout"},
        ],
    }
    assert updater_service.get_last_update_result() == state["last_result"]

    full_success = {
        "success": True,
        "tokens": {},
        "retried": 0,
        "failed": 0,
        "results": {
            "localize": {"updated": 0, "failed": 0, "failed_items": [], "retried": 0},
            "bundle": {"updated": 0, "failed": 0, "failed_items": [], "retried": 0},
        },
    }
    updater_service.record_update_result(Path("C:/game"), full_success, True, True, ["en", "jp"])

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["resources"]["bundle"] is True
    assert state["resources"]["languages"] == ["en", "jp"]
    assert state["last_result"]["success"] is True

    fingerprint["LimbusCompany.exe"]["sha256"] = "new"
    updater_service.record_update_result(Path("C:/game"), partial_failure, True, True, ["en"])

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["resources"]["localize"] is True
    assert "bundle" not in state["resources"]
    assert state["resources"]["languages"] == ["en"]
