"""下载插件 —— 下载 LLC/OurPlay/LCTA-AU 汉化包。"""

from webui.app import api_expose, CancelRunning
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils import (
    function_llc_main,
    function_ourplay_main,
    function_ourplay_api,
    function_LCTA_auto_main,
    function_bubble_main,
)
from webutils.functions import get_cache_font


@api_expose
def download_llc_translation(framework, modal_id: str = "false") -> dict:
    """下载零协汉化包。"""
    try:
        logManager.ModalLog("开始下载零协汉化包...", modal_id)
        dump_default = configManager.get("ui_default.zero.dump_default", False)
        zip_type = configManager.get("ui_default.zero.zip_type", "zip")
        use_proxy = configManager.get("ui_default.zero.use_proxy", True)
        use_cache = configManager.get("ui_default.zero.use_cache", False)
        download_source = configManager.get("ui_default.zero.download_source", "github")
        cache_path = get_cache_font(configManager.config, logManager)

        function_llc_main(
            modal_id, logManager,
            dump_default=dump_default,
            download_source=download_source,
            from_proxy=use_proxy,
            zip_type=zip_type,
            use_cache=use_cache,
            cache_path=cache_path
        )
        logManager.ModalStatus("操作完成", modal_id)
        return {"success": True, "message": "零协汉化包下载成功"}
    except CancelRunning:
        return {"success": False, "message": "已取消"}
    except Exception as e:
        logManager.exception(e)
        logManager.modalProgress(0, "下载失败", modal_id)
        logManager.ModalStatus("下载失败", modal_id)
        return {"success": False, "message": str(e)}


@api_expose
def download_ourplay_translation(framework, modal_id: str = "false") -> dict:
    """下载 OurPlay 汉化包。"""
    try:
        logManager.ModalLog("开始下载OurPlay汉化包...", modal_id)
        font_option = configManager.get("ui_default.ourplay.font_option", "keep")
        check_hash = configManager.get("ui_default.ourplay.check_hash", True)
        use_api = configManager.get("ui_default.ourplay.use_api", False)

        if use_api:
            function_ourplay_api(modal_id, logManager, font_option=font_option, check_hash=check_hash)
        else:
            function_ourplay_main(modal_id, logManager, font_option=font_option, check_hash=check_hash)

        return {"success": True, "message": "OurPlay汉化包下载成功"}
    except CancelRunning:
        return {"success": False, "message": "已取消"}
    except Exception as e:
        logManager.exception(e)
        logManager.modalProgress(0, "下载失败", modal_id)
        logManager.ModalStatus("下载失败", modal_id)
        return {"success": False, "message": str(e)}


@api_expose
def download_LCTA_auto(framework, modal_id: str = "false") -> dict:
    """LCTA-AU 翻译。"""
    try:
        logManager.ModalLog("开始翻译...", modal_id)
        function_LCTA_auto_main(modal_id, logManager, configManager.config)
        return {"success": True, "message": "翻译完成"}
    except CancelRunning:
        return {"success": False, "message": "已取消"}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def download_bubble(framework, modal_id: str = "false") -> dict:
    """下载气泡模组。"""
    try:
        logManager.ModalLog("开始下载...", modal_id)
        function_bubble_main(modal_id, logManager, configManager.config)
        return {"success": True, "message": "下载完成"}
    except CancelRunning:
        return {"success": False, "message": "已取消"}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}
