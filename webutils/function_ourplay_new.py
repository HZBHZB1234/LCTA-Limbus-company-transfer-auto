import requests
from globalManagers.LogManager import LogManager
_log_manager = LogManager()
import tempfile
from .functions import *
import shutil
import json
import base64
import os
import zipfile
from collections import defaultdict, Counter
from globalManagers.ConfigManager import ConfigManager
from webFunc import Note

def check_ver_ourplay_new(official: bool = True):
    headers = {
        'device-user': make_device(),
        'User-Agent': 'okhttp/3.12.13',
    }
    
    url = 'https://gapi.ourplay.com.cn/depends/zhapk'
    data = {"pkg": "com.ProjectMoon.LimbusCompany", "language_type": "chinese", "language_ver": 0,
            "split": 1, "is_unofficial": 2 if official else 3, "ver": "406"}
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
        "product":"V1824A",
        "mainver":306800,
        "os":"Android",
        "productId":6000,
        "hos_version":"",
        "release":"9",
        "abi":"arm64-v8a",
        "brand_name":"vivo",
        "pkg":"com.excean.gspace",
        "vc":11020,
        "manufacturer":"vivo",
        "apiPublicFlag":110,
        "vn":"8.5.9",
        "model":"V1824A",
        "packageName":"com.excean.gspace",
        "api":28,
        "brand":"vivo",
        "aid":"f219cadbb65e69de",
        "isHOS":0,
        "ab_info":["PE-1","OC-2","PG-0","PF-1"],
        "all_ab_info":["PE-1","OC-2","PG-0","PF-1"],
        "abTest":"62",
        "ssid":"1733610978679124900",
        "deviceId":"7645707876178117133",
        "userArea":330000,
        "userId":"2026-4908897",
        "guestid":61875446,
        "vip":0,
        "cdpTags":"",
        "gmp_tags":[""],
        "customizationAd":1,
        "customizationGame":1,
        "customizationPush":1,
        "uqid":"67511305",
        "cqid":"f219de4761vtz42mvosy",
        "first_channel":"610035",
        "first_sub_channel":"109",
        "last_channel":"610035",
        "last_sub_channel":"109",
        "now_channel":"610035",
        "now_sub_channel":"99",
        "uid_channel":"610035",
        "chid":"610035",
        "subchid":"109",
        "adchid":"",
        "nuser_id":"1060002610013974648",
        "nuserid_channel":610035,
        "nuserid_sub_channel":109,
        "nuserid_vercode":"11020",
        "nuserid_create_date":"2026-07-08 16:20:16",
        "language":"zh",
        "country":"cn",
        "uid":24405328,
        "rid":0,
        "compver":127200,
        "oaid":"",
        "ipv4":"36.24.25.176",
        "operatorIp":"112.0.1.1"}
    device_str = json.dumps(device)
    base64_device = base64.b64encode(device_str.encode('utf-8')).decode('utf-8')
    return base64_device

def download_ourplay(official: bool = True):
    """
    从 OurPlay 下载汉化包信息
    """
    headers = {
        'device-user': make_device(),
        'User-Agent': 'okhttp/3.12.13',
    }
    
    url = 'https://gapi.ourplay.com.cn/depends/zhapk'
    data = {"pkg": "com.ProjectMoon.LimbusCompany", "language_type": "chinese", "language_ver": 0,
            "split": 1, "is_unofficial": 2 if official else 3, "ver": "406"}
    
    _log_manager.log("正在请求 OurPlay 汉化包信息")
    
    r = requests.post(url, headers=headers, data=data)
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


