"""
tests/test_webutils_download.py
webutils 下载模块（function_llc / function_ourplay / function_ourplay_new）修复回归测试。
覆盖：
- 裸 raise（无 except 上下文）修复：错误必须带真实上下文消息
- OurPlay 新旧 API 请求体格式与超时设置
- 产物输出到配置的缓存目录（而非不可控的 CWD）
- zip 参考包临时解压目录的清理
"""
import json
import os
import shutil
import zipfile

import pytest

from globalManagers.ConfigManager import ConfigManager
from webFunc.GithubDownload import ReleaseInfo, ReleaseAsset
from webFunc import GithubDownload as GithubDownloadMod
from webutils import function_llc, function_ourplay, function_ourplay_new


# ========== 公共工具 ==========

def _make_asset(name):
    return ReleaseAsset(name=name, size=100, download_url="https://example.com/x",
                        content_type='', download_count=0, proxys=None)


def _make_release(asset):
    return ReleaseInfo(repo_owner="o", repo_name="r", tag_name="v1", name="n",
                       body="b", published_at="2024-01-01", prerelease=False,
                       draft=False, assets=[asset], proxys=None)


def _stub_llc_github(monkeypatch, asset):
    """替换 function_llc 的 GitHub 版本请求，返回固定资产。"""

    class FakeRequester:
        @staticmethod
        def update_config(*a, **k):
            pass

        @staticmethod
        def get_latest_release(*a, **k):
            return _make_release(asset)

    monkeypatch.setattr(GithubDownloadMod, "GithubRequester", FakeRequester)


def _write_workdir_zip(temp_dir):
    """创建含 transfile.zip 的工作目录（解压目标）。"""
    temp_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(temp_dir / "transfile.zip", "w") as zf:
        zf.writestr("a.txt", "x")


def _write_refer_zip(zip_path):
    """创建基板参考包 zip（带一层包裹目录）。"""
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Base/Data/story.json", json.dumps({"dataList": [{"id": "100"}]}))
        zf.writestr("Base/manifest.json", json.dumps({"v": 1}))


@pytest.fixture
def cache_dir_config(monkeypatch, tmp_path):
    """将配置的缓存目录指向临时目录，用于断言产物输出位置。"""
    monkeypatch.setattr(ConfigManager, "get",
                        lambda self, key, default=None:
                        str(tmp_path) if key == "cache_path" else default)
    return tmp_path


class FakePostResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


# ========== 修复1：裸 raise → 带上下文的错误消息 ==========

