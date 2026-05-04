"""
安装管理 Handler
处理翻译包的查找、安装、删除、字体更换
"""

import os
from . import BaseHandler


class InstallHandler(BaseHandler):
    """安装处理器"""

    def get_packages(self) -> dict:
        """获取翻译包列表"""
        from webutils.function_install import find_translation_packages

        target_dir = self.config.get('ui_default.install.package_directory', "")
        if not target_dir:
            target_dir = os.getcwd()

        packages = find_translation_packages(target_dir)
        self.log.log(f"找到 {len(packages)} 个翻译包")
        return {"success": True, "packages": packages}

    def delete_package(self, package_name: str) -> dict:
        """删除指定翻译包"""
        from webutils.function_install import delete_translation_package

        target_path = self.config.get('ui_default.install.package_directory', "")
        if not target_path:
            target_path = os.getcwd()

        result = delete_translation_package(package_name, target_path, self.log)
        if result["success"]:
            self.log.log(f"成功删除翻译包: {package_name}")
        else:
            self.log.log(f"删除翻译包失败: {result['message']}")
        return result

    def install(self, package_name: str, modal_id: str) -> dict:
        """安装翻译包"""
        from webutils.function_install import install_translation_package

        game_path = self.config.get('game_path', "")
        if not game_path:
            return {"success": False, "message": "请先设置游戏路径"}

        package_dir = self.config.get('ui_default.install.package_directory', "")
        if not package_dir:
            package_dir = os.getcwd()

        package_path = os.path.join(package_dir, package_name)
        success, message = install_translation_package(
            package_path, game_path,
            logger_=self.log,
            modal_id=modal_id
        )

        return {"success": success, "message": message}

    def change_font(self, package_name: str, font_path: str, modal_id: str) -> dict:
        """为翻译包更换字体"""
        from webutils.function_install import change_font_for_package

        result = change_font_for_package(package_name, font_path, self.log, modal_id)
        if result[0]:
            return {"success": True, "message": result[1]}
        return {"success": False, "message": result[1]}