def _resolve_refer_package(refer_package):
    """
    解析参考包路径。

    优先级：
    1. 显式参数 refer_package（目录或 zip）
    2. ConfigManager().get("ourplay.refer_package", "")
    3. 自动检测: {game_path}/LimbusCompany_Data/Lang/LLC_zh-CN/

    若是 zip → 解压到临时目录，返回解压后的根目录
    若是目录 → 直接返回

    若都不可用 → 抛出异常
    """
    # 优先级1：显式参数
    if refer_package and os.path.exists(refer_package):
        if os.path.isdir(refer_package):
            _log_manager.log(f"使用参考包目录: {refer_package}")
            return refer_package
        elif refer_package.endswith('.zip'):
            # 解压到临时目录
            extract_dir = tempfile.mkdtemp(prefix='refer_pkg_')
            _log_manager.log(f"解压参考包 {refer_package} -> {extract_dir}")
            with zipfile.ZipFile(refer_package, 'r') as zf:
                zf.extractall(extract_dir)
            # 找到解压后的根目录（可能有一层包裹）
            entries = os.listdir(extract_dir)
            if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
                return os.path.join(extract_dir, entries[0])
            return extract_dir

    # 优先级2：配置
    config_path = ConfigManager().get("ourplay.refer_package", "")
    if config_path and os.path.exists(config_path):
        _log_manager.log(f"使用配置中的参考包路径: {config_path}")
        return _resolve_refer_package(config_path)

    # 优先级3：自动检测游戏安装目录
    game_path = ConfigManager().get('game_path', '')
    if game_path:
        llc_dir = os.path.join(game_path, 'LimbusCompany_Data', 'Lang', 'LLC_zh-CN')
        if os.path.isdir(llc_dir):
            _log_manager.log(f"自动检测到参考包: {llc_dir}")
            return llc_dir

    raise Exception(
        "未找到参考包。请提供 refer_package 参数，或在配置中设置 ourplay.refer_package，"
        "或确保已安装 LLC 汉化包。"
    )


def _build_reference_index(refer_root):
    """
    遍历基板包的目录结构，为每个 JSON 文件建立索引。

    返回:
      ref_files: {relative_path: set_of_ids}  — 基板包中每个 JSON 文件及其 ID 集合
      id_to_paths: {id: [relative_path, ...]} — 每个 ID 出现在哪些文件中
    """
    ref_files = {}
    id_to_paths = defaultdict(list)

    _log_manager.log(f"正在构建参考包索引: {refer_root}")

    for dirpath, dirnames, filenames in os.walk(refer_root):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, refer_root).replace('\\', '/')

            # 跳过非 JSON 文件
            if not filename.endswith('.json'):
                continue
            # 跳过 manifest
            if filename == 'manifest.json':
                continue

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            if 'dataList' not in data or not isinstance(data['dataList'], list):
                continue

            ids = set()
            for item in data['dataList']:
                if isinstance(item, dict) and 'id' in item:
                    id_val = str(item['id'])
                    if id_val:  # 跳过空 ID
                        ids.add(id_val)
                        id_to_paths[id_val].append(rel_path)

            if ids:
                ref_files[rel_path] = ids

    _log_manager.log(f"参考包索引构建完成: {len(ref_files)} 个文件, {len(id_to_paths)} 个唯一 ID")
    return ref_files, id_to_paths


def _build_transfile_index(hash_dir):
    """
    扫描 transfile 解压后的 hash 文件目录。

    返回:
      hash_files: {hash_filename: (data_list, set_of_ids)}
      跳过统计: binary_count
    """
    hash_files = {}
    binary_count = 0

    _log_manager.log(f"正在扫描 transfile 文件: {hash_dir}")

    if not os.path.isdir(hash_dir):
        _log_manager.log(f"hash 目录不存在: {hash_dir}")
        return hash_files, binary_count

    for filename in os.listdir(hash_dir):
        filepath = os.path.join(hash_dir, filename)
        if not os.path.isfile(filepath):
            continue
        if filename == 'google_app_measurement_local.db':
            continue

        # 尝试 UTF-8 解码 + JSON 解析
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            binary_count += 1
            continue

        if 'dataList' not in data or not isinstance(data['dataList'], list):
            binary_count += 1
            continue

        ids = set()
        for item in data['dataList']:
            if isinstance(item, dict) and 'id' in item:
                id_val = str(item['id'])
                if id_val:
                    ids.add(id_val)

        hash_files[filename] = (data['dataList'], ids)

    _log_manager.log(f"transfile 扫描完成: {len(hash_files)} 个 JSON 文件, {binary_count} 个二进制/非JSON文件")
    return hash_files, binary_count


