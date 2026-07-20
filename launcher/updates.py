"""汉化包更新逻辑：更新类体系与工厂函数（从 launcher/main.py 拆分而来）"""
import json
import socket
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

from webFunc import Note, GithubDownload
from webutils import (
    find_translation_packages, install_translation_package,
    function_llc_main, check_ver_github,
    function_ourplay_main, function_ourplay_api, check_ver_ourplay,
    function_ourplay_new_main, check_ver_ourplay_new,
    check_ver_github_M,
    function_bubble_main, fancy_main, builtinFancyConfig,
)
import webutils.functions as func_utils
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

class CustomNote(Note):
    _cache_instance = {}
    @classmethod
    def create(cls, address, pwd, read_only) -> Note:
        argu = (address, pwd, read_only)
        if argu in cls._cache_instance:
            return cls._cache_instance[argu]
        else:
            note = cls(address, pwd, read_only)
            note.fetch_note_info()
            cls._cache_instance[argu] = note
            return note

def get_note_content():
    note_ = CustomNote.create(address="1df3ff8fe2ff2e4c", pwd="AutoTranslate", read_only=True)
    note_content = note_.note_content
    note_content = json.loads(note_content)
    return note_content

def update_config_last(name, version):
    ConfigManager().set(f"launcher.last_install.{name}", str(version))

class UpdateBase(ABC):
    """更新基类，定义更新操作的通用接口"""

    def __init__(self):
        self.launcher_config: dict = ConfigManager().get('launcher', {})
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

        run_bubble = self.launcher_config.get('work', {}).get('bubble', False)
        if run_bubble:
            ConfigManager().set('ui_default.bubble.install', True)
            function_bubble_main('安装气泡mod')

        run_fancy = self.launcher_config.get('work', {}).get('fancy', False)
        if run_fancy:
            gamePath = ConfigManager().get('game_path')
            lang_path = Path(gamePath) / 'LimbusCompany_Data' / 'lang'
            config_lang = json.loads((lang_path / 'config.json').read_text(encoding='utf-8')).get('lang', '')
            config_list = builtinFancyConfig
            config_list.extend(json.loads(ConfigManager().get('user_fancy', '[]')))
            enableMap = json.loads(ConfigManager().get('fancy_allow', '[]'))
            fancy_main(gamePath, config_lang, [i for i in config_list if enableMap.get(i.get('name', ''), False)])
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
        self.config: dict = self.launcher_config.get("machine", {})

    def get_latest_version(self) -> str:
        """获取LCTA-AU最新版本号"""
        download_source = self.config.get("download_source", "github")

        if download_source == "github":
            return check_ver_github_M(self.config.get("use_proxy", True))
        else:
            note_content = get_note_content()
            return str(note_content.get('machine_version', '0.0.0'))

    def check_update(self) -> bool:
        last_version = self.get_last_installed_version('machine')
        self.latest_version = self.get_latest_version()
        return last_version != self.latest_version

    def perform_update(self) -> Optional[str]:
        """执行LCTA-AU更新"""
        return function_llc_main(
            "LCTA-AU_update",
            download_source=self.config.get("download_source", "github"),
            from_proxy=self.config.get("use_proxy", True)
        )

    def update_config(self) -> bool:
        update_config_last('machine', self.latest_version)

class LLCUpdate(UpdateBase):
    """LLC更新类"""

    def __init__(self):
        super().__init__()
        self.config: dict = self.launcher_config.get("zero", {})

    def get_latest_version(self) -> str:
        """获取LLC最新版本号"""
        download_source = self.config.get("download_source", "github")

        if download_source == "github":
            return check_ver_github(self.config.get("use_proxy", True))
        else:
            note_content = get_note_content()
            return str(note_content.get('llc_version', '0.0.0'))

    def check_update(self) -> bool:
        last_version = self.get_last_installed_version('llc')
        self.latest_version = self.get_latest_version()
        return last_version != self.latest_version

    def perform_update(self) -> Optional[str]:
        """执行LLC更新"""
        return function_llc_main(
            "llc_update",
            download_source=self.config.get("download_source", "github"),
            from_proxy=self.config.get("use_proxy", True),
            zip_type=self.config.get("zip_type", "zip"),
            use_cache=True,
            cache_path=self.cache_path
        )

    def update_config(self) -> bool:
        update_config_last('llc', self.latest_version)

