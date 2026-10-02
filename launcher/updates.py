"""汉化包更新逻辑：更新类体系与工厂函数（从 launcher/main.py 拆分而来）"""
import json
import socket
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

from webFunc import GithubDownload
from webutils import (
    find_translation_packages, install_translation_package,
    function_llc_main, function_LCTA_auto_main, check_ver_github,
    function_ourplay_main, check_ver_ourplay,
    function_ourplay_new_main, check_ver_ourplay_new,
    check_ver_github_M,
    function_lanzou_tiaozhua_main, function_lanzou_tiaozhua_replace_main,
    fancy_main, builtinFancyConfig,
)
import webutils.utils as func_utils
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager

_log_manager = LogManager()

def check_network():
    try:
        socket.create_connection(("8.8.8.8", 53))
        return True
    except OSError:
        pass
    return False

def update_config_last(name, version):
    ConfigManager().set(f"launcher.last_install.{name}", str(version))

class UpdateBase(ABC):
    """更新基类，定义更新操作的通用接口"""

    def __init__(self):
        self.launcher_config: dict = ConfigManager().get('launcher', {})
        self.ui_default_config: dict = ConfigManager().get('ui_default', {})
        self.cache_path = func_utils.get_cache_font()

    def check_network_available(self) -> bool:
        """检查网络是否可用"""
        return check_network()

    def get_last_installed_version(self, name) -> str:
        """获取最后安装的版本"""
        last_config = ConfigManager().get("launcher", {}).get("last_install", {})
        return last_config.get(name, "0.0.0")

    def download_and_install(self, zip_path: str) -> bool:
        """下载并安装更新包"""
        package_list = find_translation_packages('.')
        if zip_path not in package_list:
            _log_manager.log(f"更新包 {zip_path} 不在安装包列表中，请检查安装包")
            return False

        _log_manager.log(f"更新包 {zip_path} 已在安装包列表中")
        install_translation_package(zip_path, ConfigManager().get("game_path", ""),
                                   f"update_install")
        return True

    @abstractmethod
    def check_update(self) -> bool:
        pass

    @abstractmethod
    def perform_update(self) -> Optional[str]:
        """执行更新操作，返回更新包路径"""
        pass

    @abstractmethod
    def update_config(self) -> bool:
        """更新配置文件"""
        pass

    def run(self) -> bool:
        """执行完整的更新流程"""
        if not self.check_network_available():
            _log_manager.log("当前网络不可用，无法检查更新")
            return False

        if not self.check_update():
            _log_manager.log("当前版本已经是最新版本")
            return False

        zip_path = self.perform_update()

        if not zip_path:
            _log_manager.log(f"更新包下载失败")
            return False

        _log_manager.log(f"更新包下载成功，路径: {zip_path}")

        if not self.download_and_install(zip_path):
            return False

        self.update_config()
        _log_manager.log(f"汉化包更新完成")

        run_tiaozhua = self.launcher_config.get('work', {}).get('tiaozhua', False)
        if run_tiaozhua:
            ConfigManager().set('ui_default.tiaozhua.install', True)
            function_lanzou_tiaozhua_main('安装调爪JSON')

        tiaozhua_config = ConfigManager().get('ui_default.tiaozhua', {})
        if any(tiaozhua_config.get(f'replace_{n}', False)
               for n in (3, 4, 5, 7, 8)):
            function_lanzou_tiaozhua_replace_main('安装调爪替换文本包')

        run_fancy = self.launcher_config.get('work', {}).get('fancy', False)
        if run_fancy:
            try:
                gamePath = ConfigManager().get('game_path')
                lang_path = Path(gamePath) / 'LimbusCompany_Data' / 'lang'
                config_lang = json.loads((lang_path / 'config.json').read_text(encoding='utf-8')).get('lang', '')
                from webutils.function_fancy import load_fancy_folder_rules
                config_list = [*builtinFancyConfig, *load_fancy_folder_rules()]
                enableMap = json.loads(ConfigManager().get('fancy_allow', '{}'))
                fancy_main(gamePath, config_lang, config_list, enableMap)
            except Exception as e:
                _log_manager.log_error(e)
        return True

    def special_run(self) -> bool:
        """执行完整的更新流程"""
        if not self.check_network_available():
            _log_manager.log("当前网络不可用，无法检查更新")
            return False

        self.check_update()

        self.perform_update()

