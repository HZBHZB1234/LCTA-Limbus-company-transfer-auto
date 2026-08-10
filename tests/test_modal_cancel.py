"""模态进度窗口取消/暂停机制回归测试。

覆盖：
- P0-1：net.py download_with / download_with_github 透传 CancelRunning（不再吞成失败）
- P0-3：evalFiles 中 handler 抛 CancelRunning 立即中止；失败分支不推 100%
- P2-1：_wait_continue 暂停中取消立即抛 CancelRunning
- P2-2：update_modal_progress percent 钳制为 [0,100] 整数
"""
import os

import pytest

from webui.app_api.exceptions import CancelRunning
from webui.app_api.core import CoreMixin
from webutils.utils import net as net_module
from webutils.drop import eval_files, handlers


# ========== P0-1：net.py 透传 CancelRunning ==========

class _FakeChunks:
    def __iter__(self):
        yield b"x" * 100
        yield b"y" * 100


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    @property
    def headers(self):
        return {"Content-Length": "200"}

    def iter_content(self, chunk_size):
        return _FakeChunks()


class TestDownloadWithCancel:
    """download_with 必须在 check_running 抛 CancelRunning 时原样上抛。"""

    def test_cancel_raises_not_return_false(self, monkeypatch, tmp_path):
        monkeypatch.setattr(net_module.requests, "get",
                            lambda *a, **k: _FakeResponse())

        def _raising_check(modal_id, log=True):
            raise CancelRunning

        monkeypatch.setattr(net_module._log_manager, "check_running",
                            _raising_check)
        with pytest.raises(CancelRunning):
            net_module.download_with("https://example.com/x", str(tmp_path / "x.bin"),
                                     size=0, modal_id="modal-test")

    def test_cancel_raises_before_size_validation(self, monkeypatch, tmp_path):
        """取消必须优先于下载后的大小校验逻辑。"""
        monkeypatch.setattr(net_module.requests, "get",
                            lambda *a, **k: _FakeResponse())

        def _raising_check(modal_id, log=True):
            raise CancelRunning

        monkeypatch.setattr(net_module._log_manager, "check_running",
                            _raising_check)
        with pytest.raises(CancelRunning):
            net_module.download_with("https://example.com/x", str(tmp_path / "x.bin"),
                                     size=100, modal_id="modal-test", validate=True)


class _FakeProxyManager:
    proxies = ["https://proxy1", "https://proxy2"]

    def get_proxies(self):
        return iter(self.proxies)

    def set_proxy_by_url(self, url):
        pass


class TestDownloadWithGithubCancel:
    """download_with_github 代理轮换循环不能吞掉 CancelRunning。"""

    def _make_asset(self):
        from webFunc.GithubDownload import ReleaseAsset
        return ReleaseAsset(name="x.zip", size=200,
                            download_url="https://example.com/x.zip",
                            content_type="", download_count=0,
                            proxys=_FakeProxyManager())

    def test_cancel_stops_proxy_rotation(self, monkeypatch, tmp_path):
        calls = {"n": 0}

        def fake_get(url, **kwargs):
            calls["n"] += 1
            return _FakeResponse()

        monkeypatch.setattr(net_module.requests, "get", fake_get)

        def _raising_check(modal_id, log=True):
            raise CancelRunning

        monkeypatch.setattr(net_module._log_manager, "check_running",
                            _raising_check)
        asset = self._make_asset()
        with pytest.raises(CancelRunning):
            net_module.download_with_github(asset, str(tmp_path / "x.zip"),
                                            modal_id="modal-test", use_proxy=True)
        assert calls["n"] == 1, "取消后不得继续轮换下一个代理"


# ========== P0-3：evalFiles 取消中止 + 失败不推 100 ==========

class TestEvalFilesCancel:
    @pytest.fixture
    def fake_config(self, tmp_path, monkeypatch):
        class _FakeConfig:
            def get(self, key, default=''):
                return str(tmp_path / "game") if key == "game_path" else default

        monkeypatch.setattr(eval_files, "ConfigManager",
                            lambda: _FakeConfig())
        monkeypatch.setattr(eval_files, "get_mod_path",
                            lambda: str(tmp_path / "mods"))
        return _FakeConfig

    def test_handler_cancel_propagates(self, tmp_path, monkeypatch, fake_config):
        """handler.execute 抛 CancelRunning 必须上抛，而非计入 errors 继续处理。"""

        class _RaisingHandler:
            def execute(self, context):
                raise CancelRunning

        monkeypatch.setattr(handlers.REGISTRY, "handler_for",
                            lambda t: _RaisingHandler())
        target = tmp_path / "pkg.zip"
        target.write_bytes(b"x")
        with pytest.raises(CancelRunning):
            eval_files.evalFiles({str(target): "full"}, "modal")

    def test_errors_branch_does_not_push_100(self, tmp_path, monkeypatch, fake_config):
        """存在错误时不推 100%，由前端 complete(false) 收尾。"""
        progress_calls = []
        monkeypatch.setattr(eval_files._log_manager, "update_modal_progress",
                            lambda percent, text, modal_id=None, log=True:
                            progress_calls.append(percent))

        class _FailingHandler:
            def execute(self, context):
                raise RuntimeError("boom")

        monkeypatch.setattr(handlers.REGISTRY, "handler_for",
                            lambda t: _FailingHandler())
        target = tmp_path / "pkg.zip"
        target.write_bytes(b"x")
        result = eval_files.evalFiles({str(target): "full"}, "modal")
        assert result["success"] is False
        assert result["errors"] == 1
        assert 100 not in progress_calls, "失败分支不得推 100%"


