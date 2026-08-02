import os
from typing import TypedDict
from collections.abc import Mapping

from .context import FileExecutionContext
from .handlers import REGISTRY
from ..packages.manage import get_mod_path
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
_log_manager = LogManager()


class EvalFilesResult(TypedDict):
    """evalFiles 的处理结果汇总。"""

    success: bool
    message: str
    installed: int
    modded: int
    updated: int
    imported: int
    skipped: int
    errors: int
    error_details: list[dict[str, str]]


def _build_execution_summary(results: Mapping[str, int]) -> str:
    parts = []
    if results["installed"] > 0:
        parts.append(f"{results['installed']}个汉化包")
    if results["modded"] > 0:
        parts.append(f"{results['modded']}个模组")
    if results["updated"] > 0:
        parts.append(f"{results['updated']}个更新")
    if results["imported"] > 0:
        parts.append(f"{results['imported']}个规则集")
    if results["skipped"] > 0:
        parts.append(f"跳过{results['skipped']}个")
    if results["errors"] > 0:
        parts.append(f"失败{results['errors']}个")
    return "安装完成: " + ", ".join(parts) if parts else "没有需要安装的文件"


def evalFiles(files_data: Mapping[str, str], modal_id: str = "false") -> EvalFilesResult:
    """处理拖入的文件，根据检测到的类型执行相应的安装操作。"""
    if not files_data:
        _log_manager.log_modal_process("没有需要处理的文件", modal_id)
        no_files_result: EvalFilesResult = {
            "success": True,
            "message": "没有需要处理的文件",
            "installed": 0,
            "modded": 0,
            "updated": 0,
            "imported": 0,
            "skipped": 0,
            "errors": 0,
            "error_details": [],
        }
        return no_files_result

    game_path = ConfigManager().get('game_path', '')
    mod_path = get_mod_path()
    os.makedirs(mod_path, exist_ok=True)

    total = len(files_data)
    results: dict[str, int] = {
        "installed": 0,
        "modded": 0,
        "updated": 0,
        "imported": 0,
        "skipped": 0,
        "errors": 0,
    }
    error_details: list[dict[str, str]] = []

    for index, (file_path, file_type) in enumerate(files_data.items()):
        _log_manager.check_running(modal_id)
        context = FileExecutionContext(
            file_path=os.fspath(file_path),
            file_type=file_type,
            modal_id=modal_id,
            index=index,
            total=total,
            game_path=game_path,
            mod_path=os.fspath(mod_path),
        )

        if not os.path.exists(context.file_path):
            _log_manager.log_modal_process(
                f"文件不存在，跳过: {context.file_name}", modal_id)
            results["skipped"] += 1
            continue

        try:
            handler = REGISTRY.handler_for(context.file_type)
            if handler is None:
                _log_manager.log_modal_process(
                    f"未知文件类型 '{context.file_type}'，跳过: {context.file_name}",
                    modal_id,
                )
                results["skipped"] += 1
                continue
            result_key = handler.execute(context)
            if result_key in results:
                results[result_key] += 1
        except Exception as error:
            error_msg = f"处理文件 '{context.file_name}' 时出错: {error}"
            _log_manager.log_modal_process(error_msg, modal_id)
            _log_manager.log_error(error)
            results["errors"] += 1
            error_details.append({
                "file": context.file_name,
                "error": str(error),
            })

    summary = _build_execution_summary(results)
    _log_manager.log_modal_process(summary, modal_id)
    _log_manager.log_modal_status("处理完成", modal_id)
    _log_manager.update_modal_progress(100, summary, modal_id)

    return {
        "success": results["errors"] == 0,
        "message": summary,
        "installed": results["installed"],
        "modded": results["modded"],
        "updated": results["updated"],
        "imported": results["imported"],
        "skipped": results["skipped"],
        "errors": results["errors"],
        "error_details": error_details,
    }
