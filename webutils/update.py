import os
import re
import tempfile
import zipfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import suppress
import webFunc.GithubDownload as GithubDownload
from webFunc.GithubDownload import ReleaseInfo, ReleaseAsset, GitHubReleaseFetcher
from globalManagers.LogManager import LogManager
from globalManagers.pending_pip_ops import (
    apply_pending_pip_ops,
    load_pending_ops,
    save_pending_ops,
    _normalize_pkg_name,
    _normalize_spec,
    _parse_requirements,
    _pending_ops_default_path,
    _run_pip_install,
)
_log_manager = LogManager()
from .utils.net import download_with_github

APPLICATION_PATH = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# requirements 解析与延迟依赖操作（pending）实现在
# globalManagers/pending_pip_ops.py（纯标准库模块，供 start_webui.py 启动
# 早期钩子在加载任何第三方库之前直接导入）。本模块 re-export 同名符号，
# 保持既有调用方与测试兼容。
# ---------------------------------------------------------------------------

class Updater:
    def __init__(self, repo_owner: str, repo_name: str,
                 delete_old_files: bool = True,
                 use_proxy: bool = True,
                 only_stable: bool = True,
                 modal_id: str = ''):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.repo_config = [repo_owner, repo_name]
        self.delete_old_files = delete_old_files
        self.use_proxy = use_proxy
        self.only_stable = only_stable
        self.modal_id = modal_id

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
            _log_manager.log(f"获取最新版本失败: {e}")
            _log_manager.log_modal_process(f"获取最新版本失败: {e}", self.modal_id)
            return None
    
    @staticmethod
    def _version_tuple(version: str) -> tuple:
        """将版本号转换为整数元组用于逐段比较，容错 v 前缀与带后缀的段（取段首连续数字）"""
        version = version.lstrip('v')
        parts = []
        for seg in version.split('.'):
            m = re.match(r'\d+', seg)
            parts.append(int(m.group()) if m else 0)
        return tuple(parts)

    def compare_versions(self, current_version: str, latest_version: str) -> bool:
        """比较版本号，判断是否有新版本"""
        try:
            current = self._version_tuple(current_version)
            latest = self._version_tuple(latest_version)
            with suppress(Exception):
                return latest > current
            return True
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
            modal_id=self.modal_id,  # 传递modal_id
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
        """准备依赖更新（按包名比对当前与新 requirements.txt）。

        - 涉及依赖移除或版本变动（升级）：将整个依赖修改（卸载+升级+全新安装）
          写入 pending，延迟到下次启动、加载扩展包 DLL 之前统一执行（先卸载后安装）。
          当前进程内已加载 DLL 的扩展包（pythonnet/clr_loader 等）在此窗口前
          无法被卸载/替换，延迟机制从根上规避该问题。
        - 仅全新依赖：立即安装；失败仅记日志并跳过该依赖，不中断更新流程。
        """
        requirements_path = Path(source_dir) / "requirements.txt"
        if not os.path.exists(requirements_path):
            _log_manager.log("未找到requirements.txt文件")
            _log_manager.log_modal_process("未找到requirements.txt文件", self.modal_id)
            return False
        try:
            with open(APPLICATION_PATH / "requirements.txt", 'r', encoding='utf-8') as file:
                requirements_old = _parse_requirements(file.read())

            with open(requirements_path, 'r', encoding='utf-8') as file:
                requirements_new = _parse_requirements(file.read())

            old_names = set(requirements_old)
            new_names = set(requirements_new)

            # 被移除的依赖（delete_old_files=False 时保留旧依赖，不卸载）
            uninstall_names = sorted(old_names - new_names)
            if not self.delete_old_files:
                uninstall_names = []

            # 版本变动：同名但 spec 行不同（含 pin 变更；比较前归一化
            # 包名大小写与行首尾空白，避免仅格式差异误触发延迟）
            upgrade_specs = sorted(
                requirements_new[n]
                for n in (old_names & new_names)
                if _normalize_spec(requirements_old[n]) != _normalize_spec(requirements_new[n])
            )

            # 全新添加的依赖
            fresh_specs = sorted(requirements_new[n] for n in (new_names - old_names))

            if uninstall_names or upgrade_specs:
                pending = {
                    "uninstall": uninstall_names,
                    "install": sorted(set(upgrade_specs + fresh_specs)),
                }
                if save_pending_ops(pending, _pending_ops_default_path()):
                    _log_manager.log("依赖库存在移除/升级项，将延迟到下次启动时统一处理")
                    _log_manager.log_modal_process("依赖库存在移除/升级项，将延迟到下次启动时统一处理", self.modal_id)
                    _log_manager.log_modal_status(
                        "依赖变更（卸载/升级）将在下次启动时自动完成，请重启程序",
                        self.modal_id,
                    )
                else:
                    _log_manager.log("记录待执行依赖操作失败，请手动检查依赖")
                    _log_manager.log_modal_process("记录待执行依赖操作失败，请手动检查依赖", self.modal_id)
                return True

            if not fresh_specs:
                _log_manager.log("依赖无变化")
                _log_manager.log_modal_process("依赖无变化", self.modal_id)
                return True

            for spec in fresh_specs:
                _log_manager.log(f"执行安装 {spec}")
                _log_manager.log_modal_process(f"执行安装 {spec}", self.modal_id)
                if not _run_pip_install(spec):
                    _log_manager.log(f"安装依赖失败: {spec}，跳过该依赖继续更新")
                    _log_manager.log_modal_process(f"安装依赖失败: {spec}，跳过该依赖继续更新", self.modal_id)
            return True
        except Exception as e:
            _log_manager.log(f"准备依赖更新失败: {e}")
            _log_manager.log_modal_process(f"准备依赖更新失败: {e}", self.modal_id)
            _log_manager.log_error(e)
            return False
    
    def update_files(self, source_dir: Path) -> bool:
        """更新项目文件"""
        try:
            for item in APPLICATION_PATH.iterdir():
                if item.is_file():
                    item.unlink()
                    _log_manager.log(f"删除文件 {item.name}")
                    _log_manager.log_modal_process(f"删除文件 {item.name}", self.modal_id)
                elif item.is_dir() and not item.name == 'venv':
                    shutil.rmtree(item)
                    _log_manager.log(f"删除目录 {item.name}")
                    _log_manager.log_modal_process(f"删除目录 {item.name}", self.modal_id)
                    
            for item in source_dir.iterdir():
                if item.is_file():
                    shutil.copy(item, APPLICATION_PATH)
                    _log_manager.log(f"复制文件 {item.name}")
                    _log_manager.log_modal_process(f"复制文件 {item.name}", self.modal_id)
                elif item.is_dir():
                    shutil.copytree(item, APPLICATION_PATH / item.name)
                    _log_manager.log(f"复制目录 {item.name}")
                    _log_manager.log_modal_process(f"复制目录 {item.name}", self.modal_id)
            return True
        except Exception as e:
            _log_manager.log(f"更新文件失败: {e}")
            _log_manager.log_modal_process(f"更新文件失败: {e}", self.modal_id)
            _log_manager.log_error(e)
            return False
    
    def check_and_update(self, current_version: str, _cache_dir: str = None) -> bool:
        """检查并执行更新"""
        _log_manager.log("开始检查更新...")
        _log_manager.log_modal_process("开始检查更新...", self.modal_id)
        _log_manager.log_modal_status("正在检查更新...", self.modal_id)

        # 缓存置于应用目录外的临时目录：update_files 会清空应用目录，
        # 解压源若位于应用目录内会被先删除导致复制必然失败。
        _created_cache = not _cache_dir
        cache_dir = Path(_cache_dir) if _cache_dir else Path(tempfile.mkdtemp(prefix="lcta_update_"))
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
                _log_manager.log("获取最新版本信息失败")
                _log_manager.log_modal_process("获取最新版本信息失败", self.modal_id)
                return False
            
            latest_version = release_info.tag_name
            _log_manager.log(f"当前版本: {current_version}, 最新版本: {latest_version}")
            _log_manager.log_modal_process(f"当前版本: {current_version}, 最新版本: {latest_version}", self.modal_id)
            
            # 比较版本
            if not self.compare_versions(current_version, latest_version):
                _log_manager.log("当前已是最新版本")
                _log_manager.log_modal_process("当前已是最新版本", self.modal_id)
                return False
            
            _log_manager.log("发现新版本，开始更新...")
            _log_manager.log_modal_process("发现新版本，开始更新...", self.modal_id)
            _log_manager.log_modal_status("正在更新...", self.modal_id)
            _log_manager.log(f"更新内容: {release_info.name}")
            _log_manager.log_modal_process(f"更新内容: {release_info.name}", self.modal_id)
            if release_info.body:
                _log_manager.log(f"更新详情: {release_info.body[:200]}...")
                _log_manager.log_modal_process(f"更新详情: {release_info.body[:200]}...", self.modal_id)
            
            # 下载最新版本
            zip_path = self.download_latest_release(cache_dir, release_info)
            if not zip_path:
                _log_manager.log("下载最新版本失败")
                _log_manager.log_modal_process("下载最新版本失败", self.modal_id)
                return False
            
            # 解压文件
            extract_to = cache_dir / "LCTA-update"
            try:
                with zipfile.ZipFile(zip_path, "r") as zip_file:
                    zip_file.extractall(extract_to)
            except Exception as e:
                _log_manager.log(f"解压更新包失败: {e}")
                _log_manager.log_modal_process(f"解压更新包失败: {e}", self.modal_id)
                _log_manager.log_error(e)
                return False
            
            # 准备新依赖
            _log_manager.log("正在检查依赖更新...")
            _log_manager.log_modal_process("正在检查依赖更新...", self.modal_id)
            _log_manager.log_modal_status("正在准备依赖...", self.modal_id)
            # 记录 pending 的原始状态：install_requirements 会先写入新依赖操作，
            # 若 update_files 失败需还原，避免下次启动按新版本依赖卸载旧代码
            pending_path = _pending_ops_default_path()
            pending_before = load_pending_ops(pending_path)
            if not self.install_requirements(extract_to):
                _log_manager.log("准备新依赖失败")
                _log_manager.log_modal_process("准备新依赖失败", self.modal_id)
                # 继续执行，依赖更新不是致命错误
            
            # 更新文件
            _log_manager.log("正在更新文件...")
            _log_manager.log_modal_process("正在更新文件...", self.modal_id)
            _log_manager.log_modal_status("正在替换文件...", self.modal_id)
            if not self.update_files(extract_to):
                _log_manager.log("更新文件失败")
                _log_manager.log_modal_process("更新文件失败", self.modal_id)
                if load_pending_ops(pending_path) != pending_before:
                    save_pending_ops(pending_before, pending_path)
                    _log_manager.log("更新失败，已还原待执行依赖操作记录")
                return False
            
            _log_manager.log("更新完成！")
            _log_manager.log_modal_process("更新完成！", self.modal_id)
            pending_ops = load_pending_ops(pending_path)
            if pending_ops["uninstall"] or pending_ops["install"]:
                tip = "检测到待执行的依赖变更（卸载/升级），将在下次启动时自动完成，请重启程序"
                _log_manager.log(tip)
                _log_manager.log_modal_process(tip, self.modal_id)
                _log_manager.log_modal_status(tip, self.modal_id)
            else:
                _log_manager.log_modal_status("更新完成！", self.modal_id)
            
            return True
        finally:
            # 清理缓存目录（成功与失败均清理）；仅清理本函数自建的临时目录
            if _created_cache:
                try:
                    shutil.rmtree(cache_dir)
                except:
                    pass

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
            _log_manager.log(f"获取最新版本信息成功: {release_info.tag_name}")
            _log_manager.log_modal_process(f"获取最新版本信息成功: {release_info.tag_name}", self.modal_id)
            
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
            _log_manager.log(f"检查更新失败: {e}")
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

def run_update_check(only_stable: bool = True, modal_id: str = ''):
    """运行更新检查"""
    updater = Updater("HZBHZB1234", "LCTA-Limbus-company-transfer-auto",
                      only_stable=only_stable, modal_id=modal_id)
    current_version = get_app_version()
    if not current_version:
        _log_manager.log("无法获取当前版本信息，请检查版本文件或配置文件")
    return updater.check_and_update(current_version)


# 使用示例
if __name__ == "__main__":
    run_update_check(only_stable=True)