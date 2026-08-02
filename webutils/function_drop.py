from pathlib import Path
import os

import shutil
import tempfile
import json
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .function_install import install_translation_package
from .function_fancy import import_bus_rules_file
from .function_manage import get_mod_path, safe_join_path
from .function_clean import _sanitize_zip_member_name
from .functions import extract_zip_smartly, decompress_7z
from .update import Updater
from .bus_engine import is_bus_ruleset, is_tiaozhua_config
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
_log_manager = LogManager()

FOLDERLIST = [
    'BattleAnnouncerDlg',
    'BgmLyrics',
    'EGOVoiceDig',
    'PersonalityVoiceDlg',
    'StoryData',
]

NAMEREFER = {
    'full': '汉化包',
    'nofont': '无字体汉化包',
    'FLmod': '浮士德启动器格式模组',
    'jsononly': '文本内容替换包',
    'update': '更新包',
    'invalid': '无效的文件',
    'carra': '贴图模组',
    'bank': '音效模组',
    'textFile': '文本内容替换包',
    'LCTAchange': 'LCTA文本修改包',
    'FLchange': '浮士德启动器格式文本修改包',
    'busimport': '巴士替换规则配置',
}


class FileFormatDetector(ABC):
    """文件格式判断处理器接口。"""

    def __init__(self, next_detector=None):
        self._next_detector = next_detector

    def set_next(self, next_detector):
        self._next_detector = next_detector
        return next_detector

    def handle(self, file_path):
        if self.can_handle(file_path):
            return self.detect(file_path)
        if self._next_detector is not None:
            return self._next_detector.handle(file_path)
        return 'invalid'

    @abstractmethod
    def can_handle(self, file_path):
        raise NotImplementedError

    @abstractmethod
    def detect(self, file_path):
        raise NotImplementedError


class PredicateFormatDetector(FileFormatDetector):
    """使用谓词与判断函数组成的通用格式判断处理器。"""

    def __init__(self, predicate, evaluator, next_detector=None):
        super().__init__(next_detector)
        self._predicate = predicate
        self._evaluator = evaluator

    def can_handle(self, file_path):
        return self._predicate(file_path)

    def detect(self, file_path):
        return self._evaluator(file_path)


class ExtensionFormatDetector(FileFormatDetector):
    """按文件扩展名判断格式的通用处理器。"""

    def __init__(self, extensions, evaluator, next_detector=None):
        super().__init__(next_detector)
        self._extensions = {extension.lower() for extension in extensions}
        self._evaluator = evaluator

    def can_handle(self, file_path):
        return Path(file_path).suffix.lower() in self._extensions

    def detect(self, file_path):
        return self._evaluator(file_path)


class FileFormatDetectionChain:
    """按注册顺序传递文件格式判断请求。"""

    def __init__(self, detectors=None):
        self._head = None
        self._tail = None
        for detector in detectors or ():
            self.add(detector)

    def add(self, detector):
        if self._head is None:
            self._head = detector
        else:
            self._tail.set_next(detector)
        self._tail = detector
        return self

    def detect(self, file_path):
        if self._head is None:
            return 'invalid'
        return self._head.handle(file_path)


class FileFormatExecutor(ABC):
    """文件格式执行处理器接口。"""

    def __init__(self, next_executor=None):
        self._next_executor = next_executor

    def set_next(self, next_executor):
        self._next_executor = next_executor
        return next_executor

    def handle(self, context):
        if self.can_handle(context):
            return self.execute(context)
        if self._next_executor is not None:
            return self._next_executor.handle(context)
        return None

    @abstractmethod
    def can_handle(self, context):
        raise NotImplementedError

    @abstractmethod
    def execute(self, context):
        raise NotImplementedError


class FileFormatExecutionChain:
    """按注册顺序传递文件格式执行请求。"""

    def __init__(self, executors=None):
        self._head = None
        self._tail = None
        for executor in executors or ():
            self.add(executor)

    def add(self, executor):
        if self._head is None:
            self._head = executor
        else:
            self._tail.set_next(executor)
        self._tail = executor
        return self

    def execute(self, context):
        if self._head is None:
            return None
        return self._head.handle(context)


