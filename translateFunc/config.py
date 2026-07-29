"""
translateFunc/config.py
配置数据类和结果容器。
将 translateFunc 与 ConfigManager 解耦 —— 所有配置通过 TranslateConfig 流入。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from translateFunc.enums import ProcessResult


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


@dataclass
class TranslateConfig:
    """一次翻译运行的全部配置。由调用方（WebUI 或 CLI）注入。"""
    # --- 翻译器 ---
    translator_name: str = "LLM通用翻译服务"
    translator_api: dict = field(default_factory=dict)

    # --- 路径 ---
    game_path: Path = Path()
    output_dir: Path = Path()

    # --- 功能开关 ---
    enable_proper: bool = True
    enable_role: bool = True
    enable_skill: bool = True
    # --- 并发 ---
    enable_concurrent: bool = True
    file_concurrency: int = 24
    request_concurrency: int = 16
    file_io_concurrency: int = 32

    # --- 提示词 / 管线 ---
    enable_self_check: bool = False
    enable_rule_validation: bool = True   # 启用确定性规则后处理校验（仅技能文件）

    # --- 保存 ---
    save_result: bool = True

    # --- LLM 思考模式 ---
    enable_thinking: bool = False

    # --- 调试 ---
    dump: bool = False
    dump_path: Optional[Path] = None

    # --- 规则与路径覆盖 ---
    auto_fetch_proper: bool = True
    proper_path: str = ""
    has_prefix: bool = True
    kr_path: str = ""
    jp_path: str = ""
    en_path: str = ""
    llc_path: str = ""

    @classmethod
    def from_config_manager(cls, mgr) -> "TranslateConfig":
        """从全局 ConfigManager 单例构建 TranslateConfig。"""
        configs: dict = mgr.get("ui_default.translator", {})
        game_path = Path(mgr.get("game_path", ""))
        translator_name = configs.get("translator", "LLM通用翻译服务")
        if translator_name not in {"LLM通用翻译服务", "空翻译器(使用原文)"}:
            translator_name = "LLM通用翻译服务"

        return cls(
            translator_name=translator_name,
            game_path=game_path,
            enable_proper=configs.get("enable_proper", True),
            enable_role=configs.get("enable_role", True),
            enable_skill=configs.get("enable_skill", True),
            auto_fetch_proper=configs.get("auto_fetch_proper", True),
            proper_path=configs.get("proper_path", ""),
            has_prefix=configs.get("has_prefix", True),
            kr_path=configs.get("kr_path", ""),
            jp_path=configs.get("jp_path", ""),
            en_path=configs.get("en_path", ""),
            llc_path=configs.get("llc_path", ""),
            dump=configs.get("dump", False),
            enable_concurrent=configs.get("enable_concurrent", True),
            file_concurrency=_bounded_int(
                configs.get("file_concurrency", 24), 24, 1, 128
            ),
            request_concurrency=_bounded_int(
                configs.get("request_concurrency", 16), 16, 1, 128
            ),
            file_io_concurrency=_bounded_int(
                configs.get("file_io_concurrency", 32), 32, 1, 256
            ),
            enable_self_check=configs.get("enable_self_check", False),
            enable_thinking=configs.get("enable_thinking", False),
            enable_rule_validation=configs.get("enable_rule_validation", True),
        )


def inject_thinking_mode(api_settings: dict, enable_thinking: bool) -> dict:
    """根据 enable_thinking 配置向 api_settings 注入思考模式参数。

    - DeepSeek: {"thinking": {"type": "enabled"}}（自定义格式）
    - 其他提供商: {"reasoning_effort": "medium"}（OpenAI 通用格式）

    Args:
        api_settings: 翻译器 API 配置字典（会被浅拷贝，不会修改原字典）
        enable_thinking: 是否启用思考模式

    Returns:
        修改后的 api_settings 浅拷贝
    """
    settings = dict(api_settings)  # 浅拷贝
    base_url = settings.get("base_url", "")

    # 确保 extra_body 存在
    extra_body = dict(settings.get("extra_body", {}))

    if "api.deepseek.com" in base_url:
        # DeepSeek 思考模式：thinking.type = "enabled"/"disabled"
        extra_body["thinking"] = {"type": "enabled" if enable_thinking else "disabled"}

    if enable_thinking:
        # 其他提供商使用 OpenAI 通用格式：reasoning_effort
        # Deepseek 也可以加，方便后续添加reasoning_effort配置项
        extra_body["reasoning_effort"] = "medium"

    settings["extra_body"] = extra_body
    return settings


@dataclass
class ProcessOutcome:
    """单个文件的处理结果。"""
    result: ProcessResult
    file_name: str
    extra: dict | None = None  # 错误详情、耗时等附加信息


@dataclass
class PipelineSummary:
    """一次翻译运行的汇总结果。"""
    saved: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    fallback: list[str] = field(default_factory=list)
    errors: list[ProcessOutcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.saved) + len(self.skipped) + len(self.fallback) + len(self.errors)

    @property
    def success_count(self) -> int:
        return len(self.saved)

    @property
    def fallback_count(self) -> int:
        return len(self.fallback)

    @property
    def error_count(self) -> int:
        return len(self.errors)
