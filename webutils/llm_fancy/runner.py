"""
webutils/llm_fancy/runner.py
LLM 美化编排：扫描 → bus 排除 → 分批 → LLM 调用 → 生成 bus 规则集。
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from globalManagers.ConfigManager import ConfigManager
from webutils.llm_fancy.config import LLMFancyConfig
from webutils.llm_fancy.exclude import compile_exclusion_rulesets, excluded_paths
from webutils.llm_fancy.llm import (
    build_system_prompt,
    build_translator,
    parse_batch_response,
    translate_batch,
)
from webutils.llm_fancy.scanner import Candidate, compile_selection, dedup_candidates, scan_data
from webutils.llm_fancy.splitter import estimate_item_size, split_items

logger = logging.getLogger("llm_fancy")


class LLMFancyCancelled(Exception):
    """用户取消了 LLM 美化任务。"""


@dataclass
class LLMFancyRunResult:
    files_scanned: int = 0
    candidates: int = 0
    excluded: int = 0
    deduped: int = 0
    batches: int = 0
    llm_failed: int = 0
    unchanged: int = 0
    changed: int = 0
    ruleset_name: str = ""
    ruleset_path: str = ""
    elapsed_seconds: float = 0.0
    errors: tuple[str, ...] = ()


@dataclass
class ScanResult:
    lang_dir: Path
    candidates: list
    excluded: int
    files_scanned: int
    errors: tuple[str, ...]
    deduped: int = 0


def resolve_lang_dir(game_path: str) -> Path:
    """解析当前安装语言包目录（与 fancy_main 相同的 Lang/config.json 机制）。"""
    lang_path = Path(game_path) / "LimbusCompany_Data" / "Lang"
    if not lang_path.is_dir():
        raise ValueError(f"语言目录不存在: {lang_path}")
    config_json = lang_path / "config.json"
    lang_name = ""
    if config_json.exists():
        try:
            lang_name = json.loads(
                config_json.read_text(encoding="utf-8")
            ).get("lang", "")
        except Exception:
            lang_name = ""
    if not lang_name:
        raise ValueError("无法确定当前安装汉化包（Lang/config.json 缺少 lang 字段）")
    lang_dir = lang_path / lang_name
    if not lang_dir.is_dir():
        raise ValueError(f"语言包目录不存在: {lang_dir}")
    return lang_dir


def _scan(
    config: LLMFancyConfig,
    *,
    on_log: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[Any] = None,
) -> ScanResult:
    log = on_log or (lambda message: None)
    progress = on_progress or (lambda pct, message: None)

    mgr = ConfigManager()
    game_path = mgr.get("game_path", "")
    if not game_path:
        raise ValueError("未配置游戏路径（game_path），请在设置页填写")
    lang_dir = resolve_lang_dir(game_path)
    log(f"语言包目录: {lang_dir}")

    selection = compile_selection(config.selection)
    exclusion_compiled, missing = compile_exclusion_rulesets(config.exclusions)
    if missing:
        log(f"警告：以下排除规则集不存在或不是 bus 格式，已忽略: {', '.join(missing)}")
    log(f"选择规则: {selection.name}（{len(selection.rules)} 条）")
    if exclusion_compiled:
        log(f"排除规则集: {len(exclusion_compiled)} 个")

    files = sorted(lang_dir.rglob("*.json"))
    log(f"扫描 {len(files)} 个语言文件...")
    candidates: list = []
    excluded_count = 0
    errors: list[str] = []
    for file_index, file in enumerate(files):
        if cancel_event is not None and cancel_event.is_set():
            raise LLMFancyCancelled()
        relative_path = file.relative_to(lang_dir).as_posix()
        try:
            data = json.loads(file.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            errors.append(f"{relative_path}: {exc}")
            continue
        file_candidates = scan_data(data, relative_path, selection)
        if file_candidates:
            excluded = excluded_paths(data, relative_path, exclusion_compiled)
            if excluded:
                kept = [
                    candidate
                    for candidate in file_candidates
                    if candidate.path not in excluded
                ]
                excluded_count += len(file_candidates) - len(kept)
                file_candidates = kept
            candidates.extend(file_candidates)
        if (file_index + 1) % 50 == 0 or file_index + 1 == len(files):
            progress(
                int((file_index + 1) / len(files) * 100),
                f"扫描 {file_index + 1}/{len(files)}",
            )
    log(f"扫描完成：候选 {len(candidates)} 条，被排除 {excluded_count} 条")
    return ScanResult(
        lang_dir=lang_dir,
        candidates=candidates,
        excluded=excluded_count,
        files_scanned=len(files),
        errors=tuple(errors),
    )


def scan_preview(
    config: LLMFancyConfig,
    *,
    on_log: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[Any] = None,
) -> ScanResult:
    """仅执行扫描与排除，不调用 LLM（供窗口扫描预览）。"""
    log = on_log or (lambda message: None)
    scan = _scan(config, on_log=on_log, on_progress=on_progress, cancel_event=cancel_event)
    if config.dedup_enabled:
        representatives, _ = dedup_candidates(scan.candidates)
        scan.deduped = len(scan.candidates) - len(representatives)
        if scan.deduped:
            log(
                f"去重：{scan.deduped} 条相同文本合并为 "
                f"{len(representatives)} 条，LLM 调用减少 {scan.deduped} 次"
            )
    return scan


def _process_batch(
    batch: list,
    system_prompt: str,
    api_settings: dict,
    max_length: int,
    cancel_event: Optional[Any],
) -> Optional[list]:
    if cancel_event is not None and cancel_event.is_set():
        return None
    items = [{"id": index + 1, "text": candidate.value} for index, candidate in enumerate(batch)]
    translator = build_translator(api_settings, system_prompt, max_length=max_length)
    response = translate_batch(translator, items)
    return parse_batch_response(response, len(batch))


def run_beautify(
    config: LLMFancyConfig,
    api_settings: dict,
    *,
    on_log: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[Any] = None,
    name: Optional[str] = None,
) -> LLMFancyRunResult:
    """执行完整 LLM 美化流程，生成并保存 bus 规则集。"""
    started = time.perf_counter()
    log = on_log or (lambda message: None)
    progress = on_progress or (lambda pct, message: None)

    scan = _scan(
        config,
        on_log=on_log,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )
    candidates = scan.candidates
    if config.dedup_enabled:
        representatives, groups = dedup_candidates(candidates)
        groups = {id(representatives[index]): members for index, members in groups.items()}
    else:
        representatives = candidates
        groups = {id(candidate): [candidate] for candidate in candidates}
    deduped = len(candidates) - len(representatives)
    result = LLMFancyRunResult(
        files_scanned=scan.files_scanned,
        candidates=len(candidates),
        excluded=scan.excluded,
        deduped=deduped,
        errors=scan.errors,
    )
    if not candidates:
        log("没有需要美化的文本，任务结束")
        result.elapsed_seconds = time.perf_counter() - started
        return result
    if deduped:
        log(
            f"去重：{deduped} 条相同文本合并为 "
            f"{len(representatives)} 条，LLM 调用减少 {deduped} 次"
        )

    max_length = max(int(config.max_length), 1000)
    batches = split_items(
        representatives,
        lambda candidate: estimate_item_size(candidate.value),
        max_length,
    )
    result.batches = len(batches)
    log(f"打包完成：{len(batches)} 批（每批上限 {max_length} 字符）")

    max_workers = max(1, min(int(config.max_workers), len(batches)))
    system_prompt = build_system_prompt(config.custom_prompt, config.custom_prompt_enabled)
    if config.custom_prompt_enabled and config.custom_prompt.strip():
        log("已注入自定义提示词")
    log(f"开始 LLM 美化（并发 {max_workers}）...")

    batch_results: dict[int, Optional[list]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for index, batch in enumerate(batches):
            if cancel_event is not None and cancel_event.is_set():
                raise LLMFancyCancelled()
            futures[executor.submit(
                _process_batch,
                batch,
                system_prompt,
                api_settings,
                max_length,
                cancel_event,
            )] = index
        for future in as_completed(futures):
            index = futures[future]
            try:
                texts = future.result()
            except Exception as exc:
                batch_results[index] = None
                logger.exception("LLM 批次 %d 失败", index + 1)
                log(f"批次 {index + 1} 失败: {exc}")
            else:
                batch_results[index] = texts
            completed = sum(1 for value in batch_results.values() if value is not None)
            log(f"LLM 批次完成 {completed}/{len(batches)}")
            progress(int(completed / len(batches) * 100), f"LLM 处理 {completed}/{len(batches)}")

    llm_failed = 0
    unchanged = 0
    beautified: list = []
    for index, batch in enumerate(batches):
        texts = batch_results.get(index)
        if texts is None:
            for representative in batch:
                llm_failed += len(groups[id(representative)])
            continue
        for representative, text in zip(batch, texts):
            if text is None:
                llm_failed += len(groups[id(representative)])
                continue
            for candidate in groups[id(representative)]:
                if text == candidate.value:
                    unchanged += 1
                else:
                    beautified.append((candidate, text))

    result.llm_failed = llm_failed
    result.unchanged = unchanged
    result.changed = len(beautified)

    if beautified:
        from webutils.llm_fancy.builder import (
            build_ruleset,
            enable_ruleset_in_config,
            save_ruleset,
        )

        ruleset = build_ruleset(beautified, name=name)
        saved_path = save_ruleset(ruleset, ruleset["name"])
        enable_ruleset_in_config(ruleset["name"])
        result.ruleset_name = ruleset["name"]
        result.ruleset_path = str(saved_path)
        log(f"生成规则集: {ruleset['name']}（{len(beautified)} 条规则）")
        log(f"已保存: {saved_path}")
        log("已在文本美化页自动启用，可打开「立即应用美化」生效")
    else:
        log("没有产生任何文本变化，未生成规则集")

    result.elapsed_seconds = time.perf_counter() - started
    log(
        f"完成：候选 {result.candidates}，排除 {result.excluded}，"
        f"去重 {result.deduped}，美化 {result.changed}，未变化 {result.unchanged}，"
        f"失败 {result.llm_failed}，耗时 {result.elapsed_seconds:.1f} 秒"
    )
    return result
