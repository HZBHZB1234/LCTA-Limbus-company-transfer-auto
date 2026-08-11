import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
from webutils.utils.net import download_with
from webutils.utils.io import decompress_7z
from webutils.fancy.bus import is_bus_ruleset, is_tiaozhua_config
from webutils.function_fancy import (
    import_bus_rules_file,
    load_fancy_folder_rules,
    _get_fancy_folder,
    _sanitize_filename,
)

_log_manager = LogManager()

LANZOU_FOLDER_URL = "https://wwyi.lanzoub.com/b014wpn02j"
LANZOU_FOLDER_PWD = "fib6"
LANZOU_WEB_HOST = "https://wwyi.lanzoub.com/"
LANZOU_API_BASE = "https://lz.qaiu.top"
BASE_DIRECT = "https://lz.qaiu.top/parser?url="

# 调爪「替换」文本包：3彩色气泡 / 4无色气泡 / 5随机加载文本 / 7事件美化 / 8旧翻译版气泡。
# 包 6（技能被动饰品BUFF美化）与「文本美化」功能重复，永不集成。
REPLACE_PACKAGE_PREFIXES = {
    3: '3.',
    4: '4.',
    5: '5.',
    7: '7.',
    8: '8.',
}
_REPLACE_VERSION_RE = re.compile(r'\d{1,2}\.\d{1,2}\.\d{1,2}')


def fetch_file_list():
    """通过 qaiu API 获取蓝奏云文件夹文件列表。"""
    try:
        r = requests.get(
            f'{LANZOU_API_BASE}/v2/getFileList',
            params={'url': LANZOU_FOLDER_URL, 'pwd': LANZOU_FOLDER_PWD},
            timeout=30, verify=True
        )
        r.raise_for_status()
        data = r.json()
        items = data.get('data') if isinstance(data.get('data'), list) else []
        if not items:
            _log_manager.log(f"获取文件列表失败: {data}")
        return items
    except Exception as e:
        _log_manager.log(f"获取文件列表异常: {e}")
        _log_manager.log_error(e)
        return []


def find_tiaozhua_file(filelists):
    """选中 0. 开头的调爪文本修改包文件。"""
    for file in filelists:
        if file.get('fileName', '').startswith('0.'):
            return file
    return None


def check_tiaozhua(modal_id, filelists):
    _log_manager.log_modal_process("开始检查调爪文本修改包", modal_id)
    file = find_tiaozhua_file(filelists)
    if not file:
        _log_manager.log_modal_process("无法获取文件列表", modal_id)
        return ''
    match = re.search(r'\d{1,2}\.\d{1,2}\.\d{1,2}', file.get('fileName', ''))
    if match:
        return match.group(0)
    return str(file.get('size', ''))


def get_direct_download(file_id):
    return f'{BASE_DIRECT}{LANZOU_WEB_HOST}{file_id}'


def download_tiaozhua(modal_id, save_path: Path, filelists):
    file = find_tiaozhua_file(filelists)
    if not file:
        _log_manager.log_modal_process("未找到 0. 开头的调爪文本修改包", modal_id)
        return False
    url = get_direct_download(file['fileId'])
    return download_with(url, save_path / 'tiaozhua.7z', modal_id=modal_id, validate=False)


def install_tiaozhua(modal_id, mod_path: Path):
    _log_manager.log_modal_process("开始解压调爪文本修改包", modal_id)
    with tempfile.TemporaryDirectory() as temp_dir:
        extract_dir = Path(temp_dir)
        if not decompress_7z(mod_path, extract_dir):
            _log_manager.log_modal_process("调爪文本修改包解压失败", modal_id)
            return []
        imported = []
        skipped = 0
        for json_file in sorted(extract_dir.glob('*.json')):
            try:
                data = json.loads(json_file.read_text(encoding='utf-8-sig'))
            except Exception:
                skipped += 1
                continue
            if is_tiaozhua_config(data) or is_bus_ruleset(data):
                target_name = (data.get('name') or json_file.stem).strip() \
                    or '导入的文本替换规则'
                folder = _get_fancy_folder()
                ruleset_exists = (folder / (_sanitize_filename(target_name) + '.json')).exists() \
                    or any(rs.get('name', '') == target_name
                           for rs in load_fancy_folder_rules())
                if ruleset_exists:
                    _log_manager.log_modal_process(
                        f"规则集 {target_name} 已存在，跳过导入", modal_id)
                    skipped += 1
                    continue
                result = import_bus_rules_file(str(json_file))
                imported.append(result['ruleset_name'])
                stats = result.get('stats', {})
                _log_manager.log_modal_process(
                    f"已导入 {result['ruleset_name']} "
                    f"({stats.get('converted_rules', 0)} 条规则)", modal_id)
            else:
                skipped += 1
        if skipped:
            _log_manager.log_modal_process(
                f"跳过 {skipped} 个非调爪配置文件", modal_id)
        return imported


