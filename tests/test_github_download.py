import pytest

from webFunc.GithubDownload import (
    GitHubReleaseFetcher,
    ProxyManager,
)


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def make_release_dict(tag_name="v1.0.0"):
    return {
        "tag_name": tag_name,
        "name": f"Release {tag_name}",
        "body": "body",
        "published_at": "2024-01-01T00:00:00Z",
        "prerelease": False,
        "draft": False,
        "assets": [],
    }


def make_fetcher(monkeypatch, use_proxy, **kwargs):
    monkeypatch.setattr(ProxyManager, "_fetch_proxies_from_api", lambda self: None)
    return GitHubReleaseFetcher(use_proxy=use_proxy, quiet=True, **kwargs)


class TestProxyParamsPassthrough:
    """Bug 1: 代理模式下 _make_request 必须把 params 透传给代理请求"""

    def test_params_reach_proxy_request(self, monkeypatch):
        fetcher = make_fetcher(monkeypatch, use_proxy=True, max_workers=2)
        calls = []

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(make_release_dict())

        fetcher.session.get = fake_get

        params = {"per_page": 30, "page": 2}
        data = fetcher._make_request("owner", "repo", "releases", params=params)

        assert data is not None
        assert calls
        for _, kwargs in calls:
            assert kwargs.get("params") == params, f"params 丢失: {kwargs}"


class TestListAllReleasesPageCap:
    """Bug 1: 分页死循环防护，最多请求 50 页"""

    def test_page_cap_prevents_infinite_loop(self, monkeypatch):
        fetcher = make_fetcher(monkeypatch, use_proxy=True, max_workers=2)
        pages_seen = []

        def fake_get(url, **kwargs):
            page = kwargs.get("params", {}).get("page", 1)
            pages_seen.append(page)
            return FakeResponse([make_release_dict(f"v{page}.0.0") for _ in range(30)])

        fetcher.session.get = fake_get

        releases = fetcher.list_all_releases("owner", "repo", per_page=30)

        assert releases, "应返回非空结果"
        assert max(pages_seen) == 50, f"应停止在第 50 页, 实际到第 {max(pages_seen)} 页"


class TestUpdateConfigRebuildsProxyManager:
    """Bug 2: update_config 切换 use_proxy 时必须重建 proxy_manager"""

    def test_disable_to_enable_rebuilds_manager(self, monkeypatch):
        monkeypatch.setattr(ProxyManager, "_fetch_proxies_from_api", lambda self: None)
        fetcher = GitHubReleaseFetcher(use_proxy=False, quiet=True)

        assert fetcher.proxy_manager is None
        fetcher.update_config(use_proxy=True)
        assert fetcher.use_proxy is True
        assert isinstance(fetcher.proxy_manager, ProxyManager)

    def test_enable_to_disable_clears_manager(self, monkeypatch):
        fetcher = make_fetcher(monkeypatch, use_proxy=True)

        assert fetcher.proxy_manager is not None
        fetcher.update_config(use_proxy=False)
        assert fetcher.proxy_manager is None
        assert fetcher.use_proxy is False

    def test_repair_stale_none_when_proxy_enabled(self, monkeypatch):
        monkeypatch.setattr(ProxyManager, "_fetch_proxies_from_api", lambda self: None)
        fetcher = GitHubReleaseFetcher(use_proxy=True, quiet=True)
        monkeypatch.setattr(fetcher, "proxy_manager", None)

        fetcher.update_config(use_proxy=True)
        assert isinstance(fetcher.proxy_manager, ProxyManager)


class TestAutoShutdownPoolNoNameError:
    """Bug 3: executor.shutdown 抛异常时遍历已提交的 future 集合, 不能引用未定义变量"""

    def test_shutdown_failure_does_not_raise_nameerror(self, monkeypatch):
        fetcher = make_fetcher(monkeypatch, use_proxy=True, max_workers=2)

        def fake_get(url, **kwargs):
            raise ConnectionError("mock 连接失败")

        fetcher.session.get = fake_get

        from concurrent.futures import ThreadPoolExecutor
        original_shutdown = ThreadPoolExecutor.shutdown
        state = {"calls": 0}

        def flaky_shutdown(self, wait=True, cancel_futures=False):
            if state["calls"] == 0:
                state["calls"] += 1
                raise RuntimeError("mock shutdown 失败")
            return original_shutdown(self, wait=wait, cancel_futures=cancel_futures)

        monkeypatch.setattr(ThreadPoolExecutor, "shutdown", flaky_shutdown)

        # 修复前: except 分支引用未定义的 future 会抛 NameError
        result = fetcher._make_request("owner", "repo", "releases", params={"per_page": 30, "page": 1})
        assert result is None
