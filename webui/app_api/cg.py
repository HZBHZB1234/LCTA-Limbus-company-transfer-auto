# -*- coding: utf-8 -*-
"""LCTA_API 加载页 CG 替换：存档锁定注入 + 缓存 bundle 扫描/预览/贴图替换。"""
import threading
import time

from webutils import cg
from webui.app_api.exceptions import CancelRunning


class CgMixin:

    def cg_status(self):
        """页面初始状态：游戏运行态、存档槽、密钥可用性、缓存 bundle 状态。"""
        try:
            slots = cg.list_save_slots()
            key_ok = False
            key_error = ""
            try:
                cg.get_credential()
                key_ok = True
            except Exception as e:
                key_error = str(e)
            return {"success": True, "data": {
                "save_dir": str(cg.get_save_dir()),
                "slots": slots,
                "game_running": cg.is_game_running(),
                "key_available": key_ok,
                "key_error": key_error,
                "bundle": cg.cg_bundle_status(),
            }}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cg_read(self, save_path):
        """读取指定存档的当前 CG 状态（解密）。"""
        try:
            return {"success": True, "data": cg.read_cg_model(save_path)}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cg_apply(self, save_path, forced_ids):
        """方案 A：整体覆写锁定列表（仅人格 CG，字符串 ID → forced 对象，即时写入）。"""
        try:
            if cg.is_game_running():
                return {"success": False, "message": "游戏正在运行，请先完全退出游戏再操作"}
            ids = [str(i) for i in (forced_ids or [])]
            model = cg.set_forced_cg(save_path, ids)
            self.log_ui(f"CG 锁定已更新：{', '.join(model['forced_ids']) or '（空）'}")
            return {"success": True, "data": model}
        except ValueError as e:
            self.log(str(e))
            return {"success": False, "message": str(e)}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cg_inject_pool(self, save_path, cg_id):
        """方案 B：向解锁池 _cgIdList 追加任意字符串资源 ID（Dummy/自定义等，幂等）。"""
        try:
            if cg.is_game_running():
                return {"success": False, "message": "游戏正在运行，请先完全退出游戏再操作"}
            model = cg.set_cg_id_list(save_path, str(cg_id))
            self.log_ui(f"解锁池已注入：{cg_id}（方案 B，游戏保存后可能被重建）")
            return {"success": True, "data": model}
        except ValueError as e:
            self.log(str(e))
            return {"success": False, "message": str(e)}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cg_remove_pool(self, save_path, cg_id):
        """从解锁池 _cgIdList 移除指定条目。"""
        try:
            if cg.is_game_running():
                return {"success": False, "message": "游戏正在运行，请先完全退出游戏再操作"}
            model = cg.remove_cg_id_list(save_path, str(cg_id))
            self.log_ui(f"解锁池已移除：{cg_id}")
            return {"success": True, "data": model}
        except ValueError as e:
            self.log(str(e))
            return {"success": False, "message": str(e)}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cg_scan_ids(self, modal_id="", force=False):
        """后台增量扫描缓存 bundle 枚举可用 CG（进度模态窗口 + 可取消；force=全量重扫）。"""
        try:
            self.add_modal_log("开始扫描缓存 bundle 中的加载页 CG...", modal_id)
            cancel_event = threading.Event()

            def poll_cancel():
                while not cancel_event.is_set():
                    try:
                        self.check_modal_running(modal_id, log=False)
                    except CancelRunning:
                        cancel_event.set()
                        return
                    except Exception:
                        return
                    time.sleep(0.3)

            poller = threading.Thread(target=poll_cancel, daemon=True)
            poller.start()

            def on_log(msg):
                self.add_modal_log(msg, modal_id)

            try:
                result = cg.scan_cg_ids(
                    on_log=on_log,
                    cancel_check=lambda: self.check_modal_running(modal_id, log=False),
                    is_cancelled=cancel_event.is_set,
                    force=bool(force),
                )
            finally:
                cancel_event.set()
            items = result.get("items", {})
            return {"success": True, "data": {
                "count": result.get("count", 0),
                "items": sorted(items.keys()),
                "uncached": sorted(cid for cid, rec in items.items() if not rec.get("cached")),
                # 可锁定（方案 A）＝人格 CG：名字匹配 <人格ID>_normal|_gacksung
                "lockable": sorted(
                    cid for cid in items
                    if cg.is_personality_name(cid.rsplit("/", 1)[-1])),
            }}
        except CancelRunning:
            self.add_modal_log("CG 扫描已取消", modal_id)
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"CG 扫描失败：{e}", modal_id)
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cg_preview(self, cg_id):
        """导出指定 CG 的 PNG 预览（Base64 data URI）。"""
        try:
            return {"success": True, "data": cg.preview_cg(cg_id)}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cg_replace(self, cg_id, image_path, modal_id=""):
        """方案 A：替换缓存 bundle 内贴图（保留原格式/尺寸/mipmap）。"""
        try:
            if cg.is_game_running():
                return {"success": False, "message": "游戏正在运行，请先完全退出游戏再操作"}

            def on_log(msg):
                self.add_modal_log(msg, modal_id)

            result = cg.replace_cg_texture(cg_id, image_path, on_log=on_log)
            self.log_ui(f"CG 贴图替换完成：{cg_id}")
            return result
        except Exception as e:
            self.add_modal_log(f"CG 贴图替换失败：{e}", modal_id)
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cg_restore(self, cg_id, modal_id=""):
        """从留存的原贴图数据还原 bundle。"""
        try:
            if cg.is_game_running():
                return {"success": False, "message": "游戏正在运行，请先完全退出游戏再操作"}

            def on_log(msg):
                self.add_modal_log(msg, modal_id)

            result = cg.restore_cg_texture(cg_id, on_log=on_log)
            self.log_ui(f"CG 贴图已还原：{cg_id}")
            return result
        except Exception as e:
            self.add_modal_log(f"CG 贴图还原失败：{e}", modal_id)
            self.log_error(e)
            return {"success": False, "message": str(e)}
