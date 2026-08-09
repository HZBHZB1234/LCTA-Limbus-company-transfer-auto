import json
import os
import re
import tempfile
import zipfile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from contextlib import suppress
import webFunc.GithubDownload as GithubDownload
from webFunc.GithubDownload import ReleaseInfo, ReleaseAsset, GitHubReleaseFetcher
from globalManagers.LogManager import LogManager
_log_manager = LogManager()
from .utils.net import download_with_github

APPLICATION_PATH = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# requirements 解析与延迟依赖操作（pending）
#
# 更新涉及依赖卸载/版本变动时，立即执行 pip 操作会在 Windows 上失败：
# pythonnet/clr_loader/pywebview 等扩展包 DLL 已被当前进程加载，文件无法
# 删除或替换。因此此类依赖修改统一写入 pending 文件，延迟到下一次启动、
# 加载任何扩展包 DLL 之前由 apply_pending_pip_ops() 执行（start_webui.py
# init_env() 启动早期钩子，此时进程尚未加载扩展包 DLL，卸载/升级均可成功）。
# ---------------------------------------------------------------------------

_PENDING_OPS_FILENAME = "pending_pip_ops.json"

_REQUIREMENT_PACKAGE_RE = re.compile(r"^\s*([A-Za-z0-9._-]+)")
_REQUIREMENT_NORMALIZE_RE = re.compile(r"[-_.]+")


def _normalize_pkg_name(name: str) -> str:
    """PEP 503 归一化：小写、-_. 视为等价"""
    return _REQUIREMENT_NORMALIZE_RE.sub("-", name).lower()


def _parse_requirements(text: str) -> Dict[str, str]:
    """解析 requirements 文本为 {归一化包名: 清理后的 spec 行}。

    跳过空行、`#` 行内注释（spec 以去注释后的内容为准）、
    选项行（-r/-e/--…）与裸 URL 行。
    """
    result: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        if line.startswith(("http://", "https://", "git+")):
            continue
        m = _REQUIREMENT_PACKAGE_RE.match(line)
        if not m:
            continue
        result[_normalize_pkg_name(m.group(1))] = line
    return result


def _pending_ops_default_path() -> Path:
    """pending 记录存放于 %LOCALAPPDATA%/LCTA/ 下。

    不能放在应用目录：更新文件替换（update_files）会清空应用目录。
    """
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "LCTA" / _PENDING_OPS_FILENAME
    return Path(tempfile.gettempdir()) / "LCTA" / _PENDING_OPS_FILENAME


def load_pending_ops(path: Optional[Path] = None) -> Dict[str, List[str]]:
    """读取待执行的依赖操作记录，异常或结构不符时返回空结构。"""
    p = path or _pending_ops_default_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        uninstall = data.get("uninstall", [])
        install = data.get("install", [])
        return {
            "uninstall": list(uninstall) if isinstance(uninstall, list) else [],
            "install": list(install) if isinstance(install, list) else [],
        }
    except Exception:
        return {"uninstall": [], "install": []}


def save_pending_ops(ops: Dict[str, List[str]], path: Optional[Path] = None) -> bool:
    """写入待执行的依赖操作记录（有序去重）。

    列表均为空时删除记录文件（而非写空文件）。失败返回 False 并记日志。
    """
    p = path or _pending_ops_default_path()
    clean = {
        "uninstall": list(dict.fromkeys(ops.get("uninstall", []))),
        "install": list(dict.fromkeys(ops.get("install", []))),
    }
    try:
        if not clean["uninstall"] and not clean["install"]:
            if p.exists():
                p.unlink()
            return True
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        _log_manager.log(f"保存待执行依赖操作失败: {e}")
        return False


def _run_pip(args: List[str]) -> bool:
    """执行 pip 子命令，失败记日志并返回 False。"""
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip"] + args, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        _log_manager.log(f"pip {' '.join(args)} 失败: {e}")
        err = (e.stderr or b"").decode("utf-8", errors="replace").strip()
        _log_manager.log(f"退出码: {e.returncode}，错误输出: {err or '无'}")
        return False


def _run_pip_install(spec: str) -> bool:
    return _run_pip(["install", spec])


def _run_pip_uninstall(name: str) -> bool:
    # 不带版本号：兼容旧版 pip（pip uninstall 不接受版本 specifier）
    return _run_pip(["uninstall", name, "-y"])


def apply_pending_pip_ops(path: Optional[Path] = None) -> bool:
    """启动早期执行待处理的依赖操作（先卸载后安装）。

    必须在加载任何扩展包 DLL 之前调用（start_webui.py init_env() 启动钩子）：
    此时进程尚未加载扩展模块 DLL，被锁定而无法在更新会话中卸载/替换的包
    （pythonnet/clr_loader 等）可以正常处理。全部成功后删除记录；部分失败
    保留剩余项，记日志并在下次启动时重试。异常不外抛，不阻塞启动。
    """
    ops = load_pending_ops(path)
    if not ops["uninstall"] and not ops["install"]:
        return True
    for name in list(ops["uninstall"]):
        if _run_pip_uninstall(name):
            ops["uninstall"].remove(name)
    for spec in list(ops["install"]):
        if _run_pip_install(spec):
            ops["install"].remove(spec)
    if not ops["uninstall"] and not ops["install"]:
        try:
            (path or _pending_ops_default_path()).unlink(missing_ok=True)
            return True
        except Exception as e:
            _log_manager.log(f"删除待执行依赖操作记录失败: {e}")
            return False
    save_pending_ops(ops, path)
    _log_manager.log(
        f"仍有依赖操作未完成，将在下次启动时重试: "
        f"卸载 {ops['uninstall']}，安装 {ops['install']}"
    )
    return False

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

            # 版本变动：同名但 spec 行不同（含 pin 变更）
            upgrade_specs = sorted(
                requirements_new[n]
                for n in (old_names & new_names)
                if requirements_old[n] != requirements_new[n]
            )

            # 全新添加的依赖
            fresh_specs = sorted(requirements_new[n] for n in (new_names - old_names))

            if uninstall_names or upgrade_specs:
                pending = {
                    "uninstall": uninstall_names,
                    "install": sorted(set(upgrade_specs + fresh_specs)),
                }
                if save_pending_ops(pending):
                    _log_manager.log("依赖库存在移除/升级项，将延迟到下次启动时统一处理")
                    _log_manager.log_modal_process("依赖库存在移除/升级项，将延迟到下次启动时统一处理", self.modal_id)
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
                return False
            
            _log_manager.log("更新完成！")
            _log_manager.log_modal_process("更新完成！", self.modal_id)
            _log_manager.log_modal_status("更新完成！", self.modal_id)
            
            return True
        finally:
            # 清理缓存目录（成功与失败均清理）
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