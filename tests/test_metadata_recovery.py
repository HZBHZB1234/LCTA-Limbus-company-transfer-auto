# -*- coding: utf-8 -*-
"""webutils.metadata_recovery 测试（v2 universal 管线，全部合成数据）。

覆盖：PE 解析、xorshift 模板扫描、三元组布局自动判定、结构验证、
31 节无参考求解 + 标准文件重建 + 四重自验证、流水线包装（输入校验/
期望 SHA 门/产物落盘）、游戏文件推导。

依赖 capstone（缺失时跳过 universal 核心测试，包装层测试不受影响）。
"""
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

import pytest

from webutils.metadata_recovery import (
    capstone_available,
    derive_game_files,
    output_dir,
    run_recovery,
)
from webutils.metadata_recovery import install_capstone
from webutils.metadata_recovery.pipeline import capstone_available as _pipeline_capstone
from webutils.metadata_recovery.universal import capstone_env
from webutils.metadata_recovery.universal import extract_disasm
from webutils.metadata_recovery.universal import init_locator
from webutils.metadata_recovery.universal.layouts import (
    decrypt_bytes,
    detect_layout,
    next_xorshift64,
    parse_triplets,
)
from webutils.metadata_recovery.universal.pe_loader import load_pe
from webutils.metadata_recovery.universal.rebuild_validate import (
    rebuild_standard,
    validate_standard,
)
from webutils.metadata_recovery.universal.solve_versioned import (
    _rec_of,
    _slot_candidates,
    solve,
)
from webutils.metadata_recovery.universal.verify_structural import (
    VERDICT_FAIL,
    VERDICT_PASS,
    verify,
)
from webutils.metadata_recovery.universal.versions import V39_NAMES
from webutils.metadata_recovery.universal.xorshift_scan import scan, scan_pe

TABLE_ZERO = "00" * 256  # 全零表 = 解密恒等，便于合成数据

requires_capstone = pytest.mark.skipif(
    not capstone_available(), reason="capstone 未安装（Metadata 恢复需要）")


# ------------------------------------------------------------- 工具函数

def _build_synthetic_pe(path, text_bytes=b""):
    """最小 PE32+：MZ + PE 头 + 1 个 .text 节。

    text_bytes 填充在 .text 起始处，其后补 0xAB。"""
    image_base = 0x180000000
    rva = 0x1000
    raw_off = 0x200
    raw_size = max(0x100, len(text_bytes) + 0x100)
    pe_size = raw_off + raw_size

    data = bytearray(pe_size)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)  # e_lfanew
    pe_off = 0x80
    data[pe_off:pe_off + 4] = b"PE\0\0"
    struct.pack_into("<H", data, pe_off + 4, 0x8664)  # machine AMD64
    struct.pack_into("<H", data, pe_off + 6, 1)  # num sections
    struct.pack_into("<H", data, pe_off + 20, 0xF0)  # SizeOfOptionalHeader
    opt_off = pe_off + 24
    struct.pack_into("<H", data, opt_off, 0x20B)  # opt magic PE32+
    struct.pack_into("<Q", data, opt_off + 24, image_base)
    section_off = opt_off + 240
    struct.pack_into("<8s", data, section_off, b".text\0\0\0")
    struct.pack_into("<I", data, section_off + 8, raw_size)  # VirtualSize
    struct.pack_into("<I", data, section_off + 12, rva)  # VirtualAddress
    struct.pack_into("<I", data, section_off + 16, raw_size)  # SizeOfRawData
    struct.pack_into("<I", data, section_off + 20, raw_off)  # PointerToRawData
    data[raw_off:raw_off + len(text_bytes)] = text_bytes
    for i in range(raw_off + len(text_bytes), pe_size):
        data[i] = 0xAB
    Path(path).write_bytes(bytes(data))
    return image_base, rva


# 一步 xorshift(13,7,17) 的 MSVC 展开模板字节（rax 寄存器编码）
XORSHIFT_TEMPLATE_BYTES = bytes.fromhex(
    "48C1E00D"   # shl rax, 0Dh
    "4831C0"     # xor rax, rax
    "4889C0"     # mov rax, rax
    "48C1E807"   # shr rax, 07h
    "4831C0"     # xor rax, rax
    "4889C0"     # mov rax, rax
    "48C1E011"   # shl rax, 11h
    "4831C0"     # xor rax, rax
)


