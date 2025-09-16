import winreg
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import zipfile
from shutil import rmtree, copytree,copyfile
import time
import sys
from functions import zip_folder
# 全局变量，用于日志输出
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
def change_font(path,path_font):
    '''修改字体'''
    log(f"开始修改字体为: {path}")
    if not os.path.exists(path_font):
        log("文件不存在")
        return False
    try:rmtree('temp')
    except:pass
    if not os.path.exists('temp'):
        os.mkdir('temp')
    log("正在解压文件...")
    if os.path.isdir(path):
        log('检测到为文件夹，尝试替换')
        if os.path.exists(path+'_font'):
            log('文件夹冲突')
            return False
        log('正在复制文件夹...')
        copytree(path,path+'_font')
        rmtree(f'{path}_font\\Font\\Context')
        os.mkdir(f'{path}_font\\Font\\Context')
        copyfile(path_font,f'{path}_font\\Font\\Context\\{os.path.basename(path_font)}')
        log('完成')
        return True
    with zipfile.ZipFile(path, 'r') as zip_file:
        zip_file.extractall('temp\\') 
    log("正在替换文件...")
    directory = os.path.dirname(path)
    filename = os.path.basename(path)
    # 分离文件名和扩展名
    name, ext = os.path.splitext(filename)
    if len(os.listdir('temp\\'))!=1:
        log('特殊文件格式，尝试修改')
        if os.path.exists(name):
            log("文件冲突")
            return False
        os.rename('temp\\', name)
        rmtree(f'{name}\\Font\\Context')
        os.mkdir(f'{name}\\Font\\Context')
        copyfile(path_font,f'{name}\\Font\\Context\\{os.path.basename(path_font)}')
        log("正在压缩文件...")
        # 在文件名后添加下划线并重新组合
        new_filename = f"{name}_fonted.{ext}"
        new_path = os.path.join(directory, new_filename)
        if os.path.exists(new_path):os.remove(new_path)
        zip_folder(name, f'{new_path}')
        log("正在清理文件...")
        rmtree(name)
        log('字体替换完成')
    dir_name = os.listdir('temp\\')[0]
    rmtree(f'temp\\{dir_name}\\Font\\Context')
    os.mkdir(f'temp\\{dir_name}\\Font\\Context')
    copyfile(path_font,f'temp\\{dir_name}\\Font\\Context\\{os.path.basename(path_font)}')
    log("正在压缩文件...")
    # 在文件名后添加下划线并重新组合
    new_filename = f"{name}_fonted.{ext}"
    new_path = os.path.join(directory, new_filename)
    if os.path.exists(new_path):os.remove(new_path)
    zip_folder(f'temp\\{dir_name}', f'{new_path}')
    log("正在清理文件...")
    rmtree('temp')
    log('字体替换完成')
    
def final_dir(LCTA_path, path):
    """安装文件夹形式的汉化包"""
    try:
        target_dir = os.path.join(path, 'LimbusCompany_Data', 'lang', os.path.basename(LCTA_path))
        log(f"准备安装汉化包到: {target_dir}")
        
        # 移除现有目录
        try:
            rmtree(target_dir)
            log("已移除现有汉化目录")
        except:
            log("无需移除现有汉化目录")
        
        # 复制新目录
        try:
            copytree(LCTA_path, target_dir)
            log("汉化文件夹复制成功")
        except Exception as e:
            raise Exception(f"复制汉化文件夹失败: {str(e)}")
        
        # 更新配置文件
        config_path = os.path.join(path, 'LimbusCompany_Data', 'lang', 'config.json')
        try:
            if os.path.exists(config_path):
                os.remove(config_path)
        except:
            log("移除旧配置文件失败，尝试继续")
        
        config_lang = {
            "lang": os.path.basename(LCTA_path),
            "titleFont": "",
            "contextFont": ""
        }
        
        try:
            with open(config_path, 'w', encoding='utf-8') as file:
                json.dump(config_lang, file, ensure_ascii=False, indent=4)
            log("配置文件更新成功")
        except Exception as e:
            raise Exception(f"写入配置文件失败: {str(e)}")
            
        return True, "汉化安装成功"
        
    except Exception as e:
        return False, f"安装过程中出错: {str(e)}"

