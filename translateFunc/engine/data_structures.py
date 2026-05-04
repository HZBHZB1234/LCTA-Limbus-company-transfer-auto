"""
翻译引擎数据结构
定义翻译流程中使用的所有数据类
"""

from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

if TYPE_CHECKING:
    from translatekit import TranslatorBase


class ProcessExitType(Enum):
    """文件处理的退出类型"""
    ALREADY_TRANSLATED = "already_translated"
    EMPTY_WITH_LLC = "empty_llc"
    EMPTY_NO_LLC = "empty_no"
    JSON_DECODE_ERROR = "json_decode_error"
    TRANSLATION_LENGTH_ERROR = "translation_length_error"
    SAVE_EXCEPT = "save_except_except"
    SUCCESS_SAVE = "success_save"
    NO_SAVE_SUCCESS = "no_save_success"


class ProcesserExit(Exception):
    """翻译流程控制异常"""
    def __init__(self, exit_type: ProcessExitType):
        self.exit_type = exit_type


# 空数据标记
EMPTY_DATA = [{'dataList': []}, {}, []]
EMPTY_DATA_LIST = [[], [{}]]
EMPTY_TEXT = ['', '-']
AVOID_PATH = ['usage', 'id', 'model']


@dataclass
class RequestConfig:
    """翻译请求配置"""
    is_skill: bool = False
    is_story: bool = False
    enable_proper: bool = True
    enable_role: bool = True
    enable_skill: bool = True
    max_length: int = 20000
    is_text_format: bool = False
    is_llm: bool = True
    translator: Optional['TranslatorBase'] = None
    from_lang: str = 'KR'
    save_result: bool = True
    debug_mode: bool = False


@dataclass
class PathConfig:
    """翻译路径配置"""
    target_path: Path = Path()
    llc_base_path: Path = Path()
    KR_base_path: Path = Path()
    EN_base_path: Path = Path()
    JP_base_path: Path = Path()

    def get_need_dirs(self) -> List[Path]:
        """获取需要创建的目录列表"""
        return [
            i.relative_to(self.KR_base_path)
            for i in self.KR_base_path.glob('*') if i.is_dir()
        ]

    def create_need_dirs(self):
        """创建目标目录结构"""
        for dir_path in self.get_need_dirs():
            target_dir = self.target_path / dir_path
            target_dir.mkdir(parents=True, exist_ok=True)


class FilePathConfig:
    """单个文件的路径配置"""

    def __init__(self, KR_path: Path, _PathConfig: PathConfig, has_prefix: bool = True):
        self.KR_path = KR_path
        self.rel_path = Path(KR_path.relative_to(_PathConfig.KR_base_path))
        self.rel_dir = self.rel_path.parent

        if has_prefix:
            self.real_name = self.rel_path.name[3:]  # 去掉语言前缀 KR_/EN_/JP_
            self.EN_path = _PathConfig.EN_base_path / self.rel_dir / f"EN_{self.real_name}"
            self.JP_path = _PathConfig.JP_base_path / self.rel_dir / f"JP_{self.real_name}"
        else:
            self.real_name = self.rel_path.name
            self.EN_path = _PathConfig.EN_base_path / self.rel_dir / self.real_name
            self.JP_path = _PathConfig.JP_base_path / self.rel_dir / self.real_name

        self.LLC_path = _PathConfig.llc_base_path / self.rel_dir / self.real_name
        self.target_file = _PathConfig.target_path / self.rel_dir / self.real_name

    def __str__(self):
        return f"FilePathConfig(real_name={self.real_name}, rel_path={self.rel_path})"


@dataclass
class MatcherData:
    """匹配器数据容器"""
    role_data: List[Dict[str, str]] = field(default_factory=list)
    affect_data: List[Dict[str, str]] = field(default_factory=list)
    proper_data: List[Dict[str, str]] = field(default_factory=list)
    role_refer: List[str] = field(default_factory=list)
    affect_refer: List[Dict[str, str]] = field(default_factory=list)
    proper_refer: List[str] = field(default_factory=list)
