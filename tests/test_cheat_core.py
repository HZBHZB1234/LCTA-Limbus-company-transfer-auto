"""
tests/test_cheat_core.py
CheatCore 加密分发 / 密钥门测试。

覆盖：
- tools/cheat_encrypt.py：build_blob / parse_blob / decrypt_blob 往返、密钥校验
- 门槛设计验证：repeating-key XOR 下已知明文可恢复密钥（明文碰撞分析）
- webutils/cheat_core.py：解锁（正确/错误/过短密钥）、blob 损坏、锁定清理、
  持久化密钥自动解锁、开发模式、功能页资源读取
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.cheat_encrypt import (
    MAGIC,
    ANCHOR,
    xor,
    build_blob,
    parse_blob,
    decrypt_blob,
)
from webutils import cheat_core
from webutils.cheat_core import KEY_CONFIG
from globalManagers.ConfigManager import ConfigManager

FAKE_FILES = {
    "cheatcore/cheat_damage_hook.py": (
        "# -*- coding: utf-8 -*-\n"
        "class FakeManager:\n"
        "    _calls = []\n"
        "    @classmethod\n"
        "    def get_status(cls):\n"
        "        return {'fake': True}\n"
        "    @classmethod\n"
        "    def apply(cls):\n"
        "        return {'success': True, 'multiplier': 3.0, 'enabled': True}\n"
        "    @classmethod\n"
        "    def inject(cls):\n"
        "        cls._calls.append('inject')\n"
        "        return True\n"
        "    @classmethod\n"
        "    def close(cls):\n"
        "        cls._calls.append('close')\n"
        "def start_launcher():\n"
        "    FakeManager._calls.append('start')\n"
        "def stop_launcher():\n"
        "    FakeManager._calls.append('stop')\n"
    ),
    "cheatcore/registry.py": (
        "# -*- coding: utf-8 -*-\n"
        "PLUGIN = {\n"
        "    'id': 'cheat',\n"
        "    'name': '作弊工具箱',\n"
        "    'entry': 'cheat_damage_hook',\n"
        "    'manager': 'FakeManager',\n"
        "    'api': ['get_status', 'apply', 'inject'],\n"
        "    'webui': {'section': 'cheat', 'js': 'cheat'},\n"
        "    'config': {\n"
        "        'launcher.work.cheat_damage': {'type': 'bool', 'default': False, 'label': '启用作弊工具箱', 'hint': 'h'},\n"
        "        'launcher.work.cheat_damage_multiplier': {'type': 'str', 'default': '3.0', 'label': '伤害倍率', 'hint': 'h'},\n"
        "    },\n"
        "    'launcher': {\n"
        "        'enabled_key': 'launcher.work.cheat_damage',\n"
        "        'checkbox_id': 'launcher-work-cheat-damage',\n"
        "        'consent': 'cheat',\n"
        "        'on_start': 'start_launcher',\n"
        "        'on_stop': 'stop_launcher',\n"
        "    },\n"
        "}\n"
        "def get_plugins():\n"
        "    return [PLUGIN]\n"
    ),
    "cheatcore/__init__.py": "from cheatcore.registry import get_plugins\n",
    "hooks/cheat_damage.dll": b"MZ" + b"\x90" * 100,
    "webui/sections/cheat.html": "<div class=\"cheat-ui\">ui</div>\n",
    "webui/js/cheat.js": "// fake\nwindow.initCheatPage = function() {};\n",
}

TEST_KEY = "8B4B8F729969A5E7CDFEA9423D99D7E3"  # 32 字符


def _make_src(tmp_path, files=None, key=TEST_KEY, order=None):
    """构造一个模拟的私有仓库克隆目录（含 manifest.json 与 keys/current.txt）。"""
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    files = files if files is not None else FAKE_FILES
    manifest_files = []
    for rel in (order or list(files.keys())):
        content = files[rel]
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = content.encode("utf-8")
        p.write_bytes(content)
        manifest_files.append({"src": rel, "dest": rel})
    (src / "manifest.json").write_text(
        json.dumps({"format": 1, "files": manifest_files}, ensure_ascii=False),
        encoding="utf-8",
    )
    keyfile = src / "keys" / "current.txt"
    keyfile.parent.mkdir(parents=True, exist_ok=True)
    keyfile.write_text(key, encoding="utf-8")
    return src, key


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """每个测试：禁用开发模式 + 重置解锁状态与已导入模块/插件注册。"""
    monkeypatch.setattr(cheat_core, "dev_src_dir", lambda: None)
    with cheat_core._state_lock:
        cheat_core._state.update({
            "unlocked": False, "reason": "need_key",
            "source": None, "key": None, "package": None,
        })
    from webutils.cheat_plugins import CheatPluginHost
    CheatPluginHost.clear()
    for name in ("cheatcore", "cheatcore.registry", "cheatcore.cheat_damage_hook"):
        sys.modules.pop(name, None)
    yield
    with cheat_core._state_lock:
        cheat_core._state.update({
            "unlocked": False, "reason": "need_key",
            "source": None, "key": None, "package": None,
        })
    CheatPluginHost.clear()
    for name in ("cheatcore", "cheatcore.registry", "cheatcore.cheat_damage_hook"):
        sys.modules.pop(name, None)


@pytest.fixture
def blob_env(monkeypatch, tmp_path):
    """把 path_ 指向含 cheat_core.bin 的安装目录、运行时目录指向 tmp。"""
    install = tmp_path / "install" / "cheat_core"
    install.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("path_", str(tmp_path / "install"))
    monkeypatch.setenv("LCTA_CHEAT_CORE_DIR", str(tmp_path / "runtime"))

    def _put(blob):
        (install / "cheat_core.bin").write_bytes(blob)

    return _put


def _fake_config(monkeypatch):
    """用内存 dict 替换 ConfigManager 的 get/set/save。"""
    store = {}

    def _get(self, key, default=None):
        return store.get(key, default)

    def _set(self, key, value, auto_save=True):
        store[key] = value

    def _save(self):
        pass

    monkeypatch.setattr(ConfigManager, "get", _get)
    monkeypatch.setattr(ConfigManager, "set", _set)
    monkeypatch.setattr(ConfigManager, "save", _save)
    return store


# ---------------------------------------------------------------------------
# 加密器：格式与往返
# ---------------------------------------------------------------------------


class TestEncryptor:

    def test_blob_structure(self, tmp_path):
        src, key = _make_src(tmp_path)
        blob = build_blob(src, key.encode("utf-8"))
        assert blob[: len(MAGIC)] == MAGIC
        manifest, cipher = parse_blob(blob)
        assert manifest["format"] == 1
        dests = [f["dest"] for f in manifest["files"]]
        assert dests == [
            "cheatcore/cheat_damage_hook.py",
            "cheatcore/registry.py",
            "cheatcore/__init__.py",
            "hooks/cheat_damage.dll",
            "webui/sections/cheat.html",
            "webui/js/cheat.js",
        ]
        # manifest 内包含大小与 sha256（运行期完整性校验）
        dll_entry = next(f for f in manifest["files"] if f["dest"].endswith(".dll"))
        assert dll_entry["size"] == len(FAKE_FILES["hooks/cheat_damage.dll"])
        assert len(dll_entry["sha256"]) == 64
        # 密文与明文差异显著
        assert b"FakeManager" not in cipher

    def test_decrypt_roundtrip(self, tmp_path):
        src, key = _make_src(tmp_path)
        blob = build_blob(src, key.encode("utf-8"))
        manifest, file_list = decrypt_blob(blob, key.encode("utf-8"))
        files = dict(file_list)
        assert files["webui/js/cheat.js"] == FAKE_FILES["webui/js/cheat.js"].encode("utf-8")
        assert files["hooks/cheat_damage.dll"] == b"MZ" + b"\x90" * 100

    def test_wrong_key_fails(self, tmp_path):
        src, key = _make_src(tmp_path)
        blob = build_blob(src, key.encode("utf-8"))
        with pytest.raises(ValueError):
            decrypt_blob(blob, b"wrong-key" * 2)

    def test_missing_manifest_file_fails(self, tmp_path):
        src, key = _make_src(tmp_path)
        (src / "hooks" / "cheat_damage.dll").unlink()
        with pytest.raises(FileNotFoundError):
            build_blob(src, key.encode("utf-8"))

    def test_corrupted_cipher_rejected(self, tmp_path):
        src, key = _make_src(tmp_path)
        blob = bytearray(build_blob(src, key.encode("utf-8")))
        blob[-1] ^= 0xFF  # 翻转密文最后一个字节
        with pytest.raises(ValueError):
            decrypt_blob(bytes(blob), key.encode("utf-8"))

    def test_key_recoverable_via_known_plaintext(self):
        """门槛设计验证：repeating-key XOR + 已知明文 → 直接恢复密钥。"""
        key = b"K" * 16
        known = b"# -*- coding: ut"  # 与密钥等长的已知明文块
        plain = known * 3
        cipher = xor(plain, key)
        recovered = bytes(c ^ p for c, p in zip(cipher[: len(known)], known))
        assert recovered == key

    def test_e2e_known_plaintext_collision_recovery(self, tmp_path):
        """端到端：从 blob 密文 + 首个文件可预测明文头恢复完整密钥。"""
        key = b"0123456789ABCDEF"  # 16 字节
        files = dict(FAKE_FILES)
        src, _ = _make_src(tmp_path, files=files, key=key.decode("ascii"))
        blob = build_blob(src, key)
        manifest, cipher = parse_blob(blob)
        # 攻击者：manifest 明文给出第一个文件偏移（anchor 之后）
        first = manifest["files"][0]
        off = len(ANCHOR)
        assert first["dest"] == "cheatcore/cheat_damage_hook.py"
        # 已知明文头：Python 源码通常以编码声明/docstring 开头
        known = b"# -*- coding: utf-8 -*-"
        guess = bytes(c ^ p for c, p in zip(cipher[off: off + len(known)], known))
        # anchor 位于文件前，密钥周期整体平移 len(ANCHOR) % len(key) 位
        rot = len(ANCHOR) % len(key)
        assert guess[: len(key)] == key[rot:] + key[:rot]  # 恢复的密钥周期与真实密钥一致


# ---------------------------------------------------------------------------
# 运行期加载器：解锁 / 锁定 / 自动解锁 / 开发模式
# ---------------------------------------------------------------------------


class TestCheatCoreLoader:

    def test_unlock_roundtrip(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        _fake_config(monkeypatch)

        assert cheat_core.is_unlocked() is False
        result = cheat_core.unlock(key)
        assert result["success"] is True
        assert cheat_core.is_unlocked() is True

        runtime = tmp_path / "runtime"
        assert (runtime / "cheatcore" / "cheat_damage_hook.py").exists()
        assert (runtime / "hooks" / "cheat_damage.dll").read_bytes() == b"MZ" + b"\x90" * 100
        # 包可导入并注册插件（假模块）
        pkg = cheat_core.get_package()
        assert pkg.get_plugins()[0]["id"] == "cheat"
        from webutils import CheatPluginHost
        assert [p["id"] for p in CheatPluginHost.list()] == ["cheat"]
        # 功能页资源可读取
        assert "cheat-ui" in cheat_core.section_html("cheat")
        assert "initCheatPage" in cheat_core.script_js("cheat")

    def test_wrong_key_rejected(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        _fake_config(monkeypatch)

        result = cheat_core.unlock("wrong-key-wrong-key")
        assert result["success"] is False
        assert result["reason"] == "invalid_key"
        assert cheat_core.is_unlocked() is False
        assert not (tmp_path / "runtime").exists()

    def test_short_key_rejected(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        _fake_config(monkeypatch)

        result = cheat_core.unlock("short")
        assert result["success"] is False
        assert result["reason"] == "invalid_key"

    def test_corrupt_blob_rejected(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob = bytearray(build_blob(src, key.encode("utf-8")))
        blob[-1] ^= 0xFF
        blob_env(bytes(blob))
        _fake_config(monkeypatch)

        result = cheat_core.unlock(key)
        assert result["success"] is False
        assert result["reason"] == "invalid_key"

    def test_blob_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("path_", str(tmp_path / "install"))
        monkeypatch.setenv("LCTA_CHEAT_CORE_DIR", str(tmp_path / "runtime"))
        result = cheat_core.ensure_unlocked()
        assert result["success"] is False
        assert result["reason"] == "blob_missing"

    def test_lock_clears_state_config_and_files(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        store = _fake_config(monkeypatch)

        cheat_core.unlock(key)
        assert store.get(KEY_CONFIG) == key
        result = cheat_core.lock()
        assert result["success"] is True
        assert cheat_core.is_unlocked() is False
        assert store.get(KEY_CONFIG) == ""
        assert not (tmp_path / "runtime").exists()
        # 解锁后再次解锁仍需密钥（模块状态已清）
        assert sys.modules.get("cheatcore") is None

    def test_ensure_unlocked_auto_with_stored_key(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        store = _fake_config(monkeypatch)
        store[KEY_CONFIG] = key

        result = cheat_core.ensure_unlocked()
        assert result["success"] is True
        assert result["source"] == "blob"
        assert cheat_core.is_unlocked() is True
        assert (tmp_path / "runtime" / "cheatcore" / "cheat_damage_hook.py").exists()

    def test_ensure_unlocked_clears_stale_key(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        store = _fake_config(monkeypatch)
        store[KEY_CONFIG] = "stale-stale-stale"

        result = cheat_core.ensure_unlocked()
        assert result["success"] is False
        assert result["reason"] == "need_key"
        assert store.get(KEY_CONFIG) == ""

    def test_dev_mode_unlocks_without_key(self, tmp_path, monkeypatch):
        src, key = _make_src(tmp_path)
        monkeypatch.setattr(cheat_core, "dev_src_dir", lambda: str(src))

        result = cheat_core.ensure_unlocked()
        assert result["success"] is True
        assert result["reason"] == "dev"
        pkg = cheat_core.get_package()
        assert pkg.get_plugins()[0]["id"] == "cheat"
        assert "cheat-ui" in cheat_core.section_html("cheat")

    def test_invoke_locked_then_dispatched(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        _fake_config(monkeypatch)

        from webutils import CheatPluginHost
        with pytest.raises(RuntimeError):
            CheatPluginHost.invoke("get_status")
        cheat_core.unlock(key)
        assert CheatPluginHost.invoke("get_status") == {"fake": True}
        assert CheatPluginHost.invoke("apply")["success"] is True
        with pytest.raises(RuntimeError):
            CheatPluginHost.invoke("not_in_whitelist")

    def test_config_seeded_on_unlock(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        store = _fake_config(monkeypatch)

        cheat_core.unlock(key)
        assert store.get("launcher.work.cheat_damage") is False
        assert store.get("launcher.work.cheat_damage_multiplier") == "3.0"

    def test_launcher_phase_dispatch(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        store = _fake_config(monkeypatch)
        store["launcher.work.cheat_damage"] = True
        store["cheat.disclaimer_accepted"] = True

        from webutils import CheatPluginHost
        cheat_core.unlock(key)
        # 已存在的用户值不被播种覆盖
        assert store.get("launcher.work.cheat_damage") is True
        mod = __import__("cheatcore.cheat_damage_hook", fromlist=["FakeManager"])
        mod.FakeManager._calls.clear()

        CheatPluginHost.run_launcher_phase("start")
        assert "start" in mod.FakeManager._calls
        CheatPluginHost.run_launcher_phase("stop")
        assert "stop" in mod.FakeManager._calls

    def test_launcher_phase_skipped_when_disabled_or_unconsented(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        store = _fake_config(monkeypatch)

        from webutils import CheatPluginHost
        cheat_core.unlock(key)  # 播种后 enabled=False
        mod = __import__("cheatcore.cheat_damage_hook", fromlist=["FakeManager"])
        mod.FakeManager._calls.clear()

        CheatPluginHost.run_launcher_phase("start")  # 未启用 → 跳过
        assert "start" not in mod.FakeManager._calls

        store["launcher.work.cheat_damage"] = True  # 启用但未同意风险 → 跳过
        CheatPluginHost.run_launcher_phase("start")
        assert "start" not in mod.FakeManager._calls

    def test_lock_clears_plugin_registry(self, tmp_path, monkeypatch, blob_env):
        src, key = _make_src(tmp_path)
        blob_env(build_blob(src, key.encode("utf-8")))
        _fake_config(monkeypatch)

        from webutils import CheatPluginHost
        cheat_core.unlock(key)
        assert CheatPluginHost.list()
        cheat_core.lock()
        assert CheatPluginHost.list() == []
