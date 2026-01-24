import requests
import os
import time
import json
import base64
from datetime import datetime, timedelta
from pathlib import Path
import sys

project_root = Path(os.path.dirname(__file__)).parent
print(project_root)
sys.path.append(project_root.as_posix())

from webFunc import *

ADDRESS = os.getenv("ADDRESS")
API_URL = "https://api.txttool.cn/netcut/note"


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

def get_ourplay():
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
    
    print("正在请求 OurPlay 汉化包信息")
    
    try:
        r = requests.post(url, headers=headers, data=data_json, timeout=10)
        r.raise_for_status()
        response_data = r.json()
        
        print(f"OurPlay 响应: {str(response_data)[:200]}...")  # 截断输出
        if not str(response_data.get('code')) == '1':
            print("响应错误")
            return None, None
        return response_data.get('data').get('versionCode'), response_data.get('data').get('url')
    except Exception as e:
        print(f"获取 OurPlay 版本失败: {e}")
        return None, None

def get_llc():
    """
    从 LLC 获取汉化包信息
    """
    
    try:
        GithubDownloader = GitHubReleaseFetcher(
            False,
            ignore_ssl=True
        )
        last_ver = GithubDownloader.get_latest_release(
            "LocalizeLimbusCompany", "LocalizeLimbusCompany"
        )
        return last_ver.tag_name, last_ver

    except Exception as e:
        print(f"获取 LLC 版本失败: {e}")
        return None

def get_current_week_boundary():
    """
    获取本周四凌晨5点的时间边界
    """
    now = datetime.now()
    # 计算当前周的周四（0=周一, 1=周二, 2=周三, 3=周四...）
    days_since_monday = now.weekday()
    days_to_thursday = (3 - days_since_monday) % 7
    this_thursday = now + timedelta(days=days_to_thursday)
    
    # 设置时间为周四凌晨5点
    this_thursday_5am = this_thursday.replace(hour=5, minute=0, second=0, microsecond=0)
    
    # 如果当前时间已经过了本周四5点，则使用本周四5点
    # 否则使用上周四5点
    if now >= this_thursday_5am:
        return this_thursday_5am
    else:
        last_thursday_5am = this_thursday_5am - timedelta(days=7)
        return last_thursday_5am

def should_check_ourplay(last_update_time):
    """
    判断OurPlay是否需要检查更新
    规则：以每周四凌晨五点为界，如果这周已经有更新，则仅在12点请求一次
    """
    now = datetime.now()
    week_boundary = get_current_week_boundary()
    
    # 如果上次更新是在本周四5点之后，说明本周已经有更新
    if last_update_time >= week_boundary:
        # 只有在中午12点才检查
        return now.hour == 12
    else:
        # 本周还没有更新，可以检查
        return True

def should_check_llc(last_update_time):
    """
    判断LLC是否需要检查更新
    规则：以每周四凌晨五点为界，如果这周已经有更新，则仅在12点请求一次
    """
    now = datetime.now()
    week_boundary = get_current_week_boundary()
    
    # 如果上次更新是在本周四5点之后，说明本周已经有更新
    if last_update_time >= week_boundary:
        # 只有在中午12点才检查
        return now.hour == 12
    else:
        # 本周还没有更新，可以检查
        return True

def should_check_mirror(last_update_time):
    """
    判断LLC镜像是否需要更新
    规则：如果距离上一次更新超过2.5天，则需要更新
    """
    now = datetime.now()
    if now - last_update_time >= timedelta(days=2, hours=12):
        return True
    return False