class NoUpdate(UpdateBase):
    """不执行任何更新"""
    def check_update(self) -> bool:
        _log_manager.log("未启用任何更新选项，跳过更新检查")
        return False

    def perform_update(self) -> Optional[str]:
        _log_manager.log("你是怎么触发这条日志的？")
        return None

    def update_config(self):
        pass

class MachineUpdate(UpdateBase):
    """LCTA-AU更新类"""

    def __init__(self):
        super().__init__()
        self.config: dict = self.ui_default_config.get("machine", {})

    def get_latest_version(self) -> str:
        """获取LCTA-AU最新版本号"""
        return check_ver_github_M(self.config.get("use_proxy", True))

    def check_update(self) -> bool:
        last_version = self.get_last_installed_version('machine')
        self.latest_version = self.get_latest_version()
        return last_version != self.latest_version

    def perform_update(self) -> Optional[str]:
        """执行LCTA-AU更新"""
        return function_LCTA_auto_main("LCTA-AU_update")

    def update_config(self) -> bool:
        update_config_last('machine', self.latest_version)

class LLCUpdate(UpdateBase):
    """LLC更新类"""

    def __init__(self):
        super().__init__()
        self.config: dict = self.ui_default_config.get("zero", {})

    def get_latest_version(self) -> str:
        """获取LLC最新版本号"""
        return check_ver_github(self.config.get("use_proxy", True))

    def check_update(self) -> bool:
        last_version = self.get_last_installed_version('llc')
        self.latest_version = self.get_latest_version()
        return last_version != self.latest_version

    def perform_update(self) -> Optional[str]:
        """执行LLC更新"""
        # download_source 曾支持 "api"（公益镜像源，已移除）；残留值一律按 GitHub 处理
        return function_llc_main(
            "llc_update",
            from_proxy=self.config.get("use_proxy", True),
            zip_type=self.config.get("zip_type", "zip"),
            use_cache=self.config.get("use_cache", True),
            cache_path=self.cache_path
        )

    def update_config(self) -> bool:
        update_config_last('llc', self.latest_version)

class OurPlayUpdate(UpdateBase):
    """OurPlay更新类"""

    def __init__(self):
        super().__init__()
        self.config: dict = self.ui_default_config.get("ourplay", {})

    def get_latest_version(self) -> str:
        """获取OurPlay最新版本号"""
        source = self.config.get("source", "pc")
        if source == "android":
            return str(check_ver_ourplay_new(official=self.config.get("official", True)))
        return str(check_ver_ourplay())

    def check_update(self) -> bool:
        last_version = self.get_last_installed_version('ourplay')
        self.latest_version = self.get_latest_version()
        return last_version != self.latest_version

    def update_config(self) -> bool:
        update_config_last('ourplay', self.latest_version)

    def perform_update(self) -> Optional[str]:
        """执行OurPlay更新"""
        source = self.config.get("source", "pc")
        if source == "android":
            function_ourplay_new_main(
                "ourplay_update",
                check_hash=self.config.get("check_hash", True),
                font_option=self.config.get("font_option", "simplify"),
                official=self.config.get("official", True),
                refer_package=self.config.get("refer_package", None)
            )
        else:
            function_ourplay_main(
                "ourplay_update",
                check_hash=self.config.get("check_hash", True),
                font_option=self.config.get("font_option", "simplify")
            )
        return "ourplay.zip"

