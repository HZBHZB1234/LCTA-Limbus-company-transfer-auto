# -*- coding: utf-8 -*-
"""LCTA_API 各类汉化包下载：OurPlay / 零协 / LCTA 自动 / 调爪。"""
from globalManagers.ConfigManager import ConfigManager
from webutils import (
    function_ourplay_main,
    function_ourplay_api,
    function_ourplay_new_main,
    function_llc_main,
    function_LCTA_auto_main,
    function_lanzou_tiaozhua_main,
)
from webutils.utils import get_cache_font
from webui.app_api.exceptions import CancelRunning

class DownloadMixin:

    def download_ourplay_translation(self, modal_id= "false"):
        """下载ourplay翻译"""
        try:
            self.add_modal_log("开始下载OurPlay汉化包...", modal_id)
        
            # 从配置中读取字体处理选项
            font_option = ConfigManager().get("ui_default.ourplay.font_option", "keep")
            check_hash = ConfigManager().get("ui_default.ourplay.check_hash", True)
            use_api = ConfigManager().get("ui_default.ourplay.use_api", False)
            source = ConfigManager().get("ui_default.ourplay.source", "pc")

            if source == "android":
                official = ConfigManager().get("ui_default.ourplay.official", True)
                refer_package = ConfigManager().get("ui_default.ourplay.refer_package", "")
                function_ourplay_new_main(
                    modal_id,
                    font_option=font_option,
                    check_hash=check_hash,
                    official=official,
                    refer_package=refer_package if refer_package else None
                )
            elif use_api:
                function_ourplay_api(modal_id, font_option=font_option, check_hash=check_hash)
            else:
                function_ourplay_main(modal_id, font_option=font_option, check_hash=check_hash)
        
            self.add_modal_log("OurPlay汉化包下载成功", modal_id)
            return {"success": True, "message": "OurPlay汉化包下载成功"}
        except CancelRunning:
            self.log("ourplay下载任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"出现错误{e}，下载失败", modal_id)
            self.log_error(e)
            self.log_manager.update_modal_progress(0, "下载失败", modal_id)
            self.log_manager.log_modal_status("下载失败", modal_id)
            return {"success": False, "message": str(e)}

    def download_llc_translation(self, modal_id= "false"):
        """下载LLC翻译"""
        try:
            self.add_modal_log("开始下载零协汉化包...", modal_id)
            # 从配置中读取参数
            dump_default = ConfigManager().get("ui_default.zero.dump_default", False)
            zip_type = ConfigManager().get("ui_default.zero.zip_type", "zip")
            use_proxy = ConfigManager().get("ui_default.zero.use_proxy", True)
            use_cache = ConfigManager().get("ui_default.zero.use_cache", False)
            download_source = ConfigManager().get("ui_default.zero.download_source", "github")
            cache_path = get_cache_font()
        
            # 传递新参数给function_llc_main
            function_llc_main(
                modal_id,
                dump_default=dump_default,
                download_source=download_source,
                from_proxy=use_proxy,
                zip_type=zip_type,
                use_cache=use_cache,
                cache_path=cache_path
            )
            self.add_modal_log("零协汉化包下载成功", modal_id)
            self.log_manager.log_modal_status("操作完成", modal_id)
            return {"success": True, "message": "零协汉化包下载成功"}
        except CancelRunning:
            self.log("llc下载任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"出现错误{e}，下载失败", modal_id)
            self.log_error(e)
            self.log_manager.update_modal_progress(0, "下载失败", modal_id)
            self.log_manager.log_modal_status("下载失败", modal_id)
            return {"success": False, "message": str(e)}

    def download_LCTA_auto(self, modal_id= "false"):
        """开始翻译"""
        try:
            self.add_modal_log("开始翻译...", modal_id)
            function_LCTA_auto_main(modal_id)
            self.add_modal_log("翻译完成", modal_id)
            return {"success": True, "message": "翻译完成"}
        except CancelRunning:
            self.log('用户已取消翻译流程')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def download_lanzou_tiaozhua(self, modal_id= "false"):
        """下载并导入调爪文本修改包"""
        try:
            self.add_modal_log("开始下载...", modal_id)
            function_lanzou_tiaozhua_main(modal_id)
            self.add_modal_log("下载完成", modal_id)
            return {"success": True, "message": "下载完成"}
        except CancelRunning:
            self.log('用户已取消下载流程')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}
