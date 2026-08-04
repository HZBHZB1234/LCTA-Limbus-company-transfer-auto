from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict

from globalManagers.ConfigManager import ConfigManager
from webutils.function_resource import get_limbus_resource_files, load_text_assets

logger = logging.getLogger('fancy')


class SkillColorHandler:
    CACHE_VERSION = 2
    TARGET_FILES = tuple(f'personality-skill-{index:02}.json' for index in range(1, 13))
    COLOR_MAP = {
        "INDIGO": "#2020ED",
        "VIOLET": "#8915D1",
        "CRIMSON": "#ED2525",
        "AMBER": "#F1D11F",
        "SHAMROCK": "#22FF1F",
        "AZURE": "#18EAF9",
        "SCARLET": "#FF7B1D",
        "WHITE": "#FFFFFF",
        "BLACK": "#000000",
    }

    def __init__(self) -> None:
        self.data: Dict[str, str] = {}
        self.state = "uninitialized"
        self.last_cache_hit = False

    def _cache_file(self) -> Path | None:
        config = ConfigManager()
        if not config.get('enable_cache', True):
            return None
        cache_root = Path(config.get('cache_path', 'tmp')).expanduser()
        return cache_root / 'fancy' / 'skill-colors.json'

    @staticmethod
    def _resource_fingerprint(resource_files: list[Path]) -> str:
        folder_names = sorted({path.parent.parent.name for path in resource_files})
        return "|".join(folder_names)

    def _load_cache(self, cache_file: Path, fingerprint: str) -> bool:
        try:
            payload = json.loads(cache_file.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return False
        if payload.get('version') != self.CACHE_VERSION or payload.get('fingerprint') != fingerprint:
            return False
        colors = payload.get('colors')
        if not isinstance(colors, dict):
            return False
        self.data = {str(skill_id): color for skill_id, color in colors.items() if isinstance(color, str)}
        return bool(self.data)

    def _save_cache(self, cache_file: Path, fingerprint: str) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'version': self.CACHE_VERSION,
            'fingerprint': fingerprint,
            'colors': self.data,
        }
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                dir=cache_file.parent,
                prefix=f'.{cache_file.name}.',
                suffix='.tmp',
                delete=False,
            ) as temp_file:
                json.dump(payload, temp_file, ensure_ascii=False, separators=(',', ':'))
                temp_path = Path(temp_file.name)
            os.replace(temp_path, cache_file)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def _build_color_map(self, assets: Dict[str, bytes]) -> Dict[str, str]:
        colors: Dict[str, str] = {}
        for file_name, raw_data in assets.items():
            try:
                payload = json.loads(bytes(raw_data).decode('utf-8-sig'))
                entries = payload['list']
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning('解析技能资源 %s 失败: %s', file_name, exc)
                continue
            for entry in entries:
                try:
                    skill_id = str(entry['id'])
                    attribute_type = entry['skillData'][0]['attributeType']
                except (KeyError, IndexError, TypeError):
                    continue
                color = self.COLOR_MAP.get(attribute_type)
                if color:
                    colors[skill_id] = color
        return colors

    def prepare(self) -> bool:
        if self.state == "ready":
            return True
        if self.state == "failed":
            return False

        self.last_cache_hit = False
        resource_files = get_limbus_resource_files()
        fingerprint = self._resource_fingerprint(resource_files)
        cache_file = self._cache_file()
        if cache_file is not None and self._load_cache(cache_file, fingerprint):
            self.state = "ready"
            self.last_cache_hit = True
            logger.debug('技能颜色映射命中缓存，共%s条', len(self.data))
            return True

        try:
            assets, missing = load_text_assets(self.TARGET_FILES, logger, resource_files)
            self.data = self._build_color_map(assets)
            if missing:
                logger.warning('技能颜色资源缺失%s个文件', len(missing))
            if not self.data:
                raise RuntimeError('未能生成任何技能颜色映射')
            if cache_file is not None:
                self._save_cache(cache_file, fingerprint)
        except Exception as exc:
            self.data = {}
            self.state = "failed"
            logger.exception('初始化技能颜色资源失败，本次运行不再重试: %s', exc)
            return False

        self.state = "ready"
        logger.debug('技能颜色映射初始化完成，共%s条', len(self.data))
        return True

    def apply(self, value: str, skill_id) -> str:
        if not self.prepare():
            return value
        color = self.data.get(str(skill_id))
        if color is None:
            return value
        return f'<color={color}>{value}</color>'

    def reset(self) -> None:
        self.data = {}
        self.state = "uninitialized"
        self.last_cache_hit = False


skillColorHandler = SkillColorHandler()
