"""
translateFunc/pipeline.py
TranslationPipeline —— 翻译运行的端到端编排。

流程：
  1. ProperAnalyzer.fetch_and_build() —— 获取术语，构建 JP/EN 上下文
  2. MatcherEngine.build() —— 填充全部 4 个 AC 自动机
  3. 串行处理优先文件（ScenarioModelCodes、BattleKeywords）
  4. WorkerPool.map() 并发处理剩余文件
  5. 聚合为 PipelineSummary
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import json
import logging
import os
import sys
import tempfile
from itertools import zip_longest
from typing import Any, Callable

from translateFunc.config import (
    TranslateConfig, ProcessOutcome, PipelineSummary,
    PathConfig, FilePathConfig, inject_thinking_mode,
    _suppress_translatekit_log,
)
from translateFunc.enums import ProcessResult, FileType
from translateFunc.matcher.engine import MatcherEngine
from translateFunc.matcher.proper import ProperAnalyzer
from translateFunc.processor import FileProcessor
from translateFunc.workers import WorkerPool
from translateFunc.get_proper import fetch as fetch_proper
from translateFunc.translate_request import TRANSLATOR_TRANS
# system_prompt 由 processor 通过 translator.update_config() 动态更新
from translateFunc.profiler import TimingProfiler
from translatekit import TranslationConfig as TKitConfig, TranslatorBase

# 延迟导入 LogManager 以避免模块级别的循环导入
def _get_log_manager():
    from globalManagers.LogManager import LogManager
    return LogManager()


class TranslationPipeline:
    """编排完整翻译流程的管道类。"""

    def __init__(self, config: TranslateConfig):
        self._config = config
        self._engine = MatcherEngine()
        self._analyzer: ProperAnalyzer | None = None

        # 回调函数
        self._on_log: Callable[[str], None] = lambda msg: None
        self._on_status: Callable[[str], None] = lambda msg: None
        self._on_progress: Callable[[int, str], None] = lambda pct, msg: None
        self._on_check_running: Callable[[], None] = lambda: None

    def set_callbacks(
        self,
        *,
        on_log: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_progress: Callable[[int, str], None] | None = None,
        on_check_running: Callable[[], None] | None = None,
    ) -> None:
        """注册 UI 回调函数以报告进度。"""
        if on_log:
            self._on_log = on_log
        if on_status:
            self._on_status = on_status
        if on_progress:
            self._on_progress = on_progress
        if on_check_running:
            self._on_check_running = on_check_running

    # ========== 运行 ==========

    def run(self) -> PipelineSummary:
        """执行完整的翻译管道。返回聚合的 PipelineSummary。"""
        profiler = TimingProfiler.get()
        profiler.reset()

        self._on_status("正在初始化...")
        logging.info("=== 阶段 1/5: 解析路径配置 ===")

        # 1. 解析路径
        game_path = self._config.game_path
        assets_path = game_path / "LimbusCompany_Data" / "Assets" / "Resources_moved" / "Localize"
        lang_path = game_path / "LimbusCompany_Data" / "lang"

        kr_path = Path(self._config.kr_path) if self._config.kr_path and self._config.enable_dev_settings else assets_path / "kr"
        jp_path = Path(self._config.jp_path) if self._config.jp_path and self._config.enable_dev_settings else assets_path / "jp"
        en_path = Path(self._config.en_path) if self._config.en_path and self._config.enable_dev_settings else assets_path / "en"
        llc_path = Path(self._config.llc_path) if self._config.llc_path and self._config.enable_dev_settings else lang_path / "LLC_zh-CN"

        output_dir = self._config.output_dir / "LLc-CN-LCTA"
        output_dir.mkdir(parents=True, exist_ok=True)

        base_path_config = PathConfig(
            target_path=output_dir,
            llc_base_path=llc_path,
            KR_base_path=kr_path,
            JP_base_path=jp_path,
            EN_base_path=en_path,
        )

        # 2. 获取专有名词
        logging.info("=== 阶段 2/5: 获取专有名词 ===")
        with profiler.phase("获取专有名词"):
            if self._config.enable_proper:
                self._on_status("正在获取专有名词...")
                self._analyzer = ProperAnalyzer(kr_path, jp_path, en_path)

                with profiler.phase("专有名词抓取"):
                    raw_terms = self._analyzer.fetch_terms(
                        auto_fetch=self._config.auto_fetch_proper,
                        proper_path=self._config.proper_path,
                    )

                with profiler.phase("专有名词分析"):
                    proper_terms = self._analyzer.analyze(raw_terms)
                    proper_dicts = [
                        {"term": t.kr, "translation": t.cn, "note": t.note}
                        for t in proper_terms
                    ]
                    self._engine.build_proper(proper_dicts)
                self._on_log(f"已加载 {len(proper_terms)} 个专有名词")
            else:
                self._on_log("专有名词分析已跳过（enable_proper=False）")

        # 3. 构建翻译器
        logging.info("=== 阶段 3/5: 构建匹配引擎与翻译器 ===")
        with profiler.phase("构建匹配引擎"):
            translator = self._build_translator()

        # 4. 收集目标文件
        target_files = list(kr_path.rglob("*.json"))
        self._on_log(f"找到 {len(target_files)} 个文件")

        # 5. 重排序：优先文件放在前面
        has_prefix = self._config.has_prefix
        model_name = "KR_ScenarioModelCodes-AutoCreated.json" if has_prefix else "ScenarioModelCodes-AutoCreated.json"
        keyword_name = "KR_BattleKeywords.json" if has_prefix else "BattleKeywords.json"
        model_file = kr_path / model_name
        keyword_file = kr_path / keyword_name
        if model_file.exists() and keyword_file.exists():
            target_files.remove(model_file)
            target_files.remove(keyword_file)
            priority_files = [keyword_file, model_file]
        else:
            if not model_file.exists():
                self._on_log(f"警告: 未找到模型文件 {model_name}，跳过优先处理")
            if not keyword_file.exists():
                self._on_log(f"警告: 未找到关键字文件 {keyword_name}，跳过优先处理")
            priority_files = []

        # 6. 串行处理优先文件
        logging.info("=== 阶段 4/5: 处理优先文件 ===")
        summary = PipelineSummary()
        with profiler.phase("处理优先文件"):
            for pf in priority_files:
                outcome = self._process_one(pf, base_path_config, has_prefix, translator)
                self._record_outcome(outcome, summary)

                # 处理完优先文件后更新引擎
                if pf == priority_files[1] and self._config.enable_role:  # model 文件（第2个）
                    self._update_roles(pf, base_path_config, has_prefix)
                elif pf == priority_files[0] and self._config.enable_skill:  # keyword 文件（第1个）
                    self._update_affects(pf, base_path_config, has_prefix)

        # 7. 并发处理剩余文件
        logging.info(f"=== 阶段 5/5: 并发翻译 ({len(target_files)} 个文件) ===")
        self._on_status("正在执行翻译...")
        self._on_progress(10, "正在执行翻译...")

        with profiler.phase("并发翻译"):
            if self._config.enable_concurrent and len(target_files) > 1:
                worker_pool = WorkerPool(
                    translator_factory=lambda: self._build_translator(),
                    max_workers=self._config.max_workers,
                )

                def process_fn(file_path, translator):
                    return self._process_one(file_path, base_path_config, has_prefix, translator)

                def progress_cb(done, total, fname):
                    pct = 10 + int((done / total) * 80)
                    self._on_progress(pct, f"处理 {fname} ({done}/{total})")
                    self._on_check_running()

                outcomes = worker_pool.map(target_files, process_fn, on_progress=progress_cb)
            else:
                outcomes = []
                for i, file_path in enumerate(target_files):
                    outcome = self._process_one(file_path, base_path_config, has_prefix, translator)
                    outcomes.append(outcome)
                    pct = 10 + int(((i + 1) / len(target_files)) * 80)
                    self._on_progress(pct, f"处理 {outcome.file_name} ({i + 1}/{len(target_files)})")

        for o in outcomes:
            self._record_outcome(o, summary)

        # 8. 输出剖析报告
        self._on_progress(90, "已完成汉化")
        report = profiler.report()
        self._on_log(report)
        logging.info(report)

        return summary

    # ========== 内部方法 ==========

    def _process_one(
        self, file_path: Path, base_pc: PathConfig, has_prefix: bool, translator
    ) -> ProcessOutcome:
        """处理单个文件。返回 ProcessOutcome。"""
        file_pc = FilePathConfig(KR_path=file_path, _PathConfig=base_pc, has_prefix=has_prefix)
        processor = FileProcessor(
            path_config=file_pc,
            engine=self._engine,
            translate_config=self._config,
            translator=translator,
        )
        return processor.process()

    def _record_outcome(self, outcome: ProcessOutcome, summary: PipelineSummary) -> None:
        """将 ProcessOutcome 记录到 PipelineSummary 中。"""
        if outcome.result == ProcessResult.SUCCESS_SAVED:
            summary.saved.append(outcome.file_name)
        elif outcome.result in (ProcessResult.ALREADY_TRANSLATED, ProcessResult.EMPTY_WITH_LLC, ProcessResult.EMPTY_SKIPPED):
            summary.skipped.append(outcome.file_name)
        else:
            summary.errors.append(outcome)

    def _update_roles(self, model_file: Path, base_pc: PathConfig, has_prefix: bool) -> None:
        """从 ScenarioModelCodes 更新 MatcherEngine 中的角色数据。"""
        try:
            kr_data = json.loads(model_file.read_text(encoding="utf-8-sig"))
            target = FilePathConfig(KR_path=model_file, _PathConfig=base_pc, has_prefix=has_prefix).target_file
            cn_data = json.loads(target.read_text(encoding="utf-8-sig")) if target.exists() else kr_data
            kr_list = kr_data.get("dataList", kr_data if isinstance(kr_data, list) else [])
            cn_list = cn_data.get("dataList", cn_data if isinstance(cn_data, list) else [])

            if len(kr_list) != len(cn_list):
                logging.warning(
                    f"角色数据 KR/CN 列表长度不匹配: KR={len(kr_list)}, CN={len(cn_list)}，"
                    f"将按较短列表配对"
                )

            roles = []
            for k, c in zip_longest(kr_list, cn_list):
                if k is None or c is None:
                    continue
                roles.append({
                    "id": k["id"], "kr": k["name"], "cn": c["name"],
                    "nickName": c.get("nickName", ""),
                })
            self._engine.build_roles(roles)
            self._on_log(f"已加载 {len(roles)} 个角色信息")
        except Exception as e:
            self._on_log(f"加载角色信息失败: {e}")

    def _update_affects(self, keyword_file: Path, base_pc: PathConfig, has_prefix: bool) -> None:
        """从 BattleKeywords 更新 MatcherEngine 中的状态效果数据。"""
        try:
            kr_data = json.loads(keyword_file.read_text(encoding="utf-8-sig"))
            target = FilePathConfig(KR_path=keyword_file, _PathConfig=base_pc, has_prefix=has_prefix).target_file
            cn_data = json.loads(target.read_text(encoding="utf-8-sig")) if target.exists() else kr_data
            kr_list = kr_data.get("dataList", kr_data if isinstance(kr_data, list) else [])
            cn_list = cn_data.get("dataList", cn_data if isinstance(cn_data, list) else [])

            if len(kr_list) != len(cn_list):
                logging.warning(
                    f"状态效果数据 KR/CN 列表长度不匹配: KR={len(kr_list)}, CN={len(cn_list)}，"
                    f"将按较短列表配对"
                )

            affects = []
            for k, c in zip_longest(kr_list, cn_list):
                if k is None or c is None:
                    continue
                affects.append({
                    "id": k["id"], "kr": k["name"], "cn": c["name"],
                    "desc": c.get("desc", ""),
                })
            self._engine.build_affects(affects)
            self._on_log(f"已加载 {len(affects)} 个状态效果")
        except Exception as e:
            self._on_log(f"加载状态效果失败: {e}")

    def _build_translator(self) -> TranslatorBase:
        """根据配置创建翻译器实例。

        system_prompt 和 response_format 在 processor 中按需通过
        translator.update_config() 动态更新，不在构造时设置。
        """
        translator_cls = TRANSLATOR_TRANS[self._config.translator_name]
        api_settings = dict(self._config.translator_api)
        api_settings = inject_thinking_mode(api_settings, self._config.enable_thinking)

        if self._config.is_llm:
            api_settings["response_format"] = "json_object"

        tkit_config = TKitConfig(
            api_setting=api_settings,
            debug_mode=self._config.debug_mode,
            enable_cache=True,
            enable_metrics=True,
        )

        if self._config.is_llm:
            tkit_config.text_max_length = 20000
            tkit_config.max_workers = 1

        with _suppress_translatekit_log(self._config.debug_mode):
            translator = translator_cls(tkit_config)

        return translator
