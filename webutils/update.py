import os
import zipfile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import webFunc.GithubDownload as GithubDownload
from webFunc.GithubDownload import ReleaseInfo, ReleaseAsset, GitHubReleaseFetcher
from webutils.log_manage import *
from .log_manage import LogManager
from .functions import download_with_github

APPLICATION_PATH = Path(__file__).parent.parent

class Updater:
    def __init__(self, repo_owner: str, repo_name: str, 
                 delete_old_files: bool = True, 
                 logger_: LogManager = LogManager(),
                 use_proxy: bool = True,
                 only_stable: bool = True):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.repo_config = [repo_owner, repo_name]
        self.delete_old_files = delete_old_files
        self.logger_ = logger_
        self.use_proxy = use_proxy
        self.only_stable = only_stable

    def fetcher(self) -> GitHubReleaseFetcher:
        GithubDownload.GithubRequester.update_config(self.use_proxy)
        return GithubDownload.GithubRequester

    def get_latest_version(self) -> Optional[str]:
        """获取最新版本号"""
        try:
            if self.only_stable:
                release_info = self.fetcher().get_latest_release(
                    *self.repo_config
                )
            else:
                release_info = self.fetcher().get_latest_pre_release(
                    *self.repo_config
                )
                
            if release_info:
                return release_info.tag_name
            return None
        except Exception as e:
            self.logger_.log(f"获取最新版本失败: {e}")
            self.logger_.log_modal_process(f"获取最新版本失败: {e}")
            return None
    
    def compare_versions(self, current_version: str, latest_version: str) -> bool:
        """比较版本号，判断是否有新版本"""
        try:
            # 去掉版本号前缀 v
            current = current_version.lstrip('v')
            latest = latest_version.lstrip('v')
            
            return latest != current
        except:
            return False
    
    def download_latest_release(self, cache_dir: Path, release_info: ReleaseInfo) -> Optional[str]:
        """下载最新版本源码"""
        asset = self.get_release_asset(release_info)
        if not asset:
            return None

        # 确保缓存目录存在
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 下载文件
        zip_path = cache_dir / "LCTA-update.zip"

        # 使用download_with_github下载
        success = download_with_github(
            asset=asset,
            save_path=zip_path,
            logger_=self.logger_,
            modal_id=None,  # 没有模态窗口
            progress_=[0, 100],
            use_proxy=self.use_proxy
        )

        if success:
            return zip_path
        else:
            return None

    def get_release_asset(self, release_info: ReleaseInfo) -> Optional[ReleaseAsset]:
        """获取发布版本的ReleaseAsset对象"""
        # 优先从assets中查找zip文件
        zip_assets = release_info.get_asset_by_name('LCTA-update.zip')
        return zip_assets
    
    def install_requirements(self, source_dir: str) -> bool:
        """根据新的requirements.txt安装依赖"""
        requirements_path = source_dir / "requirements.txt"
        if not os.path.exists(requirements_path):
            self.logger_.log("未找到requirements.txt文件")
            self.logger_.log_modal_process("未找到requirements.txt文件")
            return False
        try:
            with open(APPLICATION_PATH / "requirements.txt", 'r', encoding='utf-8') as file:
                requirements_old=file.read().strip().split('\n')

            with open(requirements_path, 'r', encoding='utf-8') as file:
                requirements_new=file.read().strip().split('\n')

            for i in set(requirements_new) - set(requirements_old):
                try:
                    self.logger_.log(f"执行安装 {i}")
                    self.logger_.log_modal_process(f"执行安装 {i}")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", i])
                except subprocess.CalledProcessError as e:
                    self.logger_.log(f"安装依赖错误: {e}")
                    self.logger_.log_modal_process(f"安装依赖错误: {e}")
                    self.logger_.log(f"退出码: {e.returncode}，错误输出{e.stderr}")
                    self.logger_.log_modal_process(f"退出码: {e.returncode}，错误输出{e.stderr}")

            if not self.delete_old_files:
                return True
            
            for i in set(requirements_old) - set(requirements_new):
                try:
                    self.logger_.log(f"执行卸载 {i}")
                    self.logger_.log_modal_process(f"执行卸载 {i}")
                    subprocess.check_call([sys.executable, "-m", "pip", "uninstall", i])
                except subprocess.CalledProcessError as e:
                    self.logger_.log(f"安装依赖错误: {e}")
                    self.logger_.log_modal_process(f"安装依赖错误: {e}")
                    self.logger_.log(f"退出码: {e.returncode}，错误输出{e.stderr}")
                    self.logger_.log_modal_process(f"退出码: {e.returncode}，错误输出{e.stderr}")
                return True
        except Exception as e:
            self.logger_.log(f"安装依赖失败: {e}")
            self.logger_.log_modal_process(f"安装依赖失败: {e}")
            self.logger_.log_error(e)
            return False
    
    def update_files(self, source_dir: Path) -> bool:
        """更新项目文件"""
        try:
            for item in APPLICATION_PATH.iterdir():
                if item.is_file():
                    item.unlink()
                    self.logger_.log(f"删除文件 {item.name}")
                    self.logger_.log_modal_process(f"删除文件 {item.name}")
                elif item.is_dir() and not item.name == 'venv':
                    shutil.rmtree(item)
                    self.logger_.log(f"删除目录 {item.name}")
                    self.logger_.log_modal_process(f"删除目录 {item.name}")
                    
            for item in source_dir.iterdir():
                if item.is_file():
                    shutil.copy(item, APPLICATION_PATH)
                    self.logger_.log(f"复制文件 {item.name}")
                    self.logger_.log_modal_process(f"复制文件 {item.name}")
                elif item.is_dir():
                    shutil.copytree(item, APPLICATION_PATH / item.name)
                    self.logger_.log(f"复制目录 {item.name}")
                    self.logger_.log_modal_process(f"复制目录 {item.name}")
            return True
        except Exception as e:
            self.logger_.log(f"更新文件失败: {e}")
            self.logger_.log_modal_process(f"更新文件失败: {e}")
            self.logger_.log_error(e)
            return False
    
    def restart_application(self):
        """重新启动应用"""
        try:
            os.execv('launcher.exe')
        except Exception as e:
            self.logger_.log(f"重启应用失败: {e}")
            self.logger_.log_modal_process(f"重启应用失败: {e}")
            self.logger_.log_error(e)
    
    def check_and_update(self, current_version: str, _cache_dir: str = "updateCache") -> bool:
        """检查并执行更新"""
        self.logger_.log("开始检查更新...")
        self.logger_.log_modal_process("开始检查更新...")
        self.logger_.log_modal_status("正在检查更新...")
        
        cache_dir = APPLICATION_PATH / _cache_dir
        
        # 清理缓存目录
        try:
            if cache_dir.exists():
                shutil.rmtree(str(cache_dir))
        except Exception as e:
            self.logger_.log(f"清理缓存目录失败: {e}")
            self.logger_.log_modal_process(f"清理缓存目录失败: {e}")
            self.logger_.log_error(e)
        
        # 根据only_stable参数决定获取最新版本还是稳定版本
        if self.only_stable:
            release_info = self.fetcher().get_latest_release(
                *self.repo_config
            )
        else:
            release_info = self.fetcher().get_latest_pre_release(
                *self.repo_config
            )
            
        if not release_info:
            self.logger_.log("获取最新版本信息失败")
            self.logger_.log_modal_process("获取最新版本信息失败")
            return False
        
        latest_version = release_info.tag_name
        self.logger_.log(f"当前版本: {current_version}, 最新版本: {latest_version}")
        self.logger_.log_modal_process(f"当前版本: {current_version}, 最新版本: {latest_version}")
        
        # 比较版本
        if not self.compare_versions(current_version, latest_version):
            self.logger_.log("当前已是最新版本")
            self.logger_.log_modal_process("当前已是最新版本")
            return False
        
        self.logger_.log("发现新版本，开始更新...")
        self.logger_.log_modal_process("发现新版本，开始更新...")
        self.logger_.log_modal_status("正在更新...")
        self.logger_.log(f"更新内容: {release_info.name}")
        self.logger_.log_modal_process(f"更新内容: {release_info.name}")
        if release_info.body:
            self.logger_.log(f"更新详情: {release_info.body[:200]}...")
            self.logger_.log_modal_process(f"更新详情: {release_info.body[:200]}...")
        
        # 下载最新版本
        zip_path = self.download_latest_release(cache_dir, release_info)
        if not zip_path:
            self.logger_.log("下载最新版本失败")
            self.logger_.log_modal_process("下载最新版本失败")
            return False
        
        # 解压文件
        extract_to = cache_dir / "LCTA-update"
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_file:
                zip_file.extractall(extract_to)
        except Exception as e:
            self.logger_.log(f"解压更新包失败: {e}")
            self.logger_.log_modal_process(f"解压更新包失败: {e}")
            self.logger_.log_error(e)
            return False
        
        # 安装新依赖
        self.logger_.log("正在检查依赖更新...")
        self.logger_.log_modal_process("正在检查依赖更新...")
        self.logger_.log_modal_status("正在安装新依赖...")
        if not self.install_requirements(extract_to):
            self.logger_.log("安装新依赖失败")
            self.logger_.log_modal_process("安装新依赖失败")
            # 继续执行，依赖更新不是致命错误
        
        # 更新文件
        self.logger_.log("正在更新文件...")
        self.logger_.log_modal_process("正在更新文件...")
        self.logger_.log_modal_status("正在替换文件...")
        if not self.update_files(extract_to):
            self.logger_.log("更新文件失败")
            self.logger_.log_modal_process("更新文件失败")
            return False
        
        self.logger_.log("更新完成！")
        self.logger_.log_modal_process("更新完成！")
        self.logger_.log_modal_status("更新完成！")
        
        # 清理缓存
        try:
            shutil.rmtree(cache_dir)
        except:
            pass

        self.restart_application()
        
        return True

    def check_for_updates(self, current_version: str) -> Dict[str, Any]:
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
                    "download_url": str,          # 下载链接
                    "release_url": str,           # release页面URL
                    "prerelease": bool,           # 是否为预发布版本
                    "draft": bool,                # 是否为草稿
                    "asset_count": int            # 附件数量
                }
        """
        try:
            # 根据only_stable参数决定获取最新版本还是稳定版本
            if self.only_stable:
                release_info = self.fetcher().get_latest_release(
                    *self.repo_config
                )
            else:
                release_info = self.fetcher().get_latest_pre_release(
                    *self.repo_config
                )
                
            if not release_info:
                raise Exception("无法获取release信息")
            self.logger_.log(f"获取最新版本信息成功: {release_info.tag_name}")
            self.logger_.log_modal_process(f"获取最新版本信息成功: {release_info.tag_name}")
            
            latest_version = release_info.tag_name
            has_update = self.compare_versions(current_version, latest_version)
            
            # 获取ReleaseAsset和大小
            asset = self.get_release_asset(release_info)
            download_url = ""
            size = 0
            
            if asset:
                download_url = asset.download_url
                size = asset.size
            
            # 构建release页面URL
            release_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/tag/{latest_version}"
            
            return {
                "has_update": has_update,
                "latest_version": latest_version,
                "title": release_info.name,
                "body": release_info.body,
                "published_at": release_info.published_at,
                "size": size,
                "download_url": download_url or "",
                "release_url": release_url,
                "prerelease": release_info.prerelease,
                "draft": release_info.draft,
                "asset_count": len(release_info.assets)
            }
        except Exception as e:
            self.logger_.log(f"检查更新失败: {e}")
            # 返回默认值
            return {
                "has_update": False,
                "latest_version": "",
                "title": "",
                "body": "",
                "published_at": "",
                "size": 0,
                "download_url": "",
                "release_url": "",
                "prerelease": False,
                "draft": False,
                "asset_count": 0
            }


def get_app_version() -> str:
    """从获取当前应用版本"""
    return os.getenv("__version__", "0.0.0")

def run_update_check(logger_: LogManager = LogManager(), only_stable: bool = True):
    """运行更新检查"""
    updater = Updater("HZBHZB1234", "LCTA-Limbus-company-transfer-auto", 
                      logger_=logger_, only_stable=only_stable)
    current_version = get_app_version()
    if not current_version:
        logger_.log("无法获取当前版本信息，请检查版本文件或配置文件")
    return updater.check_and_update(current_version)


# 使用示例
if __name__ == "__main__":
    run_update_check(only_stable=True)