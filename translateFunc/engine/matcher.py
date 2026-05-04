"""
文本匹配器模块
SimpleMatcher: 基于字符串包含/相等的简单匹配器
TextMatcher: 组合多个匹配器的文本匹配器
MatcherOrganizer: 管理匹配数据和匹配器，支持专有名词、角色、状态效果的更新
"""

from typing import Dict, List, Tuple
from contextlib import suppress

from .data_structures import MatcherData


class SimpleMatcher:
    """基于模式字符串列表的简单匹配器"""

    def __init__(self, patterns: List[str]):
        self.patterns = patterns

    def match(self, texts: list) -> List[List[int]]:
        """返回每个文本中匹配到的模式索引列表"""
        result = []
        for text in texts:
            result.append([i for i, p in enumerate(self.patterns) if p in text])
        return result

    def match_equal(self, texts: list) -> List:
        """精确匹配，返回匹配到的模式索引列表"""
        result = []
        for text in texts:
            try:
                result.append(self.patterns.index(text))
            except ValueError:
                result.append('')
        return result


class TextMatcher:
    """组合文本匹配器，同时管理专有名词/角色/状态效果的匹配"""

    def __init__(self):
        self.proper_matcher: SimpleMatcher = SimpleMatcher([])
        self.role_matcher: SimpleMatcher = SimpleMatcher([])
        self.affect_id_matcher: SimpleMatcher = SimpleMatcher([])
        self.affect_name_matcher: SimpleMatcher = SimpleMatcher([])


class MatcherOrganizer:
    """匹配器管理器，负责更新和维护匹配数据与匹配器"""

    def __init__(self):
        self.mData = MatcherData()
        self.tMatcher = TextMatcher()

    def update_proper(self, proper_data: List[Dict[str, str]]):
        """更新专有名词匹配数据"""
        self.mData.proper_data = proper_data
        proper_terms = [item['term'] for item in proper_data if 'term' in item]
        self.tMatcher.proper_matcher = SimpleMatcher(proper_terms)
        self.mData.proper_refer = proper_terms

    def update_models(self, kr_role: List[Dict[str, str]],
                      cn_role: List[Dict[str, str]]):
        """更新角色模型匹配数据"""
        with suppress(Exception):
            kr_role = kr_role['dataList']
        with suppress(Exception):
            cn_role = cn_role['dataList']

        role_data = [
            {
                'id': KRitem['id'],
                'kr': KRitem['name'],
                'cn': CNitem['name'],
                'nickName': CNitem.get('nickName', '')
            }
            for KRitem, CNitem in zip(kr_role, cn_role)
        ]

        role_id = [item['id'] for item in role_data]
        self.mData.role_data = role_data
        self.tMatcher.role_matcher = SimpleMatcher(role_id)
        self.mData.role_refer = role_id

    def update_efects(self, KRaffect: List[Dict[str, str]],
                      CNaffect: List[Dict[str, str]]):
        """更新状态效果匹配数据"""
        with suppress(Exception):
            KRaffect = KRaffect['dataList']
        with suppress(Exception):
            CNaffect = CNaffect['dataList']

        affectData = [
            {
                'id': KRitem['id'],
                'kr': KRitem['name'],
                'cn': CNitem['name'],
                'desc': CNitem.get('desc', '')
            }
            for KRitem, CNitem in zip(KRaffect, CNaffect)
        ]

        ids = [f'[{item["id"]}]' for item in affectData]
        names = [f'{item["kr"]} ' for item in affectData]

        self.mData.affect_data = affectData
        self.tMatcher.affect_id_matcher = SimpleMatcher(ids)
        self.tMatcher.affect_name_matcher = SimpleMatcher(names)
        self.mData.affect_refer = [
            {'id': _id, 'name': name}
            for _id, name in zip(ids, names)
        ]
