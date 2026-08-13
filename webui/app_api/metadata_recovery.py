# -*- coding: utf-8 -*-
"""LCTA_API Metadata 恢复：capstone 环境检查/安装 + v2 全自动恢复流水线。"""
import json

from globalManagers.ConfigManager import ConfigManager
from webutils import metadata_recovery
from webutils.metadata_recovery import (
    capstone_available,
    derive_game_files,
    install_capstone,
    output_dir,
    run_recovery,
)
from webui.app_api.exceptions import CancelRunning


class MetadataRecoveryMixin:

    def metadata_recovery_status(self):
        """返回页面初始状态：输出目录、capstone 可用性、游戏文件自动推导。"""
        try:
            return {"success": True, "data": {
                "out_dir": str(output_dir()),
                "capstone_available": capstone_available(),
                "derived": derive_game_files(ConfigManager().get("game_path", "")),
            }}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def metadata_recovery_install_capstone(self, modal_id=""):
        """用当前解释器 pip 安装 capstone（模态窗口实时日志）。"""
        try:
            self.add_modal_log("开始安装 capstone...", modal_id)

            def on_log(msg):
                self.add_modal_log(msg, modal_id)

            result = install_capstone(on_log=on_log)
            self.add_modal_log(result["message"], modal_id)
            if result.get("success"):
                self.log_ui("capstone 安装成功，Metadata 恢复功能可用")
            return result
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def metadata_recovery_run(self, config, modal_id=""):
        """执行 v2 完整恢复流水线（pywebview 后台线程 + 模态窗口进度）。"""
        try:
            self.add_modal_log("Metadata 恢复流水线开始", modal_id)

            def on_log(msg):
                self.add_modal_log(msg, modal_id)

            def cancel_check():
                self.check_modal_running(modal_id, log=False)

            result = run_recovery(
                metadata_path=config.get("metadata_path", ""),
                game_dll=config.get("game_dll", "") or "",
                expect_sha256=config.get("expect_sha256", "") or "",
                version=int(config.get("version") or 39),
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
