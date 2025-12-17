import requests
from .log_h import LogManager
import tempfile
from .functions import *
import shutil

NodeList = [
    {
        "id": "auto",
        "name": "自动选择节点",
        "endpoint": "https://api.zeroasso.top/v2/download/files?file_name={0}",
    },
    {
        "id": "local",
        "name": "零协会镇江节点",
        "endpoint": "https://download.zeroasso.top/files/{0}",
    },
    {
        "id": "cf",
        "name": "CloudFlare CDN(海外)",
        "endpoint": "https://cdn-download.zeroasso.top/files/{0}",
    }
]

APINode = [
    {
        "id": "local_api",
        "name": "零协会官方 API",
        "endpoint": "https://api.zeroasso.top/{0}",
    },
    {
        "id": "cf_api",
        "name": "CloudFlare CDN API(海外)",
        "endpoint": "https://cdn-api.zeroasso.top/{0}",
    }
]

font_url = "https://download.zeroasso.top/files/LLCCN-Font.7z"


def function_llc_main(modal_id, logger_: LogManager, **kwargs):
    logger_.log_modal_process("成功链接后端", modal_id)
    with tempfile.TemporaryDirectory() as temp_dir:
        logger_.log_modal_process("开始下载翻译文件", modal_id)
        logger_.log_modal_status("正在初始化链接", modal_id)

        api_url = [i['endpoint'] for i in APINode if i["id"] == kwargs.get("api_node", "local_api")][0]
        api_version = api_url.format('v2/resource/get_version')
        api_hash = api_url.format("v2/hash/get_hash")
        node_url = [i['endpoint'] for i in NodeList if i["id"] == kwargs.get("file_node", "auto")][0]
        logger_.log(f"api_url {api_url}")
        logger_.log(f"api_version {api_version}")
        logger_.log(f"api_hash {api_hash}")

        logger_.log_modal_process("开始请求元数据", modal_id)
        logger_.log_modal_status("正在请求元数据", modal_id)

        logger_.log("开始请求版本")
        version_ = requests.get(api_version)
        version_.raise_for_status()
        version_ = version_.json()
        if not version_.get("notice") == '本次文本更新没有提示。':
            logger_.log_modal_process(f"本次更新有特殊提示 {version_.get('notice')}", modal_id)
        version = version_.get("version", "unknown")
        logger_.log_modal_process(f"请求到版本 {version}")

        logger_.check_running(modal_id)
        logger_.log(f"开始请求哈希")
        hash_ = requests.get(api_hash)
        hash_.raise_for_status()
        hash_ = hash_.json()
        logger_.log(f"请求到哈希 {str(hash_)}")

        logger_.check_running(modal_id)
        logger_.log_modal_process("元数据请求完毕", modal_id)
        logger_.update_modal_progress(20, "元数据请求完毕", modal_id)

        file_name = f'LimbusLocalize_{version}.7z'
        download_url = node_url.format(file_name)
        save_path_text = f"{temp_dir}/{file_name}"
        logger_.log(f"下载地址生成完毕 {download_url}")

        logger_.log_modal_process("开始下载文本文件", modal_id)
        logger_.log_modal_status("正在下载文本文件", modal_id)

        if not download_with(download_url, save_path_text,
                             chunk_size=1024 * 100, logger_=logger_,
                             modal_id=modal_id, progress_=[20, 40]):
            logger_.log_modal_process("下载文本文件时出现错误", modal_id)
            raise

        logger_.log("文本文件下载完成")
        logger_.log_modal_process("文本文件下载完成")

        save_path_font = f"{temp_dir}/LLCCN-Font.7z"
        logger_.log_modal_process("开始下载字体文件")
        logger_.log_modal_process("正在下载字体文件")

        if not download_with(font_url, save_path_font,
                             chunk_size=1024 * 100, logger_=logger_,
                             modal_id=modal_id, progress_=[40, 70]):
            logger_.log_modal_process("下载字体文件时出现错误", modal_id)
            raise
        
        logger_.log("字体文件下载完成")
        logger_.log_modal_process("字体文件下载完成", modal_id)

        hash_ok_text, hash_ok_font = True, True
        if kwargs.get("check_hash"):
            logger_.log_modal_process("开始哈希校验", modal_id)
            logger_.log_modal_status("哈希校验")

            hash_256_text = calculate_sha256(save_path_text)
            hash_256_font = calculate_sha256(save_path_font)

            if hash_256_text:
                logger_.log(f"文本文件哈希 {hash_256_text}")
                if not hash_256_text == hash_.get("main_hash"):
                    hash_ok_text = False
                    logger_.log("文本文件哈希校验失败")
                    logger_.log_modal_process(
                        f"[warn] 文本文件哈希校验失败,期望值{hash_.get('main_hash')},实际值{hash_256_text}")
            else:
                hash_ok_text = False
                logger_.log("文本文件哈希计算失败")
            
            if hash_256_font:
                logger_.log(f"字体文件哈希 {hash_256_font}")
                if not hash_256_font == hash_.get("font_hash"):
                    hash_ok_font = False
                    logger_.log("字体文件哈希校验失败")
                    logger_.log_modal_process(
                        f"[warn] 字体文件哈希校验失败,期望值{hash_.get('font_hash')},实际值{hash_256_font}")
            else:
                hash_ok_font = False
                logger_.log("字体文件哈希计算失败")
        else:
            logger_.log_modal_process("跳过哈希校验", modal_id)

        logger_.update_modal_progress(75, "哈希校验完成", modal_id)
        logger_.log_modal_status("保存文件")
        if kwargs.get("dump_default"):
            logger_.log("dump_default")
            logger_.log_modal_process("检测到设置：保存原文件")
            shutil.copy2(save_path_text, file_name)
            logger_.log_modal_process("保存文本文件成功")
            shutil.copy2(save_path_font, "LLCCN-Font.7z")
            logger_.log_modal_process("保存字体文件成功")
            
            logger_.update_modal_progress(100, "文件保存完成", modal_id)
            
        else:
            logger_.log("make_zip")
            logger_.log_modal_process("开始解压文件", modal_id)
            logger_.log_modal_status("正在解压文件", modal_id)

            decompress_7z(save_path_text, temp_dir, logger_=logger_)
            logger_.update_modal_progress(80, "成功解压文本文件", modal_id)
            logger_.log_modal_process("成功解压文本文件", modal_id)
            logger_.check_running(modal_id)

            decompress_7z(save_path_font, temp_dir, logger_=logger_)
            logger_.update_modal_progress(90, "成功解压字体文件", modal_id)
            logger_.log_modal_process("成功解压字体文件", modal_id)
            logger_.check_running(modal_id)
            
            logger_.log_modal_status("正在打包文件")
            final_zip_path = f"LimbusLocalize_{version}.zip"
            logger_.log_modal_process("开始重新打包文件", modal_id)
            
            if not zip_folder(f'{temp_dir}\\LimbusCompany_Data\\Lang\\LLC_zh-CN', final_zip_path, logger_=logger_):
                logger_.log_modal_process("打包文件时出现错误", modal_id)
                raise
            
            logger_.update_modal_progress(100, "成功打包文件", modal_id)
            logger_.log_modal_process("成功打包文件", modal_id)
        
        if not hash_ok_text or not hash_ok_font:
            logger_.log_modal_process("操作完成，但存在哈希校验失败的文件，请注意使用风险", modal_id)
            logger_.log_modal_status("操作完成  警告：存在哈希校验失败的文件")
        else:
            logger_.log_modal_status("全部操作完成")