def _match_ref_to_transfile(ref_files, hash_files, id_to_paths):
    """
    为每个基板包文件找到最佳的 transfile hash 文件。

    算法 (O(R + T)):
    1. 构建反向索引: id -> set of hash_filenames
    2. 对每个 ref 文件，通过其 IDs 查找最佳 hash 文件
    3. 同一 hash 可以服务多个 ref 文件（游戏将多个源文件打包为一个 hash）

    返回:
      ref_to_hash: {ref_path: hash_name}  — 每个基板文件对应的 transfile hash
    """
    _log_manager.log("正在匹配文件...")

    # 1. 构建反向索引: id -> set of hash filenames
    id_to_hash = defaultdict(set)
    for hash_name, (data_list, hash_ids) in hash_files.items():
        for hid in hash_ids:
            id_to_hash[hid].add(hash_name)

    _log_manager.log(f"反向索引构建完成: {len(id_to_hash)} 个 ID 映射到 hash 文件")

    # 2. 为每个 ref 文件找到最佳 hash
    ref_to_hash = {}
    hash_usage_count = defaultdict(int)

    for ref_path, ref_ids in ref_files.items():
        hash_votes = defaultdict(int)

        for rid in ref_ids:
            if rid in id_to_hash:
                for hname in id_to_hash[rid]:
                    hash_votes[hname] += 1

        if hash_votes:
            # 评分：优先匹配率（overlap 数量），平票时选更精确的（hash 总 ID 数更少）
            best_hash = max(
                hash_votes.keys(),
                key=lambda h: (hash_votes[h], -len(hash_files[h][1]))
            )
            best_votes = hash_votes[best_hash]

            # 匹配阈值：至少 ref 文件中一半的 ID 出现在 hash 中
            min_match = max(1, len(ref_ids) * 0.5)
            if best_votes >= min_match:
                ref_to_hash[ref_path] = best_hash
                hash_usage_count[best_hash] += 1

    matched_ref_count = len(ref_to_hash)
    total_ref_count = len(ref_files)
    unique_hashes_used = len(hash_usage_count)
    multi_use_hashes = sum(1 for c in hash_usage_count.values() if c > 1)

    _log_manager.log(
        f"匹配完成: {matched_ref_count}/{total_ref_count} 个基板文件已匹配 transfile "
        f"({100*matched_ref_count/total_ref_count:.1f}%), "
        f"{total_ref_count - matched_ref_count} 个将使用回退, "
        f"{unique_hashes_used} 个 hash 文件被使用 "
        f"({multi_use_hashes} 个被多个 ref 共享)"
    )

    return ref_to_hash