def main():
    if not ADDRESS:
        print("错误: 未设置 ADDRESS 环境变量")
        exit(1)
    
    print(f"开始检查，ADDRESS: {ADDRESS}")
    
    note_ = Note(address=ADDRESS, pwd="AutoTranslate")
    note_.fetch_note_info()
    try:
        current_data = json.loads(note_.note_content)
        current_ourplay_version = current_data['ourplay_version']
        current_llc_version = current_data['llc_version']
        
        # 解析上次更新时间
        try:
            ourplay_last_update = datetime.fromisoformat(current_data.get('ourplay_last_update_time', '1970-01-01T00:00:00'))
        except (ValueError, TypeError):
            ourplay_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
        try:
            llc_last_update = datetime.fromisoformat(current_data.get('llc_last_update_time', '1970-01-01T00:00:00'))
        except (ValueError, TypeError):
            llc_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
        try:
            llc_mirror_update = datetime.fromisoformat(current_data.get('llc_mirror_update_time', '1970-01-01T00:00:00'))
        except (ValueError, TypeError):
            llc_mirror_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
    except (json.JSONDecodeError, KeyError, TypeError):
        # 首次运行，初始化数据
        print("首次运行，初始化数据")
        current_ourplay_version = None
        current_llc_version = None
        ourplay_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
        llc_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
        llc_mirror_update = datetime.fromisoformat('1970-01-01T00:00:00')
        current_data = {}
    
    # 判断是否需要检查OurPlay
    should_check_ourplay_flag = should_check_ourplay(ourplay_last_update)
    # 判断是否需要检查LLC
    should_check_llc_flag = should_check_llc(llc_last_update)
    # 判断是否需要检查LLC镜像
    should_check_llc_mirror_flag = should_check_mirror(llc_mirror_update)
    
    if not should_check_ourplay_flag and not should_check_llc_flag and not should_check_llc_mirror_flag:
        print("OurPlay和LLC本周已有更新，且不在中午12点，镜像不需要更新，跳过检查")
        return
    
    # 获取最新版本
    new_ourplay_version = None
    new_llc_version = None
    
    if should_check_ourplay_flag:
        print("检查OurPlay更新...")
        new_ourplay_version, download_url = get_ourplay()
        if new_ourplay_version is None:
            print("获取OurPlay版本失败，使用当前版本")
            new_ourplay_version = current_ourplay_version
    else:
        print("跳过OurPlay检查")
        new_ourplay_version = current_ourplay_version
    
    if should_check_llc_flag or should_check_llc_mirror_flag:
        print("检查LLC更新...")
        new_llc_version, last_ver = get_llc()
        if new_llc_version is None:
            print("获取LLC版本失败，使用当前版本")
            new_llc_version = current_llc_version
    else:
        print("跳过LLC检查")
        new_llc_version = current_llc_version
    
    if new_ourplay_version is None and new_llc_version is None:
        print("获取版本信息失败，退出")
        exit(1)
    
    # 检查是否需要更新
    need_update_ourplay = (should_check_ourplay_flag and new_ourplay_version != current_ourplay_version)
    need_update_llc = (should_check_llc_flag and new_llc_version != current_llc_version)
    
    if not need_update_ourplay and not need_update_llc and not should_check_llc_mirror_flag:
        print("版本无变化")
        return
    
    if need_update_llc or should_check_llc_mirror_flag:
        if need_update_llc:print(f"LLC版本更新: {current_llc_version} -> {new_llc_version}")
        seven_zip_asset = last_ver.get_assets_by_extension(".7z")[0]
        zip_asset = last_ver.get_assets_by_extension(".zip")[0]
        new_llc_download_url = {'zip':zip_asset.download_url, 
                                'seven':seven_zip_asset.download_url}
        with open(zip_asset.name, "wb") as f:
            r = requests.get(zip_asset.download_url)
            f.write(r.content)
            
        with open(seven_zip_asset.name, "wb") as f:
            r = requests.get(seven_zip_asset.download_url)
            f.write(r.content)
        
        file_transfer = UpFileClient()
        llc_upload_result = file_transfer.upload(zip_asset.name)
        llc_seven_upload_result = file_transfer.upload(seven_zip_asset.name)
        
        if not llc_upload_result.get('success') or not llc_seven_upload_result.get('success'):
            print("LLC文件上传失败，取消更新")
            return
        new_llc_mirror = {
            'zip': {'direct': llc_upload_result.get('direct_download_url'),
                    'web': llc_upload_result.get('download_url')},
            'seven': {'direct': llc_seven_upload_result.get('direct_download_url'),
                      'web': llc_seven_upload_result.get('download_url')}
        }
        current_data['llc_download_url'] = new_llc_download_url
        current_data['llc_download_mirror'] = new_llc_mirror
        current_data['llc_version'] = new_llc_version
        if need_update_llc:current_data['llc_last_update_time'] = datetime.now().isoformat()
        current_data['llc_mirror_update_time'] = datetime.now().isoformat()
        
    if need_update_ourplay:
        print(f"OurPlay版本更新: {current_ourplay_version} -> {new_ourplay_version}")
        current_data['ourplay_version'] = new_ourplay_version
        current_data['ourplay_download_url'] = download_url
        current_data['ourplay_last_update_time'] = datetime.now().isoformat()
        
    # 提交更新
    note_.update_note_content(json.dumps(current_data, ensure_ascii=False, indent=4))

    print("更新完成")


if __name__ == "__main__":
    main()