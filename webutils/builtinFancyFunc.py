from typing import Dict, List, Tuple, Callable
from pathlib import Path
import logging
import json
from translateFunc.proper.flat import *
logger = logging.getLogger('fancy')
logger.setLevel(logging.DEBUG)

class SkillColorHandler():
    def __init__(self) -> None:
        self.data = {}
        self.TARGET_FILES = [f'personality-skill-{i+1:0>2}.json' for i in range(12)]
        self.transfer = {
            "INDIGO": "#2020ED",
            "VIOLET": "#8915D1",
            "CRIMSON": "#ED2525",
            "AMBER": "#F1D11F",
            "SHAMROCK": "#22FF1F",
            "AZURE": "#18EAF9",
            "SCARLET": "#FF7B1D",
            "WHITE": "#FFFFFF",
            "BLACK": "#000000"
        }

    def init_resource(self):
        from .function_resource import function_resources
        tmp, NOTFOUND = function_resources(self.TARGET_FILES, logger)
        tmp = Path(tmp)
        for i in self.TARGET_FILES:
            try:
                target = tmp / i
                _data = json.loads(target.read_text(encoding='utf-8-sig'))
                self.data.update(self.processData(_data))
            except Exception as e:
                logger.exception(e)

    def processData(self, _data) -> dict:
        data = _data['list']
        data = {i['id']: i['skillData'][0]['attributeType'] for i in data}
        # data = {i['id']: {'罪孽': i['skillData'][0]['attributeType'],
        #                   '攻击属性': i['skillData'][0]['atkType'],
        #                   '强化': False if i['skillData'][0]['defaultValue'] else True,
        #                   '攻击容量': i['skillData'][0]['targetNum'],
        #                   '技能数': i['skillTier']} for i in data}
        return data

    def exportFunc(self, value: str, data: Dict[tuple, str], dst_tuple: tuple) -> str:
        if not self.data:
            self.init_resource()
        # if len(value) >= 9:
        #     return value
        id_tuple = dst_tuple[:-3]+('id',)
        _id = data[id_tuple]
        try:
            return f'<color={self.transfer[self.data[_id]]}>{value}</color>'
        except:
            return value

skillColorHandler = SkillColorHandler()

builtinFunc: Dict[str, Callable[[str, Dict[tuple, str], tuple], str]] = {
    'skillColor': skillColorHandler.exportFunc
}