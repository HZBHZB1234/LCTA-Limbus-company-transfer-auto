# -*- coding: utf-8 -*-
"""webutils.metadata_recovery 测试：提取器夹具回归、合成数据验证、
求解器、流水线端到端、PE RVA 读取。"""
import json
import struct
from pathlib import Path

import pytest

from webutils.metadata_recovery.extractor import extract_from_text
from webutils.metadata_recovery import derive_game_files, load_locator_export
from webutils.metadata_recovery.pipeline import (
    read_rva_data,
    resolve_table_hex,
    run_recovery,
)
from webutils.metadata_recovery.report import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_PASS_WITH_REVIEW,
    Report,
)
from webutils.metadata_recovery.solver import (
    STANDARD_NAMES,
    parse_reference,
    solve,
)
from webutils.metadata_recovery.verify import (
    classify_section,
    decrypt_bytes,
    verify_profile,
)

FIXTURES = Path(__file__).parent / "fixtures"
TABLE_ZERO = "00" * 256  # 全零表 = 解密恒等，便于合成数据


def _fixture_checks(text, expected):
    ext = extract_from_text(text)
    checks = []
    for name, ok in expected(ext).items():
        checks.append((name, ok))
    return ext, checks


class TestExtractorCurrentFixture:
    """07-30 真值夹具回归（原仓库 _fixture_test）。"""

    def setup_method(self):
        self.text = (FIXTURES / "metadata_initialize_current.c").read_text(encoding="utf-8")

    def test_extract_current(self):
        ext, checks = _fixture_checks(self.text, self._expected)
        failed = [n for n, ok in checks if not ok]
        assert not failed, f"FAILED: {failed} errors={ext.errors}"

    def _expected(self, ext):
        e = {
            "header_size == 0x2F4": ext.header_size == 0x2F4,
            "header_seed": ext.header_seed == 0xE039BA990B051CD7,
            "table == 0x18759C190": ext.table_addr == "0x18759C190",
            "sections == 7": len(ext.sections) == 7,
            "xorshift_loops == 16": ext.xorshift_loops == 16,
        }
        expected_sections = [
            (216, 224, -6756, 0x6437F7B47BCC353D),
            (420, 428, 5028, 0x2991189FDDC51967),
            (144, 152, 8036, 0x5647FAF029DA7235),
            (408, 416, -404, 0x9B1470F67FDC86B4),
            (396, 404, -4112, 0x01CEDA6B470922C8),
            (36, 44, 4228, 0x3B596B9B21B69FF1),
            (684, 692, 7856, 0x6E47EB74067D4A7F),
        ]
        for idx, (size_off, offset_off, adj, seed) in enumerate(expected_sections):
            got = ext.sections[idx]
            e[f"s[{idx}] size_off"] = got["size_off"] == size_off
            e[f"s[{idx}] offset_off"] = got["offset_off"] == offset_off
            e[f"s[{idx}] adj"] = got["adj"] == adj
            e[f"s[{idx}] seed"] = int(got["seed"], 16) == seed
        return e


class TestExtractor0806Fixture:
    """08-06 真值夹具回归（原仓库 _fixture_test_08_06）。"""

    def setup_method(self):
        self.text = (FIXTURES / "metadata_initialize_08-06.c").read_text(encoding="utf-8")

    def test_extract_0806(self):
        ext, checks = _fixture_checks(self.text, self._expected)
        failed = [n for n, ok in checks if not ok]
        assert not failed, f"FAILED: {failed} errors={ext.errors}"

    def _expected(self, ext):
        e = {
            "header_size == 1044": ext.header_size == 1044,
            "header_seed": ext.header_seed == 0xBC41EAFC33962B00,
            "table == 0x187356110": ext.table_addr == "0x187356110",
            "sections == 7": len(ext.sections) == 7,
            "no errors": not ext.errors,
        }
        expected_sections = [
            (1024, 1020, -1508, 0x116C4B46EACABA5),
            (664, 660, 3476, 0xD4C07427B74C818E),
            (964, 960, -6696, 0xAFDAE7074F40F834),
            (136, 132, 4304, 0xA28BFC303CE665BA),
            (592, 588, -3984, 0xFF3532DDAC34BA66),
            (652, 648, -7080, 0x1DFCEDD20A3EE02C),
            (4, 0, 2268, 0x88942C9716431E06),
        ]
        for idx, (size_off, offset_off, adj, seed) in enumerate(expected_sections):
            got = ext.sections[idx]
            e[f"s[{idx}] size_off"] = got["size_off"] == size_off
            e[f"s[{idx}] offset_off"] = got["offset_off"] == offset_off
            e[f"s[{idx}] adj"] = got["adj"] == adj
            e[f"s[{idx}] seed"] = int(got["seed"], 16) == seed
        return e