# ------------------------------------------------------------- PE / 扫描

@requires_capstone
class TestPELoader:
    def test_load_synthetic_pe(self, tmp_path):
        dll = tmp_path / "GameAssembly.dll"
        image_base, rva = _build_synthetic_pe(dll, b"\x90" * 16)
        image = load_pe(str(dll))
        assert image.image_base == image_base
        assert image.text_section.name == ".text"
        assert image.text_section.virtual_address == rva
        assert image.bytes_at_va(image_base + rva, 4) == b"\x90" * 4
        assert image.va_to_off(image_base + rva) == image.text_section.raw_offset

    def test_bad_magic(self, tmp_path):
        dll = tmp_path / "bad.dll"
        dll.write_bytes(b"MZ" + b"\x00" * 64)
        with pytest.raises(ValueError):
            load_pe(str(dll))


@requires_capstone
class TestXorshiftScan:
    def test_template_bytes_scan_raw(self):
        base = 0x180001000
        hits = scan(XORSHIFT_TEMPLATE_BYTES * 3 + b"\x00" * 8, base)
        assert hits == [base, base + len(XORSHIFT_TEMPLATE_BYTES),
                        base + len(XORSHIFT_TEMPLATE_BYTES) * 2]

    def test_scan_pe(self, tmp_path):
        dll = tmp_path / "GameAssembly.dll"
        image_base, rva = _build_synthetic_pe(dll, XORSHIFT_TEMPLATE_BYTES)
        image = load_pe(str(dll))
        hits = scan_pe(image)
        assert hits == [image_base + rva]

    def test_no_hits(self, tmp_path):
        dll = tmp_path / "GameAssembly.dll"
        image_base, rva = _build_synthetic_pe(dll, b"\x90" * 64)
        image = load_pe(str(dll))
        assert scan_pe(image) == []


# ------------------------------------------------------------- 布局

@requires_capstone
class TestLayouts:
    def test_next_xorshift64_changes_state(self):
        assert next_xorshift64(0x1) != 0x1
        assert next_xorshift64(0) == 0  # 零状态不动

    def test_decrypt_identity_with_zero_table(self):
        assert decrypt_bytes(b"\x01\x02\x03", 0x1234, bytes(256)) == b"\x01\x02\x03"

    def test_detect_offset_size_count(self):
        header = bytearray()
        entries = []
        off = 0
        for i in range(5):
            size = (i + 1) * 40
            count = i + 1
            entries.append((off, size, count))
            header += struct.pack("<iii", off, size, count)
            off += size
        best, parsed, scores = detect_layout(bytes(header), off + 100)
        assert best == "offset_size_count"
        assert scores[best] >= 0.9
        assert [e["size"] for e in parsed] == [40, 80, 120, 160, 200]

    def test_detect_count_offset_size(self):
        """08-13 字段序：count/offset/size。"""
        header = bytearray()
        entries = []
        off = 0
        for i in range(5):
            size = (i + 1) * 40
            count = i + 1
            entries.append((off, size, count))
            header += struct.pack("<iii", count, off, size)
            off += size
        best, parsed, _ = detect_layout(bytes(header), off + 100)
        assert best == "count_offset_size"
        assert [e["count"] for e in parsed] == [1, 2, 3, 4, 5]

    def test_parse_triplets_with_layout(self):
        header = struct.pack("<iii", 0, 40, 2)
        entries = parse_triplets(header, ["offset", "size", "count"])
        assert entries[0]["offset"] == 0
        assert entries[0]["size"] == 40
        assert entries[0]["count"] == 2


# ------------------------------------------------------------- 合成 31 节文件

