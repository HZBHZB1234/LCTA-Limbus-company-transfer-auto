from pathlib import Path
import os

import shutil
import tempfile
import json
import zipfile

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

def evalZip(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        namelist = zip_ref.namelist()
        notJson = [name for name in namelist if '.json' not in name]
        amount = len(namelist)
        notJsonAmount = len(notJson)
        hasFont = any('Font' in name for name in notJson)

        top_names, pkg_names = _zip_top_items(namelist)
        if _is_full_pkg_items(pkg_names) and amount > 1500:
            if hasFont:
                return 'full'
            return 'nofont'
        if any('mod_info.json' in name for name in namelist):
            return 'FLmod'
        if any('requirements.txt' in name for name in notJson) and any('start_webui.py' in name for name in notJson):
            return 'update'
        if notJsonAmount >= 3:
            return 'jsononly'
        return 'invalid'
        
def evalFolder(folder_path):
    root = _unwrap_dir(folder_path)
    items = os.listdir(folder_path)
    root_items = items if root == folder_path else os.listdir(root)

    hasFont = any('Font' in item for item in root_items)
    if _is_full_pkg_items(root_items):
        if hasFont:
            return 'full'
        return 'nofont'
    if 'mod_info.json' in items:
        return 'FLmod'
    if len(items) >= 3:
        return 'jsononly'

    return 'invalid'

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
        if is_bus_ruleset(data) or is_tiaozhua_config(data):
            return 'busimport'
        if 'dataList' in data:
            return 'textFile'
        if 'patches' in data:
            return 'LCTAchange'
        if isinstance(data, dict) and all('dataList' in i for i in data.values()):
            return 'FLchange'
        return 'invalid'
    except Exception as e:
        _log_manager.log_error(e)
        return 'invalid'
        
def evalFile(file_path):
    if Path(file_path).is_dir():
        return evalFolder(file_path)
    if file_path.endswith('.zip'):
        return evalZip(file_path)
    if file_path.endswith('.7z'):
        return eval7zip(file_path)[0]
    if file_path.endswith('.json'):
        return evalJson(file_path)
    if file_path.endswith('.carra2'):
        return 'carra'
    if file_path.endswith('.bank'):
        return 'bank'
    return 'invalid'

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

def evalFiles(files_data, modal_id="false"):
    """处理拖入的文件，根据检测到的类型执行相应的安装操作

    Args:
        files_data: dict, {file_path: type_string}, 由 handle_dropped_files 生成
        modal_id: 进度模态窗口 ID

    Returns:
        dict: {"success": bool, "message": str, "installed": int,
               "modded": int, "updated": int, "skipped": int, "errors": int,
               "error_details": list}
    """
    if not files_data:
        _log_manager.log_modal_process("没有需要处理的文件", modal_id)
        return {"success": True, "message": "没有需要处理的文件",
                "installed": 0, "modded": 0, "imported": 0, "skipped": 0, "errors": 0,
                "error_details": []}

    game_path = ConfigManager().get('game_path', '')
    mod_path = get_mod_path()
    os.makedirs(mod_path, exist_ok=True)

    total = len(files_data)
    results = {"installed": 0, "modded": 0, "imported": 0, "skipped": 0, "updated": 0, "errors": 0}
    error_details = []

    for idx, (file_path, file_type) in enumerate(files_data.items()):
        # 检查取消 — CancelRunning 会向上传播
        _log_manager.check_running(modal_id)

        file_name = Path(file_path).name
        progress_pct = int((idx / total) * 100)

        # 检查文件是否仍然存在
        if not os.path.exists(file_path):
            _log_manager.log_modal_process(f"文件不存在，跳过: {file_name}", modal_id)
            results["skipped"] += 1
            continue

        try:
            if file_type in ('full', 'nofont'):
                _log_manager.log_modal_process(f"正在安装汉化包: {file_name}", modal_id)
                _log_manager.update_modal_progress(
                    progress_pct,
                    f"安装汉化包 ({idx+1}/{total}): {file_name}",
                    modal_id)

                if not game_path:
                    raise ValueError("未设置游戏路径，无法安装汉化包")

                if file_path.endswith('.7z'):
                    tmp_dir = tempfile.mkdtemp()
                    try:
                        _log_manager.log_modal_process(f"正在解压7z文件: {file_name}", modal_id)
                        if not decompress_7z(file_path, tmp_dir):
                            raise RuntimeError(f"7z解压失败: {file_name}")
                        package_dirs = _collect_package_dirs(tmp_dir)
                        if not package_dirs:
                            raise RuntimeError(f"7z解压后未找到有效的汉化包目录: {file_name}")
                        for package_dir in package_dirs:
                            install_translation_package(
                                package_dir, game_path, modal_id=modal_id)
                    finally:
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                else:
                    install_translation_package(
                        file_path, game_path, modal_id=modal_id)

                results["installed"] += 1
                _log_manager.log_modal_process(f"汉化包安装完成: {file_name}", modal_id)

            elif file_type == 'FLmod':
                _log_manager.log_modal_process(f"正在安装模组: {file_name}", modal_id)
                _log_manager.update_modal_progress(
                    progress_pct,
                    f"安装模组 ({idx+1}/{total}): {file_name}",
                    modal_id)

                if file_path.endswith('.zip'):
                    target_name = _zip_extract_root(file_path)
                    if target_name:
                        # 覆盖前删除已有目标，与实际解压位置保持一致 (遵循项目惯例)
                        _remove_existing(safe_join_path(str(mod_path), target_name))
                    extract_zip_smartly(file_path, str(mod_path))
                else:
                    target_path = safe_join_path(str(mod_path), Path(file_path).name)
                    _remove_existing(target_path)
                    shutil.copytree(file_path, target_path)

                results["modded"] += 1
                _log_manager.log_modal_process(f"模组安装完成: {file_name}", modal_id)

            elif file_type in ('carra', 'bank'):
                label = NAMEREFER.get(file_type, file_type)
                _log_manager.log_modal_process(f"正在安装{label}: {file_name}", modal_id)
                _log_manager.update_modal_progress(
                    progress_pct,
                    f"安装{label} ({idx+1}/{total}): {file_name}",
                    modal_id)

                target_path = os.path.join(str(mod_path), file_name)
                if os.path.exists(target_path):
                    os.remove(target_path)
                shutil.copy2(file_path, str(mod_path))

                results["modded"] += 1
                _log_manager.log_modal_process(f"{label}安装完成: {file_name}", modal_id)

            elif file_type == 'jsononly':
                _log_manager.log_modal_process(f"正在安装文本替换包: {file_name}", modal_id)
                _log_manager.update_modal_progress(
                    progress_pct,
                    f"安装文本替换包 ({idx+1}/{total}): {file_name}",
                    modal_id)

                if file_path.endswith('.zip'):
                    target_name = _zip_extract_root(file_path)
                    if target_name:
                        _remove_existing(safe_join_path(str(mod_path), target_name))
                    extract_zip_smartly(file_path, str(mod_path))
                else:
                    target_path = safe_join_path(str(mod_path), Path(file_path).name)
                    _remove_existing(target_path)
                    shutil.copytree(file_path, target_path)

                results["modded"] += 1
                _log_manager.log_modal_process(f"文本替换包安装完成: {file_name}", modal_id)

            elif file_type in ('textFile', 'LCTAchange', 'FLchange'):
                label = NAMEREFER.get(file_type, file_type)
                _log_manager.log_modal_process(f"正在安装{label}: {file_name}", modal_id)
                _log_manager.update_modal_progress(
                    progress_pct,
                    f"安装{label} ({idx+1}/{total}): {file_name}",
                    modal_id)

                target_path = os.path.join(str(mod_path), file_name)
                if os.path.exists(target_path):
                    os.remove(target_path)
                shutil.copy2(file_path, str(mod_path))

                results["modded"] += 1
                _log_manager.log_modal_process(f"{label}安装完成: {file_name}", modal_id)

            elif file_type == 'busimport':
                _log_manager.log_modal_process(f"正在导入巴士规则: {file_name}", modal_id)
                imported = import_bus_rules_file(file_path)
                results["imported"] += 1
                stats = imported["stats"]
                _log_manager.log_modal_process(
                    f"规则导入完成: {imported['ruleset_name']}，"
                    f"{stats['converted_rules']} 条规则/{stats.get('converted_actions', 0)} 个操作",
                    modal_id,
                )

            elif file_type == 'invalid':
                _log_manager.log_modal_process(f"跳过无效文件: {file_name}", modal_id)
                results["skipped"] += 1

            elif file_type == 'update':
                _log_manager.log_modal_process(f"正在安装更新包: {file_name}", modal_id)
                _log_manager.update_modal_progress(
                    progress_pct,
                    f"安装更新包 ({idx+1}/{total}): {file_name}",
                    modal_id)

                tmp_dir = tempfile.mkdtemp()
                try:
                    _validate_zip_members(file_path)
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        zf.extractall(tmp_dir)

                    source_dir = tmp_dir
                    for item in os.listdir(tmp_dir):
                        item_path = os.path.join(tmp_dir, item)
                        if os.path.isdir(item_path) and \
                           os.path.exists(os.path.join(item_path, 'start_webui.py')) and \
                           os.path.exists(os.path.join(item_path, 'requirements.txt')):
                            source_dir = item_path
                            break

                    cfg = ConfigManager()
                    updater = Updater(
                        "HZBHZB1234", "LCTA-Limbus-company-transfer-auto",
                        delete_old_files=cfg.get("delete_updating", True),
                        use_proxy=cfg.get("update_use_proxy", True),
                        only_stable=cfg.get("update_only_stable", False),
                        modal_id=modal_id
                    )

                    source_path = Path(source_dir)
                    updater.install_requirements(source_path)
                    _log_manager.check_running(modal_id)
                    if not updater.update_files(source_path):
                        raise RuntimeError("更新文件失败")
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

                results["updated"] += 1
                _log_manager.log_modal_process(
                    f"更新包安装完成，请手动重启程序: {file_name}", modal_id)

            else:
                _log_manager.log_modal_process(
                    f"未知文件类型 '{file_type}'，跳过: {file_name}", modal_id)
                results["skipped"] += 1

        except Exception as e:
            error_msg = f"处理文件 '{file_name}' 时出错: {str(e)}"
            _log_manager.log_modal_process(error_msg, modal_id)
            _log_manager.log_error(e)
            results["errors"] += 1
            error_details.append({"file": file_name, "error": str(e)})

    # 构建摘要信息
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

    summary = "安装完成: " + ", ".join(parts) if parts else "没有需要安装的文件"

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
        "error_details": error_details if error_details else []
    }

if __name__ == '__main__':
    evalZip(r'E:\desktop\limbus transfer\LCTA-Limbus-company-transfer-auto\LimbusLocalize_2026032001.zip')