@dataclass(frozen=True)
class FileExecutionContext:
    """单个拖放文件的执行上下文。"""

    file_path: str
    file_type: str
    modal_id: str
    index: int
    total: int
    game_path: str
    mod_path: str

    @property
    def file_name(self):
        return Path(self.file_path).name

    @property
    def progress_pct(self):
        return int((self.index / self.total) * 100)


class PredicateFormatExecutor(FileFormatExecutor):
    """使用文件类型谓词与执行函数组成的通用执行处理器。"""

    def __init__(self, file_types, executor, next_executor=None):
        super().__init__(next_executor)
        self._file_types = set(file_types)
        self._executor = executor

    def can_handle(self, context):
        return context.file_type in self._file_types

    def execute(self, context):
        return self._executor(context)


class FallbackFormatDetector(FileFormatDetector):
    """检测链末端的默认格式。"""

    def can_handle(self, file_path):
        return True

    def detect(self, file_path):
        return 'invalid'


class FallbackFormatExecutor(FileFormatExecutor):
    """执行链末端的默认动作。"""

    def can_handle(self, context):
        return True

    def execute(self, context):
        _log_manager.log_modal_process(
            f"未知文件类型 '{context.file_type}'，跳过: {context.file_name}",
            context.modal_id,
        )
        return 'skipped'

def _is_full_pkg_items(items):
    """判断条目集合是否符合汉化包结构（FOLDERLIST 特征全部出现）"""
    return all(any(folder in item for item in items) for folder in FOLDERLIST)

def _unwrap_dir(folder_path):
    """剥开单根目录包裹：顶层仅一个目录（可有零散文件）且该目录内含汉化包特征时，
    返回该目录作为包根；否则返回原路径。"""
    items = os.listdir(folder_path)
    dirs = [i for i in items if os.path.isdir(os.path.join(folder_path, i))]
    if len(dirs) != 1:
        return folder_path
    only_path = os.path.join(folder_path, dirs[0])
    if not _is_full_pkg_items(os.listdir(only_path)):
        return folder_path
    return only_path

def _zip_top_items(namelist):
    """返回 (顶层条目, 包条目)。顶层仅一个目录条目（可有零散文件）时，
    包条目取其下一层，以识别单根目录包裹结构。"""
    top_names = set()
    dir_tops = set()
    for name in namelist:
        clean = name.replace('\\', '/').rstrip('/')
        parts = clean.split('/')
        top = parts[0] if parts else ''
        if top:
            top_names.add(top)
        if len(parts) >= 2 and top:
            dir_tops.add(top)
    if len(dir_tops) != 1:
        return top_names, top_names
    only = next(iter(dir_tops))
    prefix = only + '/'
    sub_names = set()
    for name in namelist:
        clean = name.replace('\\', '/').rstrip('/')
        if clean.startswith(prefix):
            rest = clean[len(prefix):]
            if rest:
                sub_names.add(rest.split('/')[0])
    if not sub_names:
        return top_names, top_names
    return top_names, sub_names

def _validate_zip_members(zip_path):
    """校验 zip 成员名安全性，拒绝含 `..` 段、绝对路径或盘符的成员，防止路径穿越"""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for info in zip_ref.infolist():
            _sanitize_zip_member_name(info.filename)

def _zip_extract_root(zip_path):
    """返回 zip 按 extract_zip_smartly 解压后的实际根名（用于预删除对齐）。
    单根目录返回该根名，多根目录返回 zip 文件名（不含扩展名）。"""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        root_items = set()
        for info in zip_ref.infolist():
            _sanitize_zip_member_name(info.filename)
            root_item = (info.filename.split('/')[0]
                         if '/' in info.filename else info.filename)
            if root_item:
                root_items.add(root_item)
        if not root_items:
            return None
    if len(root_items) == 1:
        return next(iter(root_items))
    return Path(zip_path).stem

def _remove_existing(path):
    """删除已存在的目标文件/文件夹（遵循项目惯例）"""
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