class TestBareRaiseWithContext:
    """所有不在 except 块内的 raise 必须携带具体失败原因。"""

    def test_llc_github_text_download_failure(self, monkeypatch, tmp_path):
        _stub_llc_github(monkeypatch, _make_asset("LimbusLocalize_v5.0.0.zip"))
        monkeypatch.setattr(function_llc, "download_with_github", lambda *a, **k: False)
        with pytest.raises(Exception, match="下载文本文件失败"):
            function_llc.function_llc_main("test", download_source="github",
                                           zip_type="zip", use_cache=False)

    def test_llc_github_font_download_failure(self, monkeypatch, tmp_path):
        _stub_llc_github(monkeypatch, _make_asset("LimbusLocalize_v5.0.0.7z"))
        calls = {"n": 0}

        def fake_download(*a, **k):
            calls["n"] += 1
            return calls["n"] == 1  # 文本成功，字体失败

        monkeypatch.setattr(function_llc, "download_with_github", fake_download)
        with pytest.raises(Exception, match="下载字体文件失败"):
            function_llc.function_llc_main("test", download_source="github",
                                           zip_type="seven", use_cache=False)

    def test_llc_api_text_download_failure(self, monkeypatch, tmp_path):
        class FakeNote:
            def __init__(self, *a, **k):
                pass

            def fetch_note_info(self):
                pass

            note_content = json.dumps({
                "llc_download_mirror": {"zip": {"direct": "https://example.com/x.zip"}}
            })

        monkeypatch.setattr(function_llc, "Note", FakeNote)
        monkeypatch.setattr(function_llc, "download_with", lambda *a, **k: False)
        with pytest.raises(Exception, match="下载文本文件失败"):
            function_llc._download_from_api(str(tmp_path), "test", "zip",
                                            True, False, True, "")

    def test_ourplay_pc_fetch_info_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(function_ourplay, "download_ourplay", lambda: None)
        with pytest.raises(Exception, match="获取 OurPlay 下载信息失败"):
            function_ourplay.function_ourplay_main("test")

    def test_ourplay_pc_download_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(function_ourplay, "download_ourplay",
                            lambda: ("https://example.com/x.zip", "md5", 100))
        monkeypatch.setattr(function_ourplay, "download_with", lambda *a, **k: False)
        with pytest.raises(Exception, match="下载 OurPlay 汉化包失败"):
            function_ourplay.function_ourplay_main("test")

    def test_ourplay_pc_api_download_failure(self, monkeypatch, tmp_path):
        class FakeNote:
            def __init__(self, *a, **k):
                pass

            def fetch_note_info(self):
                pass

            note_content = json.dumps({"ourplay_download_url": "https://example.com/x.zip"})

        monkeypatch.setattr(function_ourplay, "Note", FakeNote)
        monkeypatch.setattr(function_ourplay, "download_with", lambda *a, **k: False)
        with pytest.raises(Exception, match="下载 OurPlay 汉化包失败"):
            function_ourplay.function_ourplay_api("test")

    def test_ourplay_pc_zip_failure(self, monkeypatch, tmp_path):
        _write_workdir_zip(tmp_path)
        monkeypatch.setattr(function_ourplay, "zip_folder", lambda *a, **k: False)
        with pytest.raises(Exception, match="打包文件时出现错误"):
            function_ourplay._process_ourplay_package(str(tmp_path), "test", "keep", "")

    def test_ourplay_new_fetch_info_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(function_ourplay_new, "download_ourplay", lambda official=True: None)
        with pytest.raises(Exception, match="获取 OurPlay 下载信息失败"):
            function_ourplay_new.function_ourplay_new_main("test")

    def test_ourplay_new_download_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(function_ourplay_new, "download_ourplay",
                            lambda official=True: ("https://example.com/x.zip", "md5", 100))
        monkeypatch.setattr(function_ourplay_new, "download_with", lambda *a, **k: False)
        with pytest.raises(Exception, match="下载 OurPlay 汉化包失败"):
            function_ourplay_new.function_ourplay_new_main("test", check_hash=False)

    def test_ourplay_new_zip_failure(self, cache_dir_config, monkeypatch, tmp_path):
        _write_workdir_zip(tmp_path)
        monkeypatch.setattr(function_ourplay_new, "_convert_new_package",
                            lambda td, rp: str(tmp_path / "ourplay"))
        captured = {}

        def fake_zip_folder(folder, out):
            captured["out"] = out
            return False

        monkeypatch.setattr(function_ourplay_new, "zip_folder", fake_zip_folder)
        with pytest.raises(Exception, match="打包文件时出现错误"):
            function_ourplay_new._process_ourplay_package(str(tmp_path), "test", "keep", "")
        assert captured["out"] == os.path.join(str(tmp_path), "ourplay.zip")


# ========== 修复2：请求体格式与超时 ==========

