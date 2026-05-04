"""
下载管理 Handler
统一下载调度：零协汉化、OurPlay汉化、LCTA自动更新、气泡Mod
"""

from . import BaseHandler


class DownloadHandler(BaseHandler):
    """下载处理器"""

    def download_llc(self, modal_id: str) -> dict:
        """下载零协汉化包"""
        from webutils.function_llc import function_llc_main
        from webutils.functions import get_cache_font

        dump_default = self.config.get('ui_default.zero.dump_default', False)
        zip_type = self.config.get('ui_default.zero.zip_type', "zip")
        use_proxy = self.config.get('ui_default.zero.use_proxy', True)
        use_cache = self.config.get('ui_default.zero.use_cache', False)
        download_source = self.config.get('ui_default.zero.download_source', "github")
        cache_path = get_cache_font(self.config.raw, self.log)

        function_llc_main(
            modal_id, self.log,
            dump_default=dump_default,
            download_source=download_source,
            from_proxy=use_proxy,
            zip_type=zip_type,
            use_cache=use_cache,
            cache_path=cache_path
        )

        self.log.log_modal_status("操作完成", modal_id)
        return {"success": True, "message": "零协汉化包下载成功"}

    def download_ourplay(self, modal_id: str) -> dict:
        """下载OurPlay汉化包"""
        from webutils.function_ourplay import function_ourplay_main, function_ourplay_api

        font_option = self.config.get('ui_default.ourplay.font_option', "keep")
        check_hash = self.config.get('ui_default.ourplay.check_hash', True)
        use_api = self.config.get('ui_default.ourplay.use_api', False)

        if use_api:
            function_ourplay_api(modal_id, self.log, font_option=font_option, check_hash=check_hash)
        else:
            function_ourplay_main(modal_id, self.log, font_option=font_option, check_hash=check_hash)

        return {"success": True, "message": "OurPlay汉化包下载成功"}

    def download_lcta_auto(self, modal_id: str) -> dict:
        """下载LCTA自动更新包"""
        from webutils.function_LCTA_auto import function_LCTA_auto_main

        function_LCTA_auto_main(modal_id, self.log, self.config.raw)
        return {"success": True, "message": "下载完成"}

    def download_bubble(self, modal_id: str) -> dict:
        """下载气泡文本Mod"""
        from webutils.function_bubble import function_bubble_main

        function_bubble_main(modal_id, self.log, self.config.raw)
        return {"success": True, "message": "下载完成"}
