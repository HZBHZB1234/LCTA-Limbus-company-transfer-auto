import subprocess
import sys
import tempfile
from typing import List, Dict, Optional, Any
from pathlib import Path
import json
from datetime import datetime, timedelta
import socket
from abc import ABC, abstractmethod
import threading

# Needed for embedded python
import os

# DO NOT IMPORT ANY FILES BEFORE THESE TWO LINES
print('开始')
file_dir = Path(os.path.dirname(__file__)).parent
print(f'\n\n{file_dir}')
sys.path.insert(0, str(file_dir))

from webFunc import *
from webFunc import GithubDownload
from globalManagers.LogManager import LogManager
_log_manager = LogManager()
from globalManagers.ConfigManager import ConfigManager
from webutils import *
import webutils.load as LoadUtils
import webutils.functions as func_utils

steam_argv = ''

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
            ourplay_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
        try:
            llc_last_update = datetime.fromisoformat(
                note_content.get('llc_last_update_time', '1970-01-01T00:00:00')
            )
        except (ValueError, TypeError):
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
            machine_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
        try:
            llc_last_update = datetime.fromisoformat(
                note_content.get('llc_last_update_time', '1970-01-01T00:00:00')
            )
        except (ValueError, TypeError):
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

            machine_last_update = GithubDownload.GithubRequester.get_latest_release("HZBHZB1234",
                                        "LCTA_auto_update").published_at

            machine_last_update = datetime.fromisoformat(machine_last_update.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            machine_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
        try:
            GithubDownload.GithubRequester.update_config(use_proxy)

            llc_last_update = GithubDownload.GithubRequester.get_latest_release("LocalizeLimbusCompany",
                                        "LocalizeLimbusCompany").published_at

            llc_last_update = datetime.fromisoformat(llc_last_update.replace('Z', '+00:00'))
        except (ValueError, TypeError):
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

def main_pre():
    global steam_argv
    # 初始化单例配置管理器（第一次调用完成加载）
    ConfigManager()

    steam_argv = os.getenv('steam_argv', '')

    if steam_argv == '':
        _log_manager.log("unexpectedly missing steam_argv environment variable")
        _log_manager.log("use path in config instead")

        steam_argv = ConfigManager().get("game_path", "")+'LimbusCompany.exe'
    _log_manager.log(f"steam_argv: {steam_argv}")

    GithubDownload.init_request()

    # 使用工厂模式创建更新对象并执行更新
    update_obj = create_update()
    update_obj.run()

    # CDN优选（在启动游戏前优化CDN连接）
    config = ConfigManager()
    if not config.get('launcher.work.cdn_optimize', False):
        return

    _log_manager.log("开始CDN优选...")
    try:
        from webutils import function_cdn
        cdn_dir = os.path.join(str(file_dir), 'CFST')
        if not os.path.isdir(cdn_dir):
            _log_manager.log("CFST目录不存在，跳过CDN优选")
            return

        def launcher_log(msg):
            _log_manager.log(f"[CDN] {msg}")

        def launcher_progress(pct, msg):
            _log_manager.log(f"[CDN] {pct:.0f}%: {msg}")

        result = function_cdn.cdn_full_optimization_simple(
            cfst_dir=cdn_dir,
            log_cb=launcher_log,
            progress_cb=launcher_progress,
            cancel_check=None
        )

        if not (result.get('cf_ip') or result.get('cloudfront_mappings')):
            _log_manager.log("CDN优选未获得有效结果")
            return

        cdn_auto_apply = config.get('launcher.work.cdn_auto_apply', True)
        if not cdn_auto_apply:
            _log_manager.log("CDN优选完成（未自动写入hosts）")
            return

        success = function_cdn.elevate_write_hosts(
            cf_ip=result.get('cf_ip'),
            cloudfront_mappings=result.get('cloudfront_mappings'),
            log_cb=launcher_log
        )
        if success:
            _log_manager.log("CDN优选完成，已写入hosts")
        else:
            _log_manager.log("CDN优选完成，但hosts写入失败")

    except Exception as e:
        _log_manager.log_error(e)
        _log_manager.log("CDN优选失败，继续启动游戏")

def main_after_mod():
    from launcher.modfolder import get_mod_folder
    import launcher.patch as patch
    import launcher.sound as sound
    import launcher.changes as changes

    get_mod_folder()
    mod_zips_root_path = os.environ['mod_path']
    os.makedirs(mod_zips_root_path, exist_ok=True)

    _log_manager.log("Limbus Mod Loader version: v1.8")

    def kill_handler(*args) -> None:
        sys.exit(0)

    def cleanup_assets():
        try:
            _log_manager.log("Cleaning up assets")
            patch.cleanup_assets()
            sound.restore_sound()
            changes.cleanup_patch(steam_argv)
        except Exception as e:
            _log_manager.log_error(e)

    try:
        _log_manager.log("Limbus args: %s", sys.argv)
        cleanup_assets()
        #atexit.register(cleanup_assets)
        _log_manager.log("Detecting lunartique mods")
        patch.detect_lunartique_mods(mod_zips_root_path)
        _log_manager.log("Patching text data")
        changes.apply_patch(mod_zips_root_path, steam_argv)
        tmp_asset_root = tempfile.mkdtemp()
        _log_manager.log("Extracting mod assets to %s", tmp_asset_root)
        patch.extract_assets(tmp_asset_root, mod_zips_root_path)
        _log_manager.log("Backing up data and patching assets....")
        patch.patch_assets(tmp_asset_root)
        patch.shutil.rmtree(tmp_asset_root)
        sound.replace_sound(mod_zips_root_path,steam_argv)
        _log_manager.log("Starting game")

        # 游戏加速热键
        speed_exit = _run_speed_hotkey_if_enabled()

        subprocess.call(steam_argv)

        # 清理加速热键
        if speed_exit is not None:
            speed_exit.set()

        cleanup_assets()

    except Exception as e:
        _log_manager.log_error(e)
        sys.exit(1)

def main_after_game():

    # 游戏加速热键
    speed_exit = _run_speed_hotkey_if_enabled()

    subprocess.call(steam_argv)

    # 清理加速热键
    if speed_exit is not None:
        speed_exit.set()

def _start_speed_hotkeys(speed_factor: float, exit_event: threading.Event):
    """游戏加速热键线程入口。

    注册全局热键并阻塞直到 exit_event 被设置：
    - ctrl+s: 切换 1.0x / speed_factor
    - ctrl+shift+s: 弹出速度选择窗口

    DLL 延迟注入：首次触发热键时才注入。
    """
    import keyboard
    from webutils.function_speed import SpeedManager

    speed_enabled = [False]  # 用列表实现闭包可变引用

    def toggle_speed():
        try:
            if not SpeedManager.is_injected():
                SpeedManager.inject()
            speed_enabled[0] = not speed_enabled[0]
            SpeedManager.set_speed(speed_factor if speed_enabled[0] else 1.0)
            _log_manager.log(
                f"加速 {'开启' if speed_enabled[0] else '关闭'} "
                f"({speed_factor if speed_enabled[0] else 1.0}x)"
            )
        except Exception as e:
            _log_manager.log_error(e)

    def open_selector():
        try:
            if not SpeedManager.is_injected():
                SpeedManager.inject()
            _show_speed_slider_window()
        except Exception as e:
            _log_manager.log_error(e)

    keyboard.add_hotkey('ctrl+s', toggle_speed)
    keyboard.add_hotkey('ctrl+shift+s', open_selector)
    _log_manager.log(f"游戏加速热键已注册: ctrl+s / ctrl+shift+s (目标倍率: {speed_factor}x)")

    exit_event.wait()

    keyboard.remove_all_hotkeys()
    try:
        SpeedManager.close()
    except Exception as e:
        _log_manager.log_error(e)
    _log_manager.log("游戏加速热键已注销")


def _show_speed_slider_window():
    """弹出 WinForms 倍率选择窗口（置顶、不抢夺焦点）。"""
    import threading
    from webutils.function_speed import SpeedManager

    # 初始化 clr（参照 start_webui.py 的回退链）
    try:
        import clr
    except Exception:
        try:
            os.environ['PYTHONNET_RUNTIME'] = 'coreclr'
            import clr
        except Exception:
            os.environ['PYTHONNET_RUNTIME'] = 'mono'
            import clr

    clr.AddReference('System.Windows.Forms')
    clr.AddReference('System.Drawing')
    import System.Windows.Forms as WinForms
    from System.Drawing import Point, Size

    current = SpeedManager.get_speed() or 1.0
    slider_val = [int(max(1, min(100, current * 10)))]  # 0.1x-10.0x -> 1-100

    def run_form():
        WinForms.Application.EnableVisualStyles()

        form = WinForms.Form()
        form.Text = "游戏加速"
        form.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        form.StartPosition = WinForms.FormStartPosition.CenterScreen
        form.Size = Size(320, 170)
        form.TopMost = True
        form.MaximizeBox = False
        form.MinimizeBox = False

        # 标题标签
        title = WinForms.Label()
        title.Text = "选择游戏速度倍率"
        title.Location = Point(16, 12)
        title.AutoSize = True
        form.Controls.Add(title)

        # 滑块
        trackbar = WinForms.TrackBar()
        trackbar.Minimum = 1
        trackbar.Maximum = 100
        trackbar.Value = slider_val[0]
        trackbar.TickFrequency = 10
        trackbar.Size = Size(270, 45)
        trackbar.Location = Point(16, 35)
        form.Controls.Add(trackbar)

        # 当前值标签
        val_label = WinForms.Label()
        val_label.Text = f"当前: {trackbar.Value / 10.0:.1f}x"
        val_label.Location = Point(16, 80)
        val_label.AutoSize = True
        form.Controls.Add(val_label)

        def on_scroll(sender, args):
            val_label.Text = f"当前: {trackbar.Value / 10.0:.1f}x"

        trackbar.Scroll += on_scroll

        # 应用按钮
        apply_btn = WinForms.Button()
        apply_btn.Text = "应用"
        apply_btn.Size = Size(75, 28)
        apply_btn.Location = Point(210, 95)

        def on_apply(sender, args):
            try:
                SpeedManager.set_speed(trackbar.Value / 10.0)
            except Exception as e:
                _log_manager.log_error(e)
            form.Close()

        apply_btn.Click += on_apply
        form.Controls.Add(apply_btn)

        # 取消按钮
        cancel_btn = WinForms.Button()
        cancel_btn.Text = "取消"
        cancel_btn.Size = Size(75, 28)
        cancel_btn.Location = Point(125, 95)

        def on_cancel(sender, args):
            form.Close()

        cancel_btn.Click += on_cancel
        form.Controls.Add(cancel_btn)

        form.ShowDialog()

    t = threading.Thread(target=run_form)
    t.SetApartmentState(3)  # STA
    t.Start()
    t.Join()


def _run_speed_hotkey_if_enabled():
    """如果配置允许，启动热键线程并返回 exit_event 或 None。"""
    if not ConfigManager().get("launcher.work.speed", False):
        return None
    if not ConfigManager().get("speed.disclaimer_accepted", False):
        _log_manager.log("游戏加速已配置但未同意免责声明，跳过热键注册")
        return None

    speed_factor = float(ConfigManager().get("launcher.work.speed_factor", "2.0"))
    exit_event = threading.Event()
    t = threading.Thread(
        target=_start_speed_hotkeys,
        args=(speed_factor, exit_event),
        daemon=True,
    )
    t.start()
    return exit_event


def main():
    try:
        main_pre()
    except Exception as e:
        _log_manager.log_error(e)
    try:
        if ConfigManager().get("launcher.work.mod", False):
            main_after_mod()
        else:
            main_after_game()
    except Exception as e:
        _log_manager.log_error(e)
    _log_manager.log('正常退出')

if __name__ == '__main__':
    main()