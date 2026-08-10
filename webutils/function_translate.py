"""
webutils/function_translate.py
translateFunc.TranslationPipeline 的 WebUI 薄封装。
负责：配置加载、临时目录设置、UI 回调绑定、产物打包。
"""
import os
import sys
import tempfile
from contextlib import contextmanager, suppress
from pathlib import Path
from datetime import datetime
from typing import Callable, Iterator

from translateFunc import TranslationPipeline, TranslateConfig
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
from webutils.utils.font import get_cache_font
from webutils.utils.io import zip_folder

_log_manager = LogManager()


@contextmanager
def _translation_tmpdir() -> Iterator[str]:
    """翻译用临时目录：清理失败不顶替业务异常。

    取消后 worker 线程可能仍在写临时目录，立刻 rmtree 会抛
    PermissionError 顶替 CancelRunning（见 workers.py 取消语义）。
    Python 3.10+ 可用 TemporaryDirectory(ignore_cleanup_errors=True)，
    3.9（打包产物内嵌 3.9.6）无此参数，统一用 suppress 兜底。
    注意：3.9 下清理失败会残留临时目录于 %TEMP%（OS 自清理，可接受）。
    """
    if sys.version_info >= (3, 10):
        ctx = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    else:
        ctx = tempfile.TemporaryDirectory()
    tmpdir = ctx.__enter__()
    try:
        yield tmpdir
    finally:
        with suppress(Exception):
            ctx.cleanup()


def translate_main(
    modal_id,
    translator_config: dict,
    formating_function: Callable[[dict, dict], dict],
) -> bool:
    """WebUI 翻译主入口。

    Args:
        modal_id: UI 模态框标识符，用于进度上报。
        translator_config: 以翻译器名称为键的 API 设置字典。
        formating_function: (api_settings, translator_cls) -> 格式化后的 api_settings。

    Returns:
        汉化包打包是否成功。
    """
    with _translation_tmpdir() as tmpdir:
        _log_manager.log_modal_process("开始初始化", modal_id)
        _log_manager.log_modal_status("正在初始化", modal_id)

        tmp = Path(tmpdir)
        cfg_mgr = ConfigManager()

        # 1. 从 ConfigManager 构建 TranslateConfig
        config = TranslateConfig.from_config_manager(cfg_mgr)

        # 2. 设定 dump 输出路径（在 tempdir 外，持久化）
        if config.dump:
            dump_dir = Path(os.getcwd()) / "logs" / "translation_dump"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            config.dump_path = dump_dir / f"{ts}.jsonl"
            _log_manager.log(
                f"翻译诊断 dump 已启用，将记录完整提示词、AI 响应和异常详情: "
                f"{config.dump_path}"
            )

        # 3. 解析翻译器 API 设置
        translator_text = config.translator_name
        api_settings = translator_config.get(translator_text, {})

        # 应用 UI 格式化函数（保留旧流程）
        from translateFunc.translate_request import TRANSLATOR_TRANS
        translator_cls = TRANSLATOR_TRANS[translator_text]
        api_settings = formating_function(api_settings, translator_cls)
        config.translator_api = api_settings

        # 4. 设置输出目录
        config.output_dir = tmp

        # 5. 创建管线
        pipeline = TranslationPipeline(config)

        # 6. 绑定 UI 回调
        pipeline.set_callbacks(
            on_log=lambda msg: _log_manager.log(msg),
            on_status=lambda msg: _log_manager.log_modal_status(msg, modal_id),
            on_progress=lambda pct, msg: (
                _log_manager.update_modal_progress(pct, msg, modal_id),
                _log_manager.log_modal_process(msg, modal_id),
            ),
            on_check_running=lambda: _log_manager.check_running(modal_id),
        )

        # 7. 运行翻译
        summary = pipeline.run()

        # 8a. 持久化处理日志
        VERSION = _generate_version()
        try:
            import shutil as _shutil
            log_src = config.output_dir / "LLc-CN-LCTA" / "processing_log.jsonl"
            work_dir = Path(os.getcwd())
            log_dst = work_dir / "logs" / f"processing_log_{VERSION}.jsonl"
            log_dst.parent.mkdir(parents=True, exist_ok=True)
            if log_src.exists():
                _shutil.copy2(log_src, log_dst)
                _log_manager.log_modal_process(f"处理日志已保存: {log_dst.name}", modal_id)
        except Exception as exc:
            _log_manager.log_error(exc)

        # 8b. 上报结果
        _log_manager.log_modal_process(
            f"翻译完成: {summary.success_count} 成功, "
            f"{len(summary.skipped)} 跳过, {summary.fallback_count} 降级, "
            f"{summary.error_count} 错误",
            modal_id,
        )
        _log_manager.log_modal_status("正在打包汉化包", modal_id)

        # 9. 打包产物
        target_dir = config.output_dir / "LLc-CN-LCTA"
        _copy_assets(target_dir, config.game_path, VERSION)

        work_dir = Path(os.getcwd())
        r = zip_folder(target_dir, work_dir / f"LCTA_{VERSION}.zip", modal_id=modal_id)
        if r:
            _log_manager.log_modal_process("压缩完成", modal_id)
            _log_manager.log_modal_status("翻译完成", modal_id)
            _log_manager.update_modal_progress(100, "全部操作完成", modal_id)
            return True
        else:
            _log_manager.log_modal_process("压缩失败", modal_id)
            _log_manager.log_modal_status("操作失败", modal_id)
            _log_manager.update_modal_progress(0, "操作失败", modal_id)
            # 临时目录在 with 块退出后即被删除，失败时将产物复制到持久目录，
            # 避免"翻译结果直接消失"（旧实现靠 sleep(60) 留时间手动保存）
            preserved_dir = Path(os.getcwd()) / "logs" / "translation_output" / f"LCTA_{VERSION}"
            try:
                if target_dir.exists():
                    import shutil as _shutil
                    _shutil.copytree(target_dir, preserved_dir, dirs_exist_ok=True)
                    _log_manager.log_modal_process(
                        f"打包失败，产物已保留至: {preserved_dir}", modal_id)
            except Exception as exc:
                _log_manager.log_error(exc)
            if not (preserved_dir / "Info" / "version.json").exists():
                _log_manager.log_modal_process(
                    "打包失败且产物保留失败，请重新翻译", modal_id)
            return False


