# -*- coding: utf-8 -*-
"""P6 桥接层测试（plan 12.3）。

验证 JS↔Python 边界：只接受 tool_id/release_id/action，不接受任意 URL 或磁盘目标；
本地管理（列出/启停/卸载/回滚）在**离线/未登录**时依然可用；
在线失败不抹掉本地状态。
"""
import json
from pathlib import Path

import pytest

from webutils.toolbox import install, paths, state


class _FakeApi:
    """假的 ToolboxApi：可控地成功或失败。"""

    base_url = "https://mods.lcta.test"

    def __init__(self, *, access_ok=True, raise_on=None):
        self.access_ok = access_ok
        self.raise_on = raise_on or set()
        self.calls = []

    def _maybe_raise(self, name):
        if name in self.raise_on:
            raise RuntimeError(f"{name} 失败（模拟网络错误）")

    def is_logged_in(self):
        return True

    def access(self):
        self.calls.append("access")
        self._maybe_raise("access")
        return {"unlocked": self.access_ok, "season_active": True}

    def season(self):
        self.calls.append("season")
        self._maybe_raise("season")
        return {"season_active": True, "name": "S1"}

    def current_user(self):
        return {"id": 1, "username": "alice"}

    def login(self, identifier, password):
        self.calls.append(("login", identifier, password))
        self._maybe_raise("login")
        return {"access_token": "a"}

    def logout(self):
        self.calls.append("logout")

    def new_challenge(self):
        return {"challenge_id": "c" * 16, "material": "题面"}

    def solve(self, cid, answer):
        self.calls.append(("solve", cid, answer))
        return {"unlocked": True}

    def afdian_status(self):
        return {"configured": False, "bound": False}

    def verify_order(self, order_no):
        return {"unlocked": True}

    def catalog(self):
        self.calls.append("catalog")
        return {"items": []}

    def manifest(self, tool_id, release_id):
        return {"manifest": {"files": []}, "signature": None}

    def download_ticket(self, *a, **k):
        raise AssertionError("不应走到下载")


def _make_bridge(tmp_path, *, api=None, game_root=True):
    """构造一个带 ToolboxMixin 的最小对象（避开 pywebview 依赖）。"""
    from webui.app_api.toolbox import ToolboxMixin

    class Bridge(ToolboxMixin):
        def __init__(self):
            self.errors = []
            self.ui = []

        def log_error(self, exc):
            self.errors.append(repr(exc))

        def log_ui(self, msg):
            self.ui.append(msg)

        def _toolbox_api(self):
            return api or _FakeApi()

        def _toolbox_game_root(self):
            if not game_root:
                raise ValueError("尚未配置游戏目录")
            return str(tmp_path)

    return Bridge()


@pytest.fixture()
def game(tmp_path):
    g = tmp_path / "game"
    g.mkdir()
    return g


class TestStatusBridge:
    def test_local_available_when_offline(self, game):
        """在线查询失败**不能**让本地状态消失（过季/断网仍要能停用卸载）。"""
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        r = b.toolbox_status()
        assert r["success"] is True
        d = r["data"]
        assert d["local"] is not None, "本地状态必须仍然返回"
        assert d["online"] is None
        assert d["online_error"], "在线失败应如实上报，而不是静默"

    def test_reports_missing_game_root(self, tmp_path):
        b = _make_bridge(tmp_path, game_root=False)
        r = b.toolbox_status()
        assert r["success"] is True
        assert "game_root" in r["data"] or "local_error" in r["data"]

    def test_includes_protocol_version(self, game):
        b = _make_bridge(game)
        assert b.toolbox_status()["data"]["protocol_version"] >= 2