def _spec():
    """(name, size, count, protected) 31 节规格（size = count × 官方 rec）。

    protected=7：stringLiteral/stringLiteralData/events/properties/methods/
    images/attributeData（rec 覆盖唯一/None，便于无参考求解确定）。"""
    spec = [
        ("stringLiteral", 64, 16, True),
        ("stringLiteralData", 20003, 100, True),   # 20003 % 100 != 0 → rec None
        ("string", 200, 3, False),                 # 200 % 3 != 0 → rec None
        ("events", 120, 5, True),
        ("properties", 160, 8, True),
        ("methods", 224, 7, True),
        ("parameterDefaultValues", 48, 4, False),
        ("fieldDefaultValues", 60, 5, False),
        ("fieldAndParameterDefaultValueData", 48, 48, False),
        ("fieldMarshaledSizes", 36, 3, False),
        ("parameters", 72, 6, False),
        ("fields", 48, 4, False),
        ("genericParameters", 70, 5, False),
        ("genericParameterConstraints", 24, 6, False),
        ("genericContainers", 64, 4, False),
        ("nestedTypes", 28, 7, False),
        ("interfaces", 20, 5, False),
        ("vtableMethods", 32, 8, False),
        ("interfaceOffsets", 48, 6, False),
        ("typeDefinitions", 328, 4, False),
        ("images", 180, 5, True),
        ("assemblies", 204, 3, False),
        ("fieldRefs", 40, 5, False),
        ("referencedAssemblies", 24, 6, False),
        ("attributeData", 13001, 7, True),         # 13001 % 7 != 0 → rec None
        ("attributeDataRange", 48, 6, False),
        ("unresolvedVirtualCallParameterTypes", 28, 7, False),
        ("unresolvedVirtualCallParameterRanges", 40, 5, False),
        ("windowsRuntimeTypeNames", 0, 0, False),
        ("windowsRuntimeStrings", 0, 0, False),
        ("exportedTypeDefinitions", 24, 6, False),
    ]
    assert [s[0] for s in spec] == V39_NAMES
    return spec


def _random_content(name, size):
    """按名称哈希的伪随机字节（binary 类，避免跨节平移误匹配）。"""
    prefix = (name + ":enc").encode()
    return bytes(
        hashlib.sha256(prefix + bytes([i & 0xFF, (i >> 8) & 0xFF])).digest()[0]
        for i in range(size)
    )


