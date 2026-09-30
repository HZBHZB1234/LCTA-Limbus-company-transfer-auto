# -*- coding: utf-8 -*-
"""P6 路径安全与安全解压测试（plan 10.3 / 16.4）。

这一层是「安装器会不会毁掉用户系统」的分界线，所以测试重点是**恶意输入**：
Zip Slip、UNC、ADS、设备名、链接、压缩炸弹、大小写冲突。

不执行任何解压出来的文件（plan 10.3 第 10 条）。
"""
import os
import zipfile
from pathlib import Path

import pytest

from webutils.toolbox import archive, paths


def _make_zip(path: Path, members, *, compress=zipfile.ZIP_DEFLATED) -> Path:
    with zipfile.ZipFile(str(path), "w", compress) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return path


class TestSanitizeMemberName:
    @pytest.mark.parametrize("name,expected", [
        ("a/b.txt", "a/b.txt"),
        ("a\\b.txt", "a/b.txt"),          # 反斜杠归一化
        ("a//b.txt", "a/b.txt"),          # 空段跳过
        ("a/./b.txt", "a/b.txt"),         # '.' 跳过
        ("BepInEx/plugins/x.dll", "BepInEx/plugins/x.dll"),
    ])
    def test_accepts_safe_names(self, name, expected):
        assert paths.sanitize_member_name(name) == expected

    @pytest.mark.parametrize("name", [
        "../evil.txt",                    # Zip Slip
        "a/../../evil.txt",
        "/abs/evil.txt",                  # 绝对路径
        "\\abs\\evil.txt",
        "C:/Windows/evil.txt",            # 盘符
        "C:\\Windows\\evil.txt",
        "//server/share/evil.txt",        # UNC
        "\\\\server\\share\\evil.txt",
        "a/evil.txt:hidden",              # ADS
        "evil.txt:hidden",
        "CON", "NUL", "COM1", "LPT9",     # 保留设备名
        "NUL.txt", "con.dll",             # 带扩展名仍是设备名
        "a/evil.txt.",                    # 尾点
        "a/evil.txt ",                    # 尾空格
        "a/ev\x00il.txt",                 # NUL
        "a/ev<il.txt",                    # 非法字符
        "",                               # 空
        "..",                             # 只有上跳
        "a/..",                           # 净化后为空
    ])
    def test_rejects_unsafe_names(self, name):
        with pytest.raises(paths.UnsafePathError):
            paths.sanitize_member_name(name)

    def test_does_not_silently_clean_traversal(self):
        """上跳必须**报错**，而不是被静默「清理掉」后继续。

        静默清理会让攻击者的输入看起来正常，也让审计看不到异常。
        """
        with pytest.raises(paths.UnsafePathError):
            paths.sanitize_member_name("../../etc/passwd")


class TestIsWithin:
    def test_sibling_prefix_is_not_within(self, tmp_path):
        """``C:\\Games\\LCTA-evil`` 不在 ``C:\\Games\\LCTA`` 之内。

        这是 ``str.startswith`` 写法会漏掉的经典越界。
        """
        base = tmp_path / "LCTA"
        sibling = tmp_path / "LCTA-evil"
        base.mkdir()
        sibling.mkdir()
        assert not paths.is_within(sibling, base)
        assert paths.is_within(base, base)

    def test_nested_is_within(self, tmp_path):
        base = tmp_path / "root"
        nested = base / "a" / "b"
        nested.mkdir(parents=True)
        assert paths.is_within(nested, base)

    def test_unrelated_is_not_within(self, tmp_path):
        assert not paths.is_within(tmp_path / "x", tmp_path / "y")


class TestResolveWithin:
    def test_resolves_inside(self, tmp_path):
        got = paths.resolve_within(tmp_path, "a/b.txt")
        assert paths.is_within(got, tmp_path)

    def test_rejects_traversal(self, tmp_path):
        with pytest.raises(paths.UnsafePathError):
            paths.resolve_within(tmp_path, "../outside.txt")

    def test_rejects_absolute(self, tmp_path):
        with pytest.raises(paths.UnsafePathError):
            paths.resolve_within(tmp_path, "C:/Windows/x.txt")


