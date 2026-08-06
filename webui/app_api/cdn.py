# -*- coding: utf-8 -*-
"""LCTA_API CDN 优选：Cloudflare / CloudFront / hosts 写入移除。"""
import webutils.cdn as function_cdn
from webui.app_api.exceptions import CancelRunning

class CdnMixin:

    def cdn_get_status(self):
        """获取当前 CDN/hosts 状态"""
        try:
            status = function_cdn.read_current_hosts_mappings()
            return {"success": True, "data": status}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cdn_optimize_cloudflare(self, modal_id="false"):
        """Cloudflare CDN 优选"""
        try:
            self.add_modal_log("开始Cloudflare CDN优选...", modal_id)

            log_cb, progress_cb, cancel_check = self._make_cdn_callbacks(modal_id)

            result = function_cdn.cdn_optimize_cloudflare(
                log_cb=log_cb,
                progress_cb=progress_cb,
                cancel_check=cancel_check
            )

            if result:
                self.add_modal_log(
                    f"Cloudflare优选完成 — IP: {result['ip']} "
                    f"延迟: {result['avg_latency_ms']:.1f}ms "
                    f"下载: {result['download_mbps']:.1f}MB/s",
                    modal_id
                )
                return {"success": True, "data": result}
            else:
                self.add_modal_log("Cloudflare优选未获得有效结果", modal_id)
                return {"success": False, "message": "Cloudflare优选未获得有效结果"}

        except CancelRunning:
            self.log("CDN优选任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"出现错误{e}，优选失败", modal_id)
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cdn_optimize_cloudfront(self, modal_id="false"):
        """CloudFront API 优选"""
        try:
            self.add_modal_log("开始CloudFront API优选...", modal_id)

            log_cb, progress_cb, cancel_check = self._make_cdn_callbacks(modal_id)

            results = function_cdn.cdn_optimize_cloudfront(
                log_cb=log_cb,
                progress_cb=progress_cb,
                cancel_check=cancel_check
            )

            if results:
                summary = ", ".join(
                    f"{domain}: {info['ip']} ({info['median_latency_ms']:.0f}ms)"
                    for domain, info in results.items()
                )
                self.add_modal_log(f"CloudFront优选完成 — {summary}", modal_id)
                return {"success": True, "data": results}
            else:
                self.add_modal_log("CloudFront优选未获得有效结果", modal_id)
                return {"success": False, "message": "CloudFront优选未获得有效结果"}

        except CancelRunning:
            self.log("CDN优选任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"出现错误{e}，优选失败", modal_id)
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cdn_full_optimization(self, modal_id="false"):
        """全流程CDN优选（Cloudflare + CloudFront）"""
        try:
            self.add_modal_log("开始全流程CDN优选...", modal_id)

            log_cb, progress_cb, cancel_check = self._make_cdn_callbacks(modal_id)

            result = function_cdn.cdn_full_optimization(
                log_cb=log_cb,
                progress_cb=progress_cb,
                cancel_check=cancel_check
            )

            if result.get("success"):
                self.add_modal_log("全流程CDN优选完成", modal_id)
                return {"success": True, "data": result}
            else:
                self.add_modal_log("全流程CDN优选未获得有效结果", modal_id)
                return {"success": False, "message": "未获得有效结果", "data": result}

        except CancelRunning:
            self.log("CDN优选任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.add_modal_log(f"出现错误{e}，优选失败", modal_id)
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cdn_write_hosts(self, cf_ip=None, cloudfront_mappings=None, modal_id="false"):
        """将优选结果写入系统 hosts 文件（需要管理员权限）"""
        try:
            self.add_modal_log("正在写入 hosts...", modal_id)

            log_cb, _, _ = self._make_cdn_callbacks(modal_id)

            success, err_msg = function_cdn.elevate_write_hosts(
                cf_ip=cf_ip,
                cloudfront_mappings=cloudfront_mappings,
                log_cb=log_cb
            )

            if success:
                self.add_modal_log("hosts 写入成功", modal_id)
                return {"success": True, "message": "hosts 写入成功"}
            else:
                self.add_modal_log("hosts 写入失败", modal_id)
                return {"success": False, "message": err_msg or "hosts 写入失败"}

        except Exception as e:
            self.add_modal_log(f"写入 hosts 失败：{e}", modal_id)
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cdn_remove_cloudflare(self):
        """移除 Cloudflare hosts 条目"""
        try:
            success, err_msg = function_cdn.elevate_remove_hosts("cf", log_cb=self.log_ui)
            if success:
                self.log_ui("Cloudflare hosts 条目已移除")
                return {"success": True, "message": "Cloudflare hosts 条目已移除"}
            else:
                self.log_ui("Cloudflare hosts 条目移除失败或无条目")
                return {"success": False, "message": err_msg or "移除失败或无条目"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def cdn_remove_cloudfront(self):
        """移除 CloudFront hosts 条目"""
        try:
            success, err_msg = function_cdn.elevate_remove_hosts("cfa", log_cb=self.log_ui)
            if success:
                self.log_ui("CloudFront hosts 条目已移除")
                return {"success": True, "message": "CloudFront hosts 条目已移除"}
            else:
                self.log_ui("CloudFront hosts 条目移除失败或无条目")
                return {"success": False, "message": err_msg or "移除失败或无条目"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}