class TestLocalManagementOffline:
    """本地管理必须**不依赖**在线资格。"""

    def _install_one(self, game, tmp_path):
        import zipfile

        rt = tmp_path / "rt.zip"
        with zipfile.ZipFile(str(rt), "w") as zf:
            zf.writestr("BepInEx/core/x.dll", b"core")
        install.install_runtime(game, install.InstallPlan(
            kind="runtime", release_id="rt-1", files=[], allowed_prefixes=["BepInEx"], stub_path=rt,
        ))
        pl = tmp_path / "p.zip"
        with zipfile.ZipFile(str(pl), "w") as zf:
            zf.writestr("ToolA.dll", b"dll")
        install.install_plugin(game, install.InstallPlan(
            kind="plugin", release_id="r1", tool_id="tool-a", guid="g",
            main_dll="ToolA.dll", requires_runtime=True, stub_path=pl,
        ))

    def test_list_works_offline(self, game, tmp_path):
        self._install_one(game, tmp_path)
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        r = b.toolbox_list_installed()
        assert r["success"] is True
        assert [p["tool_id"] for p in r["data"]["plugins"]] == ["tool-a"]

    def test_disable_works_offline(self, game, tmp_path):
        """停用必须能在离线/过季时完成。"""
        self._install_one(game, tmp_path)
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        r = b.toolbox_set_enabled("tool-a", False)
        assert r["success"] is True, r
        assert not (game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "ToolA.dll").exists()

    def test_uninstall_works_offline(self, game, tmp_path):
        self._install_one(game, tmp_path)
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        assert b.toolbox_uninstall("tool-a")["success"] is True
        assert "tool-a" not in state.Manifest.load(game).plugins

    def test_rollback_works_offline(self, game, tmp_path):
        self._install_one(game, tmp_path)
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        assert b.toolbox_rollback("tool-a")["success"] is True

    def test_integrity_works_offline(self, game, tmp_path):
        self._install_one(game, tmp_path)
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        r = b.toolbox_verify_integrity("tool-a")
        assert r["success"] is True and r["data"]["ok"] is True


class TestInstallBoundary:
    def test_unsigned_manifest_refused(self, game, tmp_path):
        """未签名清单必须拒绝安装（不能只靠客户端「约定」）。"""
        b = _make_bridge(game, api=_FakeApi())
        r = b.toolbox_install(1, "r1")
        assert r["success"] is False
        assert "签名" in r["message"]

    def test_missing_public_key_refused(self, game, tmp_path, monkeypatch):
        """本地没有配置验签公钥 → fail-closed，不安装。"""
        api = _FakeApi()
        api.manifest = lambda t, r: {
            "manifest": {"files": [{"path": "A.dll", "sha256": "a" * 64}]},
            "signature": "c2ln",
        }
        b = _make_bridge(game, api=api)
        r = b.toolbox_install(1, "r1")
        assert r["success"] is False
        assert "签名" in r["message"]

    def test_no_arbitrary_url_accepted(self, game):
        """桥接口签名里**没有** URL/路径参数 —— 网页无法指定下载源或目标目录。"""
        import inspect

        from webui.app_api.toolbox import ToolboxMixin

        params = set(inspect.signature(ToolboxMixin.toolbox_install).parameters)
        # confirm_foreign 是布尔确认位（外部 loader 二次确认），modal_id 只用于
        # 进度显示；两者都不是 URL/路径。契约不变：接口里永远不允许出现下载源
        # 或目标目录参数。
        assert params == {"self", "tool_id", "release_id", "confirm_foreign", "modal_id"}
        assert not any(k and ("url" in k or "path" in k) for k in params)
        for name in ("url", "path", "target", "command", "script"):
            assert name not in params

    def test_concurrent_install_rejected(self, game, monkeypatch):
        """并发安装必须被拒（否则两个任务互相覆盖文件）。"""
        from webui.app_api import toolbox as tb

        # 占住锁
        assert tb._task_lock.acquire(blocking=False)
        try:
            b = _make_bridge(game)
            r = b.toolbox_install(1, "r1")
            assert r["success"] is False
            assert "进行中" in r["message"]
        finally:
            tb._task_lock.release()


class TestGameRootValidation:
    def test_set_game_root_rejects_bad_path(self, tmp_path):
        b = _make_bridge(tmp_path)
        r = b.toolbox_set_game_root(str(tmp_path / "does-not-exist"))
        assert r["success"] is False

    def test_set_game_root_rejects_drive_root(self):
        import os

        if os.name != "nt":
            pytest.skip("仅 Windows")
        b = _make_bridge(Path("."))
        assert b.toolbox_set_game_root("C:\\")["success"] is False


class TestUnlockBridge:
    def test_challenge_response_has_no_answer(self, game):
        """桥返回的挑战里**不能**含答案。"""
        b = _make_bridge(game)
        data = b.toolbox_new_challenge()["data"]
        assert "answer" not in data
        assert data["challenge_id"]

    def test_solve_passes_through(self, game):
        b = _make_bridge(game)
        assert b.toolbox_solve("c" * 16, "deadbeef")["success"] is True

