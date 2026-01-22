import requests
import warnings
import time
import threading
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from copy import deepcopy
from contextlib import contextmanager, suppress
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class ReleaseAsset:
    """Release资源文件信息"""
    name: str
    size: int
    download_url: str
    content_type: str
    download_count: int
    proxys: 'ProxyManager'
    
    @property
    def formatted_size(self) -> str:
        """格式化文件大小"""
        if self.size == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        size_bytes = self.size
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024
            i += 1
        return f"{size_bytes:.2f} {size_names[i]}"


@dataclass
class ReleaseInfo:
    """Release完整信息"""
    repo_owner: str
    repo_name: str
    tag_name: str
    name: str
    body: str
    published_at: str
    prerelease: bool
    draft: bool
    assets: List[ReleaseAsset]
    proxys: 'ProxyManager'
    
    def get_asset_by_name(self, name: str) -> Optional[ReleaseAsset]:
        """通过名称查找资源文件"""
        for asset in self.assets:
            if asset.name == name:
                return asset
        return None
    
    def get_assets_by_extension(self, extension: str) -> List[ReleaseAsset]:
        """通过扩展名筛选资源文件"""
        return [asset for asset in self.assets if asset.name.endswith(extension)]
    
    @property
    def source_zip_url(self) -> str:
        """源码ZIP压缩包URL"""
        return f"https://github.com/{self.repo_owner}/{self.repo_name}/archive/refs/tags/{self.tag_name}.zip"
    
    @property
    def source_tar_url(self) -> str:
        """源码TAR.GZ压缩包URL"""
        return f"https://github.com/{self.repo_owner}/{self.repo_name}/archive/refs/tags/{self.tag_name}.tar.gz"