class TestReportSelfCheck:
    def test_verdicts(self):
        rep = Report(tool="t", version="v")
        rep.gate("g1", True, "ok")
        assert rep.verdict() == VERDICT_PASS
        rep.gate("g2", False, "fail")
        assert rep.verdict() == VERDICT_FAIL
        rep2 = Report(tool="t")
        rep2.gate("g1", True, "ok")
        rep2.review("歧义?", "证据")
        assert rep2.verdict() == VERDICT_PASS_WITH_REVIEW

    def test_roundtrip(self, tmp_path):
        rep = Report(tool="t", version="v", title="标题")
        rep.gate("g", True, "ok")
        rep.set_section("s", {"a": 1})
        rep.write_all(tmp_path, "report")
        data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        assert data["verdict"] == VERDICT_PASS
        assert (tmp_path / "report.md").exists()


# ------------------------------------------------------------- 合成数据

def _synthetic_metadata():
    """构造 3 节段合成 metadata：text 节 / index 节 / 零尺寸节。

    header = 3 个 (offset,size,count) 三元组（offset_size_count 布局）。
    全零替换表 ⇒ 解密恒等。"""
    text_data = b"A" * 40 + b"B" * 24
    index_data = struct.pack("<12I", *range(12))
    entries = [
        (36, len(text_data), len(text_data)),
        (36 + len(text_data), len(index_data), 12),
        (0, 0, 0),
    ]
    header = b"".join(struct.pack("<iii", *e) for e in entries)
    assert len(header) == 36
    return header + text_data + index_data, entries


class TestVerifySynthetic:
    def test_pass(self, tmp_path):
        metadata, _ = _synthetic_metadata()
        profile = {
            "profile_id": "synth",
            "header_size": 36,
            "header_seed": "0x1",
            "table_hex": TABLE_ZERO,
            "sections": [
                {"size_off": 4, "offset_off": 0, "adj": 0, "seed": "0x1"},
                {"size_off": 16, "offset_off": 12, "adj": 0, "seed": "0x2"},
                {"size_off": 28, "offset_off": 24, "adj": 0, "seed": "0x3"},
            ],
        }
        rep = verify_profile(metadata, profile, tmp_path, "verify")
        assert rep.verdict() == VERDICT_PASS
        assert (tmp_path / "verify.json").exists()

    def test_wrong_seed_fails_structure_gate(self, tmp_path):
        metadata, _ = _synthetic_metadata()
        profile = {
            "profile_id": "synth-bad",
            "header_size": 36,
            "header_seed": "0x1",
            "table_hex": "11" * 256,  # 非恒等表 → 解密破坏文本
            "sections": [
                {"size_off": 4, "offset_off": 0, "adj": 0, "seed": "0x1"},
            ],
        }
        rep = verify_profile(metadata, profile, tmp_path, "verify-bad")
        assert rep.verdict() == VERDICT_FAIL

    def test_classify_section(self):
        kind, ev = classify_section(b"hello world " * 10)
        assert kind == "text"
        kind, ev = classify_section(struct.pack("<8I", *range(8)))
        assert kind == "index"
        kind, ev = classify_section(struct.pack("<8I", 5, 3, 9, 1, 7, 2, 8, 4))
        assert kind == "binary"

    def test_decrypt_identity_with_zero_table(self):
        assert decrypt_bytes(b"\x01\x02\x03", 0x1234, bytes(256)) == b"\x01\x02\x03"