def _generate_version() -> str:
    """生成版本号 YYYYMMDDNN，支持同日多次构建递增序号。"""
    today = datetime.now()
    current_date = today.strftime("%Y%m%d")
    work_dir = Path(os.getcwd())
    previous_version = 1999010101
    for z in work_dir.glob(f"LCTA_{current_date}??.zip"):
        with suppress(Exception):
            name = z.stem  # 如 "LCTA_2026062701"
            version_str = name.replace("LCTA_", "")
            full_version = int(version_str)
            if full_version > previous_version:
                previous_version = full_version

    try:
        prev_date = str(previous_version)[:8]
        prev_sequence = int(str(previous_version)[8:])
        if prev_date == current_date:
            new_sequence = prev_sequence + 1
            if new_sequence > 99:
                raise ValueError("当日版本序号已超过99")
            return f"{current_date}{new_sequence:02d}"
        else:
            return f"{current_date}01"
    except Exception:
        return f"{current_date}01"


def _copy_assets(target_dir: Path, game_path: Path, version: str) -> None:
    """复制许可证、版本信息和字体到输出目录。"""
    import shutil, json
    from datetime import datetime

    try:
        info_dir = target_dir / "Info"
        info_dir.mkdir(parents=True, exist_ok=True)
        license_src = game_path / "LimbusCompany_Data" / "lang" / "LLC_zh-CN" / "Info" / "LICENSE"
        if license_src.exists():
            shutil.copy(license_src, info_dir / "LICENSE")
        # 写入版本元数据
        version_target = info_dir / "version.json"
        version_target.write_text(json.dumps(
            {"version": version, "notice": "本次文本更新没有提示。"},
            ensure_ascii=False, indent=4))
    except Exception:
        pass
    try:
        font_dir = target_dir / "Font" / "Context"
        font_dir.mkdir(parents=True, exist_ok=True)
        font_src = get_cache_font()
        if font_src:
            shutil.copy(font_src, font_dir / "ChineseFont.ttf")
    except Exception:
        pass
