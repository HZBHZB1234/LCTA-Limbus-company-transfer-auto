from __future__ import annotations

import os
import zipfile
import shutil
import sys
from pathlib import Path
import tempfile
import json
import winreg

from globalManagers.LogManager import LogManager
_log_manager = LogManager()
from ..utils.io import extract_zip_smartly, zip_folder
from .clean import _sanitize_zip_member_name
from .manage import safe_join_path, get_active_lang_path


def find_translation_packages(target_dir):
    """查找当前目录下可用的汉化包"""
    items = os.listdir(target_dir)
    
    valid_packages = []
    
    for item in items:
        item_path = os.path.join(target_dir, item)
        if os.path.isfile(item_path) and item.endswith('.zip'):
            try:
                with zipfile.ZipFile(item_path, "r") as zipf:
                    namelist = zipf.namelist()
                    has_battle_announcer = any('BattleAnnouncerDlg' in name for name in namelist)
                    has_font = any('Font' in name for name in namelist)
                    
                    if has_battle_announcer and has_font:
                        valid_packages.append(item)
            except Exception as e:
                _log_manager.log_error(e)
                continue
            
        elif os.path.isdir(item_path):
            battle_announcer_path = os.path.join(item_path, 'BattleAnnouncerDlg')
            font_path = os.path.join(item_path, 'Font')
            
            if os.path.exists(battle_announcer_path) and os.path.exists(font_path):
                valid_packages.append(item)
    
    
    return valid_packages


def delete_translation_package(package_name, target_path):
    """删除指定的汉化包"""
    try:
        # 校验名称安全并解析目标路径，防止路径穿越
        package_path = safe_join_path(target_path, package_name)
        if os.path.isdir(package_path):
            shutil.rmtree(package_path)
        elif os.path.isfile(package_path):
            os.remove(package_path)
        else:
            error_msg = f"汉化包不存在: {package_name}"
            _log_manager.log(error_msg)
            return {"success": False, "message": error_msg}
        
        _log_manager.log(f"已删除汉化包: {package_name}")
        
        return {"success": True, "message":f"已删除汉化包: {package_name}"}
    except Exception as e:
        error_msg = f"删除失败: {str(e)}"
        _log_manager.log(error_msg)
        _log_manager.log_error(e)
        
        return {"success": False, "message":error_msg}


def get_system_fonts():
    """获取系统已安装的字体列表"""
    fonts = []
    font_files = {}
    
    # 获取Windows字体目录
    fonts_dir = os.path.join(os.environ['WINDIR'], 'Fonts')
    
    # 从注册表获取已安装字体信息
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as key:
            i = 0
            while True:
                try:
                    value_name, value_data, _ = winreg.EnumValue(key, i)
                    i += 1
                    
                    # 提取字体名称（移除可能的后缀如 (TrueType)）
                    font_name = value_name
                    for suffix in [" (TrueType)", " (OpenType)", " (Variable)"]:
                        if font_name.endswith(suffix):
                            font_name = font_name[:-len(suffix)]
                            break
                    
                    # 构建完整字体文件路径
                    font_path = os.path.join(fonts_dir, value_data)
                    if not os.path.isfile(font_path):
                        continue
                        
                    fonts.append(font_name)
                    font_files[font_name] = font_path
                    
                except OSError:
                    break
    except Exception as e:
        return {"success": False, "message": f"无法读取字体注册表信息: {e}"}
    
    # 按字母顺序排序字体列表
    fonts.sort(key=lambda x: x.lower())
    
    return {"success": True, "fonts": fonts, "font_files": font_files}