class TestOurplayRequestFormat:
    """旧版 PC API 用 JSON 请求体；新版 Android API 用 form-urlencoded（dict）。"""

    def test_old_api_posts_json_body_with_timeout(self, monkeypatch):
        captured = {}

        def fake_post(url, headers=None, data=None, timeout=None):
            captured.update(url=url, headers=headers, data=data, timeout=timeout)
            return FakePostResponse({"code": 1, "data": {"url": "http://x", "md5": "m", "size": 1}})

        monkeypatch.setattr(function_ourplay.requests, "post", fake_post)
        assert function_ourplay.download_ourplay() == ("http://x", "m", 1)
        assert isinstance(captured["data"], str)
        assert captured["headers"]["Content-Type"] == "application/json"
        assert captured["timeout"] == (10, 60)

    def test_new_api_posts_form_body_with_timeout(self, monkeypatch):
        captured = {}

        def fake_post(url, headers=None, data=None, timeout=None):
            captured.update(url=url, headers=headers, data=data, timeout=timeout)
            return FakePostResponse({"code": 1, "data": {"url": "http://x", "md5": "m", "size": 1}})

        monkeypatch.setattr(function_ourplay_new.requests, "post", fake_post)
        assert function_ourplay_new.download_ourplay(official=True) == ("http://x", "m", 1)
        assert isinstance(captured["data"], dict)
        assert "Content-Type" not in captured["headers"]
        assert captured["timeout"] == (10, 60)

    def test_check_ver_posts_also_have_timeout(self, monkeypatch):
        captured = []

        def fake_post(url, headers=None, data=None, timeout=None):
            captured.append(timeout)
            return FakePostResponse({"data": {"versionCode": "1.0.0"}})

        monkeypatch.setattr(function_ourplay.requests, "post", fake_post)
        monkeypatch.setattr(function_ourplay_new.requests, "post", fake_post)
        assert function_ourplay.check_ver_ourplay() == "1.0.0"
        assert function_ourplay_new.check_ver_ourplay_new() == "1.0.0"
        assert captured == [(10, 60), (10, 60)]


# ========== 修复3：产物输出到配置的缓存目录 ==========

class TestOutputToConfiguredDir:
    """产物不得写入不可控的 CWD，必须落在配置的缓存目录下。"""

    def test_llc_dump_default_writes_to_cache_dir(self, cache_dir_config, tmp_path, monkeypatch):
        text = tmp_path / "text.7z"
        font = tmp_path / "font.7z"
        text.write_bytes(b"t")
        font.write_bytes(b"f")
        captured = []
        real_copy2 = shutil.copy2

        def fake_copy2(src, dst):
            captured.append(dst)
            return real_copy2(src, dst)

        monkeypatch.setattr(function_llc.shutil, "copy2", fake_copy2)
        function_llc._process_llc_package(str(tmp_path), "test", str(text), str(font),
                                          "pkg.7z", False, "", True)
        assert len(captured) == 2
        assert captured[0] == os.path.join(str(tmp_path), "pkg.7z")
        assert captured[1] == os.path.join(str(tmp_path), "LLCCN-Font.7z")
        assert os.path.exists(captured[0]) and os.path.exists(captured[1])

    def test_llc_repack_outputs_to_cache_dir(self, cache_dir_config, tmp_path, monkeypatch):
        text = tmp_path / "text.7z"
        font = tmp_path / "font.7z"
        text.write_bytes(b"t")
        font.write_bytes(b"f")
        captured = {}

        def fake_zip_folder(folder, out):
            captured["out"] = out
            return True

        monkeypatch.setattr(function_llc, "decompress_by_extension", lambda *a, **k: None)
        monkeypatch.setattr(function_llc, "zip_folder", fake_zip_folder)
        result = function_llc._process_llc_package(str(tmp_path), "test", str(text), str(font),
                                                   "pkg.7z", True, str(font), False)
        assert captured["out"] == os.path.join(str(tmp_path), "pkg.zip")
        assert result == captured["out"]

    def test_ourplay_pc_outputs_to_cache_dir(self, cache_dir_config, tmp_path, monkeypatch):
        _write_workdir_zip(tmp_path)
        captured = {}

        def fake_zip_folder(folder, out):
            captured["out"] = out
            return True

        monkeypatch.setattr(function_ourplay, "zip_folder", fake_zip_folder)
        function_ourplay._process_ourplay_package(str(tmp_path), "test", "keep", "")
        assert captured["out"] == os.path.join(str(tmp_path), "ourplay.zip")