class OurPlayUpdate(UpdateBase):
    """OurPlay更新类"""

    def __init__(self):
        super().__init__()
        self.config: dict = self.launcher_config.get("ourplay", {})

    def get_latest_version(self) -> str:
        """获取OurPlay最新版本号"""
        source = self.config.get("source", "pc")
        if source == "android":
            return str(check_ver_ourplay_new(official=self.config.get("official", True)))
        elif self.config.get("use_api", True):
            note_content = get_note_content()
            return str(note_content.get('ourplay_version', '0.0.0'))
        else:
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
        elif not self.config.get("use_api", True):
            function_ourplay_main(
                "ourplay_update",
                check_hash=self.config.get("check_hash", True),
                font_option=self.config.get("font_option", "simplify")
            )
        else:
            function_ourplay_api(
                "ourplay_update",
                check_hash=self.config.get("check_hash", True),
                font_option=self.config.get("font_option", "simplify")
            )
        return "ourplay.zip"

class LOUpdate(UpdateBase):
    """同时更新LLC和OurPlay（根据时间戳选择最新的一个）"""

    def __init__(self):
        super().__init__()
        self.llc_update = LLCUpdate()
        self.ourplay_update = OurPlayUpdate()

    def get_latest_type(self) -> str:
        """获取最新源"""
        note_content = get_note_content()

        try:
            ourplay_last_update = datetime.fromisoformat(
                note_content.get('ourplay_last_update_time', '1970-01-01T00:00:00')
            )
        except (ValueError, TypeError):
            _log_manager.log("OurPlay 更新时间戳格式异常，回退到默认值")
            ourplay_last_update = datetime.fromisoformat('1970-01-01T00:00:00')

        try:
            llc_last_update = datetime.fromisoformat(
                note_content.get('llc_last_update_time', '1970-01-01T00:00:00')
            )
        except (ValueError, TypeError):
            _log_manager.log("LLC 更新时间戳格式异常，回退到默认值")
            llc_last_update = datetime.fromisoformat('1970-01-01T00:00:00')

        # 返回时间戳较新的版本类型
        return "ourplay" if llc_last_update < ourplay_last_update else "llc"

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

class LMAUpdate(UpdateBase):
    """同时更新LLC和LCTA-AU（通过api根据时间戳选择最新的一个）"""

    def __init__(self):
        super().__init__()
        self.llc_update = LLCUpdate()
        self.LCTA_AU_update = MachineUpdate()

    def get_latest_type(self) -> str:
        """获取最新源"""
        note_content = get_note_content()

        try:
            machine_last_update = datetime.fromisoformat(
                note_content.get('machine_last_update_time', '1970-01-01T00:00:00')
            )
        except (ValueError, TypeError):
            _log_manager.log("机翻 更新时间戳格式异常，回退到默认值")
            machine_last_update = datetime.fromisoformat('1970-01-01T00:00:00')

        try:
            llc_last_update = datetime.fromisoformat(
                note_content.get('llc_last_update_time', '1970-01-01T00:00:00')
            )
        except (ValueError, TypeError):
            _log_manager.log("LLC 更新时间戳格式异常，回退到默认值")
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
        use_proxy = self.launcher_config.get('zero', {}).get('use_proxy', True)

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

    if update_type == "llc":
        return LLCUpdate()
    elif update_type == "ourplay":
        return OurPlayUpdate()
    elif update_type == "LCTA-AU":
        return MachineUpdate()
    elif update_type == "LO":
        return LOUpdate()
    elif update_type == "LM-A":
        return LMAUpdate()
    elif update_type == "LM-G":
        return LMGUpdate()
    else:  # "no" or any other value
        return NoUpdate()