def _ref_spec():
    """31 节标准参考布局（唯一记录大小为主，含两组同 rec 节测试消歧）。"""
    spec = [
        ("stringLiteral", 160, 16, True),
        ("stringLiteralData", 300, 1, True),
        ("string", 200, 2, False),
        ("events", 80, 4, True),
        ("properties", 63, 3, True),
        ("methods", 90, 2, True),
        ("parameterDefaultValues", 64, 1, False),
        ("fieldDefaultValues", 32, 1, False),
        ("fieldAndParameterDefaultValueData", 48, 2, False),
        ("fieldMarshaledSizes", 33, 1, False),
        ("parameters", 44, 2, False),
        ("fields", 36, 1, False),
        ("genericParameters", 23, 1, False),
        ("genericParameterConstraints", 56, 2, False),
        ("genericContainers", 70, 1, False),
        ("nestedTypes", 27, 1, False),
        ("interfaces", 42, 2, False),
        ("vtableMethods", 66, 1, False),
        ("interfaceOffsets", 30, 1, False),
        ("typeDefinitions", 26, 1, False),
        ("images", 25, 1, False),
        ("assemblies", 24, 2, False),
        ("fieldRefs", 14, 1, False),
        ("referencedAssemblies", 13, 1, False),
        ("attributeData", 54, 1, True),
        ("attributeDataRange", 52, 1, True),
        ("unresolvedVirtualCallParameterTypes", 40, 1, False),
        ("unresolvedVirtualCallParameterRanges", 39, 1, False),
        ("windowsRuntimeTypeNames", 38, 1, False),
        ("windowsRuntimeStrings", 0, 0, False),
        ("exportedTypeDefinitions", 60, 3, False),
    ]
    assert [s[0] for s in spec] == STANDARD_NAMES
    return spec


def _content_stream(name, salt, size):
    """逐字节哈希流：任意两节内容互不为平移序列（避免指纹跨节误匹配）。"""
    import hashlib
    prefix = (name + salt).encode()
    return bytes(
        hashlib.sha256(prefix + bytes([i & 0xFF, (i >> 8) & 0xFF])).digest()[0]
        for i in range(size)
    )


def _ref_content(name, size):
    """参考标准文件节内容（指纹定位目标）。"""
    if size == 0:
        return b""
    return _content_stream(name, ":ref", size)


