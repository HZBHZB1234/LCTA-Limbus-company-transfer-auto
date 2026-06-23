import requests
from globalManagers.LogManager import LogManager
_log_manager = LogManager()
import tempfile
from .functions import *
import shutil
import json
import base64
import os
from webFunc import Note

def check_ver_ourplay():
    headers = {
        'device-user': make_device(),
        'traceparent': '00-6ab78dbd83864f7c9d9315a590765cdd-83864f7c9d9315a5-00',
        'tracestate': 'ODM4NjRmN2M5ZDkzMTVhNQ==',
        'Accept': 'application/json, text/json, text/x-json, text/javascript, application/xml, text/xml',
        'User-Agent': 'RestSharp/108.0.2.0',
        'Content-Type': 'application/json'
    }
    
    url = 'https://api-pc.ourplay.com.cn/pcapi/ourplay_pc/game/zh/file'
    data = {"gameid": 126447, "language_type": "chinese", "language_ver": 0}
    data_json = json.dumps(data)
    
    _log_manager.log("正在请求 OurPlay 汉化包信息")
    
    r = requests.post(url, headers=headers, data=data_json)
    r.raise_for_status()
    response_data = r.json()

    return response_data['data']['versionCode']

def make_device():
    """
    生成 OurPlay 设备信息
    """
    device = {
        "vc": 929331944,
        "vn": "2.3.9293.31944",
        "chid": 910005,
        "subchid": 1,
        "chidname": "910005",
        "scchidname": "1",
        "rid": 0,
        "product": "910005",
        "productId": 68,
        "ochid": "910005",
        "mac": "00:00:00:00:00:00",
        "deviceId": "102025070000000000",
        "apiPublicFlag": "12",
        "ab_info": ["BJ-1", "BK-1", "BL-1", "BM-0", "BX-3"],
        "pkg": "OPPC",
        "aid": "102025070000000000",
        "deviceCreatTime": 1736770000,
        "userRegTime": 0,
        "ip": None,
        "nuser_id": "1000682520000000000",
        "nuserid_is_new": "老用户",
        "nuserid_activation_date": "2025-01-01 12:00:00",
        "nuserid_channel": "910005",
        "nuserid_sub_channel": "1",
        "nuserid_ad_sub_channel": None,
        "appHash": "334e130a2d7db01b5846348bb8c859d1"
    }
    device_str = json.dumps(device)
    base64_device = base64.b64encode(device_str.encode('utf-8')).decode('utf-8')
    return base64_device

def download_ourplay():
    """
    从 OurPlay 下载汉化包信息
    """
    headers = {
        'device-user': make_device(),
        'traceparent': '00-6ab78dbd83864f7c9d9315a590765cdd-83864f7c9d9315a5-00',
        'tracestate': 'ODM4NjRmN2M5ZDkzMTVhNQ==',
        'Accept': 'application/json, text/json, text/x-json, text/javascript, application/xml, text/xml',
        'User-Agent': 'RestSharp/108.0.2.0',
        'Content-Type': 'application/json'
    }
    
    url = 'https://api-pc.ourplay.com.cn/pcapi/ourplay_pc/game/zh/file'
    data = {"gameid": 126447, "language_type": "chinese", "language_ver": 0}
    data_json = json.dumps(data)
    
    _log_manager.log("正在请求 OurPlay 汉化包信息")
    
    r = requests.post(url, headers=headers, data=data_json)
    r.raise_for_status()
    response_data = r.json()
    
    _log_manager.log(f"OurPlay 响应: {str(response_data)}")
    
    if response_data['code'] != 1:
        _log_manager.log("OurPlay 请求失败")
        return None
        
    download_url = response_data['data']['url']
    md5 = response_data['data']['md5']
    size = response_data['data']['size']
    
    _log_manager.log(f"OurPlay 下载信息: URL={download_url}, MD5={md5}, Size={size}")
        
    return download_url, md5, size


def _process_ourplay_package(temp_dir, modal_id, font_option, cache_path, hash_ok=True):
    """处理已下载的 OurPlay 汉化包：解压、字体处理、重新打包"""
    _log_manager.check_running(modal_id)
    _log_manager.log_modal_process("开始处理文件", modal_id)
    _log_manager.log_modal_status("正在处理文件", modal_id)

    _log_manager.log("正在解压文件...")
    save_path = f"{temp_dir}/transfile.zip"
    with zipfile.ZipFile(save_path, 'r') as zip_file:
        zip_file.extractall(f'{temp_dir}\\')

    _log_manager.check_running(modal_id)
    _log_manager.log("正在格式化文件...")

    if font_option == "simplify" or font_option == "llc":
        shutil.rmtree(f'{temp_dir}\\com.ProjectMoon.LimbusCompany\\Lang\\OurPlayHanHua\\Font\\Title')
        os.makedirs(f'{temp_dir}\\com.ProjectMoon.LimbusCompany\\Lang\\OurPlayHanHua\\Font\\Title')
        _log_manager.log("已精简字体")

    if font_option == "llc":
        _log_manager.log("使用缓存字体...")
        if not(cache_path and os.path.exists(cache_path)):
            raise Exception("缓存文件不存在")
        os.remove(f'{temp_dir}\\com.ProjectMoon.LimbusCompany\\Lang\\OurPlayHanHua\\Font\\Context\\ChineseFont.ttf')
        shutil.copy2(cache_path,
                    f'{temp_dir}\\com.ProjectMoon.LimbusCompany\\Lang\\OurPlayHanHua\\Font\\Context\\ChineseFont.ttf')
        _log_manager.log("已替换为缓存字体")

    _log_manager.log("正在压缩文件...")
    if not zip_folder(f'{temp_dir}\\com.ProjectMoon.LimbusCompany\\Lang\\OurPlayHanHua', 'ourplay.zip'):
        _log_manager.log_modal_process("处理文件时出现错误", modal_id)
        raise

    _log_manager.log('格式化完成')
    _log_manager.log_modal_process("文件处理完成", modal_id)
    _log_manager.update_modal_progress(100, "操作完成", modal_id)

    if not hash_ok:
        _log_manager.log_modal_process("操作完成，但存在哈希校验失败的文件，请注意使用风险", modal_id)
        _log_manager.log_modal_status("操作完成  警告：存在哈希校验失败的文件")
    else:
        _log_manager.log_modal_status("全部操作完成")


