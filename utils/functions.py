import requests
import json
from pyunpack import Archive
#import patoolib
import os
import time
import zipfile
import hashlib
import shutil
import py7zr
import base64
log_callback = None

def set_log_callback(callback):
    """设置日志回调函数"""
    global log_callback
    log_callback = callback

def log(message):
    """记录日志，如果有回调函数则使用回调，否则打印到控制台"""
    if log_callback:
        log_callback(message)
    else:
        print(message)
def walk_all_files(path,rel):
    """遍历目录下的所有文件"""
    path_list=[]
    for root, dirs, files in os.walk(path):
        for file_name in files:
            final={
                "dir":root,
                "file":file_name,
                "path":os.path.join(root,file_name),
                "relpath":os.path.relpath(os.path.join(root,file_name),start=rel)
            }
            path_list.append(final)
    return path_list
def make_device():
    device={
        "vc":929331944,
        "vn":"2.3.9293.31944",
        "chid":910005,
        "subchid":1,
        "chidname":"910005",
        "scchidname":"1",
        "rid":0,
        "product":"910005",
        "productId":68,
        "ochid":"910005",
        "mac":"00:00:00:00:00:00",
        "deviceId":"102025070000000000",
        "apiPublicFlag":"12",
        "ab_info":["BJ-1","BK-1","BL-1","BM-0","BX-3"],
        "pkg":"OPPC",
        "aid":"102025070000000000",
        "deviceCreatTime":1736770000,
        "userRegTime":0,
        "ip":None,
        "nuser_id":"1000682520000000000",
        "nuserid_is_new":"老用户",
        "nuserid_activation_date":"2025-01-01 12:00:00",
        "nuserid_channel":"910005",
        "nuserid_sub_channel":"1",
        "nuserid_ad_sub_channel":None,
        "appHash":"334e130a2d7db01b5846348bb8c859d1"
        }
    device_str=json.dumps(device)
    base64_device=base64.b64encode(device_str.encode('utf-8')).decode('utf-8')
    print(base64_device)
    return base64_device
def download_ourplay():
    headers = {
        'device-user': make_device(),
        'traceparent': '00-6ab78dbd83864f7c9d9315a590765cdd-83864f7c9d9315a5-00',
        'tracestate': 'ODM4NjRmN2M5ZDkzMTVhNQ==',
        'Accept': 'application/json, text/json, text/x-json, text/javascript, application/xml, text/xml',
        'User-Agent': 'RestSharp/108.0.2.0',
        'Content-Type': 'application/json'
    }
    url='https://api-pc.ourplay.com.cn/pcapi/ourplay_pc/game/zh/file'
    data={"gameid":126447,"language_type":"chinese","language_ver":0}
    data=json.dumps(data)
    r=requests.post(url,headers=headers,data=data)
    r=r.json()
    log(str(r))
    if r['code']!=1:
        print('ourplay_pc_game_zh_file_error')
        return r
    url=r['data']['url']
    md5=r['data']['md5']
    size=r['data']['size']
    return url,md5,size

def download_and_verify_file(progress_callback=None):
    url, expected_md5,size= download_ourplay()
    local_filename = 'transfile.zip'

    if not download_with(url, local_filename,size,16384, progress_callback):
        return False
    md5=calculate_file_md5(local_filename)
    if md5==expected_md5:
        log("\n文件下载成功")
        return True
    else:
        log("\n文件下载失败")
        return False

def calculate_file_md5(file_path):
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        chunk_size = 4096  # 每次读取的块大小
        while chunk := f.read(chunk_size):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()

def zip_folder(folder_path, output_path):
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(folder_path):
                # 添加空文件夹到zip
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    zipf.write(dir_path, os.path.relpath(dir_path, folder_path))
                # 添加文件到zip
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, os.path.relpath(file_path, folder_path))
    except Exception as e:
        log(f"压缩文件夹失败: {e}")
        return False

def get_true_zip(file_path, font_option="keep"):
    if not os.path.exists(file_path):
        log("文件不存在")
        return False
    try:shutil.rmtree('temp')
    except:pass
    if not os.path.exists('temp'):
        os.mkdir('temp')
    log("正在解压文件...")
    with zipfile.ZipFile(file_path, 'r') as zip_file:
        zip_file.extractall('temp\\') 
    log("正在格式化文件...")
    shutil.move('temp\\com.ProjectMoon.LimbusCompany\\Lang\\LLC_zh-CN','temp\\ourplay\\ourplay')
    if font_option == "llc":
        if not download_font():
            return False
        try:
            shutil.rmtree('temp\\ourplay\\ourplay\\Fonts')
        except:None
        try:
            shutil.move('Font','temp\\ourplay\\ourplay\\Font')
        except:
            log('移动失败')
    elif font_option == "simplify":
        try:
            shutil.rmtree('temp\\ourplay\\ourplay\\Font\\Title')
            os.makedirs('temp\\ourplay\\ourplay\\Font\\Title')
        except:None
    
    log("正在压缩文件...")
    zip_folder('temp\\ourplay', 'ourplay.zip')
    log("正在清理文件...")
    shutil.rmtree('temp')
    try:os.remove('transfile.zip')
    except:pass
    log('格式化完成')

