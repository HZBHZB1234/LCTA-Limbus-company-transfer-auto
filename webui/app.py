# -*- coding: utf-8 -*-
import webview
from webview.dom import DOMEventHandler
import os
import sys
import logging
import atexit
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
from webutils import SpeedManager
from webutils import InputBypassManager
from webutils import DamageHookManager

from webui.app_api.exceptions import CancelRunning
from webui.app_api.core import CoreMixin
from webui.app_api.config import ConfigMixin
from webui.app_api.translation import TranslatorMixin
from webui.app_api.packages import PackagesMixin
from webui.app_api.download import DownloadMixin
from webui.app_api.fancy import FancyMixin
from webui.app_api.windows import WindowMixin
from webui.app_api.cdn import CdnMixin
from webui.app_api.speed import SpeedMixin
from webui.app_api.input_bypass import InputBypassMixin
from webui.app_api.damage_hook import DamageHookMixin
from webui.app_api.update import UpdateMixin
from webui.app_api.drops import DropMixin
from webui.app_api.resources import ResourceMixin
from webui.rule_editor_api import RuleEditorAPI
from webui.quick_editor_api import QuickEditorAPI
from webui.llm_fancy_api import LLMFancyAPI
from webui.translation_log_api import TranslationLogViewerAPI


class LCTA_API(CoreMixin, TranslatorMixin, PackagesMixin, DownloadMixin, FancyMixin,
               WindowMixin, CdnMixin, SpeedMixin, UpdateMixin, DropMixin,
               ResourceMixin, ConfigMixin, InputBypassMixin, DamageHookMixin):
    """主窗�?-API 桥接类。方法按功能域拆分至 webui/app_api/ �?mixin�?"""
    pass


def main():
    # 获取HTML文件的绝对路径
    html_path = os.path.join(os.getenv('path_'), "webui\\index.html")

    # 创建API实例
    api = LCTA_API()
    # 创建窗口 - 先创建窗口，不立即绑定API
    window = webview.create_window(
        "LCTA - 边狱公司汉化工具箱",
        url=html_path,
        width=1200,
        height=800,
        resizable=True,
        fullscreen=False,
        text_select=True,
        js_api=api
    )

    api.set_window(window)
    window.events.closed += api.save_setting_from
    atexit.register(api.save_config_to_file)
    atexit.register(lambda: SpeedManager.close())
    atexit.register(lambda: InputBypassManager.close())
    # 设置模态窗口相关的回调
    LogManager().set_modal_callbacks(
        status_callback=api.set_modal_status,
        log_callback=api.add_modal_log,
        progress_callback=api.update_modal_progress,
        check_running=api.check_modal_running
    )

    debug_mode = ConfigManager().get("debug", False)
    enable_storage = ConfigManager().get('enable_storage', False)

    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    webview.settings['ALLOW_DOWNLOADS'] = True
    
    if not debug_mode:
        logger_c = logging.getLogger('urllib3.connectionpool')
        logger_c.setLevel(logging.INFO)

    def start_func():
        print('加载函数')
        window.dom.document.events.drop += DOMEventHandler(api.on_drop, True, True)

    if enable_storage:
        stPath = ConfigManager().get('storage_path', 'tmp')
        webview.start(
            func=start_func,
            debug=debug_mode,
            http_server=True,
            storage_path=str(Path(stPath)),
            private_mode=False
        )
    else:
        webview.start(
            func=start_func,
            debug=debug_mode,
            http_server=True
        )

if __name__ == "__main__":
    main()
