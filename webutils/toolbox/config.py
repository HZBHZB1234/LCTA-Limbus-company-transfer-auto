# -*- coding: utf-8 -*-
"""订阅工具的配置读写：**游戏路径只有一份**。

## 为什么单独一层

历史原因，游戏路径存在两个键：

- ``game_path``（顶层）—— 设置页「游戏路径」、启动器、翻译/美化/资源更新等
  所有既有功能都读它；
- ``ui_default.toolbox.game_root`` —— 订阅工具页自己的一份。

两份独立配置的直接后果是「设置里改好了，订阅工具仍说没配置」（或反过来），
而且**两个入口都看起来保存成功**。更糟的是启动器 ``launcher.toolbox_update``
曾优先读订阅工具那份，于是设置页改动对开局前自动更新不生效。

因此约定（2026-11-04）：

- ``game_path`` 是**唯一事实来源**，所有写入都只写它；
- ``ui_default.toolbox.game_root`` 降级为**只读的旧值回退**，仅为兼容已按旧
  版本配置过、且从未在设置页填过的用户 —— 读到就顺手迁到 ``game_path``，
  之后不再写回。

迁移是幂等的，且失败不影响功能（配置读不到就按「未配置」处理）。
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 唯一事实来源（顶层键，设置页 #game-path 绑定它）
GAME_PATH_KEY = "game_path"
# 旧版订阅工具自己的键：**只读回退**，不再写入
LEGACY_GAME_ROOT_KEY = "ui_default.toolbox.game_root"
TOOLBOX_CONFIG_KEY = "ui_default.toolbox"


def _config():
    """延迟导入 ConfigManager：模块级导入会让 webutils 依赖启动期配置初始化。"""
    from globalManagers.ConfigManager import ConfigManager

    return ConfigManager()


def _clean(value) -> str:
    return str(value or "").strip()


def get_game_path() -> Optional[str]:
    """当前游戏目录（已配置的绝对路径或 ``None``）。

    读取顺序：``game_path`` → 旧订阅工具键（读到即迁移到 ``game_path``）。
    这里**不校验**目录是否还存在：校验属于 ``paths.validate_game_root``，
    状态查询要能把「配置了但目录被移走」如实展示出来，而不是变成「未配置」。
    """
    try:
        cfg = _config()
    except Exception:  # noqa: BLE001 — 配置不可用按未配置处理
        logger.debug("读取 ConfigManager 失败，按未配置游戏目录处理", exc_info=True)
        return None

    current = _clean(cfg.get(GAME_PATH_KEY, ""))
    if current:
        return current

    legacy = _clean(cfg.get(LEGACY_GAME_ROOT_KEY, ""))
    if not legacy:
        return None
    # 旧值迁移：写进唯一事实来源，之后所有入口看到同一份
    try:
        cfg.set(GAME_PATH_KEY, legacy)
        logger.info("已把订阅工具旧游戏目录迁移到 game_path：%s", legacy)
    except Exception:  # noqa: BLE001 — 迁移失败不影响本次读取
        logger.warning("迁移旧游戏目录到 game_path 失败（仍按旧值使用）", exc_info=True)
    return legacy


def set_game_path(path: str) -> str:
    """写入游戏目录（**只**写 ``game_path``），返回写入值。

    校验由调用方先用 ``paths.validate_game_root`` 完成 —— 这里不做二次判断，
    避免「检查通过但保存失败」的两套口径。
    """
    value = _clean(path)
    _config().set(GAME_PATH_KEY, value)
    return value
