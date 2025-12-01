import os
import json
import requests
import zipfile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


class Updater:
    def __init__(self, repo_owner: str, repo_name: str):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        
    def get_latest_version(self) -> Optional[str]:
        """获取最新版本号"""
        try:
            response = requests.get(self.api_url)
            response.raise_for_status()
            data = response.json()
            return data.get('tag_name')
        except Exception as e:
            print(f"获取最新版本失败: {e}")
            return None
    
    def compare_versions(self, current_version: str, latest_version: str) -> bool:
        """比较版本号，判断是否有新版本"""
        try:
            # 去掉版本号前缀 v
            current = current_version.lstrip('v')
            latest = latest_version.lstrip('v')
            
            # 简单的版本比较，实际应用中可以使用更复杂的比较逻辑
            return latest != current
        except:
            return False
    
    def download_latest_release(self, cache_dir: str) -> Optional[str]:
        """下载最新版本源码"""
        try:
            # 获取最新发布信息
            response = requests.get(self.api_url)
            response.raise_for_status()
            data = response.json()
            
            # 获取源码下载URL (tarball or zipball)
            download_url = data.get('zipball_url')
            if not download_url:
                # 尝试从assets中找源码包
                assets = data.get('assets', [])
                for asset in assets:
                    if 'source' in asset.get('name', '').lower() or asset.get('name', '').endswith('.zip'):
                        download_url = asset.get('browser_download_url')
                        break
            
            if not download_url:
                print("未找到源码下载链接")
                return None
            
            # 确保缓存目录存在
            os.makedirs(cache_dir, exist_ok=True)
            
            # 下载文件
            zip_path = os.path.join(cache_dir, "latest_release.zip")
            print(f"正在下载: {download_url}")
            
            response = requests.get(download_url)
            response.raise_for_status()
            
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            return zip_path
        except Exception as e:
            print(f"下载最新版本失败: {e}")
            return None
    
    def extract_release(self, zip_path: str, extract_to: str) -> Optional[str]:
        """解压下载的文件到缓存目录"""
        try:
            os.makedirs(extract_to, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            
            # 通常zip文件会包含一个根目录，我们需要找到它
            extracted_dirs = os.listdir(extract_to)
            if extracted_dirs:
                # 返回解压后的源码目录路径
                return os.path.join(extract_to, extracted_dirs[0])
            
            return extract_to
        except Exception as e:
            print(f"解压文件失败: {e}")
            return None
    
    def install_requirements(self, source_dir: str) -> bool:
        """根据新的requirements.txt安装依赖"""
        requirements_path = os.path.join(source_dir, "requirements.txt")
        if not os.path.exists(requirements_path):
            print("未找到requirements.txt文件")
            return False
        
        try:
            # 使用当前Python环境安装依赖
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_path])
            return True
        except subprocess.CalledProcessError as e:
            print(f"安装依赖失败: {e}")
            return False
    
    def update_files(self, source_dir: str) -> bool:
        """根据update_assets/files.json配置更新文件"""
        files_config_path = os.path.join("update_assets", "files.json")
        if not os.path.exists(files_config_path):
            print("未找到文件配置文件")
            return False
        
        try:
            with open(files_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            files_to_update = config.get("files", [])
            
            # 删除当前文件（根据配置）
            for file_path in files_to_update:
                current_file = os.path.join(os.getcwd(), file_path)
                if os.path.exists(current_file):
                    try:
                        os.remove(current_file)
                        print(f"删除文件: {current_file}")
                    except Exception as e:
                        print(f"删除文件失败 {current_file}: {e}")
            
            # 移动新文件到对应目录
            for file_path in files_to_update:
                source_file = os.path.join(source_dir, file_path)
                target_file = os.path.join(os.getcwd(), file_path)
                
                if os.path.exists(source_file):
                    try:
                        # 确保目标目录存在
                        os.makedirs(os.path.dirname(target_file), exist_ok=True)
                        
                        # 复制文件
                        shutil.copy2(source_file, target_file)
                        print(f"复制文件: {source_file} -> {target_file}")
                    except Exception as e:
                        print(f"复制文件失败 {source_file}: {e}")
                        continue
            
            return True
        except Exception as e:
            print(f"更新文件失败: {e}")
            return False
    
    def restart_application(self, script_path: str = "main.py"):
        """重新启动应用"""
        try:
            # 使用当前Python解释器重新启动应用
            os.execv(sys.executable, [sys.executable, script_path] + sys.argv[1:])
        except Exception as e:
            print(f"重启应用失败: {e}")
            # 如果os.execv失败，则尝试使用subprocess
            subprocess.Popen([sys.executable, script_path] + sys.argv[1:])
    
    def check_and_update(self, current_version: str, cache_dir: str = "dev_cache") -> bool:
        """检查并执行更新"""
        print("开始检查更新...")
        
        latest_version = self.get_latest_version()
        if not latest_version:
            print("获取最新版本信息失败")
            return False
        
        print(f"当前版本: {current_version}, 最新版本: {latest_version}")
        
        if not self.compare_versions(current_version, latest_version):
            print("当前已是最新版本")
            return False
        
        print("发现新版本，开始更新...")
        
        # 下载最新版本
        zip_path = self.download_latest_release(cache_dir)
        if not zip_path:
            print("下载最新版本失败")
            return False
        
        # 解压文件
        extract_to = os.path.join(cache_dir, "extracted")
        source_dir = self.extract_release(zip_path, extract_to)
        if not source_dir:
            print("解压文件失败")
            return False
        
        # 安装新依赖
        if not self.install_requirements(source_dir):
            print("安装新依赖失败")
            return False
        
        # 更新文件
        if not self.update_files(source_dir):
            print("更新文件失败")
            return False
        
        # 更新版本文件
        update_version_file(latest_version)
        
        print("更新完成！正在重启应用...")
        
        # 重启应用
        self.restart_application()
        
        return True


def get_app_version() -> str:
    """从version.json或其他配置文件中获取当前应用版本"""
    try:
        # 尝试从version.json中获取版本
        version_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "version.json")
        with open(version_file_path, 'r', encoding='utf-8') as f:
            version_data = json.load(f)
            return version_data.get("version", "v1.0.0")
    except Exception as e:
        print(f"读取版本信息失败: {e}")
    
    # 备用方案：尝试从main.py中获取版本
    try:
        main_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")
        with open(main_py_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 查找APP_VERSION定义
            import re
            match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)', content)
            if match:
                return match.group(1)
    except Exception as e:
        print(f"从main.py读取版本信息失败: {e}")
    
    # 默认返回
    return "v1.0.0"


def update_version_file(new_version: str):
    """更新version.json文件中的版本号"""
    try:
        version_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "version.json")
        with open(version_file_path, 'r', encoding='utf-8') as f:
            version_data = json.load(f)
        
        version_data["version"] = new_version
        
        with open(version_file_path, 'w', encoding='utf-8') as f:
            json.dump(version_data, f, indent=2, ensure_ascii=False)
        
        print(f"版本文件已更新为: {new_version}")
    except Exception as e:
        print(f"更新版本文件失败: {e}")


def run_update_check():
    """运行更新检查"""
    updater = Updater("HZBHZB1234", "LCTA-Limbus-company-transfer-auto")
    current_version = get_app_version()
    return updater.check_and_update(current_version)


# 使用示例
if __name__ == "__main__":
    run_update_check()