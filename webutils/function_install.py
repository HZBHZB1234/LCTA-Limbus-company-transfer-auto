import os
import zipfile
import shutil
import sys
from pathlib import Path
import tempfile
import json
import winreg

from .log_h import LogManager
from .functions import *


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
            except:
                continue
            
        elif os.path.isdir(item_path):
            battle_announcer_path = os.path.join(item_path, 'BattleAnnouncerDlg')
            font_path = os.path.join(item_path, 'Font')
            
            if os.path.exists(battle_announcer_path) and os.path.exists(font_path):
                valid_packages.append(item)
    
    
    return valid_packages


def delete_translation_package(package_name, target_path, logger_: LogManager = None):
    """删除指定的汉化包"""
    try:
        package_path = os.path.join(target_path, package_name)
        if os.path.isdir(package_name):
            shutil.rmtree(package_path)
        elif os.path.isfile(package_name):
            os.remove(package_path)
        
        logger_.log(f"已删除汉化包: {package_name}")
        
        return {"success": True, "message":f"已删除汉化包: {package_name}"}
    except Exception as e:
        error_msg = f"删除失败: {str(e)}"
        logger_.log(error_msg)
        logger_.log_error(e)
        
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
        return {"success": False, "message": f"导出字体时出错: {str(e)}"}


def change_font_for_package(path, path_font, logger_: LogManager = None, modal_id = None):
    '''修改字体'''
    with tempfile.TemporaryDirectory() as temp_dir:
        logger_.log_modal_process(f"开始修改字体为: {path_font}", modal_id)
        if os.path.isdir(path):
            logger_.log('检测到为文件夹，尝试替换')
            if os.path.exists(path+'_font'):
                logger_.log('文件夹冲突')
                return False, "文件夹冲突"
            logger_.log_modal_process('正在创建文件夹副本...', modal_id)
            shutil.copytree(path, path+'_font')
            logger_.log_modal_process('正在替换字体文件...', modal_id)

            shutil.rmtree(f'{path}_font\\Font\\Context')
            os.mkdir(f'{path}_font\\Font\\Context')
            shutil.copyfile(path_font, f'{path}_font\\Font\\Context\\{os.path.basename(path_font)}')
            logger_.log_modal_process('已完成字体替换', modal_id)
            return True, "正常完成"
        
        logger_.log_modal_process('检测到为压缩包，尝试替换', modal_id)
        extract_zip_smartly(path, f'{temp_dir}\\')
        logger_.check_running(modal_id)
        
        logger_.log_modal_process("开始替换文件...", modal_id)
        directory = os.path.dirname(path)
        filename = os.path.basename(path)
        # 分离文件名和扩展名
        name, ext = os.path.splitext(filename)

        dir_name = os.listdir(temp_dir)[0]
        shutil.rmtree(f'{temp_dir}\\{dir_name}\\Font\\Context')
        os.mkdir(f'{temp_dir}\\{dir_name}\\Font\\Context')
        shutil.copyfile(path_font, f'{temp_dir}\\{dir_name}\\Font\\Context\\{os.path.basename(path_font)}')
        
        logger_.log_modal_process("正在压缩文件...", modal_id)
        
        new_filename = f"{name}_fonted.{ext}"
        new_path = os.path.join(directory, new_filename)
        if os.path.exists(new_path):
            os.remove(new_path)
        zip_folder(f'{temp_dir}\\{dir_name}', new_path, logger_)

        logger_.log_modal_process('字体替换完成', modal_id)
        return True, "正常完成"


def install_translation_package(package_path, game_path, logger_: LogManager = None, modal_id: str = None):    
    logger_.log_modal_process(f"准备安装汉化包: {package_path}", modal_id)
    if os.path.isfile(package_path):
        logger_.log_modal_process("检测到为压缩包，开始解压...", modal_id)
        package_name = extract_zip_smartly(package_path, game_path)
    else:
        logger_.log_modal_process("检测到为文件夹，开始复制...", modal_id)
        package_name = os.path.basename(package_path)
        shutil.copytree(package_path, os.path.join(game_path, package_name))
    lang_path = os.path.join(game_path, 'LimbusCompany_Data', 'lang')
    config_path = os.path.join(lang_path, 'config.json')
    logger_.log_modal_process("正在写入配置文件...", modal_id)
    with open(config_path, 'w', encoding='utf-8') as file:
        json.dump({
            "lang": package_name,
            "titleFont": "",
            "contextFont": ""
        }, file, ensure_ascii=False, indent=4)
    logger_.log_modal_process("汉化包安装完成", modal_id)
    return True, "汉化包安装完成"