def _section_content(name, size, protected):
    """受保护节"解密后"内容须可过结构门（零表 ⇒ 解密恒等）。"""
    if size == 0:
        return b""
    if name == "stringLiteral":
        return struct.pack(f"<{size // 4}I", *range(size // 4))  # 单调 index
    if name == "stringLiteralData":
        return (b"LCTA metadata recovery synthetic string literal data. "
                * (size // 50 + 1))[:size]                        # text
    if name == "events":
        return struct.pack(f"<{size // 4}I", *range(10, 10 + size // 4))  # 单调 index
    return _random_content(name, size) if protected else _random_content(name, size)


def _build_encrypted_metadata(spec):
    """加密 metadata：header（offset_size_count 三元组）+ 连续节内容。

    逻辑 offset == 物理 offset（adj=0），节按规范序连续排列。"""
    header_size = 31 * 12
    offsets = []
    offset = header_size
    for _, size, _, _ in spec:
        offsets.append(offset)
        offset += size
    data = bytearray(header_size)
    for i, (_, size, count, _) in enumerate(spec):
        struct.pack_into("<iii", data, i * 12, offsets[i], size, count)
    for i, (name, size, count, protected) in enumerate(spec):
        if size == 0:
            continue
        data.extend(_section_content(name, size, protected))
    return bytes(data), offsets


def _make_profile(metadata, spec, offsets):
    """构造 solver/verify 消费的 profile（7 个受保护节段，offset_size_count 布局）。"""
    protected_entries = [i for i, s in enumerate(spec) if s[3]]
    return {
        "header_size": 31 * 12,
        "header_seed": "0x1",
        "table_hex": TABLE_ZERO,
        "sections": [
            {"size_off": i * 12 + 4, "offset_off": i * 12,
             "adj": 0, "seed": f"0x{i + 1}"}
            for i in protected_entries
        ],
    }


def _intended_standard(spec):
    """按标准 v39 布局直接构造期望重建结果。"""
    header_size = 8 + 31 * 12
    data = bytearray(header_size)
    struct.pack_into("<II", data, 0, 0xFAB11BAF, 39)
    offset = header_size
    for i, (name, size, count, protected) in enumerate(spec):
        section_offset = offset if size else 0
        struct.pack_into("<iii", data, 8 + i * 12, section_offset, size, count)
        if size:
            data.extend(_section_content(name, size, protected))
            offset += size
    return bytes(data)


# ------------------------------------------------------------- 验证

@requires_capstone
class TestVerifySynthetic:
    def _inputs(self):
        spec = _spec()
        metadata, offsets = _build_encrypted_metadata(spec)
        profile = _make_profile(metadata, spec, offsets)
        return metadata, profile

    def test_pass(self):
        metadata, profile = self._inputs()
        res = verify(metadata, profile)
        assert res["verdict"] == VERDICT_PASS
        assert all(g["passed"] for g in res["gates"])
        assert res["layout"]["best"] == "offset_size_count"

    def test_wrong_seed_fails(self):
        metadata, profile = self._inputs()
        for sec in profile["sections"]:
            sec["seed"] = "0xDEADBEEF"  # 全部 seed 错误：无任何 text/index 节段，结构门须拦截
        res = verify(metadata, profile)
        assert res["verdict"] == VERDICT_FAIL
        assert not all(g["passed"] for g in res["gates"])

    def test_bad_table_length_fails(self):
        metadata, profile = self._inputs()
        profile["table_hex"] = "00" * 255
        res = verify(metadata, profile)
        assert res["verdict"] == VERDICT_FAIL


# ------------------------------------------------------------- 求解 + 重建

@requires_capstone
@pytest.mark.slow
class TestSolveRebuildSynthetic:
    def _inputs(self):
        spec = _spec()
        metadata, offsets = _build_encrypted_metadata(spec)
        profile = _make_profile(metadata, spec, offsets)
        return metadata, profile

    def test_solve_31_sections_no_review(self):
        metadata, profile = self._inputs()
        solution = solve(metadata, profile)
        assert len(solution["sections"]) == 31
        assert not solution["review"], solution["review"]
        assert len(solution["protected"]) == 7

    def test_solve_mapping_matches_spec(self):
        metadata, profile = self._inputs()
        solution = solve(metadata, profile)
        spec = _spec()
        for i, (name, _, _, _) in enumerate(spec):
            mapped = solution["sections"][name]
            assert mapped["custom_entry_index"] == i, name
            assert mapped["physical_offset_adjustment"] == 0, name

    def test_rebuild_matches_intended_standard(self):
        metadata, profile = self._inputs()
        solution = solve(metadata, profile)
        std = rebuild_standard(metadata, solution, profile["table_hex"])
        assert std == _intended_standard(_spec())

    def test_validate_gates_all_pass(self):
        metadata, profile = self._inputs()
        solution = solve(metadata, profile)
        std = rebuild_standard(metadata, solution, profile["table_hex"])
        gates = validate_standard(std, solution, metadata, profile["table_hex"])
        assert all(g["passed"] for g in gates), \
            [g["name"] + ": " + g["evidence"] for g in gates if not g["passed"]]


# ------------------------------------------------------- 字节流 rec 判定回归
# 2026-10-29 版失效根因：attributeData 恰 size==count（2234324），被 _rec_of
# 误判为整数 rec=1，导致 rec=None 的字节流槽位永远配不到它，整链求解失败
# （"无可行锚点槽位组合"）。此前各版 size≠count 未触发。以下锁死该判定。

class TestByteStreamRecRegression:
    def test_size_eq_count_blob_misjudged_as_int_rec(self):
        # 字节流 size==count 时 _rec_of 返回整数 rec（这是诱发条件本身）
        e = {"index": 80, "size": 2234324, "count": 2234324, "offset": 0}
        assert _rec_of(e) == 1

    def test_rec_none_slot_includes_misjudged_blob(self):
        # attributeData 字节 blob（被误判为 rec=1）必须仍能被 rec=None 槽位选中
        e_attr = {"index": 80, "size": 2234324, "count": 2234324, "offset": 0}
        e_vtbl = {"index": 36, "size": 13098732, "count": 3274683, "offset": 0}  # rec=4
        pool_by_rec = {1: [], 4: [e_vtbl], None: []}
        byte_blobs = [e_attr]
        cands_none = _slot_candidates(None, pool_by_rec, byte_blobs)
        assert e_attr in cands_none
        # 整数 rec 槽位不受污染：绝不把 size==count 的字节 blob 混入
        assert _slot_candidates(4, pool_by_rec, byte_blobs) == [e_vtbl]
        assert e_attr not in _slot_candidates(4, pool_by_rec, byte_blobs)

    def test_rec_none_slot_keeps_plain_none_entries(self):
        e_sld = {"index": 76, "size": 931799, "count": 32187, "offset": 0}  # size%count!=0 -> None
        assert _rec_of(e_sld) is None
        pool_by_rec = {None: [e_sld]}
        assert _slot_candidates(None, pool_by_rec, []) == [e_sld]


# ------------------------------------------------------------- 流水线包装

class TestRunRecoveryWrapper:
    def _dummy_files(self, tmp_path):
        metadata = tmp_path / "global-metadata.dat"
        dll = tmp_path / "GameAssembly.dll"
        metadata.write_bytes(b"encrypted metadata")
        dll.write_bytes(b"dll")
        return metadata, dll

    def _canned_report(self):
        return {
            "version": 39,
            "stages": {"locate": {"top1": "0x18069C5E0"},
                       "extract": {"header_size": 1236},
                       "verify": {"layout": "count_offset_size"},
                       "solve": {"review": []},
                       "rebuild": {"size": 1024}},
            "verdicts": {"locate": "PASS", "extract": "PASS", "verify": "PASS",
                         "solve": "PASS", "rebuild": "PASS"},
            "outputs": {},
            "elapsed_sec": 1.5,
        }

    def test_missing_inputs_raise(self, tmp_path):
        metadata, dll = self._dummy_files(tmp_path)
        with pytest.raises(ValueError):
            run_recovery(metadata_path="", game_dll=str(dll))
        with pytest.raises(ValueError):
            run_recovery(metadata_path=str(metadata), game_dll="")

    def test_success_and_outputs(self, tmp_path, monkeypatch):
        import webutils.metadata_recovery.pipeline as mod
        metadata, dll = self._dummy_files(tmp_path)
        monkeypatch.setattr(mod, "run_universal", lambda *a, **kw: self._canned_report())
        monkeypatch.setattr(mod, "capstone_available", lambda: True)
        result = run_recovery(metadata_path=str(metadata), game_dll=str(dll),
                              out_dir=str(tmp_path / "out"))
        assert result["success"]
        assert result["verdicts"] == self._canned_report()["verdicts"]
        run_dir = Path(result["run_dir"])
        assert (run_dir / "run-report.json").is_file()
        assert (run_dir / "run-report.md").is_file()
        data = json.loads((run_dir / "run-report.json").read_text(encoding="utf-8"))
        assert data["verdicts"]["locate"] == "PASS"
        assert result["outputs"]["report_json"].endswith("run-report.json")

    def test_expect_sha_gate(self, tmp_path, monkeypatch):
        import webutils.metadata_recovery.pipeline as mod
        metadata, dll = self._dummy_files(tmp_path)

        def _fake_run(dll, md, version=39, out_dir=None, name=None,
                      on_log=None, cancel_check=None):
            (Path(out_dir) / f"{name}-standard.dat").write_bytes(b"rebuilt bytes")
            (Path(out_dir) / f"{name}-profile.json").write_text("{}")
            return self._canned_report()

        monkeypatch.setattr(mod, "run_universal", _fake_run)
        monkeypatch.setattr(mod, "capstone_available", lambda: True)
        # 期望 SHA 匹配
        want = hashlib.sha256(b"rebuilt bytes").hexdigest().upper()
        out1 = tmp_path / "out1"
        res1 = run_recovery(metadata_path=str(metadata), game_dll=str(dll),
                            expect_sha256=want, out_dir=str(out1))
        assert res1["verdicts"]["expect_sha"] == "PASS"
        assert (Path(res1["run_dir"]) / "standard-rebuilt.dat").is_file()
        # 期望 SHA 不匹配
        out2 = tmp_path / "out2"
        res2 = run_recovery(metadata_path=str(metadata), game_dll=str(dll),
                            expect_sha256="0" * 64, out_dir=str(out2))
        assert res2["verdicts"]["expect_sha"] == "FAIL"
        assert not res2["success"]

    def test_fail_verdict_propagates(self, tmp_path, monkeypatch):
        import webutils.metadata_recovery.pipeline as mod
        metadata, dll = self._dummy_files(tmp_path)
        report = self._canned_report()
        report["verdicts"]["solve"] = "REVIEW"
        report["stages"]["solve"] = {"review": ["歧义项"]}
        monkeypatch.setattr(mod, "run_universal", lambda *a, **kw: report)
        monkeypatch.setattr(mod, "capstone_available", lambda: True)
        result = run_recovery(metadata_path=str(metadata), game_dll=str(dll),
                              out_dir=str(tmp_path / "out"))
        assert result["verdicts"]["solve"] == "REVIEW"
        assert result["success"]  # REVIEW 视为可接受（不静默失败但允许人工判断）


class TestCapstone:
    def test_available_is_bool(self):
        assert isinstance(capstone_available(), bool)
        assert isinstance(_pipeline_capstone(), bool)

    def test_output_dir(self):
        assert str(output_dir()).endswith("metadata_recovery")


class TestDeriveGameFiles:
    def test_derive_from_game_root(self, tmp_path):
        game = tmp_path / "Limbus Company"
        game.mkdir()
        meta_dir = game / "LimbusCompany_Data" / "il2cpp_data" / "Metadata"
        meta_dir.mkdir(parents=True)
        (meta_dir / "global-metadata.dat").write_bytes(b"enc")
        (game / "GameAssembly.dll").write_bytes(b"pe")
        d = derive_game_files(str(game))
        assert d["derived"]
        assert d["metadata_exists"] and d["dll_exists"]
        assert d["metadata_path"].endswith(
            "LimbusCompany_Data\\il2cpp_data\\Metadata\\global-metadata.dat")
        assert d["dll_path"].endswith("GameAssembly.dll")

    def test_missing_files_flagged(self, tmp_path):
        d = derive_game_files(str(tmp_path))
        assert d["derived"]
        assert not d["metadata_exists"] and not d["dll_exists"]
        assert d["metadata_path"]

    def test_empty_game_path(self):
        d = derive_game_files("")
        assert not d["derived"] and not d["metadata_path"]


# ------------------------------------------------- capstone 运行时自愈回归
#
# 历史 bug：init_locator / extract_disasm 在模块级 `from capstone import ...`
# 并把缺失状态冻结进 _CAPSTONE_OK。应用启动时 capstone 未装 → 页面一键
# pip 安装后 find_spec 立刻为真（页面显示"已就绪"），但反汇编仍不可用，
# 用户必须重启应用才能解密。下面这组用例把"启动后安装"这一过程固化为回归。


class _CapstoneBlocker:
    """模拟「应用启动时 capstone 未安装」：阻断 capstone 导入。"""

    def __init__(self):
        self.blocked = True

    def find_spec(self, fullname, path=None, target=None):
        if self.blocked and (fullname == "capstone"
                             or fullname.startswith("capstone.")):
            raise ImportError(f"blocked capstone import for test: {fullname}")
        return None


def _write_fake_capstone(tmp_path, body):
    """在临时目录写一个假 capstone 包（用于模拟安装结果）。"""
    pkg = tmp_path / "capstone"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(body, encoding="utf-8")
    return pkg


_FAKE_CAPSTONE_BROKEN_NATIVE = (
    "CS_ARCH_X86 = 3\n"
    "CS_MODE_64 = 8\n"
    "__version__ = '9.9.9'\n"
    "class Cs:\n"
    "    def __init__(self, arch, mode):\n"
    "        raise OSError('DLL load failed while importing capstone')\n"
)


class TestCapstoneRuntimeHealing:
    """capstone 在应用启动后才安装时，必须**同一进程内**立即可用。"""

    @pytest.fixture(autouse=True)
    def _clean_capstone_state(self):
        capstone_env.reset()
        yield
        capstone_env.reset()

    def test_missing_capstone_reports_real_error(self, monkeypatch):
        blocker = _CapstoneBlocker()
        monkeypatch.setattr(sys, "meta_path", [blocker] + list(sys.meta_path))
        capstone_env.reset()

        assert capstone_env.available(force=True) is False
        assert not capstone_env.smoke_test()
        assert capstone_env.version() == ""
        with pytest.raises(RuntimeError) as excinfo:
            init_locator._require_capstone()
        msg = str(excinfo.value)
        assert "capstone" in msg
        # 报错必须带真实异常，便于用户/日志定位（历史文案只写"请先安装"）
        assert "真实错误" in msg and "ImportError" in msg
        assert capstone_env.last_error()

    @requires_capstone
    def test_install_after_startup_usable_without_restart(self, monkeypatch):
        # 1) 应用启动时 capstone 缺失（模块级不再固化状态）
        blocker = _CapstoneBlocker()
        monkeypatch.setattr(sys, "meta_path", [blocker] + list(sys.meta_path))
        capstone_env.reset()
        assert capstone_env.available(force=True) is False
        with pytest.raises(RuntimeError):
            init_locator._require_capstone()
        with pytest.raises(RuntimeError):
            extract_disasm._require_capstone()

        # 2) 模拟页面内一键安装完成（pip 已写入 site-packages）
        blocker.blocked = False
        capstone_env.reset()

        # 3) 不重启：状态、自检、反汇编路径全部立即可用
        assert capstone_env.available(force=True) is True
        assert capstone_env.smoke_test() is True
        assert capstone_env.version()
        init_locator._require_capstone()
        extract_disasm._require_capstone()
        md = capstone_env.new_disassembler()
        assert list(md.disasm(b"\x90", 0x1000))

    def test_available_uses_real_import_not_find_spec(self, tmp_path, monkeypatch):
        _write_fake_capstone(tmp_path, "raise ImportError('模拟原生库缺失')\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        capstone_env.reset()

        # find_spec 认为"已安装"，但导入实际失败：必须判定为不可用，
        # 否则页面会显示"已就绪"而运行时仍然报缺少 capstone。
        assert importlib.util.find_spec("capstone") is not None
        assert capstone_available() is False
        assert _pipeline_capstone(force=True) is False
        assert "模拟原生库缺失" in capstone_env.last_error()

    def test_broken_native_library_detected(self, tmp_path, monkeypatch):
        _write_fake_capstone(tmp_path, _FAKE_CAPSTONE_BROKEN_NATIVE)
        monkeypatch.syspath_prepend(str(tmp_path))
        capstone_env.reset()

        # 导入成功但原生库加载失败：自检必须失败，且错误可读
        assert capstone_env.smoke_test() is False
        assert capstone_env.available(force=True) is False
        assert "DLL load failed" in capstone_env.last_error()

    def test_run_recovery_gate_mentions_install_without_restart(self, tmp_path,
                                                               monkeypatch):
        blocker = _CapstoneBlocker()
        monkeypatch.setattr(sys, "meta_path", [blocker] + list(sys.meta_path))
        capstone_env.reset()
        metadata = tmp_path / "global-metadata.dat"
        dll = tmp_path / "GameAssembly.dll"
        metadata.write_bytes(b"enc")
        dll.write_bytes(b"dll")
        with pytest.raises(RuntimeError) as excinfo:
            run_recovery(metadata_path=str(metadata), game_dll=str(dll),
                         out_dir=str(tmp_path / "out"))
        msg = str(excinfo.value)
        assert "一键安装 capstone" in msg and "无需重启" in msg


class TestInstallCapstoneFlow:
    """install_capstone：幂等 / 镜像回退 / ensurepip / 装后同进程验证。"""

    @pytest.fixture(autouse=True)
    def _clean_capstone_state(self):
        import webutils.metadata_recovery as pkg
        self.pkg = pkg
        capstone_env.reset()
        yield
        capstone_env.reset()

    def _patch_probe(self, monkeypatch, results, last_error=""):
        """smoke_test 依次返回 results（安装前检查 → 安装后验证）。"""
        seq = list(results)
        state = {"n": 0}

        def _next():
            idx = min(state["n"], len(seq) - 1)
            state["n"] += 1
            return seq[idx]

        monkeypatch.setattr(capstone_env, "smoke_test", _next)
        monkeypatch.setattr(capstone_env, "reset", lambda: None)
        monkeypatch.setattr(capstone_env, "last_error", lambda: last_error)
        monkeypatch.setattr(capstone_env, "version", lambda: "5.0.9")

    def test_already_available_skips_pip(self, monkeypatch):
        self._patch_probe(monkeypatch, [True])
        calls = []
        monkeypatch.setattr(self.pkg, "_run_pip",
                            lambda args, on_log: calls.append(args) or (0, []))
        result = install_capstone()
        assert result["success"] is True
        assert result["need_restart"] is False
        assert calls == []

    def test_success_is_immediately_usable(self, monkeypatch):
        self._patch_probe(monkeypatch, [False, True])
        logs = []
        calls = []
        monkeypatch.setattr(
            self.pkg, "_run_pip",
            lambda args, on_log: calls.append(args) or (0, ["installed"]))
        result = install_capstone(on_log=logs.append)
        assert result["success"] is True
        assert result["need_restart"] is False
        assert calls and "--upgrade" in calls[0]
        # 文案必须明确"无需重启"，这是本次修复的用户可见契约
        assert "无需重启" in result["message"]
        assert any("无需重启" in line for line in logs)

    def test_network_error_retries_with_mirror(self, monkeypatch):
        self._patch_probe(monkeypatch, [False, True])
        calls = []

        def _fake_run_pip(args, on_log):
            calls.append(args)
            if "--index-url" in args:
                return 0, ["Successfully installed capstone-5.0.9"]
            return 1, ["ERROR: Could not fetch URL https://pypi.org/simple/capstone/",
                       "Failed to establish a new connection"]

        monkeypatch.setattr(self.pkg, "_run_pip", _fake_run_pip)
        result = install_capstone()
        assert result["success"] is True
        assert len(calls) == 2
        assert "--index-url" in calls[1]

    def test_missing_pip_bootstraps_ensurepip(self, monkeypatch):
        self._patch_probe(monkeypatch, [False, True])
        runs = []
        ensurepip_calls = []
        state = {"n": 0}

        def _fake_run_pip(args, on_log):
            runs.append(args)
            state["n"] += 1
            if state["n"] == 1:
                return 1, ["No module named pip"]
            return 0, ["Successfully installed capstone-5.0.9"]

        def _fake_run(cmd, **kwargs):
            ensurepip_calls.append(cmd)
            return None

        monkeypatch.setattr(self.pkg, "_run_pip", _fake_run_pip)
        monkeypatch.setattr(self.pkg.subprocess, "run", _fake_run)
        result = install_capstone()
        assert result["success"] is True
        assert any("ensurepip" in " ".join(cmd) for cmd in ensurepip_calls)
        assert len(runs) == 2

    def test_pip_failure_reports_output(self, monkeypatch):
        self._patch_probe(monkeypatch, [False])
        monkeypatch.setattr(
            self.pkg, "_run_pip",
            lambda args, on_log: (1, ["ERROR: No matching distribution found"]))
        result = install_capstone()
        assert result["success"] is False
        assert result["need_restart"] is False
        assert "No matching distribution found" in result["message"]

    def test_pip_ok_but_unloadable_requires_restart(self, monkeypatch):
        self._patch_probe(monkeypatch, [False, False],
                          last_error="OSError: DLL load failed")
        monkeypatch.setattr(self.pkg, "_run_pip", lambda args, on_log: (0, ["ok"]))
        scheduled = []
        monkeypatch.setattr(self.pkg, "_schedule_pending_install",
                            lambda: scheduled.append(True) or True)
        result = install_capstone()
        assert result["success"] is False
        assert result["need_restart"] is True
        assert scheduled == [True]
        assert "重启" in result["message"]
        assert "DLL load failed" in result["message"]



