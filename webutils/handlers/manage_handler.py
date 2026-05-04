"""
已安装包/Mod管理 Handler
处理已安装翻译包的切换、删除，Mod的查找、启用/禁用、删除
"""

from pathlib import Path
import ctypes
from . import BaseHandler


class ManageHandler(BaseHandler):
    """管理处理器"""

    def get_installed(self) -> dict:
        """获取已安装翻译包列表"""
        from webutils.function_manage import find_installed_packages, check_lang_enabled

        enable = check_lang_enabled(self.config.get('game_path', ''))
        if not enable:
            return {"success": True, "enable": False}

        packages, selected = find_installed_packages(self.config.raw)
        self.log.log(f"找到 {len(packages)} 个已安装翻译包")
        return {"success": True, "packages": packages, "selected": selected, "enable": True}

    def delete_installed(self, package_name: str) -> dict:
        """删除已安装翻译包"""
        from webutils.function_manage import delete_installed_package
        return delete_installed_package(package_name, self.config.raw)

    def use(self, package_name: str, modal_id: str) -> dict:
        """切换使用的翻译包"""
        from webutils.function_manage import use_translation_package

        success = use_translation_package(package_name, self.config.raw)
        if success:
            return {"success": True, "message": "成功切换汉化包"}
        return {"success": False, "message": "切换汉化包失败"}

    def toggle_installed(self, able: str) -> dict:
        """切换已安装包的启用状态"""
        from webutils.function_manage import toggle_install_package

        changed = toggle_install_package(self.config.raw, able)
        return {"success": True, "changed": changed}

    def find_mods(self) -> dict:
        """查找已安装的Mod"""
        from webutils.function_manage import fing_mod

        able, disable = fing_mod(self.config.raw)
        return {"success": True, "able": able, "disable": disable}

    def toggle_mod(self, mod_name: str, enable: bool) -> dict:
        """切换Mod启用状态"""
        from webutils.function_manage import toggle_mod

        self.log.log(f'修改mod可用性 {mod_name} 为 {enable}')
        changed = toggle_mod(self.config.raw, mod_name, enable)
        return {"success": True, "changed": changed}

    def delete_mod(self, mod_name: str, enable: bool) -> dict:
        """删除Mod"""
        from webutils.function_manage import delete_mod

        self.log.log(f'删除mod {mod_name} 状态 {enable}')
        success = delete_mod(self.config.raw, mod_name, enable)
        return {"success": success, "message": ""}

    def open_mod_path(self) -> dict:
        """打开Mod文件夹"""
        from webutils.function_manage import open_mod_path

        self.log.log('打开mod文件夹')
        open_mod_path(self.config.raw)
        return {"success": True, "message": ""}

    def get_symlink_status(self) -> dict:
        """获取软链接状态"""
        from webutils.function_manage import check_symlink

        result = check_symlink()
        return {"success": True, "status": result}

    def move_folders(self, from_path: str, target_path: str) -> dict:
        """移动文件夹（使用Windows API）"""
        from webutils.functions import _move_folders

        fr_path = Path(from_path)
        user32 = ctypes.windll.user32
        paths = [
            [str(i)[idx:] for idx, letter in enumerate(str(i)) if letter.isalpha()][0]
            for i in fr_path.iterdir()
        ]
        return _move_folders(
            paths, target_path,
            hwnd=user32.FindWindowW(None, 'LCTA - 边狱公司汉化工具箱'))
