from .log_manage import LogManager
import tempfile
from .functions import *
import shutil
from web_function import *
from pathlib import Path
import json

def check_ver_github(from_proxy):
    GithubRequester.update_config(from_proxy)

    return GithubRequester.get_latest_release("LocalizeLimbusCompany",
                                  "LocalizeLimbusCompany").tag_name

def function_llc_main(modal_id, logger_: LogManager, **kwargs):
    logger_.log_modal_process("成功链接后端", modal_id)
    
    # 提前获取常用参数
    from_ = kwargs.get('download_source', 'github')  # 可选值: github, api
    from_proxy = kwargs.get('from_proxy', True)  # 是否使用代理
    zip_type = kwargs.get("zip_type", "zip")
    use_cache = kwargs.get('use_cache', '')
    dump_default = kwargs.get("dump_default", False)
    
    if use_cache and (not os.path.exists(use_cache)):
        raise Exception("缓存文件不存在")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        logger_.log_modal_process("开始下载翻译文件", modal_id)
        logger_.log_modal_status("正在初始化链接", modal_id)
        logger_.log(f'配置信息: {str(kwargs)}')

        # 根据from_参数选择不同的下载源
        if from_ == 'api':
            logger_.log_modal_process("使用API模式下载", modal_id)
            _download_from_api(temp_dir, logger_, modal_id, zip_type, from_proxy, dump_default, use_cache)
        else:
            # 原有的GitHub下载逻辑
            GithubRequester.update_config(use_proxy=from_proxy)
            GithubDownloader = GithubRequester

            logger_.log_modal_process("开始请求版本", modal_id)
            logger_.log_modal_status("正在请求版本", modal_id)

            last_ver = GithubDownloader.get_latest_release(
                "LocalizeLimbusCompany",
                "LocalizeLimbusCompany"
            )
            last_zip = last_ver.get_assets_by_extension(".7z") if zip_type == "seven" else last_ver.get_assets_by_extension(".zip")
            if not last_zip:
                logger_.log_modal_process("未找到合适的版本文件", modal_id)
                raise Exception("未找到合适的版本文件")

            last_zip = last_zip[0]
            logger_.check_running(modal_id)

            logger_.log_modal_process("版本请求完毕", modal_id)
            logger_.update_modal_progress(20, "版本请求完毕", modal_id)

            save_path_text = f"{temp_dir}/{last_zip.name}"
            logger_.log(f"下载地址获取完毕 {last_zip.download_url}")

            logger_.log_modal_process("开始下载文本文件", modal_id)
            logger_.log_modal_status("正在下载文本文件", modal_id)

            if not download_with(
                last_zip.download_url, save_path_text,
                chunk_size=1024 * 100, logger_=logger_,
                modal_id=modal_id, progress_=[20, 50]
            ):
                logger_.log_modal_process("下载文本文件时出现错误", modal_id)
                raise

            logger_.log("文本文件下载完成")
            logger_.log_modal_process("文本文件下载完成")

            font_url = "https://raw.githubusercontent.com/LocalizeLimbusCompany/LocalizeLimbusCompany/refs/heads/main/Fonts/LLCCN-Font.7z"
            save_path_font = f"{temp_dir}/LLCCN-Font.7z"
            
            if not use_cache:
                if from_proxy:
                    font_url = "https://gh-proxy.org/" + font_url
                
                logger_.log_modal_process("开始下载字体文件", modal_id)
                logger_.log_modal_status("正在下载字体文件", modal_id)

                if not download_with(
                    font_url, save_path_font,
                    chunk_size=1024 * 100, logger_=logger_,
                    modal_id=modal_id, progress_=[50, 70]
                ):
                    logger_.log_modal_process("下载字体文件时出现错误", modal_id)
                    raise
                
                logger_.log("字体文件下载完成")
                logger_.log_modal_process("字体文件下载完成", modal_id)
            
            logger_.log_modal_status("保存文件", modal_id)
            
            if dump_default:
                logger_.log("dump_default")
                logger_.log_modal_process("检测到设置：保存原文件", modal_id)
                shutil.copy2(save_path_text, last_zip.name)
                logger_.log_modal_process("保存文本文件成功", modal_id)
                
                if not use_cache:
                    shutil.copy2(save_path_font, "LLCCN-Font.7z")
                    logger_.log_modal_process("保存字体文件成功", modal_id)
                
                logger_.update_modal_progress(100, "文件保存完成", modal_id)
            else:
                logger_.log("make_zip")
                logger_.log_modal_process("开始解压文件", modal_id)
                logger_.log_modal_status("正在解压文件", modal_id)

                decompress_by_extension(save_path_text, temp_dir, logger_=logger_)
                logger_.update_modal_progress(80, "成功解压文本文件", modal_id)
                logger_.log_modal_process("成功解压文本文件", modal_id)
                logger_.check_running(modal_id)

                if not use_cache:
                    decompress_by_extension(save_path_font, temp_dir, logger_=logger_)
                    logger_.update_modal_progress(90, "成功解压字体文件", modal_id)
                    logger_.log_modal_process("成功解压字体文件", modal_id)
                    logger_.check_running(modal_id)
                else:
                    cache_path = f"{temp_dir}\\LimbusCompany_Data\\lang\\LLC_zh-CN\\Font\\Context"
                    if not os.path.exists(cache_path):
                        os.makedirs(cache_path)
                    cache_path = f"{cache_path}\\{Path(use_cache).name}"
                    shutil.copy2(use_cache, cache_path)
                
                logger_.log_modal_status("正在打包文件", modal_id)
                final_zip_path = last_zip.name.replace(".7z", ".zip")
                logger_.log_modal_process("开始重新打包文件", modal_id)
                
                lang_path = f'{temp_dir}\\LimbusCompany_Data\\Lang\\LLC_zh-CN'
                if not zip_folder(lang_path, final_zip_path, logger_=logger_):
                    logger_.log_modal_process("打包文件时出现错误", modal_id)
                    raise
                
                logger_.update_modal_progress(100, "成功打包文件", modal_id)
                logger_.log_modal_process("成功打包文件", modal_id)
                logger_.log_modal_status("全部操作完成", modal_id)
                return final_zip_path

        logger_.log_modal_status("全部操作完成", modal_id)


