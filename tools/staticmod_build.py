#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""staticmod 构建工具：把补丁 JSON 打包成 .staticmod（zip 容器）。

用法:
  # 从补丁目录打包
  python tools/staticmod_build.py build <out.staticmod> --name <mod名> \
      --version 1.0.0 --description "..." \
      --patch skill:personality-skill-01:patches/skill.json:jsonpatch \
      --full enemy:enemy-101:full/enemy-101.json

  # 校验包
  python tools/staticmod_build.py check <mod.staticmod>

  # 预览（列出包内容 + manifest）
  python tools/staticmod_build.py info <mod.staticmod>

补丁参数格式: dataClass:file:sourcePath[:opType]   (opType 默认 jsonpatch)
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

FORMAT = "staticmod/v1"


def build(out: str, name: str, version: str, description: str,
          patches, full_files) -> int:
    manifest = {
        "format": FORMAT,
        "name": name,
        "version": version,
        "description": description,
        "patches": [],
        "fullFiles": [],
    }
    out_path = Path(out)
    if not out_path.name.endswith(".staticmod"):
        out_path = out_path.with_suffix(".staticmod")

    entries = []  # (zip内路径, 源文件路径)
    for spec in patches or []:
        parts = spec.split(":")
        if len(parts) < 3 or len(parts) > 4:
            print("patch 参数错误: %r (需要 dataClass:file:source[:opType])" % spec)
            return 2
        dc, fn, src = parts[0], parts[1], parts[2]
        op_type = parts[3] if len(parts) == 4 else "jsonpatch"
        if op_type not in ("jsonpatch", "pathset"):
            print("未知 opType: %r" % op_type)
            return 2
        src_path = Path(src)
        if not src_path.is_file():
            print("补丁源文件不存在: %s" % src)
            return 2
        dest = "patches/%s.json" % dc
        entries.append((dest, src_path))
        manifest["patches"].append({
            "dataClass": dc, "file": fn,
            "opType": op_type, "source": dest,
        })

    for spec in full_files or []:
        parts = spec.split(":")
        if len(parts) != 3:
            print("full 参数错误: %r (需要 dataClass:file:source)" % spec)
            return 2
        dc, fn, src = parts
        src_path = Path(src)
        if not src_path.is_file():
            print("full 源文件不存在: %s" % src)
            return 2
        dest = "full/%s/%s.json" % (dc, fn)
        entries.append((dest, src_path))
        manifest["fullFiles"].append({
            "dataClass": dc, "file": fn, "source": dest,
        })

    if not manifest["patches"] and not manifest["fullFiles"]:
        print("至少需要一个补丁或 full 文件")
        return 2

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for dest, src in entries:
            z.write(src, dest)

    print("已生成: %s (%d 补丁, %d full)" % (out_path, len(manifest["patches"]), len(manifest["fullFiles"])))
    return 0


def check(mod: str) -> int:
    try:
        with zipfile.ZipFile(mod) as z:
            bad = z.testzip()
            if bad:
                print("包损坏: %s" % bad)
                return 1
            with z.open("manifest.json") as f:
                manifest = json.load(f)
    except (OSError, ValueError, KeyError) as e:
        print("无效包: %s" % e)
        return 1
    if manifest.get("format") != FORMAT:
        print("格式不匹配: %r" % manifest.get("format"))
        return 1
    # 校验声明的 source 都存在于包内
    missing = []
    for p in manifest.get("patches", []):
        if p.get("source") not in z.namelist():
            missing.append(p.get("source"))
    for ff in manifest.get("fullFiles", []):
        if ff.get("source") not in z.namelist():
            missing.append(ff.get("source"))
    if missing:
        print("声明的文件缺失: %s" % missing)
        return 1
    print("OK: %s (format=%s, name=%s)" % (mod, manifest.get("format"), manifest.get("name")))
    return 0


def info(mod: str) -> int:
    with zipfile.ZipFile(mod) as z:
        with z.open("manifest.json") as f:
            manifest = json.load(f)
    print("包: %s" % mod)
    print("  format:      %s" % manifest.get("format"))
    print("  name:        %s" % manifest.get("name"))
    print("  version:     %s" % manifest.get("version"))
    print("  description: %s" % manifest.get("description", ""))
    for p in manifest.get("patches", []):
        print("  patch: %s/%s (%s) <- %s" % (p.get("dataClass"), p.get("file"), p.get("opType"), p.get("source")))
    for ff in manifest.get("fullFiles", []):
        print("  full:  %s/%s <- %s" % (ff.get("dataClass"), ff.get("file"), ff.get("source")))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="staticmod 构建/校验/预览")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="打包 .staticmod")
    b.add_argument("out")
    b.add_argument("--name", required=True)
    b.add_argument("--version", default="1.0.0")
    b.add_argument("--description", default="")
    b.add_argument("--patch", action="append", default=[], help="dataClass:file:source[:opType]")
    b.add_argument("--full", action="append", default=[], help="dataClass:file:source")
    b.set_defaults(func=lambda a: build(a.out, a.name, a.version, a.description, a.patch, a.full))

    c = sub.add_parser("check", help="校验包")
    c.add_argument("mod")
    c.set_defaults(func=lambda a: check(a.mod))

    i = sub.add_parser("info", help="预览包")
    i.add_argument("mod")
    i.set_defaults(func=lambda a: info(a.mod))

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
