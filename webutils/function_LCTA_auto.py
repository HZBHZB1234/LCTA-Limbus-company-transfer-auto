import json
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
_log_manager = LogManager()
from webFunc import GithubDownload
from webFunc import Note
from webutils.functions import download_with_github, download_with

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


def function_LCTA_auto_main(modal_id):
    _log_manager.log_modal_status("正在初始化", modal_id)
    config = ConfigManager().get('machine', {})
    use_proxy = config.get('use_proxy', True)
    download_source = config.get('download_source', 'github')
    
    if download_source == 'github':
        result = _LCTA_auto_github(modal_id, use_proxy)
    else:
        result = _LCTA_auto_api(modal_id)

    if result is None:
        raise Exception("下载失败，无法继续翻译流程")
    return result