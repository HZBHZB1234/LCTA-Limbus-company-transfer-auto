# -*- coding: utf-8 -*-
"""LCTA_API Metadata 恢复：IDA 定位器插件安装 + 离线恢复流水线运行。"""
import json

from globalManagers.ConfigManager import ConfigManager
from webutils import metadata_recovery
from webutils.metadata_recovery import (
    derive_game_files,
    find_ida_plugins_dir,
    install_ida_plugin,
    load_locator_export,
    output_dir,
    plugin_installed,
    run_recovery,
)
from webui.app_api.exceptions import CancelRunning


class MetadataRecoveryMixin:

    def metadata_recovery_status(self):
        """返回页面初始状态：输出目录、IDA 插件探测/安装情况、游戏文件自动推导。"""
        try:
            plugins_dir = find_ida_plugins_dir()
            return {"success": True, "data": {
                "out_dir": str(output_dir()),
                "ida_plugins_dir": plugins_dir or "",
                "plugin_installed": plugin_installed(plugins_dir or ""),
                "derived": derive_game_files(ConfigManager().get("game_path", "")),
            }}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def metadata_recovery_install_ida_plugin(self, plugins_dir=""):
        """自动探测并安装 IDA 定位器插件（可传手动选择的 plugins 目录）。"""
        try:
            result = install_ida_plugin(plugins_dir)
            self.log_ui(f"IDA 定位器插件已安装：{result['plugin_path']}")
            return {"success": True, "data": result}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def metadata_recovery_load_export(self, export_path, rank=1):
        """载入 IDA 定位器导出（locate_candidates.json 或导出目录），按 rank 取参。"""
        try:
            result = load_locator_export(export_path, int(rank or 1))
            if result.get("success"):
                self.log_ui(
                    f"定位器导出已载入：rank {result.get('rank')} "
                    f"{result.get('candidate_name')} score={result.get('score')} "
                    f"verdict={result.get('verdict')} "
                    f"table_hex={'就绪' if result.get('table_hex') else '缺失'} "
                    f"反编译文本={'就绪' if result.get('decompile_text') else '缺失'}")
            return result
        except Exception as e:
            self.log_error(e)
            return {"success": False, "errors": [str(e)]}

    def metadata_recovery_run(self, config, modal_id=""):
        """执行完整离线恢复流水线（pywebview 后台线程 + 模态窗口进度）。"""
        try:
            self.add_modal_log("Metadata 恢复流水线开始", modal_id)

            def on_log(msg):
                self.add_modal_log(msg, modal_id)

            def cancel_check():
                self.check_modal_running(modal_id, log=False)

            result = run_recovery(
                metadata_path=config.get("metadata_path", ""),
                reference_path=config.get("reference_path", ""),
                decompile_text=config.get("decompile_text", "") or "",
                decompile_file=config.get("decompile_file", "") or "",
                candidate_profile=config.get("candidate_profile", "") or "",
                game_dll=config.get("game_dll", "") or "",
                table_hex=config.get("table_hex", "") or "",
                expect_sha256=config.get("expect_sha256", "") or "",
                profile_id=config.get("profile_id", "") or "",
                on_log=on_log,
                cancel_check=cancel_check,
            )
            self.add_modal_log(
                f"流水线完成：success={result['success']} "
                f"verdicts={json.dumps(result['verdicts'], ensure_ascii=False)}",
                modal_id)
            return result
        except CancelRunning:
            self.add_modal_log("Metadata 恢复已取消", modal_id)
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消",
                    "run_dir": str(output_dir())}
        except Exception as e:
            self.add_modal_log(f"Metadata 恢复失败：{e}", modal_id)
            self.log_error(e)
            return {"success": False, "message": str(e),
                    "run_dir": str(output_dir())}
