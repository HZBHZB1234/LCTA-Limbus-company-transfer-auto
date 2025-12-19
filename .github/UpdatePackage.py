import requests
import os
import time
import json
import base64
from datetime import datetime, timedelta

headers={
    'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0',
    'Referer':'https://webnote.cc/',
    'Origin':'https://webnote.cc/',
    'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8',
    'Accept':'application/json, text/javascript, */*; q=0.01',
    'Accept-Encoding':'gzip, deflate, br, zstd',
    'Accept-Language':'en-US,en;q=0.9',
    'Sec-Ch-Ua':'"Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"',
    'Sec-Ch-Ua-Mobile':'?0',
    'Sec-Ch-Ua-Platform':'"Windows"',
    'Sec-Fetch-Dest':'empty',
    'Sec-Fetch-Mode':'cors',
    'Sec-Fetch-Site':'cross-site',
    }
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
            return None
        return response_data.get('data').get('version_code')
    except Exception as e:
        print(f"获取 OurPlay 版本失败: {e}")
        return None

def get_llc():
    """
    从 LLC 获取汉化包信息
    """
    url = 'https://cdn-api.zeroasso.top/v2/resource/get_version'
    print("正在请求 LLC 汉化包信息")
    
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        response_data = r.json()
        return response_data['version']
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

def update_note(note_info, ourplay_version, llc_version, update_ourplay=True, update_llc=True):
    """
    更新笔记内容
    update_ourplay: 是否更新OurPlay版本和时间
    update_llc: 是否更新LLC版本和时间
    """
    now = datetime.now()
    update_time = now.isoformat()
    
    # 获取当前数据
    try:
        current_data = json.loads(note_info['note_content'])
    except (json.JSONDecodeError, KeyError):
        current_data = {}
    
    # 创建或更新数据
    data = {
        'ourplay_version': ourplay_version if update_ourplay else current_data.get('ourplay_version'),
        'llc_version': llc_version if update_llc else current_data.get('llc_version'),
        'ourplay_last_update_time': update_time if update_ourplay else current_data.get('ourplay_last_update_time', '1970-01-01T00:00:00'),
        'llc_last_update_time': update_time if update_llc else current_data.get('llc_last_update_time', '1970-01-01T00:00:00'),
        'last_check_time': update_time,
        'week_boundary': get_current_week_boundary().isoformat()
    }
    
    note_content = json.dumps(data, ensure_ascii=False, indent=2)
    
    save_data = {
        'note_name': ADDRESS, 
        'note_id': note_info['note_id'], 
        'note_content': note_content,
        'note_token': note_info['note_token'], 
        'expire_time': 94608000, 
        'note_pwd': "AutoTranslate"
    }
    
    save_response = requests.post(f'{API_URL}/save', headers=headers, data=save_data)
    save_response.raise_for_status()
    
    print(f"更新成功！更新时间: {update_time}")
    if update_ourplay:
        print(f"OurPlay版本: {ourplay_version}")
    if update_llc:
        print(f"LLC版本: {llc_version}")
    
    return save_response.json()

def main():
    if not ADDRESS:
        print("错误: 未设置 ADDRESS 环境变量")
        exit(1)
    
    print(f"开始检查，ADDRESS: {ADDRESS}")
    
    # 获取现有记录
    fetch_request = requests.post(f'{API_URL}/info',
                                 headers=headers, data={'note_name': ADDRESS, "note_pwd": "AutoTranslate"})
    fetch_request.raise_for_status()
    print(fetch_request.json())
    note_info = fetch_request.json()['data']
    
    if not str(note_info['status']) == '1':
        print("获取笔记信息失败")
        exit(1)
    
    # 获取当前数据
    note_content = note_info['note_content']
    try:
        current_data = json.loads(note_content)
        current_ourplay_version = current_data.get('ourplay_version')
        current_llc_version = current_data.get('llc_version')
        
        # 解析上次更新时间
        try:
            ourplay_last_update = datetime.fromisoformat(current_data.get('ourplay_last_update_time', '1970-01-01T00:00:00'))
        except (ValueError, TypeError):
            ourplay_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
        try:
            llc_last_update = datetime.fromisoformat(current_data.get('llc_last_update_time', '1970-01-01T00:00:00'))
        except (ValueError, TypeError):
            llc_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
            
    except (json.JSONDecodeError, KeyError):
        # 首次运行，初始化数据
        print("首次运行，初始化数据")
        current_ourplay_version = None
        current_llc_version = None
        ourplay_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
        llc_last_update = datetime.fromisoformat('1970-01-01T00:00:00')
        current_data = {}
    
    # 判断是否需要检查OurPlay
    should_check_ourplay_flag = should_check_ourplay(ourplay_last_update)
    # 判断是否需要检查LLC
    should_check_llc_flag = should_check_llc(llc_last_update)
    
    if not should_check_ourplay_flag and not should_check_llc_flag:
        print("OurPlay和LLC本周已有更新，且不在中午12点，跳过检查")
        return
    
    # 获取最新版本
    new_ourplay_version = None
    new_llc_version = None
    
    if should_check_ourplay_flag:
        print("检查OurPlay更新...")
        new_ourplay_version = get_ourplay()
        if new_ourplay_version is None:
            print("获取OurPlay版本失败，使用当前版本")
            new_ourplay_version = current_ourplay_version
    else:
        print("跳过OurPlay检查")
        new_ourplay_version = current_ourplay_version
    
    if should_check_llc_flag:
        print("检查LLC更新...")
        new_llc_version = get_llc()
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
    
    if not need_update_ourplay and not need_update_llc:
        print("版本无变化，仅更新检查时间")
        # 只更新检查时间，不更新版本和时间
        update_note(note_info, new_ourplay_version, new_llc_version, update_ourplay=False, update_llc=False)
    else:
        if need_update_ourplay:
            print(f"OurPlay发现新版本！当前: {current_ourplay_version}, 最新: {new_ourplay_version}")
        if need_update_llc:
            print(f"LLC发现新版本！当前: {current_llc_version}, 最新: {new_llc_version}")
        
        update_note(note_info, new_ourplay_version, new_llc_version, 
                   update_ourplay=need_update_ourplay, update_llc=need_update_llc)

if __name__ == "__main__":
    main()