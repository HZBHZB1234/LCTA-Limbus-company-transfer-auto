# -*- coding: utf-8 -*-
"""LCTA_API 更新：自动/手动检查、模态窗口内更新、本地更新包安装。"""
import os
import shutil
from pathlib import Path

from globalManagers.ConfigManager import ConfigManager
from globalManagers.pending_pip_ops import load_pending_ops
from webutils.update import Updater, get_app_version
from webui.app_api.exceptions import CancelRunning

class UpdateMixin:

    @staticmethod
    def _has_pending_ops() -> bool:
        """是否存在待执行的延迟依赖操作（下次启动时统一处理）。"""
        ops = load_pending_ops()
        return bool(ops["uninstall"] or ops["install"])

    def auto_check_update(self):
        """自动检查更新"""
        try:
            # 只有在配置允许时才检查更新
            if not ConfigManager().get("auto_check_update", True):
                return {"has_update": False}
            
            self.current_version = get_app_version()
            self.log(f"当前版本: {self.current_version}")
        
            # 创建更新器实例，使用新配置
            updater = Updater(
                "HZBHZB1234", 
                "LCTA-Limbus-company-transfer-auto",
                delete_old_files=ConfigManager().get("delete_updating", True),
                                use_proxy=ConfigManager().get("update_use_proxy", True),
                only_stable=ConfigManager().get("update_only_stable", False)
            )
        
            update_info = updater.check_for_updates(self.current_version)
            update_info["html_url"] = update_info.get("release_url", "")
            return update_info
        except Exception as e:
            self.log(f"检查更新时出错: {e}")
            self.log_error(e)
            return {"has_update": False}

    def manual_check_update(self):
        """手动检查更新"""
        try:                
            self.current_version = get_app_version()
            self.log(f"当前版本: {self.current_version}")
        
            # 创建更新器实例，使用新配置
            updater = Updater(
                "HZBHZB1234", 
                "LCTA-Limbus-company-transfer-auto",
                delete_old_files=ConfigManager().get("delete_updating", True),
                                use_proxy=ConfigManager().get("update_use_proxy", True),
                only_stable=ConfigManager().get("update_only_stable", False)
            )
        
            update_info = updater.check_for_updates(self.current_version)
            update_info["html_url"] = update_info.get("release_url", "")
            return update_info
        except Exception as e:
            self.log(f"检查更新时出错: {e}")
            self.log_error(e)
            return {"has_update": False}

    def perform_update_in_modal(self, modal_id):
        """在模态窗口中执行更新"""
        try:
            self.add_modal_log("开始执行更新...", modal_id)

            # 创建更新器实例，使用新配置
            updater = Updater(
                "HZBHZB1234",
                "LCTA-Limbus-company-transfer-auto",
                delete_old_files=ConfigManager().get("delete_updating", True),
                use_proxy=ConfigManager().get("update_use_proxy", True),
                only_stable=ConfigManager().get("update_only_stable", False),
                modal_id=modal_id
            )

            # 执行更新
            result = updater.check_and_update(getattr(self, 'current_version', ''))
            if result:
                if self._has_pending_ops():
                    msg = "更新完成，依赖变更将在下次启动时自动执行，请重启程序"
                    self.add_modal_log(msg, modal_id)
                    return {"success": True, "message": msg}
                return {"success": True, "message": "更新完成"}
            return {"success": False, "message": "更新失败"}
        except CancelRunning:
            self.log('更新任务已取消')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"更新失败：{e}", modal_id)
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def perform_update_from_file(self, file_path, modal_id=""):
        """从本地 LCTA 更新包 (zip) 执行手动更新"""
        try:
            self.add_modal_log(f"开始处理本地更新包: {file_path}", modal_id)
        
            if not os.path.exists(file_path):
                self.add_modal_log(f"文件不存在: {file_path}", modal_id)
                return {"success": False, "message": "文件不存在"}
        
            if not file_path.lower().endswith('.zip'):
                self.add_modal_log("选中的文件不是 zip 格式", modal_id)
                return {"success": False, "message": "请选择 zip 格式的更新包"}
        
            import tempfile
            import zipfile
        
            self.add_modal_log("正在验证更新包...", modal_id)
        
            tmp_dir = tempfile.mkdtemp()
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    zf.extractall(tmp_dir)
            
                source_dir = Path(tmp_dir)
                for item in os.listdir(tmp_dir):
                    item_path = os.path.join(tmp_dir, item)
                    if os.path.isdir(item_path) and \
                       os.path.exists(os.path.join(item_path, 'start_webui.py')) and \
                       os.path.exists(os.path.join(item_path, 'requirements.txt')):
                        source_dir = Path(item_path)
                        break
            
                if not (os.path.exists(os.path.join(str(source_dir), 'start_webui.py')) and \
                        os.path.exists(os.path.join(str(source_dir), 'requirements.txt'))):
                    self.add_modal_log("无效的 LCTA 更新包：缺少 start_webui.py 或 requirements.txt", modal_id)
                    return {"success": False, "message": "无效的更新包，缺少必要文件"}
            
                self.add_modal_log("更新包验证通过，开始更新...", modal_id)
            
                cfg = ConfigManager()
                updater = Updater(
                    "HZBHZB1234", "LCTA-Limbus-company-transfer-auto",
                    delete_old_files=cfg.get("delete_updating", True),
                    use_proxy=cfg.get("update_use_proxy", True),
                    only_stable=cfg.get("update_only_stable", False),
                    modal_id=modal_id
                )
            
                self.add_modal_log("正在安装依赖...", modal_id)
                updater.install_requirements(source_dir)
                self.check_modal_running(modal_id)
            
                self.add_modal_log("正在替换文件...", modal_id)
                if not updater.update_files(source_dir):
                    return {"success": False, "message": "更新文件失败"}

                if self._has_pending_ops():
                    msg = "更新完成，依赖变更将在下次启动时自动执行，请重启程序"
                    self.add_modal_log(msg, modal_id)
                    return {"success": True, "message": msg}
                return {"success": True, "message": "更新完成，请手动重启程序"}
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            
        except CancelRunning:
            self.log('手动更新任务已取消')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"更新失败: {e}", modal_id)
            self.log_error(e)
            return {"success": False, "message": str(e)}