def _download_from_api(temp_dir, logger_: LogManager, modal_id, zip_type, from_proxy, dump_default, use_cache):
    """使用API下载文件"""
    # 初始化Note对象并获取API数据
    note_ = Note(address="062d22d6ecb233d1", pwd="AutoTranslate", read_only=True)
    note_.fetch_note_info()
    
    try:
        api_data = json.loads(note_.note_content)
    except json.JSONDecodeError:
        logger_.log_modal_process("API数据解析失败", modal_id)
        raise Exception("API数据解析失败")
    
    # 获取相应的下载链接
    if zip_type == "seven":
        download_url = api_data.get('llc_download_mirror', {}).get('seven', {}).get('direct')
    else:
        download_url = api_data.get('llc_download_mirror', {}).get('zip', {}).get('direct')
    
    if not download_url:
        logger_.log_modal_process("未能从API获取有效的下载链接", modal_id)
        raise Exception("未能从API获取有效的下载链接")
    
    logger_.log_modal_process("开始请求版本", modal_id)
    logger_.log_modal_status("正在请求版本", modal_id)
    
    version = api_data.get('llc_version', 'unknown')
    logger_.check_running(modal_id)
    logger_.log_modal_process(f"版本请求完毕: {version}", modal_id)
    logger_.update_modal_progress(20, "版本请求完毕", modal_id)
    
    # 确定文件名
    file_name = f"LimbusLocalize_{version}.7z" if zip_type == "seven" else f"LimbusLocalize_{version}.zip"
    save_path_text = f"{temp_dir}/{file_name}"
    logger_.log(f"下载地址获取完毕 {download_url}")

    logger_.log_modal_process("开始下载文本文件", modal_id)
    logger_.log_modal_status("正在下载文本文件", modal_id)

    if not download_with(
        download_url, save_path_text,
        chunk_size=1024 * 100, logger_=logger_,
        modal_id=modal_id, progress_=[20, 50]
    ):
        logger_.log_modal_process("下载文本文件时出现错误", modal_id)
        raise

    logger_.log("文本文件下载完成")
    logger_.log_modal_process("文本文件下载完成")

    font_url = "https://raw.githubusercontent.com/LocalizeLimbusCompany/LocalizeLimbusCompany/refs/heads/main/Fonts/LLCCN-Font.7z"
    save_path_font = f"{temp_dir}/LLCCN-Font.7z"
    
    if not use_cache:
        if from_proxy:
            font_url = "https://gh-proxy.org/" + font_url
        
        logger_.log_modal_process("开始下载字体文件", modal_id)
        logger_.log_modal_status("正在下载字体文件", modal_id)

        if not download_with(
            font_url, save_path_font,
            chunk_size=1024 * 100, logger_=logger_,
            modal_id=modal_id, progress_=[50, 70]
        ):
            logger_.log_modal_process("下载字体文件时出现错误", modal_id)
            raise
        
        logger_.log("字体文件下载完成")
        logger_.log_modal_process("字体文件下载完成", modal_id)
    
    logger_.log_modal_status("保存文件", modal_id)
    
    if dump_default:
        logger_.log("dump_default")
        logger_.log_modal_process("检测到设置：保存原文件", modal_id)
        shutil.copy2(save_path_text, file_name)
        logger_.log_modal_process("保存文本文件成功", modal_id)
        
        if not use_cache:
            shutil.copy2(save_path_font, "LLCCN-Font.7z")
            logger_.log_modal_process("保存字体文件成功", modal_id)
        
        logger_.update_modal_progress(100, "文件保存完成", modal_id)
    else:
        logger_.log("make_zip")
        logger_.log_modal_process("开始解压文件", modal_id)
        logger_.log_modal_status("正在解压文件", modal_id)

        decompress_by_extension(save_path_text, temp_dir, logger_=logger_)
        logger_.update_modal_progress(80, "成功解压文本文件", modal_id)
        logger_.log_modal_process("成功解压文本文件", modal_id)
        logger_.check_running(modal_id)

        if not use_cache:
            decompress_by_extension(save_path_font, temp_dir, logger_=logger_)
            logger_.update_modal_progress(90, "成功解压字体文件", modal_id)
            logger_.log_modal_process("成功解压字体文件", modal_id)
            logger_.check_running(modal_id)
        else:
            cache_path = f"{temp_dir}\\LimbusCompany_Data\\lang\\LLC_zh-CN\\Font\\Context"
            if not os.path.exists(cache_path):
                os.makedirs(cache_path)
            cache_path = f"{cache_path}\\{Path(use_cache).name}"
            shutil.copy2(use_cache, cache_path)
        
        logger_.log_modal_status("正在打包文件", modal_id)
        final_zip_path = file_name.replace(".7z", ".zip")
        logger_.log_modal_process("开始重新打包文件", modal_id)
        
        lang_path = f'{temp_dir}\\LimbusCompany_Data\\Lang\\LLC_zh-CN'
        if not zip_folder(lang_path, final_zip_path, logger_=logger_):
            logger_.log_modal_process("打包文件时出现错误", modal_id)
            raise
        
        logger_.update_modal_progress(100, "成功打包文件", modal_id)
        logger_.log_modal_process("成功打包文件", modal_id)
        logger_.log_modal_status("全部操作完成", modal_id)
        return final_zip_path