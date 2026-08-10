# -*- coding: utf-8 -*-
"""LCTA_API 汉化包/Mod/字体/软链接/缓存清理。"""
import os
import ctypes
from pathlib import Path

from globalManagers.ConfigManager import ConfigManager
from webutils import (
    find_translation_packages,
    delete_translation_package,
    install_translation_package,
    toggle_install_package,
    check_lang_enabled,
    find_installed_packages,
    delete_installed_package,
    use_translation_package,
    fing_mod,
    toggle_mod,
    delete_mod,
    open_mod_path,
    check_symlink,
    change_font_for_package,
    get_system_fonts,
    export_system_font,
    save_cache_font,
    clean_config_main,
)
from webutils.utils import _move_folders
from webui.app_api.exceptions import CancelRunning

class PackagesMixin:

    def get_system_fonts(self):
        """获取系统已安装的字体列表"""
        try:
            result = get_system_fonts()
            return result
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"获取系统字体时出错: {str(e)}"}

    def get_translation_packages(self):
        '''获取翻译包列表'''
        try:
            # 从配置中获取汉化包目录，如果没有设置则使用当前工作目录
            target_dir = ConfigManager().get("ui_default.install.package_directory", "")
            if not target_dir:
                target_dir = os.getcwd()
            packages = find_translation_packages(target_dir)
            self.log(f"找到 {len(packages)} 个翻译包")
            return {"success": True, "packages": packages}
        except Exception as e:
            self.log(f"获取翻译包列表失败: {str(e)}")
            self.log_manager.log("获取翻译包列表失败")
            return {"success": False, "message": str(e)}

    def delete_translation_package(self, package_name):
        '''删除指定的翻译包'''
        try:
            # 从配置中获取汉化包目录，如果没有设置则使用当前工作目录
            target_path = ConfigManager().get("ui_default.install.package_directory", "")
            if not target_path:
                target_path = os.getcwd()
            result = delete_translation_package(package_name, target_path)
            if result["success"]:
                self.log(f"成功删除翻译包: {package_name}")
                return result
            else:
                self.log(f"删除翻译包失败: {result['message']}")
                return result
        except Exception as e:
            error_msg = f"删除翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log("删除翻译包时出错")
            return {"success": False, "message": error_msg}

    def install_translation(self, package_name=None, modal_id="false"):
        '''安装翻译包'''
        try:
            if package_name is None:
                self.log("安装翻译包失败: 传参错误")
                return {"success": False, "message": "传参错误"}
        
            # 获取游戏路径
            game_path = ConfigManager().get("game_path", "")
            if not game_path:
                return {"success": False, "message": "请先设置游戏路径"}
            
            self.add_modal_log(f"开始安装汉化包: {package_name}", modal_id)
        
            # 从配置中获取汉化包目录，如果没有设置则使用当前工作目录
            package_dir = ConfigManager().get("ui_default.install.package_directory", "")
            if not package_dir:
                package_dir = os.getcwd()
        
            # 构造完整包路径
            package_path = os.path.join(package_dir, package_name)
        
            # 调用安装函数
            success, message = install_translation_package(
                package_path, 
                game_path,
                                modal_id=modal_id
            )
        
            if success:
                return {"success": True, "message": message}
            else:
                return {"success": False, "message": message}
        except CancelRunning:
            self.log('安装汉化包任务已取消')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            error_msg = f"安装翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log_error(e)
            return {"success": False, "message": error_msg}

    def toggle_installed_package(self, able):
        try:
            changed = toggle_install_package(able)
            return {"success": True, "changed": changed}
        except Exception as e:
            self.log(f"切换可用状态失败: {str(e)}")
            self.log_manager.log_error(e)
            return {"success": False, "message": str(e)}

    def get_installed_packages(self):
        '''获取翻译包列表'''
        try:
            enable = check_lang_enabled(ConfigManager().get('game_path', ''))
            if not enable:
                return {"success": True, "enable": False}
            packages, selected = find_installed_packages()
            self.log(f"找到 {len(packages)} 个翻译包")
            return {"success": True, "packages": packages,
                    "selected": selected, 'enable': True}
        except Exception as e:
            self.log(f"获取翻译包列表失败: {str(e)}")
            self.log_manager.log_error(e)
            return {"success": False, "message": str(e)}

    def delete_installed_package(self, package_name):
        '''删除指定的翻译包'''
        try:
            return delete_installed_package(package_name)
        except Exception as e:
            error_msg = f"删除翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log_error(e)
            return {"success": False, "message": error_msg}

    def use_translation(self, package_name=None, modal_id="false"):
        '''安装翻译包'''
        try:
            self.add_modal_log(f"开始切换汉化包: {package_name}", modal_id)
            # 调用安装函数
            success = use_translation_package(
                package_name,
                modal_id=modal_id
            )
            if success:
                return {"success": True, "message": "成功切换汉化包"}
            else:
                return {"success": False, "message": "切换汉化包失败"}
        except CancelRunning:
            self.log('切换汉化包任务已取消')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            error_msg = f"安装翻译包时出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log_error(e)
            return {"success": False, "message": error_msg}

    def find_installed_mod(self):
        try:
            able, disable = fing_mod()
            return {"success": True, "able": able, "disable": disable}
        except Exception as e:
            error_msg = f"查找已安装mod出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log_error(e)
            return {"success": False, "message": error_msg}

    def toggle_mod(self, mod_name, enable):
        try:
            self.log_manager.log(f'修改mod可用性 {mod_name} 为 {enable}')
            changed = toggle_mod(mod_name, enable)
            return {"success": True, "changed": changed}
        except Exception as e:
            error_msg = f"切换mod出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log_error(e)
            return {"success": False, "message": error_msg}

    def delete_mod(self, mod_name, enable):
        try:
            self.log_manager.log(f'删除mod {mod_name} 状态 {enable}')
            success = delete_mod(mod_name, enable)
            return {"success": success, "message": ""}
        except Exception as e:
            error_msg = f"删除mod出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log_error(e)
            return {"success": False, "message": error_msg}

    def open_mod_path(self):
        try:
            self.log_manager.log('打开mod文件夹')
            open_mod_path()
            return {"success": True, "message": ""}
        except Exception as e:
            error_msg = f"打开mod路径出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log_error(e)
            return {"success": False, "message": error_msg}

    def get_symlink_status(self):
        """获取 Unity 和 ProjectMoon 文件夹的软链接状态"""
        try:
            result = check_symlink()
            return {"success": True, "status": result}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def move_folders(self, from_path: str, target_path: str):
        frPath = Path(from_path)
        user32 = ctypes.windll.user32
        paths = []
        for i in frPath.iterdir():
            path_str = str(i)
            # 驱动器路径含盘符（splitdrive 返回非空），UNC 路径以 \\ 开头
            if not (os.path.splitdrive(path_str)[0] or path_str.startswith('\\\\')):
                continue
            paths.append(path_str)
        return _move_folders(
            paths, target_path,
            hwnd=user32.FindWindowW(None, 'LCTA - 边狱公司汉化工具箱'))

    def change_font_for_package(self, package_name, font_path, modal_id="false"):
        '''为指定翻译包更换字体'''
        try:
            self.log(f"开始为翻译包 {package_name} 更换字体")
            result = change_font_for_package(package_name, font_path, modal_id)
            if result[0]:  # 成功
                self.log(f"为翻译包 {package_name} 更换字体成功")
                return {"success": True, "message": result[1]}
            else:  # 失败
                self.log(f"为翻译包 {package_name} 更换字体失败: {result[1]}")
                return {"success": False, "message": result[1]}
        except CancelRunning:
            self.log('更换字体任务已取消')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            error_msg = f"更换字体时出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log_error(e)
            return {"success": False, "message": error_msg}

    def get_system_fonts_list(self):
        '''获取系统字体列表'''
        try:
            self.log("获取系统字体列表")
            result = get_system_fonts()
            if result["success"]:
                self.log(f"成功获取系统字体列表，共 {len(result['fonts'])} 个字体")
                return result
            else:
                self.log(f"获取系统字体列表失败: {result['message']}")
                return result
        except Exception as e:
            error_msg = f"获取系统字体列表时出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log_error(e)
            return {"success": False, "message": error_msg}

    def export_selected_font(self, font_name, destination_path):
        '''导出选定的字体'''
        try:
            self.log(f"开始导出字体 {font_name} 到 {destination_path}")
            result = export_system_font(font_name, destination_path)
            if result["success"]:
                self.log(f"成功导出字体 {font_name}")
                return result
            else:
                self.log(f"导出字体 {font_name} 失败: {result['message']}")
                return result
        except Exception as e:
            error_msg = f"导出字体时出错: {str(e)}"
            self.log(error_msg)
            self.log_manager.log_error(e)
            return {"success": False, "message": error_msg}

    def upload_cache_font(self, file_path=None):
        '''上传本地字体文件，替换缓存中的默认字体 ChineseFont.ttf'''
        if not file_path or not os.path.isfile(file_path):
            return {"success": False, "message": "字体文件不存在"}
        if Path(file_path).suffix.lower() not in ('.ttf', '.otf'):
            return {"success": False, "message": "仅支持 .ttf / .otf 格式的字体文件"}
        try:
            target = save_cache_font(file_path)
            self.log(f"缓存字体已替换: {Path(file_path).name} → {target}")
            if not ConfigManager().get('enable_cache', True):
                return {"success": True, "message": "缓存字体已替换，但「启用资源缓存」未开启，该字体暂不会被使用"}
            return {"success": True, "message": "缓存字体已替换，后续安装汉化包时将使用该字体"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"替换缓存字体失败: {str(e)}"}

    def clean_cache(self, modal_id= "false", custom_files=None, clean_progress=None, clean_notice=None, clean_mods=None):
        """清理缓存"""
        try:
            self.add_modal_log("开始清除缓存...", modal_id)
        
            # 如果参数未从前端传递，则从配置中获取
            if custom_files is None:
                custom_files = []
            if clean_progress is None:
                clean_progress = ConfigManager().get("ui_default.clean.clean_progress", False)
            if clean_notice is None:
                clean_notice = ConfigManager().get("ui_default.clean.clean_notice", False)
            if clean_mods is None:
                clean_mods = ConfigManager().get("ui_default.clean.clean_mods", False)
        
            if clean_mods:
                roaming_path = Path.home() / "AppData" / "Roaming"
                mods_path = roaming_path / "LimbusCompanyMods"
                custom_files.append(mods_path)
        
            # 调用清理函数
            clean_config_main(
                modal_id=modal_id,
                                clean_progress=clean_progress,
                clean_notice=clean_notice,
                custom_files=custom_files
            )
        
            self.add_modal_log("缓存清除成功", modal_id)
            return {"success": True, "message": "缓存清除成功"}
        except CancelRunning:
            self.log("清理任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"出现错误{e}，清理失败", modal_id)
            self.log_error(e)
            self.log_manager.update_modal_progress(0, "清理失败", modal_id)
            self.log_manager.log_modal_status("清理失败", modal_id)
            return {"success": False, "message": str(e)}
