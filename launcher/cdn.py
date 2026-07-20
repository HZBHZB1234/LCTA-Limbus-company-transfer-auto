"""CDN优选（从 launcher/main.py 拆分而来）"""
import os
import threading
from datetime import datetime
from pathlib import Path

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager

_log_manager = LogManager()

def run_cdn_optimization(project_root: Path, cancel_event: threading.Event = None) -> None:
    """CDN优选（在启动游戏前优化CDN连接）"""
    config = ConfigManager()
    if not config.get('launcher.work.cdn_optimize', False):
        return

    try:
        cache_ttl = float(config.get('launcher.work.cdn_cache_ttl', '24.0'))
    except (ValueError, TypeError):
        cache_ttl = 0
    if cache_ttl > 0:
        last_time_str = config.get('launcher.work.last_cdn_test_time', '')
        if last_time_str:
            try:
                last_time = datetime.fromisoformat(last_time_str)
                elapsed = (datetime.now() - last_time).total_seconds() / 3600.0
                if elapsed < cache_ttl:
                    _log_manager.log(f"CDN优选缓存有效（{elapsed:.1f}h前），跳过测速")
                    return
            except Exception:
                pass

    _log_manager.log("开始CDN优选...")
    try:
        from webutils import function_cdn
        cdn_dir = os.path.join(str(project_root), 'CFST')
        if not os.path.isdir(cdn_dir):
            _log_manager.log("CFST目录不存在，跳过CDN优选")
            return

        def launcher_log(msg):
            _log_manager.log(f"[CDN] {msg}")

        def launcher_progress(pct, msg):
            _log_manager.log(f"[CDN] {pct:.0f}%: {msg}")

        def cancel_check():
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("cancelled")

        result = function_cdn.cdn_full_optimization_simple(
            cfst_dir=cdn_dir,
            log_cb=launcher_log,
            progress_cb=launcher_progress,
            cancel_check=cancel_check
        )

        if not (result.get('cf_ip') or result.get('cloudfront_mappings')):
            _log_manager.log("CDN优选未获得有效结果")
            return

        config.set('launcher.work.last_cdn_test_time', datetime.now().isoformat())

        cdn_auto_apply = config.get('launcher.work.cdn_auto_apply', True)
        if not cdn_auto_apply:
            _log_manager.log("CDN优选完成（未自动写入hosts）")
            return

        success, err_msg = function_cdn.elevate_write_hosts(
            cf_ip=result.get('cf_ip'),
            cloudfront_mappings=result.get('cloudfront_mappings'),
            log_cb=launcher_log
        )
        if success:
            _log_manager.log("CDN优选完成，已写入hosts")
        else:
            _log_manager.log(f"CDN优选完成，但hosts写入失败：{err_msg or '未知原因'}")

    except Exception as e:
        _log_manager.log_error(e)
        _log_manager.log("CDN优选失败，继续启动游戏")
