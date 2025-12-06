import os
import json
import requests
import zipfile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Callable
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class Updater:
    def __init__(self, repo_owner: str, repo_name: str, delete_old_files: bool = True, output_func: Callable[[str], None] = print):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.delete_old_files = delete_old_files
        self.output_func = output_func
        self.api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        self.session = self._create_session()
        
    def _create_session(self):
        """创建一个带有重试策略的会话"""
        session = requests.Session()
        
        # 定义重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        # 创建适配器并挂载到会话
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 禁用SSL验证以避免证书问题
        session.verify = False
        
        # 禁用警告信息
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        return session
        
    def get_latest_version(self) -> Optional[str]:
        """获取最新版本号"""
        try:
            response = self.session.get(self.api_url)
            response.raise_for_status()
            data = response.json()
            return data.get('tag_name')
        except Exception as e:
            self.output_func(f"获取最新版本失败: {e}")
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
            response = self.session.get(self.api_url)
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
                self.output_func("未找到源码下载链接")
                return None
            
            # 确保缓存目录存在
            os.makedirs(cache_dir, exist_ok=True)
            
            # 下载文件
            zip_path = os.path.join(cache_dir, "latest_release.zip")
            self.output_func(f"正在下载: {download_url}")
            
            response = self.session.get(download_url)
            response.raise_for_status()
            
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            return zip_path
        except Exception as e:
            self.output_func(f"下载最新版本失败: {e}")
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
            self.output_func(f"解压文件失败: {e}")
            return None
    
    def install_requirements(self, source_dir: str) -> bool:
        """根据新的requirements.txt安装依赖"""
        requirements_path = os.path.join(source_dir, "requirements.txt")
        if not os.path.exists(requirements_path):
            self.output_func("未找到requirements.txt文件")
            return False
        try:
            with open('requirements.txt', 'r', encoding='utf-8') as file:
                requirements_old=file.read().strip().split('\n')

            with open(requirements_path, 'r', encoding='utf-8') as file:
                requirements_new=file.read().strip().split('\n')

            for i in set(requirements_new) - set(requirements_old):
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", i])
                except subprocess.CalledProcessError as e:
                    self.output_func(f"安装依赖失败: {e}")
                    raise

            if not self.delete_old_files:
                return True
            
            for i in set(requirements_old) - set(requirements_new):
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "uninstall", i])
                except subprocess.CalledProcessError as e:
                    self.output_func(f"卸载依赖失败: {e}")
            return True
        except Exception as e:
            try:
                # 使用当前Python环境安装依赖
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_path])
                return True
            except subprocess.CalledProcessError as e:
                self.output_func(f"安装依赖失败: {e}")
                return False
    
    def update_files(self, source_dir: str) -> bool:
        """根据update_assets/files.json配置更新文件"""
        files_config_path = os.path.join("update_assets", "files.json")
        if not os.path.exists(files_config_path):
            self.output_func("未找到文件配置文件")
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
                        self.output_func(f"删除文件: {current_file}")
                    except Exception as e:
                        self.output_func(f"删除文件失败 {current_file}: {e}")
            
            for files in os.walk(source_dir):
                for file in files[2]:
                    rel_dir = os.path.relpath(files[0], source_dir)
                    rel_file = os.path.join(rel_dir, file) if rel_dir != '.' else file
                    src_file_path = os.path.join(files[0], file)
                    dest_file_path = os.path.join(os.getcwd(), rel_file)
                    
                    # 确保目标目录存在
                    os.makedirs(os.path.dirname(dest_file_path), exist_ok=True)
                    
                    shutil.copy2(src_file_path, dest_file_path)
                    self.output_func(f"更新文件: {dest_file_path}")
            
            return True
        except Exception as e:
            self.output_func(f"更新文件失败: {e}")
            return False
    
    def restart_application(self, script_path: str = "main.py"):
        """重新启动应用"""
        try:
            # 使用当前Python解释器重新启动应用
            os.execv(sys.executable, [sys.executable, script_path] + sys.argv[1:])
        except Exception as e:
            self.output_func(f"重启应用失败: {e}")
            # 如果os.execv失败，则尝试使用subprocess
            subprocess.Popen([sys.executable, script_path] + sys.argv[1:])
    
    def check_and_update(self, current_version: str, cache_dir: str = "dev_cache") -> bool:
        """检查并执行更新"""
        self.output_func("开始检查更新...")

        try:
            shutil.rmtree(cache_dir)
        except FileNotFoundError:
            pass
        
        latest_version = self.get_latest_version()
        if not latest_version:
            self.output_func("获取最新版本信息失败")
            return False
        
        self.output_func(f"当前版本: {current_version}, 最新版本: {latest_version}")
        
        if not self.compare_versions(current_version, latest_version):
            self.output_func("当前已是最新版本")
            return False
        
        self.output_func("发现新版本，开始更新...")
        
        # 下载最新版本
        zip_path = self.download_latest_release(cache_dir)
        if not zip_path:
            self.output_func("下载最新版本失败")
            return False
        
        # 解压文件
        extract_to = os.path.join(cache_dir, "extracted")
        source_dir = self.extract_release(zip_path, extract_to)
        if not source_dir:
            self.output_func("解压文件失败")
            return False
        
        # 安装新依赖
        if not self.install_requirements(source_dir):
            self.output_func("安装新依赖失败")
            return False
        
        # 更新文件
        if not self.update_files(source_dir):
            self.output_func("更新文件失败")
            return False
        
        # 更新版本文件
        update_version_file(latest_version, self.output_func)
        
        self.output_func("更新完成！正在重启应用...")
        
        # 重启应用
        self.restart_application()
        
        return True

    def check_for_updates(self, current_version: str) -> dict:
        """
        检查是否存在更新，如果存在则返回更新包大小、release标题与详情、发布时间
        
        Args:
            current_version (str): 当前版本号
            
        Returns:
            dict: 包含更新信息的字典
                {
                    "has_update": bool,           # 是否有更新
                    "latest_version": str,        # 最新版本号
                    "title": str,                 # release标题
                    "body": str,                  # release详情
                    "published_at": str,          # 发布时间
                    "size": int,                  # 更新包大小(字节)
                    "download_url": str           # 下载链接
                }
        """
        try:
            response = self.session.get(self.api_url)
            response.raise_for_status()
            data = response.json()
            
            latest_version = data.get('tag_name', '')
            
            # 检查是否有更新
            has_update = self.compare_versions(current_version, latest_version)
            
            # 获取下载信息
            download_url = data.get('zipball_url') or ''
            size = 0
            
            # 如果有assets，尝试从中获取更准确的大小信息
            assets = data.get('assets', [])
            if assets:
                # 查找zip文件的asset
                for asset in assets:
                    if asset.get('name', '').endswith('.zip'):
                        download_url = asset.get('browser_download_url', download_url)
                        size = asset.get('size', size)
                        break
            
            # 如果没有从assets获取到大小信息，则使用zipball_url
            if not size and download_url:
                # 发送HEAD请求获取文件大小
                try:
                    head_response = self.session.head(download_url)
                    if head_response.status_code == 200:
                        size_str = head_response.headers.get('Content-Length', '0')
                        size = int(size_str)
                except Exception:
                    pass  # 忽略获取大小失败的情况
            
            return {
                "has_update": has_update,
                "html_url": self.api_url.replace('api.', '').replace('/repos', ''),
                "latest_version": latest_version,
                "title": data.get('name', ''),
                "body": data.get('body', ''),
                "published_at": data.get('published_at', ''),
                "size": size,
                "download_url": download_url
            }
        except Exception as e:
            self.output_func(f"检查更新失败: {e}")
            # 返回默认值
            return {
                "has_update": False,
                "latest_version": "",
                "title": "",
                "body": "",
                "published_at": "",
                "size": 0,
                "download_url": ""
            }


