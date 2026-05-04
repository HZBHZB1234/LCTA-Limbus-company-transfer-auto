"""
LCTA WebUI 主入口（桥接层）
- 创建 pywebview 窗口
- 注册 js_api
- 管理窗口生命周期
- 委托所有业务逻辑到 webutils/handlers 模块
"""

import webview
from webview.dom import DOMEventHandler
import os
import sys
import json
import logging
import atexit
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
import threading
import time
import zipfile

from webui.bridge import APIBridge
from webui.decorators import api_expose, modal_handler, CancelRunning
from globalManagers import get_config, get_path, get_log

# 导入常量（保留在 LCTA_API 实例中供前端访问）
from webutils.const_apiConfig import LLM_TRANSLATOR, TKIT_MACHINE
from webutils.eiderConst import updateList, bindRefer, relyList


class LCTA_API(APIBridge):
    """
    LCTA API 桥接类
    通过 @api_expose 装饰器自动注册 pywebview js_api 方法
    所有业务逻辑委托给 Handler 模块
    """

    def __init__(self):
        super().__init__()

        # 初始化配置
        self.log("当前运行环境: 打包环境" if self.path.is_frozen else "当前运行环境: 开发环境")
        self.log(f"当前运行目录：{self.path.project_root}")

        # 前端常量（直接暴露给 js_api）
        self.TKIT_MACHINE = TKIT_MACHINE
        self.LLM_TRANSLATOR = LLM_TRANSLATOR
        self.updateList = updateList
        self.bindRefer = bindRefer
        self.relyList = relyList

        # 初始化全局配置
        self._init_config()

        # 初始化 Handler（延迟加载）
        self._handlers = {}
        self._init_handlers()

        # 设置日志管理器回调
        self._setup_log_callbacks()

    # ========== 初始化 ==========

    def _init_config(self):
        """初始化全局配置"""
        self.log("正在初始化配置...")

        if self.config.raw is None or not self.config.raw:
            self.log("未找到配置文件，生成默认配置")
            self.config.use_default_config()
            self.config._first_use = True

        config_ok, config_errors = self.config.validate()
        if not config_ok:
            self.log("配置文件格式错误，自动修复")
            self.log("\n".join(config_errors))
            self.config.fix()

    def _init_handlers(self):
        """初始化所有业务 Handler"""
        from webutils.handlers.config_handler import ConfigHandler
        from webutils.handlers.translate_handler import TranslateHandler
        from webutils.handlers.download_handler import DownloadHandler
        from webutils.handlers.install_handler import InstallHandler
        from webutils.handlers.manage_handler import ManageHandler
        from webutils.handlers.fancy_handler import FancyHandler
        from webutils.handlers.update_handler import UpdateHandler
        from webutils.handlers.dragdrop_handler import DragDropHandler
        from webutils.handlers.clean_handler import CleanHandler
        from webutils.handlers.font_handler import FontHandler
        from webutils.handlers.proper_handler import ProperHandler

        self._handlers = {
            'config': ConfigHandler(),
            'translate': TranslateHandler(),
            'download': DownloadHandler(),
            'install': InstallHandler(),
            'manage': ManageHandler(),
            'fancy': FancyHandler(),
            'update': UpdateHandler(),
            'dragdrop': DragDropHandler(),
            'clean': CleanHandler(),
            'font': FontHandler(),
            'proper': ProperHandler(),
        }

    def _setup_log_callbacks(self):
        """设置日志管理器回调"""
        self.log_mgr.set_log_callback(lambda msg: logging.getLogger().info(msg))
        self.log_mgr.set_error_callback(lambda e: logging.getLogger().exception(e))

        # UI 回调稍后设置（需要 window 实例）
        self._log_callbacks_pending = True

    def _bind_log_callbacks(self):
        """绑定需要 window 实例的日志回调"""
        if not self._window:
            return
        self.log_mgr.set_ui_callback(self.log_ui)
        self.log_mgr.set_modal_callbacks(
            status_callback=self.set_modal_status,
            log_callback=self.add_modal_log,
            progress_callback=self.update_modal_progress,
            check_running=self.check_modal_running
        )
        self._log_callbacks_pending = False

    # ========== 窗口管理 ==========

    def set_window(self, window):
        """设置窗口并绑定日志回调"""
        super().set_window(window)
        self._bind_log_callbacks()

    # ========== 后端内部方法 ==========

    def get_attr(self, attr_name):
        """获取实例属性（供前端通过 pywebview.api 访问）"""
        if hasattr(self, attr_name):
            return getattr(self, attr_name)
        return None

    def set_attr(self, attr_name, value):
        """设置实例属性"""
        if hasattr(self, attr_name):
            setattr(self, attr_name, value)

    def run_func(self, func_name, *args):
        """运行实例方法（供前端动态调用）"""
        if hasattr(self, func_name):
            func = getattr(self, func_name)
            return func(*args)
        self.log(f"函数 {func_name} 不存在")
        return None

    # ========== 配置相关 API ==========

    @api_expose
    def get_config_value(self, key_path, default_value=None):
        """获取单个配置值"""
        return self.config.get(key_path, default_value)

    @api_expose
    def update_config_value(self, key_path, value, create_missing=True):
        """更新单个配置值"""
        return self._handlers['config'].update_value(key_path, value, create_missing)

    @api_expose
    def update_config_batch(self, config_updates):
        """批量更新配置值"""
        return self._handlers['config'].update_batch(config_updates)

    @api_expose
    def get_config_batch(self, key_paths):
        """批量获取配置值"""
        return self._handlers['config'].get_batch(key_paths)

    @api_expose
    def save_config_to_file(self):
        """保存配置到文件"""
        return self._handlers['config'].save_to_file()

    @api_expose
    def use_default_config(self):
        """使用默认配置"""
        return self._handlers['config'].use_default()

    @api_expose
    def reset_config(self):
        """重置配置"""
        return self._handlers['config'].reset()

    @api_expose
    def save_settings(self, game_path, debug_mode, auto_update):
        """保存基本设置"""
        return self._handlers['config'].save_settings(game_path, debug_mode, auto_update)

    @api_expose
    def export_frontend_constants(self):
        """导出前端常量（压缩传输）"""
        return self._handlers['config'].export_constants()

    # ========== 翻译相关 API ==========

    @api_expose
    @modal_handler
    def start_translation(self, translator_config: dict, modal_id="false"):
        """开始翻译"""
        return self._handlers['translate'].start(translator_config, modal_id)

    def format_api_settings(self, api_settings: dict, translator) -> dict:
        """格式化API设置"""
        return self._handlers['translate'].format_api_settings(api_settings, translator)

    @api_expose
    def test_api(self, key: str, api_settings: dict) -> dict:
        """测试API密钥"""
        return self._handlers['translate'].test_api(key, api_settings)

    # ========== 下载相关 API ==========

    @api_expose
    @modal_handler
    def download_llc_translation(self, modal_id="false"):
        """下载零协汉化包"""
        return self._handlers['download'].download_llc(modal_id)

    @api_expose
    @modal_handler
    def download_ourplay_translation(self, modal_id="false"):
        """下载OurPlay汉化包"""
        return self._handlers['download'].download_ourplay(modal_id)

    @api_expose
    @modal_handler
    def download_LCTA_auto(self, modal_id="false"):
        """下载LCTA自动更新包"""
        return self._handlers['download'].download_lcta_auto(modal_id)

    @api_expose
    @modal_handler
    def download_bubble(self, modal_id="false"):
        """下载气泡文本Mod"""
        return self._handlers['download'].download_bubble(modal_id)

    # ========== 安装相关 API ==========

    @api_expose
    def get_translation_packages(self):
        """获取翻译包列表"""
        return self._handlers['install'].get_packages()

    @api_expose
    def delete_translation_package(self, package_name):
        """删除翻译包"""
        return self._handlers['install'].delete_package(package_name)

    @api_expose
    @modal_handler
    def install_translation(self, package_name=None, modal_id="false"):
        """安装翻译包"""
        if package_name is None:
            return {"success": False, "message": "传参错误"}
        return self._handlers['install'].install(package_name, modal_id)

    @api_expose
    def change_font_for_package(self, package_name, font_path, modal_id="false"):
        """更换翻译包字体"""
        return self._handlers['install'].change_font(package_name, font_path, modal_id)

    # ========== 管理相关 API ==========

    @api_expose
    def get_installed_packages(self):
        """获取已安装翻译包列表"""
        return self._handlers['manage'].get_installed()

    @api_expose
    def delete_installed_package(self, package_name):
        """删除已安装翻译包"""
        return self._handlers['manage'].delete_installed(package_name)

    @api_expose
    def use_translation(self, package_name=None, modal_id="false"):
        """切换使用的翻译包"""
        return self._handlers['manage'].use(package_name, modal_id)

    @api_expose
    def toggle_installed_package(self, able):
        """切换已安装包启用状态"""
        return self._handlers['manage'].toggle_installed(able)

    @api_expose
    def find_installed_mod(self):
        """查找已安装Mod"""
        return self._handlers['manage'].find_mods()

    @api_expose
    def toggle_mod(self, mod_name, enable):
        """切换Mod启用状态"""
        return self._handlers['manage'].toggle_mod(mod_name, enable)

    @api_expose
    def delete_mod(self, mod_name, enable):
        """删除Mod"""
        return self._handlers['manage'].delete_mod(mod_name, enable)

    @api_expose
    def open_mod_path(self):
        """打开Mod文件夹"""
        return self._handlers['manage'].open_mod_path()

    @api_expose
    def get_symlink_status(self):
        """获取软链接状态"""
        return self._handlers['manage'].get_symlink_status()

    @api_expose
    def move_folders(self, from_path, target_path):
        """移动文件夹"""
        return self._handlers['manage'].move_folders(from_path, target_path)

    # ========== 字体相关 API ==========

    @api_expose
    def get_system_fonts(self):
        """获取系统字体列表"""
        return self._handlers['font'].get_system_fonts()

    @api_expose
    def get_system_fonts_list(self):
        """获取系统字体列表（别名）"""
        return self._handlers['font'].get_fonts_list()

    @api_expose
    def export_selected_font(self, font_name, destination_path):
        """导出选定字体"""
        return self._handlers['font'].export_font(font_name, destination_path)

    # ========== 文本美化 API ==========

    @api_expose
    def get_fancy_rulesets(self):
        """获取美化规则集"""
        return self._handlers['fancy'].get_rulesets()

    @api_expose
    def fancy_main(self, config_list, enableMap):
        """执行文本美化"""
        return self._handlers['fancy'].execute(config_list, enableMap)

    # ========== 专有名词 API ==========

    @api_expose
    @modal_handler
    def fetch_proper_nouns(self, modal_id="false"):
        """抓取专有词汇"""
        return self._handlers['proper'].fetch(modal_id)

    # ========== 清理 API ==========

    @api_expose
    @modal_handler
    def clean_cache(self, modal_id="false", custom_files=None,
                    clean_progress=None, clean_notice=None, clean_mods=None):
        """清理缓存"""
        if custom_files is None:
            custom_files = []
        return self._handlers['clean'].clean(
            modal_id, custom_files, clean_progress, clean_notice, clean_mods
        )

    # ========== 更新相关 API ==========

    @api_expose
    def auto_check_update(self):
        """自动检查更新"""
        return self._handlers['update'].auto_check()

    @api_expose
    def manual_check_update(self):
        """手动检查更新"""
        return self._handlers['update'].manual_check()

    @api_expose
    @modal_handler
    def perform_update_in_modal(self, modal_id):
        """在模态窗口中执行更新"""
        return self._handlers['update'].perform_update(modal_id)

    # ========== 拖拽文件 API ==========

    @api_expose
    def handle_dropped_files(self):
        """处理拖拽文件"""
        files_data = self.current_files
        self.current_files = []
        return self._handlers['dragdrop'].handle_dropped(files_data)

    @api_expose
    def eval_dropped_files(self, files_data, modal_id="false"):
        """评估并安装拖拽文件"""
        return self._handlers['dragdrop'].eval_dropped(files_data, modal_id)

    # ========== 拖拽事件处理 ==========

    def drag_in(self, e):
        """拖入事件"""
        print("drag in")

    def on_drop(self, e):
        """放下事件"""
        files = e['dataTransfer']['files']
        self.current_files = [file['pywebviewFullPath'] for file in files]
        self._window.evaluate_js(
            "dragDropManager.hideMask();dragDropManager.onFileDropCallback()"
        )
        print(f'Event: {e["type"]}. Dropped files:')
        for file in files:
            print(file.get('pywebviewFullPath'))

    # ========== 生命周期 ==========

    def save_setting_from(self):
        """从UI收集配置更新"""
        js_code = '''
        const updates = configManager.collectConfigFromUI();
        configManager.updateConfigValues(updates)
            .then(function(result) {
                configManager.flushPendingUpdates()
            });
        '''
        self._window.evaluate_js(js_code)

    def on_close(self):
        """窗口关闭时保存配置"""
        self.config.save()

    def init_github(self):
        """初始化 GitHub 下载器"""
        import webFunc.GithubDownload as GithubDownload
        import webutils.function_llc as function_llc

        max_workers = self.config.get('github_max_workers', "4")
        timeout = self.config.get('github_timeout', "8")
        GithubDownload.init_request(
            max_workers=int(max_workers) if max_workers.isdigit() else 4,
            timeout=int(timeout) if timeout.isdigit() else 8
        )
        function_llc.font_assets_seven.proxys = GithubDownload.GithubRequester.proxy_manager
        function_llc.font_assets_raw.proxys = GithubDownload.GithubRequester.proxy_manager

    def init_cache(self):
        """初始化缓存目录和字体"""
        import shutil
        from webutils.functions import get_cache_font

        if self.config.get('enable_cache', False):
            cache_path = self.config.get('cache_path', '')
            os.makedirs(cache_path, exist_ok=True)
            if self.config.get('game_path', ''):
                cache_file = Path(cache_path) / 'ChineseFont.ttf'
                if not cache_file.exists():
                    shutil.copy2(
                        get_cache_font(self.config.raw, self.log_mgr),
                        cache_file
                    )

    def init_log(self):
        """初始化日志压缩（旧日志打包为zip）"""
        for i in Path('logs').glob('app.log.*'):
            if i.name.endswith('.zip'):
                continue
            try:
                with zipfile.ZipFile(
                    Path('logs') / f'{i.name}.zip', 'w', zipfile.ZIP_DEFLATED
                ) as zipf:
                    zipf.write(i, arcname=i.name)
                i.unlink()
            except Exception as e:
                self.log(f"压缩日志文件 {i} 时出错: {e}")
                self.log_error(e)

    def check_show(self) -> dict:
        """检查是否需要显示更新日志"""
        last_version = self.config.get('last_version', 'v1.0.0')
        current_version = os.environ.get("__version__", "v5.0.0")

        if last_version != current_version:
            self.config.set('last_version', current_version)
            update_note = (
                (self.path.webui_dir / 'assets' / 'update.md')
                .read_text(encoding='utf-8').split('\n')
            )
            r = []
            flag = False
            for line in update_note:
                if line.startswith('##'):
                    if flag:
                        break
                    else:
                        flag = True
                r.append(line)

            text = '\n'.join(r)
            text += '''\n<button class="primary-btn" onclick="goAndShow('elder');elderManager.initPage();">
    <i class="fas fa-play"></i>
    进入老年人模式来配置更新的内容
</button>
'''
            return {'show': True, 'message': text}
        return {'show': False}

    def resetElder(self):
        """重置老年人模式"""
        default_config = self.config.raw_default
        if default_config and 'elder' in default_config:
            self.config.set('elder', default_config['elder'])
        else:
            raise Exception("无法加载内置默认配置，重置老年人模式失败")