def decompress_7z(file_path,output_dir='.'):
    if not os.path.exists(file_path):
        log(f"压缩文件不存在: {file_path}")
        return False

    if output_dir is None:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_dir = os.path.join(os.getcwd(), base_name)
    
    os.makedirs(output_dir, exist_ok=True)

    try:
        log(f"开始解压文件: {file_path}")
        Archive(file_path).extractall(output_dir)
        log(f"解压完成")
        return True
    except Exception as e:
        log(f"解压失败: {e}")
        return False

def download_with(url, save_path, size=0, chunk_size=1024, progress_callback=None):
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()  # 检查请求是否成功
            
            # 获取文件总大小
            if size == 0:
                total_size = int(r.headers.get('Content-Length', 0))
            else:
                total_size = size
            downloaded_size = 0
            
            log(f"开始下载文件，总大小: {total_size // 1024} KB")
            
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if progress_callback and not progress_callback((downloaded_size / total_size) * 100):
                        log("\n下载已取消")
                        return False
                    
                    downloaded_size += len(chunk)
                    f.write(chunk)
                    
                    # 计算下载进度百分比
                    progress = (downloaded_size / total_size) * 100
                    if progress_callback:
                        progress_callback(progress)
                    #print(f"\r下载进度: {progress:.2f}%", end='', flush=True)
            
            log("\n下载完成")
        return True
    except Exception as e:
        log(f"\n下载失败: {e}")
        try:
            os.remove(save_path)
        except:
            pass
        return False

def download_font(progress_callback=None):
    url='https://download.zeroasso.top/files/LLCCN-Font.7z'
    if not download_with(url,'font.7z', progress_callback=progress_callback):
        return False
    if not decompress_7z('font.7z'):
        return False
    try:
        shutil.move('LimbusCompany_Data\Lang\LLC_zh-CN\Font','Font')
        log('储存字体成功')
    except:
        log('储存字体失败')
        return False
    log('开始删除临时文件')
    try:
        os.remove('font.7z')
    except:
        pass
    try:
        shutil.rmtree('LimbusCompany_Data')
    except:
        pass
    log('删除临时文件成功')

def download_llc(progress_callback=None, convert=True, clean_temp=True):
    url_7z='https://download.zeroasso.top/files/LimbusLocalize_latest.7z'
    url_font='https://download.zeroasso.top/files/LLCCN-Font.7z'
    log('正在下载LLC文本')
    if not download_with(url_7z,'LLC_content.7z', progress_callback=progress_callback):
        return False
    
    if progress_callback:
        progress_callback(33)
    
    log('正在下载LLC字体')
    if not download_with(url_font,'LLC_font.7z', progress_callback=progress_callback):
        return False
    
    if progress_callback:
        progress_callback(66)
    
    log('下载完成')
    
    if not convert:
        return True
        
    log('正在解压LLC文本')
    if not decompress_7z('LLC_content.7z'):
        try:
            shutil.rmtree(r'LimbusCompany_Data')
        except:None
        return False
        
    log('正在解压LLC字体')
    if not decompress_7z('LLC_font.7z'):
        try:
            shutil.rmtree(r'LimbusCompany_Data')
        except:None
        return False
        
    log('解压完成')
    try:
        zip_folder(r'LimbusCompany_Data\Lang\LLC_zh-CN','LLC_ZH.zip')
    except:
        log('压缩失败')
        try:
            shutil.rmtree(r'LimbusCompany_Data')
        except:None
        return False
        
    if clean_temp:
        if not clean_llc_temp():
            return False
            
    return True

def clean_llc_temp():
    log('开始删除临时文件')
    try:
        shutil.rmtree(r'LimbusCompany_Data')
    except:None
    try:
        os.remove('LLC_content.7z')
    except:None
    try:
        os.remove('LLC_font.7z')
    except:None
    log('删除临时文件成功')
    return True

if __name__ == '__main__':
    make_device()