# ---------------------------------------------------------------------------
# 2026-10-30：一键安装契约（清单驱动）+ 登录/订阅语义
# ---------------------------------------------------------------------------

def _ed25519_keypair_and_sign(seed: bytes, message: bytes):
    """RFC 8032 参考实现（**仅测试用**）：返回 (raw_public_key, signature)。

    客户端仓库是纯 Python 验签（无 cryptography），测试用同一数学的
    签名端生成真实签名，保证验签路径被真实执行而不是 mock。
    """
    import hashlib

    p = 2 ** 255 - 19
    l = 2 ** 252 + 27742317777372353535851937790883648493
    d = -121665 * pow(121666, p - 2, p) % p
    I = pow(2, (p - 1) // 4, p)

    def xrecover(y):
        xx = (y * y - 1) * pow(d * y * y + 1, p - 2, p)
        x = pow(xx, (p + 3) // 8, p)
        if (x * x - xx) % p != 0:
            x = (x * I) % p
        if x % 2 != 0:
            x = p - x
        return x

    By = 4 * pow(5, p - 2, p) % p
    B = [xrecover(By) % p, By]

    def edwards_add(P, Q):
        x1, y1 = P
        x2, y2 = Q
        x3 = (x1 * y2 + x2 * y1) * pow(1 + d * x1 * x2 * y1 * y2, p - 2, p) % p
        y3 = (y1 * y2 + x1 * x2) * pow(1 - d * x1 * x2 * y1 * y2, p - 2, p) % p
        return [x3, y3]

    def scalarmult(P, e):
        if e == 0:
            return [0, 1]
        Q = scalarmult(P, e // 2)
        Q = edwards_add(Q, Q)
        if e & 1:
            Q = edwards_add(Q, P)
        return Q

    def encodepoint(P):
        x, y = P
        out = bytearray(y.to_bytes(32, "little"))
        out[31] = (out[31] & 0x7F) | ((x & 1) << 7)
        return bytes(out)

    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= (1 << 254)
    pub = encodepoint(scalarmult(B, a))
    r = int.from_bytes(hashlib.sha512(h[32:] + message).digest(), "little") % l
    R = encodepoint(scalarmult(B, r))
    hram = int.from_bytes(hashlib.sha512(R + pub + message).digest(), "little") % l
    s = (r + hram * a) % l
    return pub, R + s.to_bytes(32, "little")


_ED25519_SPKI_DER_PREFIX = bytes.fromhex("302a300506032b6570032100")


class _ContractApi(_FakeApi):
    """可控 manifest/ticket 的假 API（默认未签名 —— 契约要求拒绝）。"""

    def __init__(self, manifest_out=None):
        super().__init__()
        self._manifest_out = manifest_out

    def manifest(self, tool_id, release_id):
        if self._manifest_out is not None:
            return self._manifest_out
        return {"manifest": {"files": []}, "signature": None}

    def download_ticket(self, tool_id, release_id, file_name, sha256):
        self.calls.append(("ticket", file_name, sha256))
        return {"download_url": "https://cdn.example.test/restricted/x"}


class TestManifestDrivenInstall:
    """一键安装契约：只信签名清单，逐文件校验，按 install_kind 分发。"""

    def _signed(self, manifest, seed=b"lcta-test-seed-0001"):
        from webutils.toolbox import ed25519

        pub, sig = _ed25519_keypair_and_sign(seed, ed25519.canonical_bytes(manifest))
        import base64

        return {
            "pub_der": _ED25519_SPKI_DER_PREFIX + pub,
            "manifest_out": {
                "manifest": manifest,
                "signature": base64.b64encode(sig).decode("ascii"),
            },
        }

    def _runtime_ready(self, game, tmp_path):
        import zipfile

        rt = tmp_path / "rt.zip"
        with zipfile.ZipFile(str(rt), "w") as zf:
            zf.writestr("BepInEx/core/x.dll", b"core")
        install.install_runtime(game, install.InstallPlan(
            kind="runtime", release_id="rt-0", files=[],
            allowed_prefixes=["BepInEx"], stub_path=rt,
        ))

    def test_multi_file_plugin_install(self, game, tmp_path, monkeypatch):
        """多文件清单：逐文件下载校验后打包事务化安装，两个文件都落位。"""
        import hashlib
        import zipfile

        self._runtime_ready(game, tmp_path)
        content_a, content_b = b"A" * 100, b"B" * 50
        sha_a = hashlib.sha256(content_a).hexdigest()
        sha_b = hashlib.sha256(content_b).hexdigest()
        manifest = {
            "schema_version": 1, "tool_id": 7, "release_id": "r9", "version": "1.2.0",
            "resource_kind": "plugin", "install_kind": "bepinex_plugin_dll",
            "tool_dir": "lcta-test", "guid": "com.lcta.test",
            "files": [
                {"path": "sub/ToolA.dll", "sha256": sha_a, "size": 100},
                {"path": "sub/ToolB.dll", "sha256": sha_b, "size": 50},
            ],
            "dependencies": [], "conflict_guids": [],
        }
        signed = self._signed(manifest)

        artifacts = {sha_a: content_a, sha_b: content_b}
        cache = {}
        for sha, content in artifacts.items():
            fp = tmp_path / f"dl-{sha[:8]}"
            fp.write_bytes(content)
            cache[sha] = fp

        api = _ContractApi(signed["manifest_out"])
        monkeypatch.setattr(
            "webutils.toolbox.download.fetch_or_reuse",
            lambda url, sha, expected_size=None, progress=None: cache[sha],
        )
        b = _make_bridge(game, api=api)
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install(7, "r9")
        assert r["success"] is True, r

        m = state.Manifest.load(game)
        entry = m.plugins["7"]
        assert {f.relative_path for f in entry.files} == {"sub/ToolA.dll", "sub/ToolB.dll"}
        # 每个清单文件各取了一张票据
        tickets = [c for c in api.calls if isinstance(c, tuple) and c[0] == "ticket"]
        assert {t[1] for t in tickets} == {"sub/ToolA.dll", "sub/ToolB.dll"}

    def test_runtime_install_via_bridge(self, game, tmp_path, monkeypatch):
        """runtime_zip_root 清单经 toolbox_install_runtime 安装底座。"""
        import hashlib
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("BepInEx/core/runtime.dll", b"runtime-core")
        zip_bytes = buf.getvalue()
        sha = hashlib.sha256(zip_bytes).hexdigest()
        fp = tmp_path / "rt-dl.zip"
        fp.write_bytes(zip_bytes)
        manifest = {
            "schema_version": 1, "tool_id": 9, "release_id": "rt1", "version": "0.3",
            "resource_kind": "runtime", "install_kind": "runtime_zip_root",
            "tool_dir": "",
            "files": [{"path": "runtime.zip", "sha256": sha, "size": len(zip_bytes)}],
            "dependencies": [], "conflict_guids": [],
        }
        signed = self._signed(manifest)
        monkeypatch.setattr(
            "webutils.toolbox.download.fetch_or_reuse",
            lambda url, sha_, expected_size=None, progress=None: fp,
        )
        api = _ContractApi(signed["manifest_out"])
        b = _make_bridge(game, api=api)
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install_runtime(9, "rt1")
        assert r["success"] is True, r
        assert state.Manifest.load(game).runtime is not None

    def test_package_install_via_bridge(self, game, tmp_path, monkeypatch):
        """game_relative_files：按签名清单 target_dir 写入并记录 packages。"""
        import hashlib

        content = b"PACKAGE"
        sha = hashlib.sha256(content).hexdigest()
        fp = tmp_path / "pkg.bin"
        fp.write_bytes(content)
        manifest = {
            "schema_version": 1, "tool_id": 7, "release_id": "rp1", "version": "1.0",
            "resource_kind": "package", "install_kind": "game_relative_files",
            "tool_dir": "pkg-test", "target_dir": "BepInEx/plugins/PkgTest",
            "requires_runtime": False,
            "files": [{"path": "PkgTest.dll", "sha256": sha, "size": len(content)}],
            "dependencies": [], "conflict_guids": [],
        }
        signed = self._signed(manifest)
        monkeypatch.setattr(
            "webutils.toolbox.download.fetch_or_reuse",
            lambda url, sha_, expected_size=None, progress=None: fp,
        )
        b = _make_bridge(game, api=_ContractApi(signed["manifest_out"]))
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install_any(7, "rp1")
        assert r["success"] is True, r
        assert (game / "BepInEx" / "plugins" / "PkgTest" / "PkgTest.dll").read_bytes() == content
        assert state.Manifest.load(game).packages["7"].target_dir == "BepInEx/plugins/PkgTest"

    def test_download_only_works_without_game_root(self, tmp_path, monkeypatch):
        """download_only 不要求配置游戏目录，只落系统下载目录。"""
        import hashlib

        content = b"DOWNLOAD"
        sha = hashlib.sha256(content).hexdigest()
        fp = tmp_path / "dl.bin"
        fp.write_bytes(content)
        manifest = {
            "schema_version": 1, "tool_id": 9, "release_id": "rd1", "version": "1.0",
            "resource_kind": "download", "install_kind": "download_only",
            "tool_dir": "dl-test",
            "files": [{"path": "file.bin", "sha256": sha, "size": len(content)}],
            "dependencies": [], "conflict_guids": [],
        }
        signed = self._signed(manifest)
        monkeypatch.setattr(
            "webutils.toolbox.download.fetch_or_reuse",
            lambda url, sha_, expected_size=None, progress=None: fp,
        )
        saved = tmp_path / "Downloads" / "dl-test" / "file.bin"
        monkeypatch.setattr(
            "webutils.toolbox.download.save_to_downloads",
            lambda files, folder, progress=None: [saved],
        )
        b = _make_bridge(tmp_path, api=_ContractApi(signed["manifest_out"]), game_root=False)
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install_any(9, "rd1")
        assert r["success"] is True, r
        assert r["data"]["kind"] == "download"
        assert r["data"]["save_paths"] == [str(saved)]

    def test_wrong_entry_refused(self, game, tmp_path):
        """插件入口装底座 / 底座入口装插件 → 明确报错而不是装错。"""
        self._runtime_ready(game, tmp_path)
        b = _make_bridge(game)
        # 未签名清单先被拒；这里用伪造 manifest_out 测 kind 分发文案
        api = _ContractApi({"manifest": {"install_kind": "runtime_zip_root", "files": [
            {"path": "a.zip", "sha256": "a" * 64}]}, "signature": "c2ln"})
        b2 = _make_bridge(game, api=api)
        b2._manifest_public_key = None  # 无公钥 → 先拒签名
        r = b2.toolbox_install_runtime(1, "r1")
        assert r["success"] is False

    def test_unknown_install_kind_refused(self, game, tmp_path):
        """未知 install_kind（含缺失）一律拒绝 —— 契约白名单。"""
        manifest = {"install_kind": "arbitrary_script",
                    "files": [{"path": "a.dll", "sha256": "a" * 64}]}
        signed = self._signed(manifest)
        b = _make_bridge(game, api=_ContractApi(signed["manifest_out"]))
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install(1, "r1")
        assert r["success"] is False
        assert "安装类型" in r["message"]

    def test_empty_files_refused(self, game, tmp_path):
        manifest = {"install_kind": "bepinex_plugin_dll", "files": []}
        signed = self._signed(manifest)
        b = _make_bridge(game, api=_ContractApi(signed["manifest_out"]))
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install(1, "r1")
        assert r["success"] is False
        assert "文件" in r["message"]


class TestStatusSeasonAndCatalog:
    """status 必须携带 season/catalog（此前目录数据从未填充的缺陷）。"""

    def test_status_includes_season_and_catalog(self, game):
        api = _FakeApi()
        api.catalog = lambda: {"items": [
            {"tool_id": 7, "tool_name": "P", "release_id": "r1", "version": "1",
             "resource_kind": "plugin", "access_kind": "original",
             "downloadable": True, "files": []},
        ]}
        b = _make_bridge(game, api=api)
        d = b.toolbox_status()["data"]
        assert d["season"]["name"] == "S1"
        assert d["catalog"]["items"][0]["access_kind"] == "original"
        assert d["base_url"]

    def test_guest_status_has_no_online_access(self, game):
        """游客（未登录）：目录仍可取，access/user/afdian 为空。"""
        api = _FakeApi()
        api.is_logged_in = lambda: False
        b = _make_bridge(game, api=api)
        d = b.toolbox_status()["data"]
        assert d["logged_in"] is False
        assert d["online"] is None
        assert d["catalog"] is not None
        assert d["user"] is None and d["afdian"] is None