def find_replace_file(filelists, prefix):
    """选中以指定前缀开头的调爪「替换」文本包文件。"""
    for file in filelists:
        if file.get('fileName', '').startswith(prefix):
            return file
    return None


def _replace_package_version(file) -> str:
    """从替换包文件名中提取版本号（如 26.8.6），无则回退到文件大小。"""
    match = _REPLACE_VERSION_RE.search(file.get('fileName', ''))
    if match:
        return match.group(0)
    return str(file.get('size', ''))


def download_replace_package(modal_id, save_path: Path, file) -> bool:
    url = get_direct_download(file['fileId'])
    return download_with(url, save_path, modal_id=modal_id, validate=False)


def resolve_replace_target_dir(game_path: str) -> Path:
    """返回调爪「替换」文本包的目标语言目录（当前启用的汉化目录）。

    与 fancy 引擎一致：`lang/<config.json 的 lang 值>/`；禁用态走 `_lang`。
    """
    from webutils.packages.manage import get_active_lang_path
    lang_base = get_active_lang_path(game_path)
    config_path = lang_base / 'config.json'
    lang_name = ''
    try:
        config_lang = json.loads(config_path.read_text(encoding='utf-8'))
        lang_name = config_lang.get('lang', '')
    except Exception:
        lang_name = ''
    if not lang_name:
        raise ValueError('无法从 lang/config.json 读取当前启用的语言包')
    return lang_base / lang_name