# ========== 日志配置 ==========

def setup_logging() -> logging.Logger:
    """配置日志系统，使用 TimedRotatingFileHandler 按时间轮转"""
    if not os.path.exists('logs'):
        os.makedirs('logs')

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    handler = TimedRotatingFileHandler(
        'logs/app.log',
        when='midnight',
        interval=1,
        encoding='utf-8',
        utc=False,
        delay=False,
        atTime=None
    )

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# ========== 主入口 ==========

def main():
    """启动 LCTA WebUI"""
    html_path = os.path.join(os.getenv('path_'), "webui\\index.html")

    # 设置日志
    logger = setup_logging()
    logger.info("正在启动 LCTA WebUI v5.0.0")

    # 创建 API 实例
    api = LCTA_API()
    logger.info('API 已创建')

    # 创建窗口
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
    atexit.register(api.config.save)

    logger.info("WebUI窗口已创建")

    debug_mode = api.config.get("debug", False)
    enable_storage = api.config.get('enable_storage', False)

    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    webview.settings['ALLOW_DOWNLOADS'] = True

    if not debug_mode:
        logger_c = logging.getLogger('urllib3.connectionpool')
        logger_c.setLevel(logging.INFO)

    def start_func():
        """窗口就绪后的初始化回调"""
        print('加载函数')
        # 注册拖拽事件
        window.dom.document.events.dragenter += DOMEventHandler(api.drag_in, True, True)
        window.dom.document.events.dragstart += DOMEventHandler(api.drag_in, True, True)
        window.dom.document.events.dragover += DOMEventHandler(api.drag_in, True, True, debounce=500)
        window.dom.document.events.drop += DOMEventHandler(api.on_drop, True, True)

    if enable_storage:
        st_path = api.config.get('storage_path', 'tmp')
        webview.start(
            func=start_func,
            debug=debug_mode,
            http_server=True,
            storage_path=str(Path(st_path)),
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
