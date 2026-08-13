#!/usr/bin/env python3
"""versions.py - IL2CPP metadata 版本表（v39）。

记录 31 标准节名、规范序、固定记录大小（rec）。rec=None 表示无固定
记录大小（字节流/变长表）。rec=0 表示零尺寸节。

v39 rec 常量表从 08-06 标准文件（global-metadata-standard-steam-2026-08-06.dat）
导出：rec = size // count（整除时）。
"""

from __future__ import annotations

V39_NAMES = [
    "stringLiteral", "stringLiteralData", "string", "events", "properties",
    "methods", "parameterDefaultValues", "fieldDefaultValues",
    "fieldAndParameterDefaultValueData", "fieldMarshaledSizes", "parameters",
    "fields", "genericParameters", "genericParameterConstraints",
    "genericContainers", "nestedTypes", "interfaces", "vtableMethods",
    "interfaceOffsets", "typeDefinitions", "images", "assemblies", "fieldRefs",
    "referencedAssemblies", "attributeData", "attributeDataRange",
    "unresolvedVirtualCallParameterTypes",
    "unresolvedVirtualCallParameterRanges", "windowsRuntimeTypeNames",
    "windowsRuntimeStrings", "exportedTypeDefinitions",
]

# (name -> rec)。v39 导出值；rec=0 表示零尺寸节。
V39_REC = {
    "stringLiteral": 4,
    "stringLiteralData": None,        # 字节流（size≈count）
    "string": None,                   # 变长表
    "events": 24,
    "properties": 20,
    "methods": 32,
    "parameterDefaultValues": 12,
    "fieldDefaultValues": 12,
    "fieldAndParameterDefaultValueData": 1,
    "fieldMarshaledSizes": 12,
    "parameters": 12,
    "fields": 12,
    "genericParameters": 14,
    "genericParameterConstraints": 4,
    "genericContainers": 16,
    "nestedTypes": 4,
    "interfaces": 4,
    "vtableMethods": 4,
    "interfaceOffsets": 8,
    "typeDefinitions": 82,
    "images": 36,
    "assemblies": 68,
    "fieldRefs": 8,
    "referencedAssemblies": 4,
    "attributeData": None,            # 字节流（size≈count）
    "attributeDataRange": 8,
    "unresolvedVirtualCallParameterTypes": 4,
    "unresolvedVirtualCallParameterRanges": 8,
    "windowsRuntimeTypeNames": 0,
    "windowsRuntimeStrings": 0,
    "exportedTypeDefinitions": 4,
}

VERSIONS = {
    39: {
        "names": V39_NAMES,
        "rec": V39_REC,
    },
}


def version_table(metadata_version: int) -> dict:
    if metadata_version not in VERSIONS:
        raise ValueError(f"unsupported IL2CPP metadata version {metadata_version}")
    return VERSIONS[metadata_version]
