"""
tests/test_webutils_functions.py
webutils/functions.py 的下载与解压工具函数单元测试。
覆盖：download_with 的 verify/validate 语义分离、超时设置、
下载后大小校验、decompress_zip 返回值契约。
"""
import time
import zipfile

import pytest

from webutils import functions as funcs


# ========== decompress_zip 返回值契约 ==========

class TestDecompressZip:
    """decompress_zip 成功返回 True，失败返回 False。"""

    def _make_zip(self, path, files=("a.txt",)):
        with zipfile.ZipFile(path, 'w') as zf:
            for name in files:
                zf.writestr(name, "内容")

    def test_success_returns_true(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        out_dir = tmp_path / "out"
        self._make_zip(zip_path)
        assert funcs.decompress_zip(str(zip_path), str(out_dir)) is True
        assert (out_dir / "a.txt").exists()

    def test_missing_file_returns_false(self, tmp_path):
        assert funcs.decompress_zip(str(tmp_path / "nope.zip"), str(tmp_path)) is False

    def test_corrupted_zip_returns_false(self, tmp_path):
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_bytes(b"not a real zip file")
        assert funcs.decompress_zip(str(bad_zip), str(tmp_path)) is False


# ========== download_with verify / validate 语义 ==========

class FakeResponse:
    """模拟 requests 流式响应对象。"""

    def __init__(self, chunks, content_length=0, error=None):
        self._chunks = list(chunks)
        self._error = error
        self.headers = {'Content-Length': str(content_length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def raise_for_status(self):
        if self._error:
            raise self._error

    def iter_content(self, chunk_size):
        return iter(self._chunks)


@pytest.fixture
def fake_get(monkeypatch):
    """替换 requests.get，捕获调用参数并返回可控的响应。"""
    calls = {}

    def _fake_get(url, **kwargs):
        calls['url'] = url
        calls['kwargs'] = kwargs
        return FakeResponse(calls['chunks'], calls['content_length'], calls['error'])

    calls['chunks'] = [b'a' * 100]
    calls['content_length'] = 100
    calls['error'] = None

    monkeypatch.setattr(funcs.requests, 'get', _fake_get)
    return calls


class TestDownloadWith:
    """download_with 的 verify/timeout/validate 行为。"""

    def test_request_verify_true_and_timeout_set(self, fake_get, tmp_path):
        """verify 必须固定为 True，且必须携带 (connect, read) 超时。"""
        save_path = tmp_path / "dl.bin"
        assert funcs.download_with("https://example.com/f", str(save_path)) is True
        kwargs = fake_get['kwargs']
        assert kwargs['verify'] is True
        assert kwargs['timeout'] == (10, 60)
        assert fake_get['url'] == "https://example.com/f"
        assert save_path.exists()

    def test_validate_false_skips_size_check(self, fake_get, tmp_path):
        """validate=False 时即使大小不匹配也应视为成功。"""
        fake_get['content_length'] = 100
        save_path = tmp_path / "dl.bin"
        assert funcs.download_with(
            "https://example.com/f", str(save_path),
            size=999, validate=False
        ) is True

    def test_validate_true_size_mismatch_returns_false(self, fake_get, tmp_path):
        """validate=True 且下载大小与期望不符时返回 False。"""
        fake_get['content_length'] = 100
        save_path = tmp_path / "dl.bin"
        assert funcs.download_with(
            "https://example.com/f", str(save_path), size=999
        ) is False

    def test_validate_true_size_match_returns_true(self, fake_get, tmp_path):
        """validate=True 且大小匹配时返回 True。"""
        fake_get['content_length'] = 100
        save_path = tmp_path / "dl.bin"
        assert funcs.download_with(
            "https://example.com/f", str(save_path), size=100
        ) is True

    def test_http_error_returns_false(self, fake_get, tmp_path):
        """服务器返回错误状态码时返回 False 且不产生文件。"""
        fake_get['error'] = RuntimeError("404 Not Found")
        save_path = tmp_path / "dl.bin"
        assert funcs.download_with("https://example.com/f", str(save_path)) is False


# ========== 响应迭代超时保护 ==========

class TestIterWithTimeout:
    """_iter_with_timeout 对停滞的分块迭代抛出超时。"""

    def test_fast_chunks_pass_through(self):
        chunks = iter([b'1', b'2', b'3'])
        assert list(funcs._iter_with_timeout(chunks, timeout=10)) == [b'1', b'2', b'3']

    def test_stalled_chunk_raises_timeout(self):
        def slow_chunks():
            yield b'1'
            time.sleep(0.2)
            yield b'2'

        with pytest.raises(TimeoutError):
            list(funcs._iter_with_timeout(slow_chunks(), timeout=0.05))
