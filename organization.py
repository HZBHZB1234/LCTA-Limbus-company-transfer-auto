import json
import os
import jsonpatch
import importlib.util
import translate
class translate_organize():
    def __init__(self,config,log):
        self.config=config
        self.log=log
        (
            self.custom_script,
            self.cache_trans,
            self.team_trans,
            self.excel_output,
            self.log_enabled,
            self.half_trans,
            self.backup,
            self.script_path,
            self.half_trans_path,
            self.backup_path,
            self.game_path,
            self.LLC_path,
            self.lang
        )=(
            self.config.get("custom_script"),
            self.config.get("cache_trans"),
            self.config.get("team_trans"),
            self.config.get("excel_output"),
            self.config.get("log_enabled"),
            self.config.get("half_trans"),
            self.config.get("backup_enabled"),
            self.config.get("script_path"),
            self.config.get("half_trans_path"),
            self.config.get("backup_path"),
            self.config.get("game_path"),
            self.config.get("LLC_path"),
            self.config.get("formal_language")
        )
        if self.custom_script:
            spec = importlib.util.spec_from_file_location("module_name", self.script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.translate=module.translate()
    def check_type_organized(self):
        '''分发类型检查任务，返回嵌套列表'''
