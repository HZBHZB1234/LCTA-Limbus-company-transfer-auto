import json
import os
import shutil
import tempfile
from typing import Optional
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
_log_manager = LogManager()
from webFunc import GithubDownload
from webFunc import Note
from webutils.utils.io import extract_zip_smartly, zip_folder
from webutils.utils.font import get_cache_font
from webutils.utils.net import download_with_github, download_with

def check_ver_github_M(from_proxy):
    GithubDownload.GithubRequester.update_config(from_proxy)

    return GithubDownload.GithubRequester.get_latest_release("HZBHZB1234",
                                  "LCTA_auto_update").tag_name

def _LCTA_auto_github(modal_id, use_proxy) -> str:
    release = GithubDownload.GithubRequester.get_latest_release(
        "HZBHZB1234", "LCTA_auto_update")
    assets = release.get_assets_by_extension(".zip")[0]
    r = download_with_github(assets, assets.name, modal_id=modal_id, use_proxy=use_proxy)
    if r:
        _log_manager.log_modal_process("下载完成", modal_id)
        _log_manager.log_modal_status("下载完成", modal_id)
        return assets.name
    else:
        _log_manager.log_modal_process("下载失败", modal_id)
        _log_manager.log_modal_status("下载失败", modal_id)
        return None

def _LCTA_auto_api(modal_id) -> str:
    note_ = Note(address="1df3ff8fe2ff2e4c", pwd="AutoTranslate", read_only=True)
    note_.fetch_note_info()
    
    try:
        api_data = json.loads(note_.note_content)
    except json.JSONDecodeError:
        _log_manager.log_modal_process("API数据解析失败", modal_id)
        raise Exception("API数据解析失败")
    
    # 获取相应的下载链接
    download_url = api_data.get('machine_download_mirror', {}).get('zip', {}).get('direct')
    if not download_url:
        _log_manager.log_modal_process("未能从API获取有效的下载链接", modal_id)
        raise Exception("未能从API获取有效的下载链接")
    _log_manager.log_modal_process(f"下载地址获取完毕 {download_url}", modal_id)
    _log_manager.update_modal_progress(30, "下载地址获取完毕", modal_id)
    
    _log_manager.log_modal_process("开始下载", modal_id)
    _log_manager.log_modal_status("正在下载", modal_id)
    
    r = download_with(download_url, 'LCTA_auto.zip', modal_id=modal_id, progress_=[30, 100])
    if r:
        _log_manager.log_modal_process("下载完成", modal_id)
        _log_manager.log_modal_status("下载完成", modal_id)
        return 'LCTA_auto.zip'
    else:
        _log_manager.log_modal_process("下载失败", modal_id)
        _log_manager.log_modal_status("下载失败", modal_id)
        return None


def _resolve_font_path(modal_id, temp_dir) -> Optional[str]:
    """获取注入汉化包的中文字体路径：优先缓存字体，缺失时在 temp_dir 内下载 LLC 官方字体。"""
    font = get_cache_font()
    if font and os.path.exists(font):
        return font
    _log_manager.log_modal_process("缓存中无中文字体，正在下载 LLC 官方字体", modal_id)
    from webutils.function_llc import font_assets_seven
    from webutils.utils.io import decompress_by_extension
    font_7z = os.path.join(temp_dir, 'LLCCN-Font.7z')
    if not download_with_github(
            font_assets_seven, font_7z, chunk_size=1024 * 100, modal_id=modal_id):
        _log_manager.log_modal_process("LLC 官方字体下载失败", modal_id)
        return None
    if not decompress_by_extension(font_7z, temp_dir):
        _log_manager.log_modal_process("LLC 官方字体解压失败", modal_id)
        return None
    for root, dirs, files in os.walk(temp_dir):
        for name in files:
            if name.lower().endswith(('.ttf', '.otf')):
                return os.path.join(root, name)
    _log_manager.log_modal_process("未在 LLC 字体包中找到字体文件", modal_id)
    return None


def _inject_font_into_zip(zip_path, font_path, modal_id) -> bool:
    """解压 LCTA-AU 包，注入 Font/Context/ChineseFont.ttf 后原地重新打包。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        extracted = extract_zip_smartly(zip_path, temp_dir)
        if extracted:
            root = os.path.join(temp_dir, extracted)
        else:
            subdirs = [entry for entry in os.listdir(temp_dir)
                       if os.path.isdir(os.path.join(temp_dir, entry))]
            root = os.path.join(temp_dir, subdirs[0]) if len(subdirs) == 1 else temp_dir
        package_root = root
        if not os.path.exists(os.path.join(root, 'BattleAnnouncerDlg')):
            pkg_subdirs = [
                entry for entry in os.listdir(root)
                if os.path.isdir(os.path.join(root, entry))
                and os.path.exists(os.path.join(root, entry, 'BattleAnnouncerDlg'))
            ]
            if len(pkg_subdirs) == 1:
                package_root = os.path.join(root, pkg_subdirs[0])
        font_dir = os.path.join(package_root, 'Font', 'Context')
        os.makedirs(font_dir, exist_ok=True)
        shutil.copy2(font_path, os.path.join(font_dir, 'ChineseFont.ttf'))
        _log_manager.log_modal_process("正在将字体打包进汉化包", modal_id)
        return zip_folder(root, zip_path, modal_id=modal_id)


def function_LCTA_auto_main(modal_id):
    _log_manager.log_modal_status("正在初始化", modal_id)
    config = ConfigManager().get('ui_default.machine', {})
    use_proxy = config.get('use_proxy', True)
    download_source = config.get('download_source', 'github')
    
    if download_source == 'github':
        result = _LCTA_auto_github(modal_id, use_proxy)
    else:
        result = _LCTA_auto_api(modal_id)

    if result is None:
        raise Exception("下载失败，无法继续翻译流程")

    with tempfile.TemporaryDirectory() as temp_dir:
        font_path = _resolve_font_path(modal_id, temp_dir)
        if not font_path:
            raise Exception("未能获取中文字体，无法为 LCTA-AU 汉化包添加 Font 文件夹")
        if not _inject_font_into_zip(result, font_path, modal_id):
            raise Exception("为 LCTA-AU 汉化包注入字体失败")
    _log_manager.log_modal_process("字体注入完成", modal_id)
    return result