class LOUpdate(UpdateBase):
    """更新LLC或OurPlay（零协优先，零协已是最新时才更新 OurPlay）"""

    def __init__(self):
        super().__init__()
        self.llc_update = LLCUpdate()
        self.ourplay_update = OurPlayUpdate()

    def _has_pending(self, update: UpdateBase, name: str) -> bool:
        """查询某源是否存在待更新的新版。查询失败按「无新版」处理，
        好让另一个源仍有机会被选中（整体不会因单个源查不到而停摆）。"""
        try:
            return bool(update.check_update())
        except Exception as e:
            _log_manager.log(f"检查 {name} 更新失败，按无新版处理: {e}")
            return False

    def get_latest_type(self) -> str:
        """选择本次要更新的源：零协优先，零协无新版时才考虑 OurPlay。

        旧实现比较两端的「最后更新时间」时间戳决定谁更新，该时间戳来自已下线的
        公益笔记 API；而 OurPlay 官方接口不返回任何时间字段（只有 versionCode），
        故改为按「是否有新版待更新」的确定性优先级选择。
        """
        if self._has_pending(self.llc_update, 'llc'):
            return "llc"
        if self._has_pending(self.ourplay_update, 'ourplay'):
            return "ourplay"
        return ""

    def perform_update(self) -> Optional[str]:
        """根据时间戳选择执行哪个更新"""
        select_type = self.get_latest_type()
        if select_type == "ourplay":
            self.ourplay_update.run()
        elif select_type == "llc":
            self.llc_update.run()
        else:
            return False

    def check_update(self) -> bool:
        return True

    def update_config(self) -> bool:
        return True

    def run(self):
        self.special_run()

class LMGUpdate(UpdateBase):
    """同时更新LLC和LCTA-AU（通过github根据时间戳选择最新的一个）"""

    def __init__(self):
        super().__init__()
        self.llc_update = LLCUpdate()
        self.LCTA_AU_update = MachineUpdate()

    def get_latest_type(self) -> str:
        """获取最新源"""
        use_proxy = self.ui_default_config.get('zero', {}).get('use_proxy', True)

        try:
            GithubDownload.GithubRequester.update_config(use_proxy)

            release = GithubDownload.GithubRequester.get_latest_release("HZBHZB1234",
                                        "LCTA_auto_update")
            if release is None:
                raise ValueError("获取 GitHub release 失败")
            machine_last_update = release.published_at

            machine_last_update = datetime.fromisoformat(machine_last_update.replace('Z', '+00:00'))
        except (ValueError, TypeError, AttributeError):
            _log_manager.log("机翻(GitHub) 更新时间戳格式异常，回退到默认值")
            machine_last_update = datetime.fromisoformat('1970-01-01T00:00:00')

        try:
            GithubDownload.GithubRequester.update_config(use_proxy)

            release = GithubDownload.GithubRequester.get_latest_release("LocalizeLimbusCompany",
                                        "LocalizeLimbusCompany")
            if release is None:
                raise ValueError("获取 GitHub release 失败")
            llc_last_update = release.published_at

            llc_last_update = datetime.fromisoformat(llc_last_update.replace('Z', '+00:00'))
        except (ValueError, TypeError, AttributeError):
            _log_manager.log("LLC(GitHub) 更新时间戳格式异常，回退到默认值")
            llc_last_update = datetime.fromisoformat('1970-01-01T00:00:00')

        # 返回时间戳较新的版本类型
        return "machine" if llc_last_update < machine_last_update else "llc"

    def perform_update(self) -> Optional[str]:
        """根据时间戳选择执行哪个更新"""
        select_type = self.get_latest_type()
        if select_type == "machine":
            self.LCTA_AU_update.run()
        elif select_type == "llc":
            self.llc_update.run()
        else:
            return False

    def check_update(self) -> bool:
        _log_manager.log('尝试进行检查')
        return True

    def update_config(self) -> bool:
        return True

    def run(self):
        self.special_run()

def create_update() -> UpdateBase:
    """根据配置创建更新对象"""
    update_type = ConfigManager().get('launcher.work.update', "no")

    # "LM-A" 是已移除的「公益镜像源」更新模式，历史配置里的残留值统一按 GitHub 源处理
    if update_type == "LM-A":
        _log_manager.log("更新模式 LM-A（公益镜像源）已移除，按 GitHub 源 (LM-G) 处理")
        update_type = "LM-G"

    if update_type == "llc":
        return LLCUpdate()
    elif update_type == "ourplay":
        return OurPlayUpdate()
    elif update_type == "LCTA-AU":
        return MachineUpdate()
    elif update_type == "LO":
        return LOUpdate()
    elif update_type == "LM-G":
        return LMGUpdate()
    else:  # "no" or any other value
        return NoUpdate()