class TestManagedLayout:
    def test_disabled_dir_is_outside_bepinex_plugins(self, tmp_path):
        """停用目录必须在 BepInEx 加载树**之外**。

        只改配置布尔值不够 —— BepInEx 仍会加载 plugins 下的 DLL。
        """
        game = tmp_path / "game"
        game.mkdir()
        d = paths.disabled_dir(game, "tool-a", "r1")
        plugins = game / "BepInEx" / "plugins"
        assert not paths.is_within(d, plugins)
        assert paths.is_within(d, paths.toolbox_dir(game))

    def test_plugin_dir_layout(self, tmp_path):
        game = tmp_path / "game"
        game.mkdir()
        p = paths.plugin_dir(game, "tool-a")
        assert p.parts[-4:] == ("BepInEx", "plugins", "LCTA", "tool-a")

    @pytest.mark.parametrize("bad", ["../evil", "a/b", "A B", "", "tool..a", "x" * 80])
    def test_rejects_unsafe_ids(self, tmp_path, bad):
        """工具 ID 必须走白名单：否则 ID 里塞 '..' 就能让受管路径逃逸。"""
        with pytest.raises(paths.UnsafePathError):
            paths.plugin_dir(tmp_path, bad)

    def test_assert_managed_target_rejects_outside(self, tmp_path):
        game = tmp_path / "game"
        game.mkdir()
        outside = tmp_path / "important.txt"
        outside.write_text("data")
        with pytest.raises(paths.UnsafePathError):
            paths.assert_managed_target(game, outside)

    def test_assert_managed_target_allows_managed(self, tmp_path):
        game = tmp_path / "game"
        game.mkdir()
        paths.assert_managed_target(game, paths.disabled_dir(game, "t", "r1"))