def export_system_font(font_name, destination_path):
    """导出系统字体文件到指定位置"""
    try:
        # 获取Windows字体目录
        fonts_dir = os.path.join(os.environ['WINDIR'], 'Fonts')
        
        # 从注册表获取指定字体的文件名
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as key:
            i = 0
            target_font_path = None
            while True:
                try:
                    value_name, value_data, _ = winreg.EnumValue(key, i)
                    i += 1
                    
                    # 提取字体名称（移除可能的后缀如 (TrueType)）
                    reg_font_name = value_name
                    for suffix in [" (TrueType)", " (OpenType)", " (Variable)"]:
                        if reg_font_name.endswith(suffix):
                            reg_font_name = reg_font_name[:-len(suffix)]
                            break
                    
                    if reg_font_name == font_name:
                        target_font_path = os.path.join(fonts_dir, value_data)
                        break
                except OSError:
                    break
        
        if not target_font_path or not os.path.isfile(target_font_path):
            return {"success": False, "message": f"找不到字体文件: {font_name}"}
        
        # 检查目标路径的目录是否存在，如果不存在则创建
        destination_dir = os.path.dirname(destination_path)
        if not os.path.exists(destination_dir):
            os.makedirs(destination_dir)
        
        # 复制字体文件到目标位置
        shutil.copy2(target_font_path, destination_path)
        
        return {"success": True, "message": f"字体已导出到: {destination_path}"}
        
    except Exception as e:
        _log_manager.log_error(e)
        return {"success": False, "message": f"导出字体时出错: {str(e)}"}


def change_font_for_package(path, path_font, modal_id = None):
    '''修改字体'''
    with tempfile.TemporaryDirectory() as temp_dir:
        _log_manager.log_modal_process(f"开始修改字体为: {path_font}", modal_id)
        if os.path.isdir(path):
            _log_manager.log('检测到为文件夹，尝试替换')
            _log_manager.log_modal_process('正在创建文件夹副本...', modal_id)
            _log_manager.check_running(modal_id)
            font_dir = os.path.join(temp_dir, os.path.basename(path))
            shutil.copytree(path, font_dir)
            _log_manager.log_modal_process('正在替换字体文件...', modal_id)
            _log_manager.check_running(modal_id)

            font_context = os.path.join(font_dir, 'Font', 'Context')
            if os.path.isdir(font_context):
                shutil.rmtree(font_context)
            os.makedirs(font_context, exist_ok=True)
            shutil.copyfile(path_font, os.path.join(font_context, os.path.basename(path_font)))
            _log_manager.log_modal_process('已完成字体替换', modal_id)

            directory = os.path.dirname(path)
            name = os.path.splitext(os.path.basename(path))[0]
            new_path = os.path.join(directory, f"{name}_fonted.zip")
            if os.path.exists(new_path):
                os.remove(new_path)
            zip_folder(font_dir, new_path, modal_id=modal_id)

            _log_manager.log_modal_process('字体替换完成', modal_id)
            return True, "正常完成"
        
        _log_manager.log_modal_process('检测到为压缩包，尝试替换', modal_id)
        extract_zip_smartly(path, f'{temp_dir}\\')
        _log_manager.check_running(modal_id)
        
        _log_manager.log_modal_process("开始替换文件...", modal_id)
        directory = os.path.dirname(path)
        filename = os.path.basename(path)
        # 分离文件名和扩展名
        name, ext = os.path.splitext(filename)

        entries = os.listdir(temp_dir)
        if not entries:
            _log_manager.log('压缩包内容为空，无法替换字体')
            return False, "压缩包内容为空，无法替换字体"
        dir_name = entries[0]
        font_context = os.path.join(temp_dir, dir_name, 'Font', 'Context')
        if os.path.isdir(font_context):
            shutil.rmtree(font_context)
        os.makedirs(font_context, exist_ok=True)
        shutil.copyfile(path_font, os.path.join(font_context, os.path.basename(path_font)))
        
        _log_manager.log_modal_process("正在压缩文件...", modal_id)
        
        new_filename = f"{name}_fonted.{ext}"
        new_path = os.path.join(directory, new_filename)
        if os.path.exists(new_path):
            os.remove(new_path)
        zip_folder(f'{temp_dir}\\{dir_name}', new_path, modal_id=modal_id)

        _log_manager.log_modal_process('字体替换完成', modal_id)
        return True, "正常完成"