def final_not_one(LCTA_path, path):
    """安装特殊格式的汉化包"""
    try:
        dir_name = LCTA_path[:-4]  # 移除.zip扩展名
        target_dir = os.path.join(path, 'LimbusCompany_Data', 'lang', os.path.basename(dir_name))
        
        log(f"准备安装汉化包到: {target_dir}")
        
        # 移除现有目录
        try:
            rmtree(target_dir)
            log("已移除现有汉化目录")
        except:
            log("无需移除现有汉化目录")
        
        # 解压文件
        try:
            with zipfile.ZipFile(LCTA_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
            log("汉化包解压成功")
        except Exception as e:
            raise Exception(f"解压汉化包失败: {str(e)}")
        
        # 更新配置文件
        config_path = os.path.join(path, 'LimbusCompany_Data', 'lang', 'config.json')
        try:
            if os.path.exists(config_path):
                os.remove(config_path)
        except:
            log("移除旧配置文件失败，尝试继续")
        
        config_lang = {
            "lang": os.path.basename(dir_name),
            "titleFont": "",
            "contextFont": ""
        }
        
        try:
            with open(config_path, 'w', encoding='utf-8') as file:
                json.dump(config_lang, file, ensure_ascii=False, indent=4)
            log("配置文件更新成功")
        except Exception as e:
            raise Exception(f"写入配置文件失败: {str(e)}")
            
        return True, "汉化安装成功"
        
    except Exception as e:
        return False, f"安装过程中出错: {str(e)}"

def final(LCTA_path, path):
    """安装标准zip格式的汉化包"""
    try:
        # 检查zip文件完整性
        with zipfile.ZipFile(LCTA_path, "r") as zipf:
            result = zipf.testzip()
            if result is not None:
                raise Exception("汉化包文件损坏")
            
            dir_name = zipf.namelist()
            if not dir_name:
                raise Exception("汉化包为空或损坏")
            
            dir_name = zipf.namelist()[0]
            if dir_name.endswith('/'):
                dir_name = dir_name[:-1]
        
        target_dir = os.path.join(path, 'LimbusCompany_Data', 'lang')
        
        log(f"准备安装汉化包到: {target_dir}")
        
        # 移除现有目录
        try:
            rmtree(os.path.join(target_dir, dir_name))
            log("已移除现有汉化目录")
        except:
            log("无需移除现有汉化目录")
        
        # 解压文件
        try:
            with zipfile.ZipFile(LCTA_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
            log("汉化包解压成功")
        except Exception as e:
            raise Exception(f"解压汉化包失败: {str(e)}")
        
        # 更新配置文件
        config_path = os.path.join(target_dir, 'config.json')
        try:
            if os.path.exists(config_path):
                os.remove(config_path)
        except:
            log("移除旧配置文件失败，尝试继续")
        
        config_lang = {
            "lang": dir_name,
            "titleFont": "",
            "contextFont": ""
        }
        
        try:
            with open(config_path, 'w', encoding='utf-8') as file:
                json.dump(config_lang, file, ensure_ascii=False, indent=4)
            log("配置文件更新成功")
        except Exception as e:
            raise Exception(f"写入配置文件失败: {str(e)}")
            
        return True, "汉化安装成功"
        
    except Exception as e:
        return False, f"安装过程中出错: {str(e)}"

def final_correct(LCTA_path, path):
    """根据汉化包类型选择合适的安装方法"""
    try:
        if LCTA_path.endswith('.zip'):
            with zipfile.ZipFile(LCTA_path, "r") as zipf:
                result = zipf.testzip()
                if result is not None:
                    return False, "汉化包文件损坏"
                
                dir_name = zipf.namelist()
                if not dir_name:
                    return False, "汉化包为空或损坏"
                
                # 检查是否包含必要的目录
                has_battle = any('BattleAnnouncerDlg' in name for name in dir_name)
                has_font = any('Font' in name for name in dir_name)
                
                if has_battle or has_font:
                    return final_not_one(LCTA_path, path)
                
                # 检查是否只有一个顶层目录
                first_level_dirs = set()
                for name in dir_name:
                    parts = name.split('/')
                    if len(parts) > 0 and parts[0]:
                        first_level_dirs.add(parts[0])
                
                if len(first_level_dirs) == 1:
                    return final(LCTA_path, path)
                else:
                    return False, "汉化包格式不正确，应包含一个顶层目录"
        elif os.path.isdir(LCTA_path):
            # 检查是否是有效的汉化文件夹
            has_battle = os.path.isdir(os.path.join(LCTA_path, 'BattleAnnouncerDlg'))
            has_font = os.path.isdir(os.path.join(LCTA_path, 'Font'))
            
            if has_battle and has_font:
                return final_dir(LCTA_path, path)
            else:
                return False, "选择的文件夹不是有效的汉化包"
        else:
            return False, "不支持的文件格式"
            
    except Exception as e:
        return False, f"安装过程中出错: {str(e)}"

def write_path(path):
    """写入游戏路径到配置文件"""
    try:
        if os.path.exists(os.path.expanduser("~") + '\\limbus.txt'):
            os.remove(os.path.expanduser("~") + '\\limbus.txt')
    except:
        pass
    
    try:
        if os.path.exists('path.txt'):
            os.remove('path.txt')
    except:
        pass
    
    try:
        with open(os.path.expanduser("~") + '\\limbus.txt', 'w', encoding='utf-8') as file:
            file.write(path)
        with open("path.txt", 'w', encoding='utf-8') as file:
            file.write(path)
        return True, "路径保存成功"
    except Exception as e:
        return False, f"保存路径失败: {str(e)}"

def choose_path():
    """选择文件对话框"""
    return filedialog.askopenfilename()

def has_change():
    """手动选择游戏路径"""
    try:
        if os.path.exists(os.path.expanduser("~") + '\\limbus.txt'):
            os.remove(os.path.expanduser("~") + '\\limbus.txt')
    except:
        pass
    
    try:
        if os.path.exists('path.txt'):
            os.remove('path.txt')
    except:
        pass
    
    exe_name = ""
    path_little = ""
    
    while not exe_name == "LimbusCompany.exe":
        path_little = choose_path()
        if not path_little:  # 用户取消了选择
            return None
        
        name_list = path_little.split("/")
        exe_name = name_list[-1]
        
        if not exe_name == "LimbusCompany.exe":
            messagebox.showwarning('LCTA', "请选择LimbusCompany.exe文件")
    
    path_little = path_little[:-17]  # 移除"/LimbusCompany.exe"
    
    success, message = write_path(path_little)
    if not success:
        messagebox.showerror('LCTA', message)
        return None
    
    return path_little

def find_lcb():
    """查找游戏安装路径"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Valve\Steam')
        value, value_type = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        
        applist = []
        with open(value + '\\steamapps\\libraryfolders.vdf', 'r') as f:
            a = f.read()
            for i in a.split('\n'):
                if 'path' in i:
                    applist.append(i.split('\"')[3])
        
        for i in applist:
            game_path = i + '\\steamapps\\common\\Limbus Company\\'
            if os.path.exists(game_path + 'LimbusCompany.exe'):
                return game_path
                
        return None
    except Exception as e:
        log(f"查找游戏路径时出错: {str(e)}")
        return None

def install(LCTA_path, game_path):
    """安装汉化包的主函数 - 适配UI版本"""
    if not LCTA_path:
        return False, "未选择汉化包文件"
    
    if not game_path:
        return False, "未设置游戏路径"
    
    if not os.path.exists(game_path):
        return False, "游戏路径不存在"
    
    # 检查汉化包是否存在
    if not os.path.exists(LCTA_path):
        return False, "汉化包文件不存在"
    
    # 执行安装
    return final_correct(LCTA_path, game_path)

# 以下函数用于在单独运行install.py时提供命令行界面
if __name__ == '__main__':
    def console_log(message):
        print(message)
    
    set_log_callback(console_log)
    
    root = tk.Tk()
    root.withdraw()
    
    # 获取游戏路径
    game_path = None
    if os.path.exists('path.txt'):
        with open("path.txt", "r") as f:
            game_path = f.readline().strip()
    
    if not game_path or not os.path.exists(game_path):
        game_path = find_lcb()
        if game_path and messagebox.askyesno('LCTA', f'这是你的游戏地址吗?\n{game_path}'):
            write_path(game_path)
        else:
            messagebox.showinfo('LCTA', "请指定游戏路径(选择游戏exe文件)")
            game_path = has_change()
    
    if not game_path:
        messagebox.showerror('LCTA', "无法获取游戏路径，安装中止")
        sys.exit(1)
    
    # 选择汉化包
    LCTA_path = filedialog.askopenfilename(
        title="选择汉化包文件",
        filetypes=[("Zip文件", "*.zip"), ("所有文件", "*.*")]
    )
    
    if not LCTA_path:
        messagebox.showinfo('LCTA', "未选择汉化包，安装中止")
        sys.exit(0)
    
    # 执行安装
    success, message = install(LCTA_path, game_path)
    
    if success:
        messagebox.showinfo('LCTA', message)
    else:
        messagebox.showerror('LCTA', message)
    
    root.destroy()