def _convert_new_package(temp_dir, refer_package):
    """
    将新 API 的 hash 文件转换为标准 OurPlayHanHua 目录结构。

    确保输出包中的文件列表与基板包完全一致（不多不少）。
    匹配到的文件使用 transfile 版本（OurPlay 翻译），
    未匹配到的使用基板包原文件（回退）。

    返回: 输出目录的绝对路径（OurPlayHanHua 目录）
    """
    # 1. 解析参考包
    refer_root = _resolve_refer_package(refer_package)

    # 2. 构建索引
    ref_files, id_to_paths = _build_reference_index(refer_root)
    if not ref_files:
        raise Exception("参考包中未找到任何有效的 JSON 文件")

    # 3. 扫描 transfile
    hash_dir = os.path.join(temp_dir, 'com.ProjectMoon.LimbusCompany')
    hash_files, binary_count = _build_transfile_index(hash_dir)
    _log_manager.log(f"transfile 统计: {len(hash_files)} JSON, {binary_count} 二进制文件已跳过")

    # 4. 匹配
    ref_to_hash = _match_ref_to_transfile(ref_files, hash_files, id_to_paths)

    # 5. 创建输出目录
    output_root = os.path.join(temp_dir, 'output')
    ourplay_root = os.path.join(output_root, 'OurPlayHanHua')
    os.makedirs(ourplay_root, exist_ok=True)

    # 确保 Font 目录存在（find_translation_packages 验证需要）
    font_context_dir = os.path.join(ourplay_root, 'Font', 'Context')
    font_title_dir = os.path.join(ourplay_root, 'Font', 'Title')
    os.makedirs(font_context_dir, exist_ok=True)
    os.makedirs(font_title_dir, exist_ok=True)

    # 6. 复制文件
    from_transfile = 0
    from_reference = 0

    for ref_path in ref_files:
        dest = os.path.join(ourplay_root, ref_path.replace('/', os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        if ref_path in ref_to_hash:
            # 使用 transfile hash 文件的内容
            hash_name = ref_to_hash[ref_path]
            src = os.path.join(hash_dir, hash_name)
            shutil.copy2(src, dest)
            from_transfile += 1
        else:
            # 回退：使用基板包原文件
            src = os.path.join(refer_root, ref_path.replace('/', os.sep))
            if os.path.exists(src):
                shutil.copy2(src, dest)
            from_reference += 1

    # 7. 复制非 dataList 文件（Font、Info、没有 dataList 的 JSON 等）
    for dirpath, dirnames, filenames in os.walk(refer_root):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, refer_root).replace('\\', '/')

            # 跳过已在步骤 6 中处理的 JSON 文件
            if rel_path in ref_files:
                continue
            # 跳过 manifest
            if filename == 'manifest.json':
                continue

            dest = os.path.join(ourplay_root, rel_path.replace('/', os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(filepath, dest)

    # 8. 统计日志
    total = from_transfile + from_reference
    match_rate = 100 * from_transfile / total if total > 0 else 0
    _log_manager.log(
        f"转换完成: 总计 {total} 个文件, "
        f"来自 transfile: {from_transfile} ({match_rate:.1f}%), "
        f"来自基板回退: {from_reference} ({100-match_rate:.1f}%), "
        f"跳过二进制: {binary_count}"
    )

    return ourplay_root


def _process_ourplay_package(temp_dir, modal_id, font_option, cache_path, hash_ok=True, refer_package=None):
    """处理已下载的 OurPlay 汉化包：解压、格式转换、字体处理、重新打包"""
    _log_manager.check_running(modal_id)
    _log_manager.log_modal_process("开始处理文件", modal_id)
    _log_manager.log_modal_status("正在处理文件", modal_id)

    # 1. 解压 transfile.zip
    _log_manager.log("正在解压文件...")
    save_path = os.path.join(temp_dir, 'transfile.zip')
    with zipfile.ZipFile(save_path, 'r') as zip_file:
        zip_file.extractall(temp_dir)

    _log_manager.check_running(modal_id)
    _log_manager.log("正在格式化文件...")

    # 2. 格式转换（核心逻辑）
    _log_manager.update_modal_progress(65, "正在转换文件结构", modal_id)
    ourplay_root = _convert_new_package(temp_dir, refer_package)

    _log_manager.check_running(modal_id)
    _log_manager.update_modal_progress(85, "文件结构转换完成", modal_id)

    # 3. 字体处理（与旧 API 相同逻辑）
    if font_option == "simplify" or font_option == "llc":
        title_dir = os.path.join(ourplay_root, 'Font', 'Title')
        if os.path.isdir(title_dir):
            shutil.rmtree(title_dir)
        os.makedirs(title_dir, exist_ok=True)
        _log_manager.log("已精简字体")

    if font_option == "llc":
        _log_manager.log("使用缓存字体...")
        if not (cache_path and os.path.exists(cache_path)):
            raise Exception("缓存文件不存在")
        font_dest = os.path.join(ourplay_root, 'Font', 'Context', 'ChineseFont.ttf')
        if os.path.exists(font_dest):
            os.remove(font_dest)
        shutil.copy2(cache_path, font_dest)
        _log_manager.log("已替换为缓存字体")

    # 4. 打包为 ourplay.zip
    _log_manager.log("正在压缩文件...")
    _log_manager.update_modal_progress(95, "正在打包", modal_id)

    if not zip_folder(ourplay_root, 'ourplay.zip'):
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


def function_ourplay_new_main(modal_id, **kwargs):
    """
    OurPlay 下载主函数
    """
    _log_manager.log_modal_process("成功链接后端", modal_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        _log_manager.log_modal_process("开始下载 OurPlay 汉化包", modal_id)
        _log_manager.log_modal_status("正在初始化链接", modal_id)

        # 获取下载信息
        download_info = download_ourplay(official=kwargs.get("official", True))
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
            hash_ok,
            refer_package=kwargs.get("refer_package")
        )