def _collect_package_dirs(root_dir):
    """收集 7z 解压目录中的汉化包根目录列表。
    单根目录包裹时剥开包裹层；多顶层条目时仅目录项作为包根（文件项不构成汉化包结构，跳过）。"""
    items = sorted(os.listdir(root_dir))
    dirs = [os.path.join(root_dir, i) for i in items
            if os.path.isdir(os.path.join(root_dir, i))]
    if len(dirs) == 1:
        inner = dirs[0]
        if _is_full_pkg_items(os.listdir(inner)):
            return [inner]
    return dirs


@dataclass(frozen=True)
class ZipFormatInspection:
    """zip 文件格式判断所需的只读信息。"""

    names: tuple
    non_json_names: tuple
    package_names: frozenset

    @property
    def amount(self):
        return len(self.names)

    @property
    def non_json_amount(self):
        return len(self.non_json_names)

    @property
    def has_font(self):
        return any('Font' in name for name in self.non_json_names)


@dataclass(frozen=True)
class FolderFormatInspection:
    """目录格式判断所需的只读信息。"""

    path: str
    items: tuple
    package_items: tuple

    @property
    def has_font(self):
        return any('Font' in item for item in self.package_items)


@dataclass(frozen=True)
class JsonFormatInspection:
    """JSON 格式判断所需的只读信息。"""

    data: object


def _build_zip_format_detection_chain():
    return FileFormatDetectionChain([
        PredicateFormatDetector(
            lambda inspection: (
                _is_full_pkg_items(inspection.package_names)
                and inspection.amount > 1500
            ),
            lambda inspection: 'full' if inspection.has_font else 'nofont',
        ),
        PredicateFormatDetector(
            lambda inspection: any(
                'mod_info.json' in name for name in inspection.names
            ),
            lambda inspection: 'FLmod',
        ),
        PredicateFormatDetector(
            lambda inspection: (
                any('requirements.txt' in name
                    for name in inspection.non_json_names)
                and any('start_webui.py' in name
                        for name in inspection.non_json_names)
            ),
            lambda inspection: 'update',
        ),
        PredicateFormatDetector(
            lambda inspection: inspection.non_json_amount >= 3,
            lambda inspection: 'jsononly',
        ),
        FallbackFormatDetector(),
    ])


def _build_folder_format_detection_chain():
    return FileFormatDetectionChain([
        PredicateFormatDetector(
            lambda inspection: _is_full_pkg_items(inspection.package_items),
            lambda inspection: 'full' if inspection.has_font else 'nofont',
        ),
        PredicateFormatDetector(
            lambda inspection: 'mod_info.json' in inspection.items,
            lambda inspection: 'FLmod',
        ),
        PredicateFormatDetector(
            lambda inspection: len(inspection.items) >= 3,
            lambda inspection: 'jsononly',
        ),
        FallbackFormatDetector(),
    ])


def _build_json_format_detection_chain():
    return FileFormatDetectionChain([
        PredicateFormatDetector(
            lambda inspection: (
                is_bus_ruleset(inspection.data)
                or is_tiaozhua_config(inspection.data)
            ),
            lambda inspection: 'busimport',
        ),
        PredicateFormatDetector(
            lambda inspection: (
                isinstance(inspection.data, dict)
                and 'dataList' in inspection.data
            ),
            lambda inspection: 'textFile',
        ),
        PredicateFormatDetector(
            lambda inspection: (
                isinstance(inspection.data, dict)
                and 'patches' in inspection.data
            ),
            lambda inspection: 'LCTAchange',
        ),
        PredicateFormatDetector(
            lambda inspection: (
                isinstance(inspection.data, dict)
                and all(
                    isinstance(item, dict) and 'dataList' in item
                    for item in inspection.data.values()
                )
            ),
            lambda inspection: 'FLchange',
        ),
        FallbackFormatDetector(),
    ])


_ZIP_FORMAT_DETECTION_CHAIN = _build_zip_format_detection_chain()
_FOLDER_FORMAT_DETECTION_CHAIN = _build_folder_format_detection_chain()
_JSON_FORMAT_DETECTION_CHAIN = _build_json_format_detection_chain()


