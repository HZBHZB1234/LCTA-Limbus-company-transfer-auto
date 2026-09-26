# -*- coding: utf-8 -*-
"""LCTA_API 公告汉化：状态查询 / 同步与取消 / 还原官方原文 / 服务连通性测试。"""
from webutils.notice import get_notice_manager


class NoticeMixin:

    def _notice_manager(self):
        """公告汉化后台任务管理器（懒加载单例）。

        刻意以 `_` 开头：pywebview 的 `get_functions` 会递归展开非可调用属性的
        公开方法，私有名可避免把管理器内部方法一并暴露成前端 API。
        """
        return get_notice_manager()

    def notice_get_info(self):
        """页面初始化信息：路径、目标语言、公告清单与逐条汉化状态。"""
        try:
            return self._notice_manager().get_info()
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def notice_get_status(self):
        """同步任务进度（页面轮询）。"""
        try:
            return self._notice_manager().get_status()
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def notice_start_sync(self, force=False):
        """启动同步：按官方清单把未汉化的公告逐篇交给翻译服务并落盘。"""
        try:
            result = self._notice_manager().start_sync(bool(force))
            if result.get("success"):
                self.log_ui("公告汉化同步任务已启动")
            else:
                self.log("公告汉化同步未启动: {}".format(result.get("message")))
            return result
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def notice_cancel_sync(self):
        """取消正在运行的同步任务。"""
        try:
            return self._notice_manager().cancel()
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def notice_restore(self, files=None):
        """还原官方原文（删除本工具写入的公告文件，游戏下次进大厅重新下载）。"""
        try:
            return self._notice_manager().restore(files)
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def notice_test_service(self, file_name=""):
        """测试翻译服务连通性：请求一篇目标公告并校验（不落盘）。"""
        try:
            return self._notice_manager().test_service(file_name or "")
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def notice_open_dir(self, target="notice"):
        """在资源管理器中打开游戏公告缓存目录 / 本工具缓存目录。"""
        from pathlib import Path

        from webutils.notice import paths as notice_paths

        try:
            path = (
                notice_paths.get_cache_dir()
                if target == "cache"
                else notice_paths.get_notice_dir()
            )
            Path(path).mkdir(parents=True, exist_ok=True)
            self.open_explorer(str(path))
            return {"success": True, "message": str(path)}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}
