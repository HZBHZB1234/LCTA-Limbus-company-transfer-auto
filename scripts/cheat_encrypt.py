#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LCTA CheatCore 构建期加密器（纯标准库，可被测试导入）

把私有仓库 LCTA_CheatingCore 的功能文件按 manifest.json 加密打包为
cheat_core.bin，随 LCTA 发布包分发。格式说明见私有仓库 README。

用法::

    python scripts/cheat_encrypt.py build --src <私有仓库克隆目录> --key <密钥文件> --out <cheat_core.bin>
    python scripts/cheat_encrypt.py info  --in <cheat_core.bin>
"""

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

MAGIC = b"LCTACC01"
ANCHOR = b"LCTA-CHEAT-KEY-OK!"
KEY_MIN_LEN = 8

MANIFEST_NAME = "manifest.json"


def xor(data: bytes, key: bytes) -> bytes:
    """repeating-key XOR。"""
    if not key:
        raise ValueError("密钥为空")
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


def load_key(key_path: Path) -> bytes:
    """读取密钥文件，去空白后按 UTF-8 编码；长度不足报错。"""
    text = key_path.read_text(encoding="utf-8").strip()
    key = text.encode("utf-8")
    if len(key) < KEY_MIN_LEN:
        raise ValueError(
            f"密钥长度不足：{len(key)} 字节 < 最小 {KEY_MIN_LEN} 字节（{key_path}）"
        )
    return key


def load_manifest(src_dir: Path) -> dict:
    """读取私有仓库的 manifest.json 并校验字段。"""
    manifest_path = src_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"未找到 {manifest_path}（私有仓库克隆目录不对？）")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or not isinstance(manifest.get("files"), list):
        raise ValueError(f"{manifest_path} 格式非法：需要 format=1 与 files 列表")
    for item in manifest["files"]:
        if not isinstance(item, dict) or not item.get("src") or not item.get("dest"):
            raise ValueError(f"{manifest_path} 存在缺少 src/dest 的条目: {item!r}")
    return manifest


def build_blob(src_dir: Path, key: bytes) -> bytes:
    """按 manifest 读取文件并打包为 blob 字节。所有 src 文件必须存在。"""
    manifest = load_manifest(src_dir)
    files = []
    payload_parts = [ANCHOR]
    for item in manifest["files"]:
        fpath = src_dir / item["src"]
        data = fpath.read_bytes()
        files.append(
            {
                "dest": item["dest"],
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        payload_parts.append(data)
    payload = b"".join(payload_parts)
    manifest_bytes = json.dumps(
        {"format": 1, "files": files}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return (
        MAGIC
        + struct.pack("<I", len(manifest_bytes))
        + manifest_bytes
        + xor(payload, key)
    )


def parse_blob(data: bytes):
    """解析 blob，返回 (manifest, cipher_payload)。格式非法抛 ValueError。"""
    if len(data) < len(MAGIC) + 4 or data[: len(MAGIC)] != MAGIC:
        raise ValueError("blob magic 不匹配（不是 LCTA cheat_core.bin）")
    mlen = struct.unpack("<I", data[len(MAGIC): len(MAGIC) + 4])[0]
    end = len(MAGIC) + 4 + mlen
    if mlen <= 0 or end > len(data):
        raise ValueError("blob manifest 长度非法")
    try:
        manifest = json.loads(data[len(MAGIC) + 4: end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"blob manifest 解析失败: {e}") from e
    return manifest, data[end:]


def decrypt_blob(data: bytes, key: bytes):
    """用密钥解密 blob，返回 (manifest, [(dest, 明文文件字节)...])。

    密钥错误 / 内容被篡改抛 ValueError。
    """
    manifest, cipher = parse_blob(data)
    payload = xor(cipher, key)
    if not payload.startswith(ANCHOR):
        raise ValueError("解密密钥错误（anchor 校验失败）")
    files = []
    offset = len(ANCHOR)
    for item in manifest.get("files", []):
        size = int(item["size"])
        chunk = payload[offset: offset + size]
        if len(chunk) != size:
            raise ValueError("blob 数据不完整（manifest 与密文长度不一致）")
        if hashlib.sha256(chunk).hexdigest() != item.get("sha256"):
            raise ValueError(f"文件 {item.get('dest')} 校验失败（密钥错误或数据损坏）")
        files.append((item["dest"], chunk))
        offset += size
    return manifest, files


def cmd_build(args) -> int:
    src_dir = Path(args.src)
    key = load_key(Path(args.key))
    blob = build_blob(src_dir, key)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    manifest, _ = parse_blob(blob)
    print(
        f"cheat_core.bin 生成完成: {out} ({len(blob)} 字节, "
        f"{len(manifest['files'])} 个文件, 密钥 {len(key)} 字节)"
    )
    return 0


def cmd_info(args) -> int:
    data = Path(args.infile).read_bytes()
    manifest, _ = parse_blob(data)
    print(f"magic: {MAGIC.decode()!r}  密文长度: {len(data) - len(MAGIC) - 4 - len(json.dumps(manifest, ensure_ascii=False).encode('utf-8'))} 字节")
    for f in manifest["files"]:
        print(f"  {f['dest']}: {f['size']} 字节 (sha256 {f['sha256'][:16]}...)")


def main(argv=None) -> int:
    # CI/无中文控制台环境下强制 UTF-8 输出，避免 charmap 编解码崩溃
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(description="LCTA CheatCore 加密器")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="读取私有仓库并按 manifest 加密打包")
    p_build.add_argument("--src", required=True, help="私有仓库克隆目录（含 manifest.json）")
    p_build.add_argument("--key", required=True, help="密钥文件路径")
    p_build.add_argument("--out", required=True, help="输出 blob 路径")
    p_build.set_defaults(func=cmd_build)

    p_info = sub.add_parser("info", help="查看 blob 明文头信息")
    p_info.add_argument("--in", dest="infile", required=True, help="blob 路径")
    p_info.set_defaults(func=cmd_info)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