# ========== 修复4：zip 参考包临时目录清理 ==========

class TestReferPackageCleanup:
    """_resolve_refer_package 返回清理句柄，_convert_new_package 结束后删除临时目录。"""

    def test_resolve_zip_returns_cleanup_handle(self, tmp_path):
        zip_path = tmp_path / "refer.zip"
        _write_refer_zip(zip_path)
        root, cleanup = function_ourplay_new._resolve_refer_package(str(zip_path))
        assert cleanup and os.path.isdir(cleanup)
        assert root == os.path.join(cleanup, "Base")
        assert os.path.isfile(os.path.join(root, "Data", "story.json"))
        shutil.rmtree(cleanup, ignore_errors=True)

    def test_resolve_dir_returns_none_cleanup(self, tmp_path):
        d = tmp_path / "refdir"
        d.mkdir()
        root, cleanup = function_ourplay_new._resolve_refer_package(str(d))
        assert root == str(d)
        assert cleanup is None

    def test_resolve_none_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ConfigManager, "get",
                            lambda self, key, default=None:
                            "" if key in ("ourplay.refer_package", "game_path") else default)
        with pytest.raises(Exception, match="未找到参考包"):
            function_ourplay_new._resolve_refer_package("")

    def test_bad_zip_cleans_temp_dir(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not a zip")
        fake_tmp = tmp_path / "fake_tmp"
        monkeypatch.setattr(function_ourplay_new.tempfile, "mkdtemp", lambda **k: str(fake_tmp))
        with pytest.raises(Exception):
            function_ourplay_new._resolve_refer_package(str(bad))
        assert not os.path.exists(str(fake_tmp))

    @pytest.fixture
    def fake_mkdtemp(self, monkeypatch, tmp_path):
        """将 mkdtemp 限定到临时根目录，便于断言清理结果。"""
        fake_root = tmp_path / "fake_tmp"
        fake_root.mkdir()
        counter = {"n": 0}

        def _fake_mkdtemp(**kwargs):
            counter["n"] += 1
            d = fake_root / f"refer_pkg_{counter['n']}"
            d.mkdir()
            return str(d)

        monkeypatch.setattr(function_ourplay_new.tempfile, "mkdtemp", _fake_mkdtemp)
        return fake_root

    def test_convert_cleans_temp_dir_after_success(self, tmp_path, fake_mkdtemp):
        zip_path = tmp_path / "refer.zip"
        _write_refer_zip(zip_path)
        temp_dir = tmp_path / "work"
        temp_dir.mkdir()
        hash_dir = temp_dir / "com.ProjectMoon.LimbusCompany"
        hash_dir.mkdir()
        (hash_dir / "hash1.json").write_text(json.dumps({"dataList": [{"id": "100"}]}),
                                             encoding="utf-8")
        ourplay_root = function_ourplay_new._convert_new_package(str(temp_dir), str(zip_path))
        assert os.path.isdir(ourplay_root)
        assert list(fake_mkdtemp.iterdir()) == [], "转换完成后临时解压目录应被清理"
        out_file = os.path.join(ourplay_root, "Data", "story.json")
        assert os.path.isfile(out_file)
        assert json.load(open(out_file, encoding="utf-8")) == {"dataList": [{"id": "100"}]}

    def test_convert_cleans_temp_dir_after_failure(self, tmp_path, fake_mkdtemp):
        zip_path = tmp_path / "refer.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("Base/manifest.json", json.dumps({"v": 1}))
        temp_dir = tmp_path / "work"
        temp_dir.mkdir()
        with pytest.raises(Exception, match="参考包中未找到任何有效的 JSON 文件"):
            # 参考包无有效 JSON → 转换抛错，临时目录仍应被清理
            function_ourplay_new._convert_new_package(str(temp_dir), str(zip_path))
        assert list(fake_mkdtemp.iterdir()) == [], "转换失败时临时解压目录也应被清理"
