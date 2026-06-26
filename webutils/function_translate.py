"""
webutils/function_translate.py
translateFunc.TranslationPipeline 的 WebUI 薄封装。
负责：配置加载、临时目录设置、UI 回调绑定、产物打包。
"""
import os
import time
import tempfile
from pathlib import Path
from datetime import datetime
from contextlib import suppress
from typing import Callable

from translateFunc import TranslationPipeline, TranslateConfig
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
from webutils.functions import get_cache_font, zip_folder

_log_manager = LogManager()


def translate_main(
    modal_id,
    translator_config: dict,
    formating_function: Callable[[dict, dict], dict],
):
    """WebUI 翻译主入口。

    Args:
        modal_id: UI 模态框标识符，用于进度上报。
        translator_config: 以翻译器名称为键的 API 设置字典。
        formating_function: (api_settings, translator_cls) -> 格式化后的 api_settings。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _log_manager.log_modal_process("开始初始化", modal_id)
        _log_manager.log_modal_status("正在初始化", modal_id)

        tmp = Path(tmpdir)
        cfg_mgr = ConfigManager()

        # 1. 从 ConfigManager 构建 TranslateConfig
        config = TranslateConfig.from_config_manager(cfg_mgr)

        # 2. 解析翻译器 API 设置
        translator_text = config.translator_name
        api_settings = translator_config.get(translator_text, {})

        # 应用 UI 格式化函数（保留旧流程）
        from translateFunc.translate_request import TRANSLATOR_TRANS
        translator_cls = TRANSLATOR_TRANS[translator_text]
        api_settings = formating_function(api_settings, translator_cls)
        config.translator_api = api_settings

        # 3. 设置输出目录
        config.output_dir = tmp

        # 4. 创建管线
        pipeline = TranslationPipeline(config)

        # 5. 绑定 UI 回调
        pipeline.set_callbacks(
            on_log=lambda msg: _log_manager.log(msg),
            on_status=lambda msg: _log_manager.log_modal_status(msg, modal_id),
            on_progress=lambda pct, msg: (
                _log_manager.update_modal_progress(pct, msg, modal_id),
                _log_manager.log_modal_process(msg, modal_id),
            ),
            on_check_running=lambda: _log_manager.check_running(modal_id),
        )

        # 6. 运行翻译
        summary = pipeline.run()

        # 7. 上报结果
        _log_manager.log_modal_process(
            f"翻译完成: {summary.success_count} 成功, "
            f"{len(summary.skipped)} 跳过, {summary.error_count} 错误",
            modal_id,
        )
        _log_manager.log_modal_status("正在打包汉化包", modal_id)

        # 8. 打包产物
        target_dir = config.output_dir / "LLc-CN-LCTA"
        VERSION = _generate_version()
        _copy_assets(target_dir, config.game_path, VERSION)

        work_dir = Path(os.getcwd())
        r = zip_folder(target_dir, work_dir / f"LCTA_{VERSION}.zip")
        if r:
            _log_manager.log_modal_process("压缩完成", modal_id)
            _log_manager.log_modal_status("翻译完成", modal_id)
            _log_manager.update_modal_progress(100, "全部操作完成", modal_id)
        else:
            _log_manager.log_modal_process("压缩失败", modal_id)
            _log_manager.log_modal_status("操作失败", modal_id)
            _log_manager.update_modal_progress(100, "操作失败", modal_id)
            os.system(f'explorer "{tmp}"')
            _log_manager.log_modal_process(
                "目前已打开产物文件夹，如果有需要，请在60秒内保存数据", modal_id
            )
            time.sleep(60)


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
