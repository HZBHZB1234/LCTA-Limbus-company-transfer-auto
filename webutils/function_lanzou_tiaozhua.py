import json
import re
import sys
import tempfile
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
        if version_config.exists() and version and \
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
