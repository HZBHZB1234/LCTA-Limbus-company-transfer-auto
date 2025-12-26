import os
import zipfile
from shutil import rmtree
from pathlib import Path
import tempfile
from typing import List, Optional

from .log_manage import LogManager
from .functions import *


def clean_config_main(modal_id: str, logger_: LogManager, clean_progress: bool = False, clean_notice: bool = False, custom_files: List[str] = None):
    """
    清理配置主函数，用于WebUI调用
    
    :param modal_id: 模态窗口ID
    :param logger_: 日志管理器
    :param clean_progress: 是否清理进度文件
    :param clean_notice: 是否清理通知文件
    :param custom_files: 自定义要删除的文件/文件夹列表
    """
    logger_.log_modal_process("开始清理本地缓存文件", modal_id)
    
    # 获取LocalLow路径
    local_low_path = Path(os.environ['APPDATA']).parent / 'LocalLow'
    local_low_path = local_low_path.resolve()
    
    # 清理进度文件
    if clean_progress:
        logger_.log_modal_process("正在清除本地进程文件...", modal_id)
        limbus_dir = local_low_path / 'ProjectMoon' / 'LimbusCompany'
        if limbus_dir.exists():
            # 获取所有文件，找到包含'save'的文件
            save_files = [f for f in limbus_dir.iterdir() if f.is_file() and 'save' in f.name.lower()]
            if save_files:
                save_file = save_files[0]
                try:
                    save_file.unlink()
                    logger_.log_modal_process(f"本地进程文件已清除: {save_file.name}", modal_id)
                except Exception as e:
                    logger_.log_modal_process(f"删除进度文件失败: {str(e)}", modal_id)
                    logger_.log_error(e)
            else:
                logger_.log_modal_process("未找到本地进程文件", modal_id)
        else:
            logger_.log_modal_process("未找到LimbusCompany目录", modal_id)
    
    # 清理通知文件
    if clean_notice:
        logger_.log_modal_process("正在清除本地通知文件...", modal_id)
        notice_file = local_low_path / 'ProjectMoon' / 'LimbusCompany' / 'synchronous-data_product.json'
        notice_dir = local_low_path / 'ProjectMoon' / 'LimbusCompany' / 'notice'
        
        # 删除通知文件
        if notice_file.exists():
            try:
                notice_file.unlink()
                logger_.log_modal_process("本地通知文件已清除", modal_id)
            except Exception as e:
                logger_.log_modal_process(f"删除通知文件失败: {str(e)}", modal_id)
                logger_.log_error(e)
        
        # 删除通知目录
        if notice_dir.exists():
            try:
                rmtree(notice_dir)
                logger_.log_modal_process("本地通知目录已清除", modal_id)
            except Exception as e:
                logger_.log_modal_process(f"删除通知目录失败: {str(e)}", modal_id)
                logger_.log_error(e)
    
    # 清理自定义文件
    if custom_files:
        deleted_count = 0
        for file_path in custom_files:
            try:
                if os.path.isfile(file_path):
                    deleted_count += clear_by_mod(file_path, logger_, modal_id)
                elif os.path.isdir(file_path):
                    deleted_count += sum(map(lambda x: clear_by_mod(os.path.join(file_path, x), logger_, modal_id), os.listdir(file_path)))
                    logger_.log_modal_process(f"已删除mod目录{file_path}下的对应文件", modal_id)
                else:
                    logger_.log_modal_process(f"{file_path} 不存在", modal_id)
            except Exception as e:
                logger_.log_modal_process(f"删除 {file_path} 失败: {str(e)}", modal_id)
                logger_.log_error(e)
        
        if deleted_count > 0:
            logger_.log_modal_process(f"已删除 {deleted_count} 个自定义文件/文件夹", modal_id)
    
    logger_.log_modal_process("清理完成", modal_id)
    logger_.log_modal_status("操作完成", modal_id)