def evalZip(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        namelist = zip_ref.namelist()

    _, package_names = _zip_top_items(namelist)
    inspection = ZipFormatInspection(
        names=tuple(namelist),
        non_json_names=tuple(name for name in namelist if '.json' not in name),
        package_names=frozenset(package_names),
    )
    return _ZIP_FORMAT_DETECTION_CHAIN.detect(inspection)


def evalFolder(folder_path):
    root = _unwrap_dir(folder_path)
    items = tuple(os.listdir(folder_path))
    package_items = tuple(items if root == folder_path else os.listdir(root))
    inspection = FolderFormatInspection(
        path=folder_path,
        items=items,
        package_items=package_items,
    )
    return _FOLDER_FORMAT_DETECTION_CHAIN.detect(inspection)


def eval7zip(file_path):
    with tempfile.TemporaryDirectory() as tmp:
        try:
            if decompress_7z(file_path, tmp):
                return evalFolder(tmp), tmp
            return 'invalid', tmp
        except Exception as e:
            _log_manager.log_error(e)
            return 'invalid', tmp


def evalJson(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        return _JSON_FORMAT_DETECTION_CHAIN.detect(JsonFormatInspection(data))
    except Exception as e:
        _log_manager.log_error(e)
        return 'invalid'


def _build_file_format_detection_chain():
    return FileFormatDetectionChain([
        PredicateFormatDetector(
            lambda file_path: Path(file_path).is_dir(),
            lambda file_path: evalFolder(file_path),
        ),
        ExtensionFormatDetector(
            ('.zip',),
            lambda file_path: evalZip(file_path),
        ),
        ExtensionFormatDetector(
            ('.7z',),
            lambda file_path: eval7zip(file_path)[0],
        ),
        ExtensionFormatDetector(
            ('.json',),
            lambda file_path: evalJson(file_path),
        ),
        ExtensionFormatDetector(
            ('.carra2',),
            lambda file_path: 'carra',
        ),
        ExtensionFormatDetector(
            ('.bank',),
            lambda file_path: 'bank',
        ),
        FallbackFormatDetector(),
    ])


_FILE_FORMAT_DETECTION_CHAIN = _build_file_format_detection_chain()


def evalFile(file_path):
    return _FILE_FORMAT_DETECTION_CHAIN.detect(os.fspath(file_path))

def makeMessage(content):
    message = '<div>'
    count = {key: 0 for key in NAMEREFER}
    for i in content.values():
        count[i] += 1
    for key, value in count.items():
        if value > 0:
            message += f"<p>{NAMEREFER.get(key, key)}: {value}个</p>"
    message += '<br/><hr /><br/>'
    message += '<details><summary>点击展开完整列表</summary><br />'

    for i, t in content.items():
        message += f'<p><strong>{Path(i).name}</strong>: {NAMEREFER.get(t, t)}</p>'
    message += '</details><br /><hr /><br />'
    message += '<p>点击确认以安装</p>'
    message += '</div>'
    if count['update'] and not all(count[key] == 0 for key in count if key != 'update'):
        return 'invalid'
    if all(count[key] == 0 for key in count if key != 'invalid') and count['invalid'] > 0:
        return 'none'
    return message


def _update_execution_progress(context, label):
    _log_manager.update_modal_progress(
        context.progress_pct,
        f"{label} ({context.index + 1}/{context.total}): {context.file_name}",
        context.modal_id,
    )


def _execute_translation_package(context):
    _log_manager.log_modal_process(
        f"正在安装汉化包: {context.file_name}", context.modal_id)
    _update_execution_progress(context, '安装汉化包')

    if not context.game_path:
        raise ValueError("未设置游戏路径，无法安装汉化包")

    if Path(context.file_path).suffix.lower() == '.7z':
        with tempfile.TemporaryDirectory() as tmp_dir:
            _log_manager.log_modal_process(
                f"正在解压7z文件: {context.file_name}", context.modal_id)
            if not decompress_7z(context.file_path, tmp_dir):
                raise RuntimeError(f"7z解压失败: {context.file_name}")
            package_dirs = _collect_package_dirs(tmp_dir)
            if not package_dirs:
                raise RuntimeError(
                    f"7z解压后未找到有效的汉化包目录: {context.file_name}")
            for package_dir in package_dirs:
                install_translation_package(
                    package_dir, context.game_path, modal_id=context.modal_id)
    else:
        install_translation_package(
            context.file_path, context.game_path, modal_id=context.modal_id)

    _log_manager.log_modal_process(
        f"汉化包安装完成: {context.file_name}", context.modal_id)
    return 'installed'


def _execute_archive_package(context):
    label = '模组' if context.file_type == 'FLmod' else '文本替换包'
    _log_manager.log_modal_process(
        f"正在安装{label}: {context.file_name}", context.modal_id)
    _update_execution_progress(context, f"安装{label}")

    if Path(context.file_path).suffix.lower() == '.zip':
        target_name = _zip_extract_root(context.file_path)
        if target_name:
            _remove_existing(
                safe_join_path(str(context.mod_path), target_name))
        extract_zip_smartly(context.file_path, str(context.mod_path))
    else:
        target_path = safe_join_path(
            str(context.mod_path), Path(context.file_path).name)
        _remove_existing(target_path)
        shutil.copytree(context.file_path, target_path)

    _log_manager.log_modal_process(
        f"{label}安装完成: {context.file_name}", context.modal_id)
    return 'modded'


def _execute_single_file_mod(context):
    label = NAMEREFER.get(context.file_type, context.file_type)
    _log_manager.log_modal_process(
        f"正在安装{label}: {context.file_name}", context.modal_id)
    _update_execution_progress(context, f"安装{label}")

    target_path = safe_join_path(str(context.mod_path), context.file_name)
    _remove_existing(target_path)
    shutil.copy2(context.file_path, str(context.mod_path))

    _log_manager.log_modal_process(
        f"{label}安装完成: {context.file_name}", context.modal_id)
    return 'modded'


def _execute_direct_file(context):
    label = NAMEREFER.get(context.file_type, context.file_type)
    _log_manager.log_modal_process(
        f"正在安装{label}: {context.file_name}", context.modal_id)
    _update_execution_progress(context, f"安装{label}")

    target_path = safe_join_path(str(context.mod_path), context.file_name)
    _remove_existing(target_path)
    shutil.copy2(context.file_path, str(context.mod_path))

    _log_manager.log_modal_process(
        f"{label}安装完成: {context.file_name}", context.modal_id)
    return 'modded'


def _execute_bus_import(context):
    _log_manager.log_modal_process(
        f"正在导入巴士规则: {context.file_name}", context.modal_id)
    imported = import_bus_rules_file(context.file_path)
    stats = imported['stats']
    _log_manager.log_modal_process(
        f"规则导入完成: {imported['ruleset_name']}，"
        f"{stats['converted_rules']} 条规则/"
        f"{stats.get('converted_actions', 0)} 个操作",
        context.modal_id,
    )
    return 'imported'


def _execute_update_package(context):
    _log_manager.log_modal_process(
        f"正在安装更新包: {context.file_name}", context.modal_id)
    _update_execution_progress(context, '安装更新包')

    with tempfile.TemporaryDirectory() as tmp_dir:
        _validate_zip_members(context.file_path)
        with zipfile.ZipFile(context.file_path, 'r') as zip_ref:
            zip_ref.extractall(tmp_dir)

        source_dir = Path(tmp_dir)
        for item in os.listdir(tmp_dir):
            item_path = Path(tmp_dir) / item
            if (
                item_path.is_dir()
                and (item_path / 'start_webui.py').exists()
                and (item_path / 'requirements.txt').exists()
            ):
                source_dir = item_path
                break

        cfg = ConfigManager()
        updater = Updater(
            "HZBHZB1234", "LCTA-Limbus-company-transfer-auto",
            delete_old_files=cfg.get("delete_updating", True),
            use_proxy=cfg.get("update_use_proxy", True),
            only_stable=cfg.get("update_only_stable", False),
            modal_id=context.modal_id,
        )
        updater.install_requirements(source_dir)
        _log_manager.check_running(context.modal_id)
        if not updater.update_files(source_dir):
            raise RuntimeError("更新文件失败")

    _log_manager.log_modal_process(
        f"更新包安装完成，请手动重启程序: {context.file_name}",
        context.modal_id,
    )
    return 'updated'


def _skip_file(context):
    _log_manager.log_modal_process(
        f"跳过无效文件: {context.file_name}", context.modal_id)
    return 'skipped'


def _build_file_execution_chain():
    return FileFormatExecutionChain([
        PredicateFormatExecutor(
            ('full', 'nofont'), _execute_translation_package),
        PredicateFormatExecutor(
            ('FLmod', 'jsononly'), _execute_archive_package),
        PredicateFormatExecutor(
            ('carra', 'bank'), _execute_single_file_mod),
        PredicateFormatExecutor(
            ('textFile', 'LCTAchange', 'FLchange'), _execute_direct_file),
        PredicateFormatExecutor(('busimport',), _execute_bus_import),
        PredicateFormatExecutor(('update',), _execute_update_package),
        PredicateFormatExecutor(('invalid',), _skip_file),
        FallbackFormatExecutor(),
    ])


_FILE_EXECUTION_CHAIN = _build_file_execution_chain()


def _build_execution_summary(results):
    parts = []
    if results["installed"] > 0:
        parts.append(f"{results['installed']}个汉化包")
    if results["modded"] > 0:
        parts.append(f"{results['modded']}个模组")
    if results["updated"] > 0:
        parts.append(f"{results['updated']}个更新")
    if results["imported"] > 0:
        parts.append(f"{results['imported']}个规则集")
    if results["skipped"] > 0:
        parts.append(f"跳过{results['skipped']}个")
    if results["errors"] > 0:
        parts.append(f"失败{results['errors']}个")
    return "安装完成: " + ", ".join(parts) if parts else "没有需要安装的文件"


def evalFiles(files_data, modal_id="false"):
    """处理拖入的文件，根据检测到的类型执行相应的安装操作。"""
    if not files_data:
        _log_manager.log_modal_process("没有需要处理的文件", modal_id)
        return {
            "success": True,
            "message": "没有需要处理的文件",
            "installed": 0,
            "modded": 0,
            "updated": 0,
            "imported": 0,
            "skipped": 0,
            "errors": 0,
            "error_details": [],
        }

    game_path = ConfigManager().get('game_path', '')
    mod_path = get_mod_path()
    os.makedirs(mod_path, exist_ok=True)

    total = len(files_data)
    results = {
        "installed": 0,
        "modded": 0,
        "updated": 0,
        "imported": 0,
        "skipped": 0,
        "errors": 0,
    }
    error_details = []

    for index, (file_path, file_type) in enumerate(files_data.items()):
        _log_manager.check_running(modal_id)
        context = FileExecutionContext(
            file_path=os.fspath(file_path),
            file_type=file_type,
            modal_id=modal_id,
            index=index,
            total=total,
            game_path=game_path,
            mod_path=os.fspath(mod_path),
        )

        if not os.path.exists(context.file_path):
            _log_manager.log_modal_process(
                f"文件不存在，跳过: {context.file_name}", modal_id)
            results["skipped"] += 1
            continue

        try:
            result_key = _FILE_EXECUTION_CHAIN.execute(context)
            if result_key in results:
                results[result_key] += 1
        except Exception as error:
            error_msg = f"处理文件 '{context.file_name}' 时出错: {error}"
            _log_manager.log_modal_process(error_msg, modal_id)
            _log_manager.log_error(error)
            results["errors"] += 1
            error_details.append({
                "file": context.file_name,
                "error": str(error),
            })

    summary = _build_execution_summary(results)
    _log_manager.log_modal_process(summary, modal_id)
    _log_manager.log_modal_status("处理完成", modal_id)
    _log_manager.update_modal_progress(100, summary, modal_id)

    return {
        "success": results["errors"] == 0,
        "message": summary,
        "installed": results["installed"],
        "modded": results["modded"],
        "updated": results["updated"],
        "imported": results["imported"],
        "skipped": results["skipped"],
        "errors": results["errors"],
        "error_details": error_details,
    }


if __name__ == '__main__':
    evalZip(r'E:\desktop\limbus transfer\LCTA-Limbus-company-transfer-auto\LimbusLocalize_2026032001.zip')