def function_ourplay_main(modal_id, **kwargs):
    """
    OurPlay 下载主函数
    """
    _log_manager.log_modal_process("成功链接后端", modal_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        _log_manager.log_modal_process("开始下载 OurPlay 汉化包", modal_id)
        _log_manager.log_modal_status("正在初始化链接", modal_id)

        # 获取下载信息
        download_info = download_ourplay()
        if not download_info:
            _log_manager.log_modal_process("获取 OurPlay 下载信息失败", modal_id)
            raise

        url, expected_md5, size = download_info
        save_path = f"{temp_dir}/transfile.zip"

        _log_manager.log(f"OurPlay 下载地址: {url}")
        _log_manager.check_running(modal_id)
        _log_manager.log_modal_process("开始下载汉化包", modal_id)
        _log_manager.log_modal_status("正在下载汉化包", modal_id)

        # 下载文件
        if not download_with(url, save_path, size=size, chunk_size=1024*100,
                            modal_id=modal_id, progress_=[0, 50]):
            _log_manager.log_modal_process("下载 OurPlay 汉化包时出现错误", modal_id)
            raise

        _log_manager.log("OurPlay 汉化包下载完成")
        _log_manager.log_modal_process("OurPlay 汉化包下载完成", modal_id)
        _log_manager.update_modal_progress(50, "下载完成", modal_id)

        # 验证 MD5
        hash_ok = True
        if kwargs.get("check_hash"):
            _log_manager.log_modal_process("正在验证文件完整性", modal_id)
            _log_manager.log_modal_status("正在验证文件", modal_id)

            actual_md5 = calculate_md5(save_path)
            if not actual_md5:
                _log_manager.log_modal_process("计算文件 MD5 失败", modal_id)
                hash_ok = False
            elif actual_md5 != expected_md5:
                hash_ok = False
                _log_manager.log_modal_process(f"文件校验失败，期望值: {expected_md5}, 实际值: {actual_md5}", modal_id)
            else:
                _log_manager.log_modal_process("文件校验通过", modal_id)
            _log_manager.update_modal_progress(60, "文件校验完成", modal_id)
        else:
            _log_manager.log_modal_process("跳过文件校验", modal_id)
            _log_manager.update_modal_progress(60, "跳过文件校验", modal_id)

        _process_ourplay_package(
            temp_dir, modal_id,
            kwargs.get("font_option", "keep"),
            kwargs.get('cache_path', ""),
            hash_ok
        )
            
def function_ourplay_api(modal_id, **kwargs):
    """
    OurPlay API 下载函数
    """
    _log_manager.log_modal_process("成功链接后端", modal_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        _log_manager.log_modal_process("开始下载 OurPlay 汉化包", modal_id)
        _log_manager.log_modal_status("正在初始化链接", modal_id)

        note_ = Note(address="1df3ff8fe2ff2e4c", pwd="AutoTranslate", read_only=True)
        note_.fetch_note_info()
        url = json.loads(note_.note_content).get("ourplay_download_url")
        save_path = f"{temp_dir}/transfile.zip"

        _log_manager.log(f"OurPlay 下载地址: {url}")
        _log_manager.check_running(modal_id)
        _log_manager.log_modal_process("开始下载汉化包", modal_id)
        _log_manager.log_modal_status("正在下载汉化包", modal_id)

        # 下载文件
        if not download_with(url, save_path, chunk_size=1024*100,
                            modal_id=modal_id, progress_=[0, 50]):
            _log_manager.log_modal_process("下载 OurPlay 汉化包时出现错误", modal_id)
            raise

        _log_manager.log("OurPlay 汉化包下载完成")
        _log_manager.log_modal_process("OurPlay 汉化包下载完成", modal_id)
        _log_manager.update_modal_progress(50, "下载完成", modal_id)

        _log_manager.log_modal_process("跳过文件校验", modal_id)
        _log_manager.update_modal_progress(60, "跳过文件校验", modal_id)

        _process_ourplay_package(
            temp_dir, modal_id,
            kwargs.get("font_option", "keep"),
            kwargs.get('cache_path', "")
        )