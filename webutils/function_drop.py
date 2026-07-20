from pathlib import Path
import os

import shutil
import tempfile
import json
import zipfile

from .function_install import install_translation_package
from .function_manage import get_mod_path
from .functions import extract_zip_smartly, decompress_7z
from .update import Updater
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
}

def evalZip(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        namelist = zip_ref.namelist()
        notJson = [name for name in namelist if '.json' not in name]
        amount = len(namelist)
        notJsonAmount = len(notJson)
        hasFont = any('Font' in name for name in notJson)

        top_names = set()
        for name in namelist:
            clean = name.replace('\\', '/').rstrip('/')
            top = clean.split('/')[0]
            if top:
                top_names.add(top)
        if all(any(folder in top for top in top_names) for folder in FOLDERLIST) and amount > 1500:
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
    items = os.listdir(folder_path)
    hasFont = any('Font' in item for item in items)
    if all(any(folder in item for item in items) for folder in FOLDERLIST):
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
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
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
                "installed": 0, "modded": 0, "skipped": 0, "errors": 0,
                "error_details": []}

    game_path = ConfigManager().get('game_path', '')
    mod_path = get_mod_path()
    os.makedirs(mod_path, exist_ok=True)

    total = len(files_data)
    results = {"installed": 0, "modded": 0, "skipped": 0, "updated": 0, "errors": 0}
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
                        items = os.listdir(tmp_dir)
                        if not items:
                            raise RuntimeError(f"7z文件为空: {file_name}")
                        package_dir = os.path.join(tmp_dir, items[0])
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

                target_name = (Path(file_path).stem
                               if file_path.endswith('.zip')
                               else Path(file_path).name)
                target_path = os.path.join(str(mod_path), target_name)

                # 覆盖前删除已有目标 (遵循项目惯例)
                if os.path.exists(target_path):
                    if os.path.isdir(target_path):
                        shutil.rmtree(target_path)
                    else:
                        os.remove(target_path)

                if file_path.endswith('.zip'):
                    extract_zip_smartly(file_path, str(mod_path))
                else:
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
                    target_name = Path(file_path).stem
                    target_path = os.path.join(str(mod_path), target_name)
                    if os.path.exists(target_path):
                        if os.path.isdir(target_path):
                            shutil.rmtree(target_path)
                        else:
                            os.remove(target_path)
                    extract_zip_smartly(file_path, str(mod_path))
                else:
                    target_name = Path(file_path).name
                    target_path = os.path.join(str(mod_path), target_name)
                    if os.path.exists(target_path) and os.path.isdir(target_path):
                        shutil.rmtree(target_path)
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
        "skipped": results["skipped"],
        "errors": results["errors"],
        "error_details": error_details if error_details else []
    }

if __name__ == '__main__':
    evalZip(r'E:\desktop\limbus transfer\LCTA-Limbus-company-transfer-auto\LimbusLocalize_2026032001.zip')