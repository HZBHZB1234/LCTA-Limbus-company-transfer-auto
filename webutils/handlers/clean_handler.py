"""
缓存清理 Handler
处理缓存、进度、通知的清理
"""

from pathlib import Path
from . import BaseHandler


class CleanHandler(BaseHandler):
    """缓存清理处理器"""

    def clean(self,
              modal_id: str,
              custom_files: list = None,
              clean_progress: bool = None,
              clean_notice: bool = None,
              clean_mods: bool = None) -> dict:
        """执行缓存清理"""
        from webutils.function_clean import clean_config_main

        if custom_files is None:
            custom_files = []

        # 如果参数未指定，从配置读取
        if clean_progress is None:
            clean_progress = self.config.get('ui_default.clean.clean_progress', False)
        if clean_notice is None:
            clean_notice = self.config.get('ui_default.clean.clean_notice', False)
        if clean_mods is None:
            clean_mods = self.config.get('ui_default.clean.clean_mods', False)

        if clean_mods:
            roaming_path = Path.home() / "AppData" / "Roaming"
            mods_path = roaming_path / "LimbusCompanyMods"
            custom_files.append(mods_path)

        clean_config_main(
            modal_id=modal_id,
            logger_=self.log,
            clean_progress=clean_progress,
            clean_notice=clean_notice,
            custom_files=custom_files
        )

        return {"success": True, "message": "缓存清除成功"}