# ========== P2-6：clean.py 取消检查点不被吞 ==========

class TestCleanCancel:
    def test_clear_by_mod_cancel_propagates(self, monkeypatch, tmp_path):
        """clear_by_mod 内层循环的 check_running 抛 CancelRunning 必须上抛，
        不得被函数级 except Exception 吞成 return 0。"""
        from webutils.packages import clean as clean_module

        def _raising_check(modal_id, log=True):
            raise CancelRunning

        monkeypatch.setattr(clean_module._log_manager, "check_running",
                            _raising_check)
        monkeypatch.setattr(clean_module, "check_by_mod",
                            lambda path: ["Installation/Foo", "Data"])
        mod_file = tmp_path / "mod.zip"
        mod_file.write_bytes(b"x")
        with pytest.raises(CancelRunning):
            clean_module.clear_by_mod(str(mod_file), "modal")

    def test_clean_config_main_cancel_not_swallowed(self, monkeypatch, tmp_path):
        """clear_by_mod 抛出的 CancelRunning 不能被 clean_config_main
        循环内的 except Exception 吞掉（否则取消显示为成功）。"""
        from webutils.packages import clean as clean_module

        def _raising_clear(mod_path, modal_id):
            raise CancelRunning

        monkeypatch.setattr(clean_module, "clear_by_mod", _raising_clear)
        custom_file = tmp_path / "x.zip"
        custom_file.write_bytes(b"x")
        with pytest.raises(CancelRunning):
            clean_module.clean_config_main("modal", custom_files=[str(custom_file)])


# ========== P2-6：WorkerPool 取消不等待在飞任务 ==========

class TestWorkerPoolCancel:
    def test_cancel_from_progress_propagates(self):
        """on_progress 抛 CancelRunning 时 map() 必须立即上抛，
        而不是把所有任务吞成 SAVE_ERROR 后正常返回。"""
        from translateFunc.workers import WorkerPool
        from translateFunc.config import ProcessOutcome, ProcessResult

        def _quick_worker(file_item, translator):
            return ProcessOutcome(ProcessResult.SUCCESS_SAVED, str(file_item))

        def _cancel_progress(done, total, fname):
            raise CancelRunning

        pool = WorkerPool(translator_factory=lambda: None, max_workers=2)
        with pytest.raises(CancelRunning):
            pool.map([1, 2, 3], _quick_worker, on_progress=_cancel_progress)


# ========== P2-1：_wait_continue 暂停中取消 ==========

class TestWaitContinue:
    def _make_core(self, monkeypatch):
        import webui.app_api.core as core_module
        monkeypatch.setattr(core_module.time, "sleep", lambda s: None)
        return CoreMixin.__new__(CoreMixin)

    def test_pause_then_cancel_raises(self, monkeypatch):
        core = self._make_core(monkeypatch)
        statuses = iter(["pause", "pause", "cancel"])
        monkeypatch.setattr(core, "_check_modal_running",
                            lambda modal_id: next(statuses))
        with pytest.raises(CancelRunning):
            core._wait_continue("modal")

    def test_pause_then_resume_returns(self, monkeypatch):
        core = self._make_core(monkeypatch)
        statuses = iter(["pause", "pause", "running"])
        monkeypatch.setattr(core, "_check_modal_running",
                            lambda modal_id: next(statuses))
        assert core._wait_continue("modal") is None

    def test_running_returns_immediately(self, monkeypatch):
        core = self._make_core(monkeypatch)
        monkeypatch.setattr(core, "_check_modal_running",
                            lambda modal_id: "running")
        assert core._wait_continue("modal") is None


# ========== P2-2：percent 钳制 ==========

class _FakeWindow:
    def __init__(self):
        self.calls = []

    def evaluate_js(self, code):
        self.calls.append(code)


class TestPercentClamp:
    def _make_core(self):
        core = CoreMixin.__new__(CoreMixin)
        core._window = _FakeWindow()
        return core

    def test_float_percent_becomes_int(self):
        core = self._make_core()
        core.update_modal_progress(83.33333333333333, "x", "modal", log=False)
        assert "updateProgress(83" in core._window.calls[0]

    def test_above_100_clamped(self):
        core = self._make_core()
        core.update_modal_progress(150.5, "x", "modal", log=False)
        assert "updateProgress(100" in core._window.calls[0]

    def test_below_0_clamped(self):
        core = self._make_core()
        core.update_modal_progress(-5, "x", "modal", log=False)
        assert "updateProgress(0" in core._window.calls[0]

    def test_none_value_returns_0(self):
        core = self._make_core()
        core.update_modal_progress(None, "x", "modal", log=False)
        assert "updateProgress(0" in core._window.calls[0]

    def test_modal_false_skips_js(self):
        core = self._make_core()
        core.update_modal_progress(50, "x", "false", log=False)
        assert core._window.calls == []
