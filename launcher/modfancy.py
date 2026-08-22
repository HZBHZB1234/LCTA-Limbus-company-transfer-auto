"""模组目录内「非预期 JSON」的 fancy 引擎临时应用。

mod 加载器（changes.apply_patch）只消费带 `patchs` 键的文本补丁 JSON，
其余 JSON 之前被静默跳过。本模块在文本补丁流程之后运行：识别 mod 目录中
无法作为文本补丁的 JSON（bus / 调爪 / FL / LCJE / v2 文本美化规则集），
用项目的 fancy 引擎（MIT，非 GPL 派生的 LimbusModLoader 代码）临时编译并
应用到游戏 `LimbusCompany_Data/lang/**` 文件。

「临时」通过已有的 `.bak` 回滚机制保证：本模块在写回每个 lang 文件前若其
`.bak` 不存在则备份，`cleanup_patch`（启动前/游戏退出时）会把 `.bak` 还原为
原 `.json`，因此这些美化改动只在本次启动会话内生效。
"""

import json
import shutil
from pathlib import Path

from globalManagers.LogManager import LogManager

_log_manager = LogManager()


def detect_compiled_rulesets(mod_path: str) -> "list":
    """扫描模组目录内非文本补丁（无 `patchs`）的 JSON，识别并编译为 fancy 规则集。

    返回 `[(kind, compiled), ...]`，`kind` 为 `'bus'` 或 `'v2'`，顺序不保证
    （应用阶段会统一按 bus 在前排序）。无法识别的 JSON 仅记录日志并跳过。
    """
    from launcher.modcache import enabled_mod_files
    from webutils.fancy.bus import (
        compile_bus_ruleset,
        convert_fl_config,
        convert_lcje_config,
        convert_tiaozhua_config,
        is_bus_ruleset,
        is_fl_config,
        is_lcje_config,
        is_tiaozhua_config,
    )
    from webutils.fancy.engine import compile_rulesets

    compiled = []
    for f in enabled_mod_files(mod_path, "*.json"):
        try:
            with open(f, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:
            _log_manager.log("跳过无效 json（模组美化检测）%s: %s", f, e)
            continue
        if not isinstance(data, dict):
            continue
        # 已被文本补丁流程消费的文件跳过
        if "patchs" in data:
            continue
        try:
            if is_tiaozhua_config(data):
                ruleset, _stats = convert_tiaozhua_config(data)
                compiled.append(("bus", compile_bus_ruleset(ruleset)))
                _log_manager.log("模组美化：识别为调爪文本配置 -> bus 规则集: %s", f)
            elif is_fl_config(data):
                ruleset, _stats = convert_fl_config(data)
                compiled.append(("bus", compile_bus_ruleset(ruleset)))
                _log_manager.log("模组美化：识别为 FL 替换配置 -> bus 规则集: %s", f)
            elif is_lcje_config(data):
                ruleset, _stats = convert_lcje_config(data)
                compiled.append(("bus", compile_bus_ruleset(ruleset)))
                _log_manager.log("模组美化：识别为 LCJE 配置 -> bus 规则集: %s", f)
            elif is_bus_ruleset(data):
                compiled.append(("bus", compile_bus_ruleset(data)))
                _log_manager.log("模组美化：识别为 bus 规则集: %s", f)
            elif data.get("version") == 2 and "name" in data and "rules" in data:
                compiled.append(("v2", compile_rulesets([data])))
                _log_manager.log("模组美化：识别为 v2 文本美化规则集: %s", f)
            else:
                _log_manager.log("模组 JSON 非文本补丁且非已知美化规则集，跳过: %s", f)
        except Exception as e:
            _log_manager.log("识别/编译模组美化规则集失败 %s: %s", f, e)
    return compiled


def apply_compiled_to_lang(lang_path: Path, compiled: "list") -> None:
    """将已编译的 fancy 规则集临时应用到 `lang` 下的所有语言包 JSON 文件。

    相对路径按各语言包目录计算（与 `function_fancy.fancy_main` 一致），
    由规则集自身的文件选择器决定命中哪些文件。写回前对无 `.bak` 的文件
    建立备份，保证启动/退出时 `cleanup_patch` 可回滚。
    """
    if not compiled:
        return
    from webutils.fancy.bus import apply_bus
    from webutils.fancy.engine import apply_rules

    # bus 文本替换先于 v2 文本美化，与 fancy_main 执行顺序对齐
    compiled = sorted(compiled, key=lambda item: 0 if item[0] == "bus" else 1)

    # 遍历每个语言包目录（lang 下的一级子目录即包）
    package_dirs = [d for d in lang_path.iterdir() if d.is_dir()] if lang_path.is_dir() else []
    if not package_dirs:
        _log_manager.log("模组美化：未找到任何语言包目录，跳过 %s", lang_path)
        return

    total_matched = 0
    total_changed = 0
    for package_dir in package_dirs:
        files = list(package_dir.rglob("*.json"))
        for file in files:
            if file.suffix != ".json":
                continue
            relative = file.relative_to(package_dir).as_posix()
            matched_entries = []
            for kind, c in compiled:
                if kind == "v2":
                    file_rules = c.for_file(relative)
                    if file_rules.rules:
                        matched_entries.append(("v2", file_rules))
                else:
                    bus_rules = c.for_file(relative)
                    if bus_rules:
                        matched_entries.append(("bus", (c, bus_rules)))
            if not matched_entries:
                continue
            total_matched += 1
            try:
                # 备份以便启动时回滚（临时应用）
                bak = file.with_suffix(".bak")
                if not bak.exists():
                    shutil.copyfile(file, bak)
                data = json.loads(file.read_text(encoding="utf-8-sig"))
                changed_paths = set()
                for kind, matched_rules in matched_entries:
                    if kind == "v2":
                        result = apply_rules(data, matched_rules)
                    else:
                        compiled_bus, bus_rules = matched_rules
                        result = apply_bus(data, compiled_bus, relative, rules=bus_rules)
                    data = result.data
                    changed_paths.update(result.changed_paths)
                if changed_paths:
                    file.write_text(
                        json.dumps(data, ensure_ascii=False, indent=4),
                        encoding="utf-8",
                    )
                    total_changed += 1
            except Exception as e:
                _log_manager.log("应用模组美化规则到 %s 失败: %s", file, e)
    _log_manager.log(
        "模组美化：匹配 %d 个文件，修改 %d 个文件（临时，退出时回滚）",
        total_matched,
        total_changed,
    )


def apply_fancy_patches(mod_path: str, lang_path: Path) -> None:
    """识别模组目录中的非预期 JSON 并用 fancy 引擎临时应用。"""
    compiled = detect_compiled_rulesets(mod_path)
    if not compiled:
        return
    _log_manager.log("模组美化：识别到 %d 个规则集，开始临时应用", len(compiled))
    apply_compiled_to_lang(lang_path, compiled)