def clear_by_mod(mod_path: str, logger_: LogManager, modal_id: str) -> int:
    """
    根据mod路径清理相关文件
    
    :param mod_path: mod文件路径
    :param logger_: 日志管理器
    :param modal_id: 模态窗口ID
    :return: 删除的项目数量
    """
    local_low_path = Path(os.environ['APPDATA']).parent / 'LocalLow'
    local_low_path = local_low_path.resolve()
    
    unity_dir = local_low_path / 'Unity' / 'ProjectMoon_LimbusCompany'
    
    try:
        # 检查mod文件是否存在
        if not os.path.exists(mod_path):
            logger_.log_modal_process(f"mod文件不存在: {mod_path}", modal_id)
            return 0
        
        # 获取mod文件中的目录结构
        dirs_to_delete = check_by_mod(mod_path)
        
        deleted_count = 0
        for dir_path in dirs_to_delete:
            # 如果路径包含Installation，取其后的目录名
            if 'Installation/' in dir_path:
                path_del = Path(dir_path).name
            else:
                path_del = Path(dir_path).parts[0] if Path(dir_path).parts else None
            
            if path_del and path_del != 'Installation/':
                target_path = unity_dir / path_del
                if target_path.is_dir():
                    try:
                        rmtree(target_path)
                        deleted_count += 1
                        logger_.log_modal_process(f"已删除: {path_del}", modal_id)
                    except Exception as e:
                        logger_.log_modal_process(f"删除 {path_del} 失败: {str(e)}", modal_id)
                        logger_.log_error(e)
                else:
                    logger_.log_modal_process(f"{path_del} 不是一个目录", modal_id)
        
        return deleted_count
        
    except Exception as e:
        logger_.log_modal_process(f"处理mod清理时发生错误: {str(e)}", modal_id)
        logger_.log_error(e)
        return 0


def check_by_mod(mod_path: str) -> List[str]:
    """
    检查mod文件并返回需要删除的目录列表
    
    :param mod_path: mod文件路径
    :return: 需要删除的目录路径列表
    """
    try:
        with zipfile.ZipFile(mod_path, 'r') as zip_file:
            # 获取所有文件列表
            all_files = zip_file.namelist()
            
            # 提取第一层目录结构
            first_level_dirs = set()
            for file_path in all_files:
                # 分割路径，获取第一层目录
                parts = file_path.split('/')
                if parts and parts[0]:
                    first_level_dirs.add(parts[0])
            
            # 判断第二层目录中是否存在Assets文件夹
            assets_found = False
            second_level_items = set()
            
            for file_path in all_files:
                parts = file_path.split('/')
                # 检查是否为第二层目录的文件或文件夹
                if len(parts) >= 2 and parts[0] in first_level_dirs:
                    # 只取第二层的项目（文件或文件夹）
                    second_level_item = '/'.join(parts[:2]) + ('/' if not file_path.endswith('/') and len(parts) > 2 else '')
                    second_level_items.add(second_level_item)
                    # 检查是否存在Assets文件夹
                    if parts[1] == 'Assets':
                        assets_found = True
            
            # 如果找到Assets文件夹，返回Assets\Installation\目录中的一层文件和文件夹
            if assets_found:
                installation_items = set()
                for file_path in all_files:
                    parts = file_path.split('/')
                    # 检查是否在Assets\Installation\路径下
                    if len(parts) >= 3 and parts[1] == 'Assets' and parts[2] == 'Installation':
                        # 只取Installation目录下的一层
                        installation_item = '/'.join(parts[:4]) + ('/' if len(parts) > 4 else '')
                        installation_items.add(installation_item)
                return list(installation_items)
            else:
                # 否则返回第二层目录的一层文件和文件夹
                return list(second_level_items)
                
    except zipfile.BadZipFile:
        raise ValueError("无效的zip文件")
    except FileNotFoundError:
        raise FileNotFoundError("找不到指定的zip文件")
    except Exception as e:
        raise Exception(f"处理zip文件时发生错误: {str(e)}")

