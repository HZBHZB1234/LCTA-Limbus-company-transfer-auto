from typing import Dict, List, Tuple, Callable
import requests

class SkillColorHandler():
    def __init__(self) -> None:
        self.data = {}
        self.DATAURL = r'https://limbuscompany.huijiwiki.com/api/rest_v1/namespace/data?filter={%22Data_Identitychoose%22:%22Identitychoose%22}&count=true&pagesize=1000'

    def init_resource(self):
        header = {
            'User-Agent': r'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'Accept': r'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': r'gzip, deflate, br, zstd'
        }
        r = requests.get(self.DATAURL, verify=False, headers=header)
        r.raise_for_status()
        self.data = r.json()['_embedded']

    def exportFunc(self, value: str, data: Dict[tuple, str], dst_tuple: tuple) -> str:
        if not self.data:
            self.init_resource()

skillColorHandler = SkillColorHandler()

builtinFunc: Dict[str, Callable[[str, Dict[tuple, str], tuple], str]] = {
    'skillColor': skillColorHandler.exportFunc
}