def install_translation_package(package_path, game_path, modal_id: str = None):    
    _log_manager.log_modal_process(f"准备安装汉化包: {package_path}", modal_id)
    _log_manager.check_running(modal_id)
    # 安装目标为当前启用的汉化目录（禁用态为 _lang），不重建 lang 造成双目录
    base_dir = Path(game_path) / 'LimbusCompany_Data'
    base_dir.mkdir(parents=True, exist_ok=True)
    game_path = str(get_active_lang_path(game_path))
    
    # 先确定要安装的汉化包名称
    if os.path.isfile(package_path):
        _log_manager.log_modal_process("检测到为压缩包，获取解压后文件夹名...", modal_id)
        # 获取解压后的文件夹名称
        with zipfile.ZipFile(package_path, "r") as zipf:
            namelist = zipf.namelist()
            # 校验所有成员名安全，拒绝路径穿越类成员
            for name in namelist:
                _sanitize_zip_member_name(name)
            if not namelist:
                raise ValueError("压缩包为空，无法安装汉化包")
            # 获取压缩包内的第一个文件夹名称（假设汉化包结构为文件夹/...）
            first_item = namelist[0]
            package_name = first_item.replace('\\', '/').split('/')[0]
            # 只接受单个目录名形态，拒绝空名、'.'/'..' 与含分隔符/盘符的名称
            if (not package_name or package_name in ('.', '..')
                    or '/' in package_name or '\\' in package_name
                    or ':' in package_name or os.path.isabs(package_name)):
                raise ValueError(f"压缩包内不存在有效的汉化包目录: {first_item}")
    else:
        _log_manager.log_modal_process("检测到为文件夹，获取文件夹名...", modal_id)
        package_name = os.path.basename(package_path)
    
    # 删除同名的旧汉化包文件夹
    target_package_path = os.path.join(game_path, package_name)
    if os.path.exists(target_package_path) and os.path.isdir(target_package_path):
        _log_manager.log_modal_process(f"正在删除旧的汉化包文件夹: {package_name}", modal_id)
        _log_manager.check_running(modal_id)
        try:
            shutil.rmtree(target_package_path)
            _log_manager.log(f"已删除旧汉化包文件夹: {package_name}")
        except Exception as e:
            error_msg = f"删除旧汉化包文件夹失败: {package_name} - {str(e)}"
            _log_manager.log(error_msg)
            _log_manager.log_error(e)
            # 继续安装，不中断
    
    # 安装新的汉化包
    if os.path.isfile(package_path):
        _log_manager.log_modal_process("开始解压压缩包...", modal_id)
        # 使用原来的解压函数
        extracted_name = extract_zip_smartly(package_path, game_path)
        # 如果解压函数返回的名称与我们预期的不一致，使用返回的名称
        if extracted_name and extracted_name != package_name:
            package_name = extracted_name
            _log_manager.log(f"解压后的文件夹名与预期不同，使用: {package_name}")
    else:
        _log_manager.log_modal_process("开始复制文件夹...", modal_id)
        dest_path = os.path.join(game_path, package_name)
        os.makedirs(dest_path, exist_ok=True)
        for root, dirs, files in os.walk(package_path):
            _log_manager.check_running(modal_id)
            rel_root = os.path.relpath(root, package_path)
            target_root = dest_path if rel_root == '.' else os.path.join(dest_path, rel_root)
            os.makedirs(target_root, exist_ok=True)
            for file in files:
                _log_manager.check_running(modal_id)
                shutil.copy2(os.path.join(root, file), os.path.join(target_root, file))
    
    # 写入配置文件
    config_path = os.path.join(game_path, 'config.json')
    _log_manager.log_modal_process("正在写入配置文件...", modal_id)
    _log_manager.check_running(modal_id)
    with open(config_path, 'w', encoding='utf-8') as file:
        json.dump({
            "lang": package_name,
            "titleFont": "",
            "contextFont": ""
        }, file, ensure_ascii=False, indent=4)
    
    _log_manager.log_modal_process("汉化包安装完成", modal_id)
    return True, "汉化包安装完成"