class TestValidateGameRoot:
    def test_accepts_normal_dir(self, tmp_path):
        game = tmp_path / "game"
        game.mkdir()
        assert paths.validate_game_root(game) == game.resolve()

    def test_rejects_missing(self, tmp_path):
        with pytest.raises(paths.UnsafePathError):
            paths.validate_game_root(tmp_path / "nope")

    def test_rejects_file(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(paths.UnsafePathError):
            paths.validate_game_root(f)

    def test_rejects_drive_root(self):
        if os.name != "nt":
            pytest.skip("仅 Windows")
        with pytest.raises(paths.UnsafePathError):
            paths.validate_game_root("C:\\")


class TestInspectArchive:
    def test_accepts_clean_archive(self, tmp_path):
        z = _make_zip(tmp_path / "ok.zip", [("BepInEx/plugins/x.dll", b"data")])
        cleaned = archive.inspect_archive(z)
        assert cleaned == [("BepInEx/plugins/x.dll", 4)]

    def test_rejects_zip_slip(self, tmp_path):
        z = _make_zip(tmp_path / "slip.zip", [("../evil.txt", b"x")])
        with pytest.raises(archive.ArchiveError):
            archive.inspect_archive(z)

    def test_rejects_ads_member(self, tmp_path):
        z = _make_zip(tmp_path / "ads.zip", [("evil.txt:hidden", b"x")])
        with pytest.raises(archive.ArchiveError):
            archive.inspect_archive(z)

    def test_rejects_reserved_device_name(self, tmp_path):
        z = _make_zip(tmp_path / "dev.zip", [("NUL.dll", b"x")])
        with pytest.raises(archive.ArchiveError):
            archive.inspect_archive(z)

    def test_rejects_too_many_members(self, tmp_path):
        z = _make_zip(tmp_path / "many.zip", [(f"f{i}.txt", b"x") for i in range(50)])
        with pytest.raises(archive.ArchiveError):
            archive.inspect_archive(z, max_members=10)

    def test_rejects_oversized_single_member(self, tmp_path):
        z = _make_zip(tmp_path / "big.zip", [("big.bin", b"x" * 5000)])
        with pytest.raises(archive.ArchiveError):
            archive.inspect_archive(z, max_single=1000)

    def test_rejects_oversized_total(self, tmp_path):
        z = _make_zip(tmp_path / "total.zip", [(f"f{i}.bin", b"x" * 400) for i in range(10)])
        with pytest.raises(archive.ArchiveError):
            archive.inspect_archive(z, max_total=1000)

    def test_rejects_zip_bomb_ratio(self, tmp_path):
        """高压缩比 = 炸弹特征（这里 100KB 的零字节压缩后极小）。"""
        z = _make_zip(tmp_path / "bomb.zip", [("zeros.bin", b"\x00" * 200000)])
        with pytest.raises(archive.ArchiveError) as ei:
            archive.inspect_archive(z, max_ratio=50)
        assert "压缩" in str(ei.value)

    def test_rejects_case_collision(self, tmp_path):
        """大小写冲突在 NTFS 上是同一路径，会互相覆盖。"""
        z = _make_zip(tmp_path / "case.zip", [("A.dll", b"1"), ("a.dll", b"2")])
        with pytest.raises(archive.ArchiveError):
            archive.inspect_archive(z)

    def test_rejects_corrupt_archive(self, tmp_path):
        p = tmp_path / "corrupt.zip"
        p.write_bytes(b"not a zip at all")
        with pytest.raises(archive.ArchiveError):
            archive.inspect_archive(p)

    def test_rejects_corrupt_member_crc(self, tmp_path):
        """CRC 损坏的成员必须被拒（否则安装出「成功但文件坏了」）。"""
        p = tmp_path / "badcrc.zip"
        with zipfile.ZipFile(str(p), "w") as zf:
            zf.writestr("a.txt", b"hello")
        # 篡改数据区，破坏 CRC
        raw = bytearray(p.read_bytes())
        idx = raw.find(b"hello")
        raw[idx:idx + 5] = b"HELLO"
        p.write_bytes(bytes(raw))
        with pytest.raises(archive.ArchiveError):
            archive.inspect_archive(p)


class TestExtractZipSafe:
    def test_extracts_cleanly(self, tmp_path):
        z = _make_zip(tmp_path / "ok.zip", [
            ("BepInEx/plugins/x.dll", b"data"),
            ("BepInEx/config/x.cfg", b"cfg"),
        ])
        dest = tmp_path / "dest"
        written = archive.extract_zip_safe(z, dest)
        assert len(written) == 2
        assert (dest / "BepInEx" / "plugins" / "x.dll").read_bytes() == b"data"

    def test_writes_nothing_on_unsafe_member(self, tmp_path):
        """先检查后解压：不安全包不得留下解压到一半的目录。"""
        z = _make_zip(tmp_path / "mix.zip", [
            ("good.txt", b"ok"),
            ("../evil.txt", b"bad"),
        ])
        dest = tmp_path / "dest"
        with pytest.raises(archive.ArchiveError):
            archive.extract_zip_safe(z, dest)
        assert not (dest / "good.txt").exists(), "应在写任何文件之前就拒绝"

    def test_layout_whitelist_rejects_outside_prefix(self, tmp_path):
        """底座包只允许写入声明的路径前缀内。"""
        z = _make_zip(tmp_path / "base.zip", [
            ("BepInEx/core/x.dll", b"1"),
            ("winhttp.dll", b"2"),
        ])
        dest = tmp_path / "dest"
        with pytest.raises(archive.ArchiveError):
            archive.extract_zip_safe(z, dest, allowed_prefixes=["BepInEx"])

    def test_layout_whitelist_allows_declared(self, tmp_path):
        z = _make_zip(tmp_path / "base.zip", [
            ("BepInEx/core/x.dll", b"1"),
            ("winhttp.dll", b"2"),
        ])
        dest = tmp_path / "dest"
        written = archive.extract_zip_safe(
            z, dest, allowed_prefixes=["BepInEx", "winhttp.dll"]
        )
        assert len(written) == 2

    def test_backslash_member_lands_in_same_place(self, tmp_path):
        """反斜杠成员名必须归一化到同一位置，不能变成「带反斜杠的文件名」。"""
        z = _make_zip(tmp_path / "bs.zip", [("BepInEx\\plugins\\x.dll", b"d")])
        dest = tmp_path / "dest"
        archive.extract_zip_safe(z, dest)
        assert (dest / "BepInEx" / "plugins" / "x.dll").exists()

    def test_cancel_stops_extraction(self, tmp_path):
        z = _make_zip(tmp_path / "c.zip", [(f"f{i}.txt", b"x") for i in range(5)])
        dest = tmp_path / "dest"
        calls = {"n": 0}

        def _cancel():
            calls["n"] += 1
            return calls["n"] > 2

        with pytest.raises(archive.ArchiveError):
            archive.extract_zip_safe(z, dest, should_cancel=_cancel)

    def test_progress_reports_total(self, tmp_path):
        z = _make_zip(tmp_path / "p.zip", [("a.txt", b"12345"), ("b.txt", b"123")])
        dest = tmp_path / "dest"
        seen = []
        archive.extract_zip_safe(z, dest, progress=lambda n, d, t: seen.append((n, d, t)))
        assert seen[-1][1] == seen[-1][2] == 8


class TestLinkSafety:
    def test_rejects_dest_that_is_link(self, tmp_path):
        """目标目录本身是 junction/符号链接 → 中止（防顺链写出区外）。"""
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("当前环境不支持创建符号链接")
        z = _make_zip(tmp_path / "ok.zip", [("a.txt", b"x")])
        with pytest.raises(archive.ArchiveError):
            archive.extract_zip_safe(z, link)

    def test_rejects_symlinked_parent(self, tmp_path):
        """路径链上含指向区外的链接 → 中止。"""
        outside = tmp_path / "outside"
        outside.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        try:
            (dest / "esc").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("当前环境不支持创建符号链接")
        z = _make_zip(tmp_path / "ok.zip", [("esc/evil.txt", b"x")])
        with pytest.raises(archive.ArchiveError):
            archive.extract_zip_safe(z, dest)
        assert not (outside / "evil.txt").exists()