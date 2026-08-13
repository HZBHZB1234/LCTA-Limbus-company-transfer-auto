# -*- coding: utf-8 -*-
"""webutils.metadata_recovery 测试（v2 universal 管线，全部合成数据）。

覆盖：PE 解析、xorshift 模板扫描、三元组布局自动判定、结构验证、
31 节无参考求解 + 标准文件重建 + 四重自验证、流水线包装（输入校验/
期望 SHA 门/产物落盘）、游戏文件推导。

依赖 capstone（缺失时跳过 universal 核心测试，包装层测试不受影响）。
"""
import hashlib
import json
import struct
from pathlib import Path

import pytest

from webutils.metadata_recovery import (
    capstone_available,
    derive_game_files,
    output_dir,
    run_recovery,
)
from webutils.metadata_recovery.pipeline import capstone_available as _pipeline_capstone
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
from webutils.metadata_recovery.universal.solve_versioned import solve
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
        profile["sections"][0]["seed"] = "0xDEADBEEF"  # 破坏 stringLiteral 解密
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


