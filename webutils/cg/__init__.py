# -*- coding: utf-8 -*-
"""加载页 CG 替换：存档锁定注入（方案 A forced 对象 / 方案 B 解锁池）+ 缓存 bundle 扫描/预览/贴图替换。

公共 API：
    存档：list_save_slots / read_cg_model / set_forced_cg / set_cg_id_list
          / remove_cg_id_list / is_personality_name / normalize_cg_id
          / get_credential / is_game_running / get_save_dir / get_cache_root
    资源：scan_cg_ids / preview_cg / replace_cg_texture / restore_cg_texture
          / cg_bundle_status
"""
from .save import (
    get_cache_root,
    get_credential,
    get_save_dir,
    is_game_running,
    is_personality_name,
    list_save_slots,
    normalize_cg_id,
    read_cg_model,
    remove_cg_id_list,
    set_cg_id_list,
    set_forced_cg,
)
from .bundle import (
    cg_bundle_status,
    load_index,
    preview_cg,
    replace_cg_texture,
    restore_cg_texture,
    scan_cg_ids,
)

__all__ = [
    "get_cache_root",
    "get_credential",
    "get_save_dir",
    "is_game_running",
    "is_personality_name",
    "list_save_slots",
    "normalize_cg_id",
    "read_cg_model",
    "remove_cg_id_list",
    "set_cg_id_list",
    "set_forced_cg",
    "cg_bundle_status",
    "load_index",
    "preview_cg",
    "replace_cg_texture",
    "restore_cg_texture",
    "scan_cg_ids",
]
