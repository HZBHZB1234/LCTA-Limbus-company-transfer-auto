"""tests/test_lanzou_tiaozhua_replace.py

调爪「替换」文本包（3/4/5/7/8）下载与应用逻辑回归测试。
覆盖：
- 前缀挑选文件（find_replace_file）
- 版本号解析与缺失包跳过
- 选择性解压（只拷贝 `文件/*.json`，跳过 python/ 与根级文件）
- 目标语言目录解析（lang/config.json 的 lang 值）
- 路径穿越成员拒绝
"""
import json
import zipfile

import pytest

from webutils.function_lanzou_tiaozhua import (
    REPLACE_PACKAGE_PREFIXES,
    _REPLACE_VERSION_RE,
    _replace_package_version,
    _select_replace_packages,
    find_replace_file,
    install_replace_package,
    resolve_replace_target_dir,
)


def _file(file_name, file_id="abc123"):
    return {"fileName": file_name, "fileId": file_id, "size": 123456}


# ========== 前缀挑选 ==========

class TestFindReplaceFile:
    def test_matches_prefix(self):
        fl = [
            _file("0.特殊 推荐 巴士文本自动替换脚本26.8.7.7z"),
            _file("3.彩色（替换）BattleSpeechBubbleDlg26.8.6.zip"),
            _file("8.旧翻译版 主文件不包含 彩色气（替换）BattleSpeechBubbleDlg26.8.6.zip"),
        ]
        assert find_replace_file(fl, "3.")["fileId"] == "abc123"
        assert find_replace_file(fl, "8.")["fileId"] == "abc123"

    def test_not_found_returns_none(self):
        fl = [_file("3.彩色（替换）BattleSpeechBubbleDlg26.8.6.zip")]
        assert find_replace_file(fl, "4.") is None

    def test_prefixes_exclude_package_6(self):
        assert 6 not in REPLACE_PACKAGE_PREFIXES
        assert sorted(REPLACE_PACKAGE_PREFIXES) == [3, 4, 5, 7, 8]


# ========== 气泡互斥选择 ==========

class TestSelectReplacePackages:
    def test_single_bubble_kept(self):
        assert _select_replace_packages({"replace_4": True}) == [4]

    def test_non_bubble_multiple(self):
        cfg = {"replace_5": True, "replace_7": True}
        assert _select_replace_packages(cfg) == [5, 7]

    def test_bubble_exclusive_keeps_min(self):
        cfg = {"replace_3": True, "replace_4": True, "replace_8": True,
               "replace_5": True}
        assert _select_replace_packages(cfg) == [3, 5]

    def test_two_bubbles_keeps_min(self):
        cfg = {"replace_4": True, "replace_8": True}
        assert _select_replace_packages(cfg) == [4]

    def test_none_selected(self):
        assert _select_replace_packages({"replace_3": False, "replace_5": False}) == []

    def test_unknown_key_ignored(self):
        assert _select_replace_packages({"replace_9": True, "replace_5": True}) == [5]


# ========== 版本号解析 ==========

class TestReplaceVersion:
    def test_extract_date(self):
        assert _replace_package_version(
            _file("5.随机加载文本（替换）26.8.6.zip")) == "26.8.6"

    def test_fallback_to_size(self):
        assert _replace_package_version(_file("5.随机加载文本.zip")) == "123456"

    def test_regex_matches_real_names(self):
        names = [
            "3.彩色（替换）BattleSpeechBubbleDlg26.8.6.zip",
            "7.事件美化（替换）26.8.6.zip",
        ]
        for n in names:
            assert _REPLACE_VERSION_RE.search(n)


# ========== 目标目录解析 ==========

class TestResolveTargetDir:
    def test_reads_config_lang(self, tmp_path):
        lang = tmp_path / "LimbusCompany_Data" / "lang"
        active = lang / "LLC_zh-CN"
        active.mkdir(parents=True)
        (lang / "config.json").write_text(
            json.dumps({"lang": "LLC_zh-CN"}), encoding="utf-8")
        assert resolve_replace_target_dir(str(tmp_path)) == active

    def test_missing_config_raises(self, tmp_path):
        (tmp_path / "LimbusCompany_Data" / "lang").mkdir(parents=True)
        with pytest.raises(ValueError, match="config.json"):
            resolve_replace_target_dir(str(tmp_path))


# ========== 选择性解压 ==========

class TestInstallReplacePackage:
    @pytest.fixture
    def lang_env(self, tmp_path, monkeypatch):
        lang = tmp_path / "LimbusCompany_Data" / "lang"
        active = lang / "LLC_zh-CN"
        active.mkdir(parents=True)
        (lang / "config.json").write_text(
            json.dumps({"lang": "LLC_zh-CN"}), encoding="utf-8")
        return str(tmp_path), active

    def _make_zip(self, zip_path):
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("文件/BattleSpeechBubbleDlg.json",
                        json.dumps({"dataList": [{"id": "1"}]}, ensure_ascii=False))
            zf.writestr("文件/BattleSpeechBubbleDlg-exme.json",
                        json.dumps({"dataList": [{"id": "2"}]}, ensure_ascii=False))
            zf.writestr("python/python.exe", b"bundled-runtime-should-be-skipped")
            zf.writestr("jieya.py", "print('skipped')")
            zf.writestr("点击自动安装（先解压）.bat", "@echo off")

    def test_copies_json_only(self, lang_env, tmp_path, monkeypatch):
        game_path, active = lang_env
        zip_path = tmp_path / "pkg.zip"
        self._make_zip(zip_path)

        class _LM:
            @staticmethod
            def check_running(modal_id):
                pass

            def log_modal_process(self, msg, modal_id):
                pass

        monkeypatch.setattr(
            "webutils.function_lanzou_tiaozhua._log_manager", _LM())
        installed = install_replace_package("test", zip_path, game_path)

        assert installed == 2
        assert (active / "BattleSpeechBubbleDlg.json").exists()
        assert (active / "BattleSpeechBubbleDlg-exme.json").exists()
        # 根级目录不应出现冗余文件
        assert not (active / "python").exists()
        assert not (active / "jieya.py").exists()
        data = json.loads((active / "BattleSpeechBubbleDlg.json").read_text(encoding="utf-8"))
        assert data["dataList"][0]["id"] == "1"

    def test_path_traversal_rejected(self, lang_env, tmp_path, monkeypatch):
        game_path, active = lang_env
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("文件/../../escape.json", "{}")
        with pytest.raises(ValueError, match="不安全的路径"):
            install_replace_package("test", zip_path, game_path)

    def test_no_json_raises(self, lang_env, tmp_path):
        game_path, _ = lang_env
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("python/python.exe", b"x")
        with pytest.raises(ValueError, match="未找到可应用的文本文件"):
            install_replace_package("test", zip_path, game_path)
