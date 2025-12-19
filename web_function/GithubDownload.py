import requests
import warnings
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class ReleaseAsset:
    """Release资源文件信息"""
    name: str
    size: int
    download_url: str
    content_type: str
    download_count: int
    
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
    tag_name: str
    name: str
    body: str
    published_at: str
    prerelease: bool
    draft: bool
    assets: List[ReleaseAsset]
    
    @property
    def source_code_urls(self) -> Dict[str, str]:
        """获取源码压缩包URL"""
        tag = self.tag_name
        return {
            "zip": f"https://github.com/{{owner}}/{{repo}}/archive/refs/tags/{tag}.zip",
            "tar.gz": f"https://github.com/{{owner}}/{{repo}}/archive/refs/tags/{tag}.tar.gz"
        }
    
    def get_asset_by_name(self, name: str) -> Optional[ReleaseAsset]:
        """通过名称查找资源文件"""
        for asset in self.assets:
            if asset.name == name:
                return asset
        return None
    
    def get_assets_by_extension(self, extension: str) -> List[ReleaseAsset]:
        """通过扩展名筛选资源文件"""
        return [asset for asset in self.assets if asset.name.endswith(extension)]


class GitHubReleaseFetcher:
    """
    GitHub Release信息获取器
    专注于获取Release信息，不包含下载逻辑
    """
    
    def __init__(self, repo_owner: str, repo_name: str, 
                 use_proxy: bool = True, 
                 proxy_url: str = "https://gh-proxy.org/",
                 ignore_ssl: bool = False):
        """
        初始化获取器
        
        Args:
            repo_owner: 仓库所有者
            repo_name: 仓库名称
            use_proxy: 是否使用代理加速API请求
            proxy_url: 代理服务器地址
            ignore_ssl: 是否忽略SSL证书错误
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.use_proxy = use_proxy
        self.proxy_url = proxy_url.rstrip('/')
        self.ignore_ssl = ignore_ssl
        
        # GitHub API基础URL
        self.github_api_base = "https://api.github.com"
        
        # 配置requests会话
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Release-Fetcher'
        })
        
        # 忽略SSL警告
        if self.ignore_ssl:
            self.session.verify = False
            warnings.filterwarnings('ignore', message='Unverified HTTPS request')
    
    def _build_api_url(self, endpoint: str) -> str:
        """构建GitHub API URL"""
        api_url = f"{self.github_api_base}/repos/{self.repo_owner}/{self.repo_name}/{endpoint}"
        
        # 如果启用代理，应用代理到API URL
        if self.use_proxy:
            api_url = f"{self.proxy_url}/{api_url}"
            
        return api_url
    
    def get_latest_release(self) -> Optional[ReleaseInfo]:
        """
        获取最新release的完整信息
        
        Returns:
            ReleaseInfo对象，如果失败则返回None
        """
        try:
            api_url = self._build_api_url("releases/latest")
            
            print(f"正在获取最新release: {self.repo_owner}/{self.repo_name}")
            if self.use_proxy:
                print(f"使用代理: {self.proxy_url}")
            
            response = self.session.get(api_url, timeout=30)
            response.raise_for_status()
            
            release_data = response.json()
            return self._parse_release_data(release_data)
            
        except requests.exceptions.RequestException as e:
            print(f"获取release信息失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"状态码: {e.response.status_code}")
            return None
        except Exception as e:
            print(f"发生未知错误: {e}")
            return None
    
    def get_release_by_tag(self, tag_name: str) -> Optional[ReleaseInfo]:
        """
        通过标签获取指定release信息
        
        Args:
            tag_name: 标签名称
            
        Returns:
            ReleaseInfo对象，如果失败则返回None
        """
        try:
            api_url = self._build_api_url(f"releases/tags/{tag_name}")
            
            print(f"正在获取release: {self.repo_owner}/{self.repo_name} @ {tag_name}")
            
            response = self.session.get(api_url, timeout=30)
            response.raise_for_status()
            
            release_data = response.json()
            return self._parse_release_data(release_data)
            
        except requests.exceptions.RequestException as e:
            print(f"获取release信息失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 404:
                    print(f"未找到标签: {tag_name}")
                else:
                    print(f"状态码: {e.response.status_code}")
            return None
        except Exception as e:
            print(f"发生未知错误: {e}")
            return None
    
    def list_all_releases(self, per_page: int = 30) -> List[ReleaseInfo]:
        """
        列出所有release（分页）
        
        Args:
            per_page: 每页数量
            
        Returns:
            ReleaseInfo对象列表
        """
        try:
            api_url = self._build_api_url("releases")
            params = {"per_page": per_page}
            
            print(f"正在列出所有release: {self.repo_owner}/{self.repo_name}")
            
            releases = []
            page = 1
            
            while True:
                params["page"] = page
                response = self.session.get(api_url, params=params, timeout=30)
                response.raise_for_status()
                
                page_data = response.json()
                if not page_data:
                    break
                
                for release in page_data:
                    releases.append(self._parse_release_data(release))
                
                page += 1
                
                # 如果返回的数量小于per_page，说明已经到最后一页
                if len(page_data) < per_page:
                    break
            
            return releases
            
        except requests.exceptions.RequestException as e:
            print(f"获取release列表失败: {e}")
            return []
        except Exception as e:
            print(f"发生未知错误: {e}")
            return []
    
    def _parse_release_data(self, release_data: Dict[str, Any]) -> ReleaseInfo:
        """解析GitHub API返回的release数据"""
        # 解析资源文件
        assets = []
        for asset in release_data.get('assets', []):
            assets.append(ReleaseAsset(
                name=asset['name'],
                size=asset['size'],
                download_url=asset['browser_download_url'],
                content_type=asset.get('content_type', 'application/octet-stream'),
                download_count=asset.get('download_count', 0)
            ))
        
        # 创建ReleaseInfo对象
        release_info = ReleaseInfo(
            tag_name=release_data['tag_name'],
            name=release_data.get('name', ''),
            body=release_data.get('body', ''),
            published_at=release_data.get('published_at', ''),
            prerelease=release_data.get('prerelease', False),
            draft=release_data.get('draft', False),
            assets=assets
        )
        
        return release_info
    
    def get_simple_release_info(self) -> Optional[Dict[str, Any]]:
        """
        获取简化的release信息（兼容旧版本）
        
        Returns:
            包含基本信息的字典
        """
        release_info = self.get_latest_release()
        if not release_info:
            return None
        
        # 构建简化信息
        assets_info = []
        for asset in release_info.assets:
            assets_info.append({
                'name': asset.name,
                'size': asset.size,
                'formatted_size': asset.formatted_size,
                'download_url': asset.download_url,
                'content_type': asset.content_type
            })
        
        # 构建源码压缩包URL（带占位符）
        source_urls = release_info.source_code_urls
        for key in source_urls:
            source_urls[key] = source_urls[key].format(
                owner=self.repo_owner,
                repo=self.repo_name
            )
        
        return {
            'repo': f"{self.repo_owner}/{self.repo_name}",
            'tag_name': release_info.tag_name,
            'name': release_info.name,
            'body': release_info.body[:500] + "..." if len(release_info.body) > 500 else release_info.body,
            'published_at': release_info.published_at,
            'prerelease': release_info.prerelease,
            'draft': release_info.draft,
            'assets': assets_info,
            'source_code_urls': source_urls,
            'total_assets': len(release_info.assets)
        }


def print_release_summary(release_info: ReleaseInfo) -> None:
    """打印release摘要信息"""
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
    print(f"  ZIP: https://github.com/{{owner}}/{{repo}}/archive/refs/tags/{release_info.tag_name}.zip")
    print(f"  TAR.GZ: https://github.com/{{owner}}/{{repo}}/archive/refs/tags/{release_info.tag_name}.tar.gz")


# 使用示例
if __name__ == "__main__":
    # 创建获取器实例
    fetcher = GitHubReleaseFetcher(
        repo_owner="microsoft",
        repo_name="vscode",
        use_proxy=True,
        proxy_url="https://gh-proxy.org/"
    )
    
    # 获取最新release信息
    latest_release = fetcher.get_latest_release()
    
    if latest_release:
        print("=" * 60)
        print_release_summary(latest_release)
        print("=" * 60)
        
        # 获取简化信息（兼容旧API）
        simple_info = fetcher.get_simple_release_info()
        print("\n简化信息格式:")
        print(f"仓库: {simple_info['repo']}")
        print(f"版本: {simple_info['tag_name']}")
        print(f"资源文件数: {simple_info['total_assets']}")
        
        # 查找特定文件
        print("\n查找Windows安装包:")
        windows_assets = latest_release.get_assets_by_extension(".exe")
        for asset in windows_assets:
            print(f"  - {asset.name}: {asset.download_url}")