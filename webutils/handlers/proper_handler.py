"""
专有名词抓取 Handler
处理Paratranz平台上的专有词汇抓取
"""

from . import BaseHandler


class ProperHandler(BaseHandler):
    """专有名词处理器"""

    def fetch(self, modal_id: str) -> dict:
        """抓取专有词汇"""
        from webutils.function_fetch import function_fetch_main

        proper_config = self.config.get('ui_default.proper', {})
        function_fetch_main(
            modal_id, self.log,
            **proper_config
        )
        return {"success": True, "message": "专有词汇抓取成功"}