def install_replace_package(modal_id, zip_path: Path, game_path: str) -> int:
    """解压替换包中 `文件/`（或首个含 json 的非 python 顶层目录）的全部 .json 到目标语言目录。

    选择性读取，不解压包内冗余的 python 解释器。返回拷贝文件数。
    """
    from webutils.packages.clean import _sanitize_zip_member_name
    _log_manager.log_modal_process("开始应用调爪替换文本包", modal_id)
    target_dir = resolve_replace_target_dir(game_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    with zipfile.ZipFile(zip_path, 'r') as zf:
        # 按顶层目录分组收集 json 成员（跳过 python/ 与根级文件）
        roots: dict = {}
        for info in zf.infolist():
            name = _sanitize_zip_member_name(info.filename)
            parts = name.split('/')
            if len(parts) < 2 or not parts[0]:
                continue
            root = parts[0]
            if root == 'python':
                continue
            if name.lower().endswith('.json'):
                roots.setdefault(root, []).append((parts, info))
        if not roots:
            raise ValueError('压缩包内未找到可应用的文本文件')
        source_root = '文件' if '文件' in roots else sorted(roots)[0]
        for parts, info in roots[source_root]:
            _log_manager.check_running(modal_id)
            rel = '/'.join(parts[1:])
            if not rel:
                continue
            dest = (target_dir / rel).resolve()
            if target_dir.resolve() not in dest.parents:
                raise ValueError(f"压缩包成员路径超出目标目录: {info.filename}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(info))
            copied += 1
    _log_manager.log_modal_process(f"调爪替换文本包应用完成，共 {copied} 个文件", modal_id)
    return copied


def _select_replace_packages(tiaozhua_config: dict) -> list:
    """按勾选状态收集替换包编号（升序），并强制三种气泡包（3/4/8）互斥。

    仅识别已知前缀（REPLACE_PACKAGE_PREFIXES 内）；气泡包同时勾选多个时
    仅保留编号最小者，返回最终待应用列表。
    """
    selected = []
    for key, enabled in tiaozhua_config.items():
        if not key.startswith('replace_') or not enabled:
            continue
        try:
            num = int(key.rsplit('_', 1)[1])
        except ValueError:
            continue
        if num in REPLACE_PACKAGE_PREFIXES:
            selected.append(num)
    selected.sort()
    bubble_kept = None
    for num in selected:
        if num in (3, 4, 8):
            if bubble_kept is None:
                bubble_kept = num
    if bubble_kept is not None:
        selected = [n for n in selected if n not in (3, 4, 8) or n == bubble_kept]
    return selected


def function_lanzou_tiaozhua_replace_main(modal_id):
    """下载并应用调爪「替换」文本包（勾选 ui_default.tiaozhua.replace_* 的包）。

    三种气泡（3彩色/4无色/8旧翻译版）互斥：若同时勾选多个，仅应用前缀最小者。
    包缺失（如线上暂无）时记录日志并跳过，不影响其他包。
    """
    game_path = ConfigManager().get('game_path', '')
    if not game_path:
        _log_manager.log_modal_process("未设置游戏路径，无法应用调爪替换文本包", modal_id)
        return

    tiaozhua_config = ConfigManager().get('ui_default.tiaozhua', {})
    selected = _select_replace_packages(tiaozhua_config)
    if not selected:
        _log_manager.log_modal_process("未勾选任何调爪替换文本包", modal_id)
        return

    file_list = fetch_file_list()
    if not file_list:
        _log_manager.log_modal_process("获取文件列表失败，无法应用调爪替换文本包", modal_id)
        return

    enable_cache = ConfigManager().get('enable_cache', True)
    cache_path = Path(ConfigManager().get('cache_path', '.')) if enable_cache else Path('.')
    cache_path.mkdir(parents=True, exist_ok=True)

    for num in selected:
        prefix = REPLACE_PACKAGE_PREFIXES.get(num)
        if not prefix:
            continue
        file = find_replace_file(file_list, prefix)
        if not file:
            _log_manager.log_modal_process(f"未找到 {num}. 开头的调爪替换文本包，跳过", modal_id)
            continue

        mod_ = cache_path / f'tiaozhua_replace_{num}.zip'
        version = _replace_package_version(file)
        version_config = cache_path / f'tiaozhua_replace_{num}_version.txt'
        if enable_cache and version_config.exists() and mod_.exists() and version and \
                version == version_config.read_text(encoding='utf-8'):
            _log_manager.log_modal_process(f"替换文本包 {num} 缓存已存在，无需下载", modal_id)
        elif download_replace_package(modal_id, mod_, file):
            version_config.write_text(version, encoding='utf-8')

        if not mod_.exists():
            _log_manager.log_modal_process(f"替换文本包 {num} 下载失败，跳过", modal_id)
            continue
        try:
            install_replace_package(modal_id, mod_, game_path)
        except Exception as e:
            _log_manager.log(f"应用替换文本包 {num} 失败: {e}")
            _log_manager.log_error(e)
            _log_manager.log_modal_process(f"应用替换文本包 {num} 失败: {e}", modal_id)


def function_lanzou_tiaozhua_main(modal_id):
    tiaozhua_config = ConfigManager().get('ui_default.tiaozhua', {})
    install = tiaozhua_config.get('install', False)
    enable_cache = ConfigManager().get('enable_cache', True)
    cache_path = Path(ConfigManager().get('cache_path', '.')) if enable_cache else Path('.')

    file_list = fetch_file_list()
    mod_ = cache_path / 'tiaozhua.7z'

    if enable_cache:
        version = check_tiaozhua(modal_id, file_list)
        version_config = cache_path / 'tiaozhua_version.txt'
        if version_config.exists() and mod_.exists() and version and \
                version == version_config.read_text(encoding='utf-8'):
            _log_manager.log_modal_process("缓存已存在，无需下载", modal_id)
        elif download_tiaozhua(modal_id, cache_path, file_list):
            version_config.write_text(version, encoding='utf-8')
    else:
        download_tiaozhua(modal_id, cache_path, file_list)

    if install and mod_.exists():
        install_tiaozhua(modal_id, mod_)


if __name__ == '__main__':
    files = fetch_file_list()
    print(files)
    print(check_tiaozhua('', files))