class ProxyManager:
    """简化的代理管理器"""
    
    def __init__(self):
        self.proxies: List[str] = []
        self.current_index: int = 0
        self.last_successful_proxy: Optional[str] = None  # 记录上一次成功的代理
        self._initialize_proxies()
    
    def _initialize_proxies(self):
        """初始化代理列表"""
        # 添加默认代理
        self.proxies.append("https://gh-proxy.org/")
        
        # 尝试从API获取代理列表
        try:
            self._fetch_proxies_from_api()
        except Exception as e:
            print(f"从API获取代理列表失败，使用默认代理: {e}")
    
    def _fetch_proxies_from_api(self):
        """从API获取代理列表"""
        api_url = "https://api.akams.cn/github"
        try:
            response = requests.get(api_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200:
                nodes_data = data.get("data", [])
                new_proxies = []
                
                for node_data in nodes_data:
                    url = node_data.get("url", "").rstrip('/') + '/'
                    # 只添加有效的HTTPS代理
                    if url.startswith("https://") and "gh-proxy.org" not in url:
                        new_proxies.append(url)
                
                if new_proxies:
                    self.proxies.extend(new_proxies)
                    print(f"成功加载 {len(new_proxies)} 个代理")
                    
        except Exception as e:
            print(f"获取代理列表失败: {e}")
    
    def set_proxy_by_url(self, proxy_url: str):
        """根据代理URL设置当前代理，并记录为成功代理"""
        if proxy_url in self.proxies:
            self.current_index = self.proxies.index(proxy_url)
            self.last_successful_proxy = proxy_url  # 记录成功使用的代理
            return True
        return False
    
    def get_proxies(self) -> List[str]:
        """获取优先代理列表：上一次成功代理优先，然后是其他代理"""
        result = self.proxies[self.current_index:] + self.proxies[:self.current_index]
        
        return result

class GitHubReleaseFetcher:
    """
    简化的GitHub Release信息获取器
    现在可以在请求时指定仓库，提高复用性
    """
    
    def __init__(self, use_proxy: bool = True, ignore_ssl: bool = False):
        """
        初始化获取器
        
        Args:
            use_proxy: 是否使用代理加速API请求
            ignore_ssl: 是否忽略SSL证书错误
        """
        self.use_proxy = use_proxy
        self.ignore_ssl = ignore_ssl
        
        # GitHub API基础URL
        self.github_api_base = "https://api.github.com"
        
        # 代理管理器
        self.proxy_manager = ProxyManager() if use_proxy else None
        
        # 配置requests会话
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Release-Fetcher/1.0'
        })
        
        # 线程池配置
        self.max_workers = 3  # 最大并发线程数
        self.request_timeout = 8  # 单个请求超时时间
        
        # 忽略SSL警告
        if self.ignore_ssl:
            self.session.verify = False
            warnings.filterwarnings('ignore', message='Unverified HTTPS request')
    
    def update_config(self, use_proxy: bool = True, ignore_ssl: bool = False):
        self.use_proxy = use_proxy
        self.ignore_ssl = ignore_ssl
    
    def _build_api_url(self, repo_owner: str, repo_name: str, endpoint: str, proxy_url: str = "") -> str:
        """构建API URL"""
        api_url = f"{self.github_api_base}/repos/{repo_owner}/{repo_name}/{endpoint}"
        
        # 如果使用代理
        if proxy_url:
            api_url = f"{proxy_url}{api_url}"
            
        return api_url
    
    def _request_with_proxy(self, repo_owner: str, repo_name: str, endpoint: str, 
                          proxy_url: str, timeout: float = None) -> Optional[Dict[str, Any]]:
        """使用指定代理发送请求"""
        if timeout is None:
            timeout = self.request_timeout
            
        api_url = self._build_api_url(repo_owner, repo_name, endpoint, proxy_url)
        
        try:
            response = self.session.get(api_url, timeout=timeout)
            if response.status_code == 200:
                return response.json(), proxy_url
            else:
                print(f"代理 {proxy_url} 返回状态码: {response.status_code}")
                return None, proxy_url
                
        except Exception as e:
            print(f"代理 {proxy_url} 请求失败: {e}")
            return None, proxy_url
    
    def _make_request(self, repo_owner: str, repo_name: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        发送请求，使用线程池有限并发尝试代理
        
        Returns:
            JSON响应数据，如果失败则返回None
        """
        if not self.use_proxy or not self.proxy_manager:
            # 不使用代理，直接请求
            api_url = self._build_api_url(repo_owner, repo_name, endpoint)
            try:
                response = self.session.get(api_url, timeout=30, **kwargs)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"直接请求失败: {e}")
                return None
        
        # 使用优先代理列表
        proxies = self.proxy_manager.get_proxies()
        
        if not proxies:
            print("没有可用的代理")
            return None
        
        print(f"使用线程池（最大 {self.max_workers} 个线程）尝试 {len(proxies)} 个代理...")
        
        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        @contextmanager
        def auto_shutdown_pool():
            yield
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except:
                for _future in future:
                    with suppress(Exception):
                        if not _future.done():
                            _future.cancel()
                executor.shutdown(wait=False)
        
        # 创建线程池
        with auto_shutdown_pool():
            # 提交所有代理请求任务
            future_to_proxy = {}
            for proxy_url in proxies:
                future = executor.submit(
                    self._request_with_proxy, 
                    repo_owner, repo_name, endpoint, proxy_url
                )
                future_to_proxy[future] = proxy_url
            
            try:
                # 遍历完成的任务
                for future in as_completed(future_to_proxy):
                    try:
                        data, used_proxy = future.result()
                        
                        if data is not None:
                            # 找到可用的代理
                            self.proxy_manager.set_proxy_by_url(used_proxy)
                            print(f"成功使用代理: {used_proxy}")
                            return data
                            
                    except Exception as e:
                        proxy_url = future_to_proxy[future]
                        print(f"代理 {proxy_url} 任务异常: {e}")
                        
            except TimeoutError:
                print(f"请求超时")
        
        print("所有代理尝试均失败")
        return None    
    def get_latest_release(self, repo_owner: str, repo_name: str) -> Optional[ReleaseInfo]:
        """
        获取最新release的完整信息
        
        Args:
            repo_owner: 仓库所有者
            repo_name: 仓库名称
            
        Returns:
            ReleaseInfo对象，如果失败则返回None
        """
        try:
            print(f"正在获取最新release: {repo_owner}/{repo_name}")
            
            data = self._make_request(repo_owner, repo_name, "releases/latest")
            if data is None:
                print("获取release信息失败")
                return None
                
            return self._parse_release_data(repo_owner, repo_name, data)
            
        except Exception as e:
            print(f"获取release信息失败: {e}")
            return None
    
    def get_latest_pre_release(self, repo_owner: str, repo_name: str) -> Optional[ReleaseInfo]:
        """
        获取最新的预发布版release
        如果第一页没有预发布版本，则返回最新版本
        
        Args:
            repo_owner: 仓库所有者
            repo_name: 仓库名称
        """
        try:
            print(f"正在获取第 1 页release列表...")
            params = {"per_page": 30, "page": 1}
            
            data = self._make_request(repo_owner, repo_name, "releases", params=params)
            if data is None or not data:
                print(f"未找到任何release或请求失败")
                return None
            
            # 在当前页中查找预发布版本
            for release in data:
                # 检查是否为预发布
                if release.get('prerelease', False) and not release.get('draft', False):
                    print(f"在第 1 页找到预发布版本: {release.get('tag_name')}")
                    return self._parse_release_data(repo_owner, repo_name, release)
            
            # 如果没有找到预发布版本，则返回最新版本（即第一页的第一个release）
            print(f"第一页没有找到预发布版本，返回最新版本")
            return self._parse_release_data(repo_owner, repo_name, data[0])
                
        except Exception as e:
            print(f"获取最新预发布版失败: {e}")
            return None
    
    def get_release_by_tag(self, repo_owner: str, repo_name: str, tag_name: str) -> Optional[ReleaseInfo]:
        """
        通过标签获取指定release信息
        
        Args:
            repo_owner: 仓库所有者
            repo_name: 仓库名称
            tag_name: 标签名称
        """
        try:
            print(f"正在获取release: {repo_owner}/{repo_name}@{tag_name}")
            
            data = self._make_request(repo_owner, repo_name, f"releases/tags/{tag_name}")
            if data is None:
                print(f"获取标签 {tag_name} 失败")
                return None
            
            return self._parse_release_data(repo_owner, repo_name, data)
            
        except Exception as e:
            print(f"获取release信息失败: {e}")
            return None
    
    def list_all_releases(self, repo_owner: str, repo_name: str, per_page: int = 30) -> List[ReleaseInfo]:
        """
        列出所有release（分页）
        
        Args:
            repo_owner: 仓库所有者
            repo_name: 仓库名称
            per_page: 每页数量
        """
        try:
            print(f"正在列出所有release: {repo_owner}/{repo_name}")
            
            releases = []
            page = 1
            
            while True:
                params = {"per_page": per_page, "page": page}
                
                data = self._make_request(repo_owner, repo_name, "releases", params=params)
                if data is None:
                    break
                    
                if not data:
                    break
                
                for release in data:
                    releases.append(self._parse_release_data(repo_owner, repo_name, release))
                
                page += 1
                
                # 如果返回的数量小于per_page，说明已经到最后一页
                if len(data) < per_page:
                    break
            
            return releases
            
        except Exception as e:
            print(f"获取release列表失败: {e}")
            return []
    
    def _parse_release_data(self, repo_owner: str, repo_name: str, release_data: Dict[str, Any]) -> ReleaseInfo:
        """解析GitHub API返回的release数据"""
        # 解析资源文件
        assets = []
        proxys = deepcopy(self.proxy_manager)
        for asset in release_data.get('assets', []):
            true_download_url = asset['browser_download_url']
            true_download_url = [true_download_url[i:] for i in range(len(true_download_url))
                                 if true_download_url[i:].startswith('https://github.com')]
            if not true_download_url:
                true_download_url = [asset['browser_download_url']]
            true_download_url = true_download_url[0]
            assets.append(ReleaseAsset(
                name=asset['name'],
                size=asset['size'],
                download_url=true_download_url,
                content_type=asset.get('content_type', 'application/octet-stream'),
                download_count=asset.get('download_count', 0),
                proxys=proxys
            ))
        
        # 创建ReleaseInfo对象
        return ReleaseInfo(
            repo_owner=repo_owner,
            repo_name=repo_name,
            tag_name=release_data['tag_name'],
            name=release_data.get('name', ''),
            body=release_data.get('body', ''),
            published_at=release_data.get('published_at', ''),
            prerelease=release_data.get('prerelease', False),
            draft=release_data.get('draft', False),
            assets=assets,
            proxys=proxys
        )


def print_release_summary(release_info: ReleaseInfo) -> None:
    """打印release摘要信息"""
    print(f"仓库: {release_info.repo_owner}/{release_info.repo_name}")
    print(f"版本: {release_info.tag_name}")
    print(f"名称: {release_info.name}")
    print(f"发布日期: {release_info.published_at}")
    print(f"预发布: {'是' if release_info.prerelease else '否'}")
    print(f"草稿: {'是' if release_info.draft else '否'}")
    
    if release_info.assets:
        print(f"\n资源文件 ({len(release_info.assets)} 个):")
        for i, asset in enumerate(release_info.assets, 1):
            print(f"  {i:2d}. {asset.name:<40} {asset.formatted_size:>10} (下载: {asset.download_count})")
    else:
        print("\n该release没有额外的资源文件")
    
    # 源码压缩包信息
    print(f"\n源码压缩包:")
    print(f"  ZIP: {release_info.source_zip_url}")
    print(f"  TAR.GZ: {release_info.source_tar_url}")


# 全局请求器实例
GithubRequester: GitHubReleaseFetcher = None

def init_request():
    """初始化全局请求器"""
    global GithubRequester
    GithubRequester = GitHubReleaseFetcher(
        use_proxy=True,
        ignore_ssl=True
        )
    print("GitHub请求器已初始化")


# 使用示例
if __name__ == "__main__":
    init_request()
    
    fetcher = GithubRequester
    
    # 获取不同仓库的最新release信息
    print("=" * 60)
    print("示例1: 获取vscode的最新release")
    print("=" * 60)
    latest_release = fetcher.get_latest_release("microsoft", "vscode")
    if latest_release:
        print_release_summary(latest_release)
        
        # 查找特定文件
        print("\n查找Windows安装包:")
        windows_assets = latest_release.get_assets_by_extension(".exe")
        for asset in windows_assets:
            print(f"  - {asset.name}: {asset.download_url}")

    print("\n" + "=" * 60)
    print("示例2: 获取pytorch的最新预览版release")
    print("=" * 60)
    stable_release = fetcher.get_latest_pre_release("pytorch", "pytorch")
    if stable_release:
        print_release_summary(stable_release)
    
    print("\n" + "=" * 60)
    print("示例3: 使用全局请求器获取numpy的特定版本")
    print("=" * 60)
    if GithubRequester:
        numpy_release = GithubRequester.get_release_by_tag("numpy", "numpy", "v1.24.0")
        if numpy_release:
            print_release_summary(numpy_release)