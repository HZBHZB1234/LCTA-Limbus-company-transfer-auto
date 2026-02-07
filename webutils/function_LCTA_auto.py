import json
from .log_manage import LogManager
from webFunc import GithubDownload
from webFunc import Note
from webutils.functions import download_with_github, download_with

def _LCTA_auto_github(modal_id, logger_: LogManager, use_proxy):
    release = GithubDownload.GithubRequester.get_latest_release(
        "HZBHZB1234", "LCTA_auto_update")
    assets = release.get_assets_by_extension(".zip")[0]
    r = download_with_github(assets, assets.name, logger_=logger_,
        modal_id=modal_id, use_proxy=use_proxy)
    if r:
        logger_.log_modal_process("下载完成", modal_id)
        logger_.log_modal_status("下载完成", modal_id)
    else:
        logger_.log_modal_process("下载失败", modal_id)
        logger_.log_modal_status("下载失败", modal_id)
    
def _LCTA_auto_api(modal_id, logger_: LogManager):
    note_ = Note(address="1df3ff8fe2ff2e4c", pwd="AutoTranslate", read_only=True)
    note_.fetch_note_info()
    
    try:
        api_data = json.loads(note_.note_content)
    except json.JSONDecodeError:
        logger_.log_modal_process("API数据解析失败", modal_id)
        raise Exception("API数据解析失败")
    
    # 获取相应的下载链接
    download_url = api_data.get('machine_download_mirror', {}).get('zip', {}).get('direct')
    if not download_url:
        logger_.log_modal_process("未能从API获取有效的下载链接", modal_id)
        raise Exception("未能从API获取有效的下载链接")
    logger_.log_modal_process(f"下载地址获取完毕 {download_url}", modal_id)
    logger_.update_modal_progress(30, "下载地址获取完毕", modal_id)
    
    logger_.log_modal_process("开始下载", modal_id)
    logger_.log_modal_status("正在下载", modal_id)
    
    r = download_with(download_url, 'LCTA_auto.zip', logger_=logger_,
                      modal_id=modal_id, progress_=[30, 100])
    if r:
        logger_.log_modal_process("下载完成", modal_id)
        logger_.log_modal_status("下载完成", modal_id)
    else:
        logger_.log_modal_process("下载失败", modal_id)
        logger_.log_modal_status("下载失败", modal_id)
    

def function_LCTA_auto_main(modal_id, logger_: LogManager, whole_config):
    logger_.log_modal_status("正在初始化", modal_id)
    config = whole_config.get('machine', {})
    use_proxy = config.get('use_proxy', True)
    download_source = config.get('download_source', 'github')
    
    if download_source == 'github':
        _LCTA_auto_github(modal_id, logger_, use_proxy)
    else:
        _LCTA_auto_api(modal_id, logger_)