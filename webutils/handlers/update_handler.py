"""
更新检查 Handler
处理应用更新检查与执行
"""

import os
from . import BaseHandler


class UpdateHandler(BaseHandler):
    """更新处理器"""

    def _create_updater(self):
        """创建 Updater 实例"""
        from webutils.update import Updater
        return Updater(
            "HZBHZB1234",
            "LCTA-Limbus-company-transfer-auto",
            delete_old_files=self.config.get("delete_updating", True),
            logger_=self.log,
            use_proxy=self.config.get("update_use_proxy", True),
            only_stable=self.config.get("update_only_stable", False)
        )

    def auto_check(self) -> dict:
        """自动检查更新"""
        if not self.config.get("auto_check_update", True):
            return {"has_update": False}

        from webutils.update import get_app_version
        version = get_app_version()
        self.log.log(f"当前版本: {version}")

        updater = self._create_updater()
        update_info = updater.check_for_updates(version)
        return update_info

    def manual_check(self) -> dict:
        """手动检查更新"""
        from webutils.update import get_app_version
        version = get_app_version()
        self.log.log(f"当前版本: {version}")

        updater = self._create_updater()
        update_info = updater.check_for_updates(version)
        return update_info

    def perform_update(self, modal_id: str) -> bool:
        """在模态窗口中执行更新"""
        from webutils.update import get_app_version

        if os.getenv('update') == 'False':
            return False

        version = get_app_version()
        updater = self._create_updater()
        result = updater.check_and_update(version)
        return result
