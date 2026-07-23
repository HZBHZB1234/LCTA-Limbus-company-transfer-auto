"""
translateFunc/config.py
配置数据类和结果容器。
将 translateFunc 与 ConfigManager 解耦 —— 所有配置通过 TranslateConfig 流入。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from translateFunc.enums import ProcessResult


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
    enable_dev_settings: bool = False

    # --- 并发 ---
    max_workers: int = 4
    enable_concurrent: bool = True

    # --- 提示词 / 管线 ---
    translation_mode: str = "multi_stage"     # "multi_stage" | "single_stage"
    enable_self_check: bool = False
    enable_rule_validation: bool = True   # 启用确定性规则后处理校验（仅技能文件）
    disambiguation_mode: str = "hybrid"       # "similarity" | "llm" | "hybrid"
    min_confidence: str = "medium"            # "high" | "medium" | "low"
    prompt_format: str = "xml_json"           # "xml_json" | "xml_xml" | "json_json"

    # --- 保存 ---
    save_result: bool = True

    # --- LLM 思考模式 ---
    enable_thinking: bool = False

    # --- 调试 ---
    debug_mode: bool = False
    dump: bool = False
    dump_path: Optional[Path] = None

    # --- 兼容旧配置项 ---
    is_llm: bool = True
    from_lang: str = "EN"
    auto_fetch_proper: bool = True
    proper_path: str = ""
    fallback: bool = True
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
        debug_mode = mgr.get("debug", False)

        return cls(
            translator_name=configs.get("translator", "LLM通用翻译服务"),
            is_llm=(configs.get("translator", "LLM通用翻译服务") == "LLM通用翻译服务"),
            game_path=game_path,
            enable_proper=configs.get("enable_proper", True),
            enable_role=configs.get("enable_role", True),
            enable_skill=configs.get("enable_skill", True),
            enable_dev_settings=configs.get("enable_dev_settings", False),
            from_lang=configs.get("from_lang", "EN"),
            auto_fetch_proper=configs.get("auto_fetch_proper", True),
            proper_path=configs.get("proper_path", ""),
            fallback=configs.get("fallback", True),
            has_prefix=configs.get("has_prefix", True),
            kr_path=configs.get("kr_path", ""),
            jp_path=configs.get("jp_path", ""),
            en_path=configs.get("en_path", ""),
            llc_path=configs.get("llc_path", ""),
            debug_mode=debug_mode,
            dump=configs.get("dump", False),
            # 新增配置项及其默认值：
            max_workers=configs.get("max_workers", 4),
            enable_concurrent=configs.get("enable_concurrent", True),
            translation_mode=configs.get("translation_mode", "multi_stage"),
            enable_self_check=configs.get("enable_self_check", False),
            disambiguation_mode=configs.get("disambiguation_mode", "hybrid"),
            min_confidence=configs.get("min_confidence", "medium"),
            prompt_format=configs.get("prompt_format", "xml_json"),
            enable_thinking=configs.get("enable_thinking", False),
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


# --- 路径配置 ---

@dataclass
class PathConfig:
    """各语言目录的基础路径。"""
    target_path: Path = Path()
    llc_base_path: Path = Path()
    KR_base_path: Path = Path()
    JP_base_path: Path = Path()
    EN_base_path: Path = Path()

    def create_need_dirs(self):
        """确保目标输出目录存在。"""
        self.target_path.mkdir(parents=True, exist_ok=True)


@dataclass
class FilePathConfig:
    """单个文件在所有语言下的路径集合。"""
    KR_path: Path
    _PathConfig: PathConfig
    has_prefix: bool = True

    @property
    def rel_path(self) -> Path:
        return self.KR_path.relative_to(self._PathConfig.KR_base_path)

    @property
    def rel_dir(self) -> Path:
        return self.rel_path.parent

    @property
    def real_name(self) -> str:
        name = self.KR_path.name
        if self.has_prefix:
            for pre in ("KR_", "EN_", "JP_", "LLC_"):
                if name.startswith(pre):
                    return name[len(pre):]
        return name

    @property
    def target_file(self) -> Path:
        return self._PathConfig.target_path / self.rel_path.parent / self.real_name

    @property
    def EN_path(self) -> Path:
        if self.has_prefix:
            return self._PathConfig.EN_base_path / self.rel_path.parent / f"EN_{self.real_name}"
        return self._PathConfig.EN_base_path / self.rel_path

    @property
    def JP_path(self) -> Path:
        if self.has_prefix:
            return self._PathConfig.JP_base_path / self.rel_path.parent / f"JP_{self.real_name}"
        return self._PathConfig.JP_base_path / self.rel_path

    @property
    def LLC_path(self) -> Path:
        return self._PathConfig.llc_base_path / self.rel_dir / self.real_name


from contextlib import contextmanager
import logging as _logging


@contextmanager
def _suppress_translatekit_log(debug_mode: bool):
    """在 translator 构造期间临时抑制 translatekit 的 debug 日志。

    使用 try/finally 确保即使构造失败也恢复日志级别。
    修复 B3：translator 构造异常时 logger 级别永久泄漏。

    定义在 config.py 而非 pipeline.py，避免 pipeline ↔ processor 循环导入。
    """
    if not debug_mode:
        _logging.getLogger("translatekit").setLevel(_logging.INFO)
    try:
        yield
    finally:
        if not debug_mode:
            _logging.getLogger("translatekit").setLevel(_logging.DEBUG)
