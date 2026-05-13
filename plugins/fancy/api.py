"""美化插件 —— 文本美化规则（渐变、着色等）。"""

import json
from pathlib import Path

from webui.app import api_expose
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils import builtinFancyConfig, fancy_main


@api_expose
def get_fancy_rulesets(framework) -> dict:
    """获取所有美化规则集。"""
    return {
        "success": True,
        "data": {
            "builtin": builtinFancyConfig,
            "user": json.loads(configManager.get("user_fancy", "[]")),
            "enabled": json.loads(configManager.get("fancy_allow", "{}")),
        }
    }


@api_expose
def run_fancy(framework, config_list: list, enable_map: dict) -> dict:
    """执行文本美化。"""
    try:
        game_path = configManager.get("game_path", "")
        lang_path = Path(game_path) / "LimbusCompany_Data" / "lang"
        config_lang = json.loads(
            (lang_path / "config.json").read_text(encoding="utf-8")
        ).get("lang", "")
        enabled_rules = [i for i in config_list if enable_map.get(i.get("name", ""), False)]
        fancy_main(game_path, config_lang, enabled_rules)
        return {"success": True, "message": "文本美化完成"}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}