def get_app_version() -> str:
    """从version.json或其他配置文件中获取当前应用版本"""
    try:
        # 尝试从version.json中获取版本
        version_file_path = os.path.join(os.getenv('path_'), os.path.dirname(os.path.dirname(__file__)), "version.json")
        with open(version_file_path, 'r', encoding='utf-8') as f:
            version_data = json.load(f)
            return version_data.get("version", None)
    except Exception as e:
        print(f"读取版本信息失败: {e}")
    
    # 默认返回
    return None


def update_version_file(new_version: str, output_func: Callable[[str], None] = print):
    """更新version.json文件中的版本号"""
    try:
        version_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "version.json")
        with open(version_file_path, 'r', encoding='utf-8') as f:
            version_data = json.load(f)
        
        version_data["version"] = new_version
        
        with open(version_file_path, 'w', encoding='utf-8') as f:
            json.dump(version_data, f, indent=2, ensure_ascii=False)
        
        output_func(f"版本文件已更新为: {new_version}")
    except Exception as e:
        output_func(f"更新版本文件失败: {e}")


def run_update_check(output_func: Callable[[str], None] = print):
    """运行更新检查"""
    updater = Updater("HZBHZB1234", "LCTA-Limbus-company-transfer-auto", output_func=output_func)
    current_version = get_app_version()
    if not current_version:
        output_func("无法获取当前版本信息，请检查版本文件或配置文件")
    return updater.check_and_update(current_version)


# 使用示例
if __name__ == "__main__":
    run_update_check()