def _protected_content(name, size):
    """受保护节"解密后"内容：零替换表 ⇒ 解密恒等，须可直接过结构门。

    stringLiteral/stringLiteralData/attributeData → 可打印文本（text 门）；
    events → 单调 u32（index 门）；其余 → 类随机（binary 门）。
    """
    if size == 0:
        return b""
    if name in ("stringLiteral", "stringLiteralData", "attributeData"):
        text = b"LCTA metadata recovery synthetic protected string data. "
        return (text * ((size // len(text)) + 1))[:size]
    if name == "events":
        return struct.pack(f"<{size // 4}I", *range(size // 4))
    return _content_stream(name, ":enc", size)


def _build_reference(spec):
    """标准 v39 参考文件：sanity + version + 31 三元组 + 连续节内容。"""
    header_size = 8 + 31 * 12
    offsets = []
    offset = header_size
    for _, size, _, _ in spec:
        offsets.append(offset)
        offset += size
    data = bytearray(header_size)
    struct.pack_into("<II", data, 0, 0xFAB11BAF, 39)
    for i, (name, size, count, _) in enumerate(spec):
        struct.pack_into("<iii", data, 8 + i * 12, offsets[i], size, count)
        data.extend(_ref_content(name, size))
    return bytes(data), offsets


def _build_metadata(spec, offsets):
    """加密文件：header 三元组（物理=逻辑） + 节内容（受保护节为乱码）。"""
    header_size = 31 * 12
    entries = []
    for i, (name, size, count, protected) in enumerate(spec):
        offset = offsets[i] - (8 + 31 * 12) + header_size  # 相对本文件头
        entries.append((offset, size, count))
    data = bytearray(header_size)
    for i, e in enumerate(entries):
        struct.pack_into("<iii", data, i * 12, *e)
    for i, (name, size, count, protected) in enumerate(spec):
        if size == 0:
            continue
        content = _protected_content(name, size) if protected else _ref_content(name, size)
        data.extend(content)
    return bytes(data), entries


class TestSolverSynthetic:
    def _inputs(self, tmp_path):
        spec = _ref_spec()
        ref_data, ref_offsets = _build_reference(spec)
        meta_data, entries = _build_metadata(spec, ref_offsets)
        reference = parse_reference(ref_data)
        header_size = 31 * 12
        protected_entries = [i for i, s in enumerate(spec) if s[3]]
        profile = {
            "profile_id": "synth-31",
            "header_size": header_size,
            "header_seed": "0x1",
            "table_hex": TABLE_ZERO,
            "sections": [
                {"size_off": i * 12 + 4, "offset_off": i * 12,
                 "adj": 0, "seed": f"0x{i + 1}"}
                for i in protected_entries
            ],
        }
        return meta_data, profile, reference

    def test_solve_31_sections(self, tmp_path):
        meta_data, profile, reference = self._inputs(tmp_path)
        rep = Report(tool="test", version="synth", title="求解合成")
        solution = solve(meta_data, profile, reference, rep)
        assert solution
        assert len(solution["sections"]) == 31
        assert rep.verdict() == VERDICT_PASS

    def test_solve_mapping_matches_spec(self, tmp_path):
        meta_data, profile, reference = self._inputs(tmp_path)
        rep = Report(tool="test", version="synth", title="求解合成")
        solution = solve(meta_data, profile, reference, rep)
        spec = _ref_spec()
        for i, (name, _, _, _) in enumerate(spec):
            mapped = solution["sections"][name]
            assert mapped["custom_entry_index"] == i
            assert mapped["physical_offset_adjustment"] == 0


class TestPipelineEndToEnd:
    def _write_inputs(self, tmp_path):
        spec = _ref_spec()
        ref_data, ref_offsets = _build_reference(spec)
        meta_data, _ = _build_metadata(spec, ref_offsets)
        metadata_path = tmp_path / "global-metadata.dat"
        ref_path = tmp_path / "global-metadata-standard.dat"
        metadata_path.write_bytes(meta_data)
        ref_path.write_bytes(ref_data)
        return str(metadata_path), str(ref_path)

    def test_full_pipeline(self, tmp_path):
        metadata_path, ref_path = self._write_inputs(tmp_path)
        spec = _ref_spec()
        header_size = 31 * 12
        protected_entries = [i for i, s in enumerate(spec) if s[3]]
        profile_path = tmp_path / "candidate_profile.json"
        profile_path.write_text(json.dumps({
            "profile_id": "synth",
            "header_size": header_size,
            "header_seed": "0x1",
            "sections": [
                {"size_off": i * 12 + 4, "offset_off": i * 12,
                 "adj": 0, "seed": f"0x{i + 1}"}
                for i in protected_entries
            ],
        }, ensure_ascii=False), encoding="utf-8")

        logs = []
        result = run_recovery(
            metadata_path=metadata_path,
            reference_path=ref_path,
            candidate_profile=str(profile_path),
            table_hex=TABLE_ZERO,
            profile_id="synth-run",
            out_dir=str(tmp_path / "out"),
            on_log=logs.append,
        )
        assert result["success"], result
        assert result["verdicts"]["verify"] == VERDICT_PASS
        assert result["verdicts"]["solve"] == VERDICT_PASS
        assert result["verdicts"]["apply"] == VERDICT_PASS
        assert (Path(result["run_dir"]) / "synth-run.generated.json").exists()
        assert (Path(result["run_dir"]) / "standard-rebuilt.dat").exists()
        assert (Path(result["run_dir"]) / "section-map.json").exists()

    def test_extract_from_text_stage(self, tmp_path):
        """用 08-06 夹具文本走完整流水线（提取 PASS；参数与合成文件不匹配
        → verify FAIL → solve FAIL → apply SKIP，但流程不崩溃、产物齐全）。"""
        metadata_path, ref_path = self._write_inputs(tmp_path)
        decompile = (FIXTURES / "metadata_initialize_08-06.c").read_text(encoding="utf-8")
        result = run_recovery(
            metadata_path=metadata_path,
            reference_path=ref_path,
            decompile_text=decompile,
            table_hex=TABLE_ZERO,
            out_dir=str(tmp_path / "out2"),
        )
        assert result["verdicts"]["extract"] == VERDICT_PASS
        assert result["verdicts"]["verify"] == VERDICT_FAIL
        assert result["verdicts"]["solve"] == VERDICT_FAIL
        assert result["verdicts"]["apply"] == "SKIP"
        assert not result["success"]
        assert (Path(result["run_dir"]) / "candidate_profile.json").exists()
        assert (Path(result["run_dir"]) / "solve-report.json").exists()

    def test_verify_only_when_no_reference(self, tmp_path):
        """不提供参考标准文件：solve/apply 标记 SKIP，verify 单独可完成。"""
        metadata_path, _ = self._write_inputs(tmp_path)
        spec = _ref_spec()
        protected_entries = [i for i, s in enumerate(spec) if s[3]]
        profile_path = tmp_path / "candidate_profile.json"
        profile_path.write_text(json.dumps({
            "profile_id": "synth",
            "header_size": 31 * 12,
            "header_seed": "0x1",
            "sections": [
                {"size_off": i * 12 + 4, "offset_off": i * 12,
                 "adj": 0, "seed": f"0x{i + 1}"}
                for i in protected_entries
            ],
        }, ensure_ascii=False), encoding="utf-8")
        result = run_recovery(
            metadata_path=metadata_path,
            candidate_profile=str(profile_path),
            table_hex=TABLE_ZERO,
            out_dir=str(tmp_path / "out3"),
        )
        assert result["success"]
        assert result["verdicts"]["extract"] == "SKIP"
        assert result["verdicts"]["verify"] == VERDICT_PASS
        assert result["verdicts"]["solve"] == "SKIP"
        assert result["verdicts"]["apply"] == "SKIP"


class TestTableHex:
    def test_manual_table_hex(self):
        assert resolve_table_hex(table_hex=TABLE_ZERO) == TABLE_ZERO

    def test_invalid_manual_hex(self):
        with pytest.raises(ValueError):
            resolve_table_hex(table_hex="00" * 100)

    def test_no_source_returns_none(self):
        assert resolve_table_hex() is None
        assert resolve_table_hex(decompile_text="nothing here") is None


def _build_synthetic_pe(path):
    """最小 PE32+：MZ + PE 头 + 1 个 .text 节，数据填充 0xAB。"""
    image_base = 0x180000000
    rva = 0x1000
    raw_off = 0x200
    raw_size = 0x100
    pe_size = raw_off + raw_size

    data = bytearray(pe_size)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)  # e_lfanew
    pe_off = 0x80
    data[pe_off:pe_off + 4] = b"PE\0\0"
    struct.pack_into("<H", data, pe_off + 4, 0x8664)  # machine AMD64
    struct.pack_into("<H", data, pe_off + 6, 1)  # num sections
    struct.pack_into("<H", data, pe_off + 20, 0xF0)  # SizeOfOptionalHeader (PE32+ = 240)
    opt_off = pe_off + 24
    struct.pack_into("<H", data, opt_off, 0x20B)  # opt magic PE32+
    struct.pack_into("<Q", data, opt_off + 24, image_base)
    section_off = opt_off + 240  # PE32+ optional header 固定 240 字节
    struct.pack_into("<8s", data, section_off, b".text\0\0\0")
    struct.pack_into("<I", data, section_off + 8, raw_size)  # VirtualSize
    struct.pack_into("<I", data, section_off + 12, rva)  # VirtualAddress
    struct.pack_into("<I", data, section_off + 16, raw_size)  # SizeOfRawData
    struct.pack_into("<I", data, section_off + 20, raw_off)  # PointerToRawData
    for i in range(raw_off, pe_size):
        data[i] = 0xAB
    Path(path).write_bytes(bytes(data))
    return image_base, rva


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


class TestLoadLocatorExport:
    def _make_export(self, tmp_path):
        export = tmp_path / "locator_out"
        export.mkdir()
        (export / "decompile_rank1_sub_111.c").write_text(
            "char sub_111() { return 1; }", encoding="utf-8")
        (export / "decompile_rank2_sub_222.c").write_text(
            "char sub_222() { return 2; }", encoding="utf-8")
        hex1 = "00" * 256
        hex2 = "11" * 256
        (export / "locate_candidates.json").write_text(json.dumps({
            "verdict": "PASS",
            "candidates": [
                {"rank": 1, "name": "sub_111", "score": 100.0, "table_hex": hex1},
                {"rank": 2, "name": "sub_222", "score": 80.0, "table_hex": hex2},
                {"rank": 3, "name": "sub_333", "score": 60.0, "table_hex": "22" * 256},
            ],
        }), encoding="utf-8")
        return export, hex1, hex2

    def test_load_dir_default_rank1(self, tmp_path):
        export, hex1, _ = self._make_export(tmp_path)
        r = load_locator_export(str(export))
        assert r["success"]
        assert r["verdict"] == "PASS"
        assert r["rank"] == 1 and r["candidate_name"] == "sub_111"
        assert r["table_hex"] == hex1
        assert r["decompile_text"] == "char sub_111() { return 1; }"
        assert r["has_decompile"]
        assert len(r["candidates"]) == 3
        assert not r["errors"]

    def test_load_json_file_path(self, tmp_path):
        export, hex1, _ = self._make_export(tmp_path)
        r = load_locator_export(str(export / "locate_candidates.json"))
        assert r["success"] and r["table_hex"] == hex1

    def test_load_rank2(self, tmp_path):
        export, _, hex2 = self._make_export(tmp_path)
        r = load_locator_export(str(export), rank=2)
        assert r["success"]
        assert r["candidate_name"] == "sub_222"
        assert r["table_hex"] == hex2
        assert r["decompile_text"] == "char sub_222() { return 2; }"

    def test_rank_without_decompile(self, tmp_path):
        export, _, _ = self._make_export(tmp_path)
        r = load_locator_export(str(export), rank=3)
        assert r["success"]
        assert r["table_hex"] == "22" * 256  # hex 仍载入
        assert not r["has_decompile"] and not r["decompile_text"]
        assert any("无反编译文本" in e for e in r["errors"])

    def test_rank_out_of_range(self, tmp_path):
        export, _, _ = self._make_export(tmp_path)
        r = load_locator_export(str(export), rank=9)
        assert not r["success"]
        assert any("rank=9" in e for e in r["errors"])

    def test_missing_dir(self, tmp_path):
        r = load_locator_export(str(tmp_path / "nope"))
        assert not r["success"]

    def test_corrupted_json(self, tmp_path):
        export = tmp_path / "out"
        export.mkdir()
        (export / "locate_candidates.json").write_text("{broken", encoding="utf-8")
        r = load_locator_export(str(export))
        assert not r["success"]
        assert any("解析失败" in e for e in r["errors"])

    def test_dir_without_json(self, tmp_path):
        r = load_locator_export(str(tmp_path))
        assert not r["success"]
        assert any("locate_candidates.json" in e for e in r["errors"])


class TestReadRvaData:
    def test_read_from_synthetic_pe(self, tmp_path):
        dll = tmp_path / "GameAssembly.dll"
        image_base, rva = _build_synthetic_pe(dll)
        got = read_rva_data(str(dll), image_base + rva, 16)
        assert got == b"\xAB" * 16

    def test_bad_magic(self, tmp_path):
        dll = tmp_path / "bad.dll"
        dll.write_bytes(b"MZ" + b"\x00" * 64)
        with pytest.raises(ValueError):
            read_rva_data(str(dll), 0x180001000, 16)
