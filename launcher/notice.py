# -*- coding: utf-8 -*-
"""Launcher 集成：启动游戏前增量同步并汉化官方公告。

在 `PHASE_PREPARE_MOD` 阶段执行（早于游戏进程创建，确保写入的公告文件在
游戏读取前就位）。只处理官方清单里新增或未汉化的公告，并受「Launcher 启动
预算」约束；服务不可用、超时或任何异常都只记录日志，不阻塞游戏启动。

实现细节见 `webutils/notice/core.py`：公告文本不走官方语言包，改用「按官方
同名文件名预置公告缓存」的方式替换，游戏判定缓存只 `File.Exists`，因此写入
后不会被覆盖或重新下载。
"""
from __future__ import annotations

import logging
import time

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager

_log_manager = LogManager()

DEFAULT_BUDGET_SECONDS = 30.0
MIN_BUDGET_SECONDS = 5.0


def _budget_seconds() -> float:
    try:
        value = float(ConfigManager().get("notice.launcher_timeout", DEFAULT_BUDGET_SECONDS))
    except (TypeError, ValueError):
        value = DEFAULT_BUDGET_SECONDS
    return max(MIN_BUDGET_SECONDS, value)


def run_notice_sync(cancel_event=None) -> dict:
    """启动前同步一次公告汉化，返回结果摘要（不抛异常）。"""
    if not ConfigManager().get("notice.enabled", False):
        return {"skipped": True, "reason": "未启用公告汉化"}

    try:
        from webutils.notice import NoticeLocalizer
    except Exception as e:  # pragma: no cover - 导入失败不应阻塞启动
        _log_manager.log_error(e)
        return {"skipped": True, "reason": "公告汉化模块加载失败"}

    try:
        localizer = NoticeLocalizer.from_config()
    except Exception as e:
        _log_manager.log_error(e)
        return {"skipped": True, "reason": "读取公告汉化配置失败"}

    if not localizer.service_url:
        _log_manager.log("公告汉化已跳过: 未配置翻译服务地址", level=logging.WARNING)
        return {"skipped": True, "reason": "未配置翻译服务地址"}

    budget = _budget_seconds()
    deadline = time.monotonic() + budget
    _log_manager.log("公告汉化: 开始增量同步（预算 {:.0f} 秒）".format(budget))

    def progress(done: int, total: int, message: str) -> None:
        _log_manager.log("公告汉化 [{}/{}] {}".format(done, total, message))

    try:
        result = localizer.sync(
            cancel_event=cancel_event, progress=progress, deadline=deadline
        )
    except Exception as e:
        _log_manager.log_error(e)
        return {"skipped": False, "success": False, "reason": str(e)}

    if result.get("cancelled"):
        _log_manager.log("公告汉化已取消", level=logging.WARNING)
    elif result.get("timed_out"):
        _log_manager.log(
            "公告汉化已达启动预算（已汉化 {} 篇），剩余公告留待下次同步".format(
                result.get("translated", 0)
            ),
            level=logging.WARNING,
        )
    elif result.get("pending"):
        _log_manager.log(
            "公告汉化: 服务端尚未命中缓存（已汉化 {} 篇），剩余公告留待下次同步".format(
                result.get("translated", 0)
            ),
            level=logging.WARNING,
        )
    elif result.get("failed"):
        _log_manager.log(
            "公告汉化完成，但 {} 篇失败: {}".format(
                result.get("failed"), result.get("message")
            ),
            level=logging.WARNING,
        )
        for item in result.get("items") or []:
            if item.get("status") == "failed":
                _log_manager.log(
                    "公告汉化失败文件: {} — {}".format(
                        item.get("file"), item.get("message")
                    ),
                    level=logging.WARNING,
                )
    else:
        _log_manager.log("公告汉化: {}".format(result.get("message")))

    return result
