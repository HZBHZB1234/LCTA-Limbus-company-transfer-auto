"""
字体管理 Handler
处理系统字体获取和导出
"""

from . import BaseHandler


class FontHandler(BaseHandler):
    """字体管理处理器"""

    def get_system_fonts(self) -> dict:
        """获取系统已安装的字体列表"""
        from webutils.function_install import get_system_fonts
        return get_system_fonts()

    def get_fonts_list(self) -> dict:
        """获取系统字体列表（别名）"""
        from webutils.function_install import get_system_fonts

        result = get_system_fonts()
        if result.get("success"):
            self.log.log(f"成功获取系统字体列表，共 {len(result.get('fonts', []))} 个字体")
        return result

    def export_font(self, font_name: str, destination_path: str) -> dict:
        """导出选定的字体"""
        from webutils.function_install import export_system_font

        result = export_system_font(font_name, destination_path, self.log)
        if result.get("success"):
            self.log.log(f"成功导出字体 {font_name}")
        return result
