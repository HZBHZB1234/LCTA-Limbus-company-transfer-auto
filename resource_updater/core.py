import hashlib
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from globalManagers.LogManager import LogManager


_log_manager = LogManager()

USER_AGENT = "UnityPlayer/6000.3.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)"
X_REQUESTED_WITH = "this_is_header_value"
LOCALIZE_LANGUAGES = ("jp", "en", "kr")
FINGERPRINT_FILES = (
    Path("LimbusCompany.exe"),
)

ProgressCallback = Callable[[str, str, Optional[float]], None]


class UpdateError(Exception):
    pass


class TokenNotFound(UpdateError):
    pass


class DownloadError(UpdateError):
    pass


class DownloadCancelled(UpdateError):
    pass


class Aria2Error(UpdateError):
    pass


def default_work_dir() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / "LCTA" / "resource-updater"
    return Path.home() / ".lcta" / "resource-updater"


def default_unity_cache_dir() -> Path:
    if sys.platform == "win32":
        return Path.home() / "AppData" / "LocalLow" / "Unity" / "ProjectMoon_LimbusCompany"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "Unity" / "ProjectMoon_LimbusCompany"
    return Path.home() / ".cache" / "unity3d" / "ProjectMoon_LimbusCompany"


def resolve_aria2_binary() -> Optional[Path]:
    candidates = []
    resource_root = os.getenv("path_")
    if resource_root:
        candidates.append(Path(resource_root) / "tools" / "aria2" / "aria2c.exe")
    candidates.append(Path(__file__).resolve().parent.parent / "tools" / "aria2" / "aria2c.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = shutil.which("aria2c")
    return Path(found) if found else None


def _headers(include_xrw: bool) -> Dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    if include_xrw:
        headers["X-Requested-With"] = X_REQUESTED_WITH
    return headers


def http_get(url: str, include_xrw: bool, timeout: int = 60) -> bytes:
    last_error = None
    for attempt in range(3):
        try:
            _log_manager.debug(
                "[游戏资源更新/HTTP] GET 第 {}/3 次: {} (xrw={})".format(
                    attempt + 1, url, include_xrw
                )
            )
            request = urllib.request.Request(url, headers=_headers(include_xrw))
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
            _log_manager.debug(
                "[游戏资源更新/HTTP] GET 完成: {} ({} bytes)".format(url, len(data))
            )
            return data
        except Exception as exc:
            last_error = exc
            _log_manager.debug(
                "[游戏资源更新/HTTP] GET 失败: {} ({})".format(url, exc)
            )
            if attempt < 2:
                time.sleep(1 + attempt)
    raise DownloadError("GET 请求失败: {} ({})".format(url, last_error))


def http_download(
    url: str,
    destination: Path,
    include_xrw: bool,
    cancel_event: threading.Event,
    progress: Optional[Callable[[int, Optional[int]], None]] = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(destination.name + ".part")
    request = urllib.request.Request(url, headers=_headers(include_xrw))
    _log_manager.debug(
        "[游戏资源更新/HTTP] 开始下载: {} -> {} (xrw={})".format(
            url, destination, include_xrw
        )
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response, temp_path.open("wb") as output:
            total_text = response.headers.get("Content-Length")
            total = int(total_text) if total_text and total_text.isdigit() else None
            downloaded = 0
            while True:
                if cancel_event.is_set():
                    raise DownloadCancelled("更新已取消")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)
        temp_path.replace(destination)
        _log_manager.debug(
            "[游戏资源更新/HTTP] 下载完成: {} -> {}".format(url, destination)
        )
    except urllib.error.HTTPError as exc:
        temp_path.unlink(missing_ok=True)
        _log_manager.debug(
            "[游戏资源更新/HTTP] 下载 HTTP 错误: {} (HTTP {})".format(url, exc.code)
        )
        if exc.code == 404:
            raise FileNotFoundError(url) from exc
        raise DownloadError("下载失败: {} (HTTP {})".format(url, exc.code)) from exc
    except Exception as exc:
        temp_path.unlink(missing_ok=True)
        _log_manager.debug(
            "[游戏资源更新/HTTP] 下载异常: {} ({})".format(url, exc)
        )
        raise


class Aria2Client:
    def __init__(self, binary: Path, jobs: int, connection_limit: int = 8):
        self.binary = binary
        self.jobs = max(1, jobs)
        self.connection_limit = max(1, min(16, connection_limit))
        self.secret = hashlib.sha256(
            "{}:{}".format(os.getpid(), time.time()).encode("utf-8")
        ).hexdigest()[:24]
        self.process = None
        self.endpoint = None
        self.request_id = 0

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        command = [
            str(self.binary), "--no-conf", "--enable-rpc",
            "--rpc-listen-all=false", "--rpc-listen-port={}".format(port),
            "--rpc-secret={}".format(self.secret),
            "--max-concurrent-downloads={}".format(self.jobs),
            "--max-connection-per-server={}".format(self.connection_limit),
            "--split=16", "--min-split-size=4M",
            "--continue=true", "--auto-file-renaming=false", "--allow-overwrite=true",
            "--file-allocation=none", "--max-tries=5", "--retry-wait=3",
            "--console-log-level=error", "--quiet=true",
        ]
        try:
            _log_manager.debug(
                "[游戏资源更新/aria2] 启动 {}，并发数 {}".format(
                    self.binary, self.jobs
                )
            )
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise Aria2Error("无法启动 aria2c: {}".format(exc)) from exc
        self.endpoint = "http://127.0.0.1:{}/jsonrpc".format(port)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            try:
                self.call("getVersion", [])
                _log_manager.debug(
                    "[游戏资源更新/aria2] RPC 已就绪: {}".format(self.endpoint)
                )
                return
            except Aria2Error:
                time.sleep(0.2)
        self.stop()
        raise Aria2Error("aria2c RPC 启动超时")

    def stop(self) -> None:
        process, self.process = self.process, None
        self.endpoint = None
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            process.kill()
        _log_manager.debug("[游戏资源更新/aria2] 进程已停止")

    def call(self, method: str, params: List[Any]) -> Any:
        if not self.endpoint:
            raise Aria2Error("aria2c 尚未启动")
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "aria2.{}".format(method),
            "params": ["token:{}".format(self.secret)] + params,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise Aria2Error("aria2c RPC 调用失败: {}".format(exc)) from exc
        if "error" in body:
            error = body["error"]
            raise Aria2Error(error.get("message") or str(error))
        return body.get("result")

    def add(self, url: str, destination: Path, include_xrw: bool) -> str:
        destination.parent.mkdir(parents=True, exist_ok=True)
        options = {"dir": str(destination.parent), "out": destination.name}
        options["header"] = [
            "{}: {}".format(key, value) for key, value in _headers(include_xrw).items()
        ]
        gid = str(self.call("addUri", [[url], options]))
        _log_manager.debug(
            "[游戏资源更新/aria2] 已提交 {} -> {} (gid={})".format(
                url, destination, gid
            )
        )
        return gid

    def status(self, gid: str) -> Dict[str, Any]:
        return self.call("tellStatus", [gid, [
            "status", "totalLength", "completedLength", "downloadSpeed",
            "errorCode", "errorMessage",
        ]])

    def remove_all(self) -> None:
        try:
            self.call("removeAll", [])
        except Aria2Error:
            try:
                self.call("forceRemoveAll", [])
            except Aria2Error:
                pass


class GameInfo:
    def __init__(self, game_dir: Path):
        self.game_dir = Path(game_dir)
        self.data_dir = self.game_dir / "LimbusCompany_Data"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "StreamingAssets" / "aa" / "settings.json"

    @property
    def resources_path(self) -> Path:
        return self.data_dir / "resources.assets"

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / "StreamingAssets" / "aa" / "catalog.bin"

    @property
    def executable_path(self) -> Path:
        return self.game_dir / "LimbusCompany.exe"

    def _settings(self) -> Dict[str, Any]:
        return json.loads(self.settings_path.read_text(encoding="utf-8-sig"))

    def catalog_url(self) -> str:
        for location in self._settings().get("m_CatalogLocations", []):
            internal_id = str(location.get("m_InternalId", ""))
            if not internal_id.startswith("https://download.limbuscompanycdn.org/"):
                continue
            base, separator, query = internal_id.partition("?")
            if base.endswith(".hash"):
                base = base[:-5] + ".bin"
            elif not base.endswith(".bin"):
                continue
            return base + (separator + query if separator else "")
        raise TokenNotFound("无法从 settings.json 提取远程 catalog 地址")

    def validate(self) -> None:
        missing = [
            path
            for path in (
                self.executable_path,
                self.settings_path,
                self.resources_path,
                self.catalog_path,
            )
            if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError(
                "游戏资源文件缺失: {}".format(", ".join(str(path) for path in missing))
            )

    def extract_tokens(self) -> Dict[str, Optional[str]]:
        self.validate()
        settings = self._settings()
        s_pattern = re.compile(
            r"download\.limbuscompanycdn\.org/(s\d{8}_[A-Za-z0-9_-]+)/"
        )
        s_token = None
        for location in settings.get("m_CatalogLocations", []):
            match = s_pattern.search(location.get("m_InternalId", ""))
            if match:
                s_token = match.group(1)
                break
        resources = self.resources_path.read_bytes()
        l_tokens = {
            match.group(1).decode("ascii")
            for match in re.finditer(
                rb"downloadcommon\.limbuscompanycdn\.org/(l\d{8}_[A-Za-z0-9_-]+)",
                resources,
            )
        }
        server_infos = {
            match.group(1).decode("ascii")
            for match in re.finditer(rb"serverinfos_([A-Za-z0-9_-]+)\.json", resources)
        }

        def newest(values: Sequence[str]) -> Optional[str]:
            def date_key(value: str) -> str:
                match = re.search(r"\d{8}", value)
                return match.group(0) if match else value

            return max(values, key=date_key) if values else None

        l_token = newest(list(l_tokens))
        if not s_token or not l_token:
            raise TokenNotFound("无法从游戏文件提取 S/L CDN 令牌")
        tokens = {"s": s_token, "l": l_token, "serverinfo": newest(list(server_infos))}
        _log_manager.debug("[游戏资源更新] 已提取 CDN 令牌: {}".format(tokens))
        return tokens


def _bundle_inner(name: str) -> Optional[str]:
    match = re.search(r"([0-9a-f]{32})\.bundle$", name)
    return match.group(1) if match else None


def parse_catalog(catalog_path: Path) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    data = catalog_path.read_bytes()
    names = set()
    for match in re.finditer(rb"[A-Za-z0-9_.\-]+\.bundle", data):
        name = match.group(0).decode("ascii", "replace")
        if len(name) < 200 and not re.match(r"^(?:l_)?[0-9a-f]{32}\.bundle$", name):
            names.add(name)
    ordered_names = sorted(names)
    outer_pattern = re.compile(rb"(?<![0-9a-f])([0-9a-f]{32})(?![0-9a-f])")
    metadata = {}
    for name in ordered_names:
        inner = _bundle_inner(name)
        if not inner:
            continue
        index = data.find(name.encode("ascii"))
        if index >= 0:
            match = outer_pattern.search(data[index + len(name): index + len(name) + 200])
            if match:
                outer = match.group(1).decode("ascii")
                if outer != inner:
                    metadata[name] = {"inner": inner, "outer": outer}
                    continue
        if "_monoscripts_" in name or name.startswith("vfx__unitybuiltinassets_"):
            prefix = name[: -(len(inner) + len(".bundle"))].rstrip("_")
            if prefix:
                metadata[name] = {"inner": inner, "outer": prefix}
    return ordered_names, metadata


def build_game_fingerprint(game_dir: Path) -> Dict[str, Dict[str, Any]]:
    root = Path(game_dir)
    fingerprint = {}
    for relative_path in FINGERPRINT_FILES:
        path = root / relative_path
        if not path.is_file():
            raise FileNotFoundError(str(path))
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        fingerprint[relative_path.as_posix()] = {
            "sha256": digest.hexdigest(),
            "size": path.stat().st_size,
        }
    _log_manager.debug("[游戏资源更新] 游戏 EXE 指纹: {}".format(fingerprint))
    return fingerprint


class ResourceUpdater:
    def __init__(
        self,
        game_dir: Path,
        work_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
        jobs: int = 8,
        engine: str = "auto",
        progress_callback: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
        retry_max: int = 0,
        retry_delay: float = 30.0,
        connection_limit: int = 8,
    ):
        self.game = GameInfo(Path(game_dir))
        self.work_dir = Path(work_dir) if work_dir else default_work_dir()
        self.cache_dir = Path(cache_dir) if cache_dir else default_unity_cache_dir()
        self.jobs = max(1, min(int(jobs), 32))
        self.engine = engine
        self.progress_callback = progress_callback
        self.cancel_event = cancel_event or threading.Event()
        self.aria2 = None
        self.retry_max = max(0, int(retry_max))
        self.retry_delay = max(0.0, float(retry_delay))
        self.connection_limit = max(1, min(16, int(connection_limit)))

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.aria2:
            self.aria2.remove_all()

    def report(
        self,
        channel: str,
        message: str,
        fraction: Optional[float] = None,
        level: int = logging.INFO,
    ) -> None:
        if fraction is None:
            _log_manager.log("[游戏资源更新/{}] {}".format(channel, message), level)
        else:
            _log_manager.log(
                "[游戏资源更新/{}] {} ({}%)".format(
                    channel, message, int(max(0.0, min(1.0, fraction)) * 100)
                ),
                level,
            )
        if self.progress_callback:
            self.progress_callback(channel, message, fraction)

    def _cleanup_failed_download(self, destination: Path, remove_parent: bool) -> None:
        for path in (
            destination.with_name(destination.name + ".part"),
            Path(str(destination) + ".aria2"),
        ):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                _log_manager.debug(
                    "[游戏资源更新] 清理临时文件失败: {} ({})".format(path, exc)
                )
        if not remove_parent:
            return
        entry_dir = destination.parent
        shutil.rmtree(entry_dir, ignore_errors=True)
        try:
            entry_dir.parent.rmdir()
        except OSError:
            pass
        _log_manager.debug(
            "[游戏资源更新] 已清理失败下载目录: {}".format(entry_dir)
        )

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise DownloadCancelled("更新已取消")

    def _sleep_cancel(self, seconds: float) -> None:
        """分片休眠，期间响应取消事件。"""
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            self._check_cancel()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.5, remaining))

    def _probe_failure(self, url: str) -> str:
        """最终失败时对 URL 发一次 Range 探针，抓取状态码与诊断响应头，用于下次定性根因。"""
        try:
            request = urllib.request.Request(url, headers=_headers(True))
            request.add_header("Range", "bytes=0-0")
            try:
                response = urllib.request.urlopen(request, timeout=8)
            except urllib.error.HTTPError as exc:
                response = exc
            code = getattr(response, "code", getattr(response, "status", "?"))
            headers = getattr(response, "headers", {}) or {}
            parts = ["probe: HTTP {}".format(code)]
            for key in (
                "server",
                "x-cache",
                "x-amz-cf-id",
                "x-amz-cf-pop",
                "cf-ray",
                "x-amz-error-type",
                "retry-after",
            ):
                value = headers.get(key)
                if value:
                    parts.append("{}={}".format(key, value))
            try:
                snippet = (
                    response.read(100)
                    .decode("utf-8", "replace")
                    .strip()
                    .replace("\n", " ")[:80]
                )
                if snippet:
                    parts.append(snippet)
            except Exception:
                pass
            return " | ".join(parts)
        except Exception as exc:
            return "probe: 探针失败 ({})".format(exc)

    def _resolved_engine(self) -> str:
        if self.engine not in ("auto", "aria2", "builtin"):
            raise ValueError("未知下载引擎: {}".format(self.engine))
        binary = resolve_aria2_binary()
        if self.engine == "aria2" and not binary:
            raise Aria2Error("找不到随包 aria2c.exe，也未在 PATH 中找到 aria2c")
        if self.engine == "builtin":
            return "builtin"
        return "aria2" if binary else "builtin"

    def _aria_client(self) -> Aria2Client:
        if self.aria2 is None:
            binary = resolve_aria2_binary()
            if not binary:
                raise Aria2Error("找不到 aria2c")
            self.aria2 = Aria2Client(binary, self.jobs, connection_limit=self.connection_limit)
            self.aria2.start()
        return self.aria2

    def _download_many_aria2(
        self,
        channel: str,
        tasks: List[
            Tuple[
                str,
                Path,
                bool,
                bool,
                Optional[Callable[[Path], None]],
                bool,
            ]
        ],
    ) -> Dict[str, Any]:
        client = self._aria_client()
        pending = []
        failed = skipped = completed = retried = 0
        failed_items = []

        def record_failure(
            url: str,
            destination: Path,
            reason: str,
            cleanup_parent: bool,
            diagnostics: Optional[str] = None,
        ) -> None:
            item = {
                "name": url.rsplit("/", 1)[-1] or destination.name,
                "url": url,
                "reason": reason,
            }
            if diagnostics:
                item["diagnostics"] = diagnostics
            failed_items.append(item)
            self._cleanup_failed_download(destination, cleanup_parent)

        for (
            url,
            destination,
            include_xrw,
            skip_not_found,
            post_action,
            cleanup_parent,
        ) in tasks:
            try:
                gid = client.add(url, destination, include_xrw)
                pending.append({
                    "gid": gid,
                    "url": url,
                    "destination": destination,
                    "include_xrw": include_xrw,
                    "skip_not_found": skip_not_found,
                    "post_action": post_action,
                    "cleanup_parent": cleanup_parent,
                    "retries_left": self.retry_max,
                    "retry_at": None,
                })
            except Exception as exc:
                failed += 1
                record_failure(url, destination, "提交下载失败: {}".format(exc), cleanup_parent)
                self.report(
                    channel, "提交下载失败: {}".format(exc), level=logging.WARNING
                )
        total = len(tasks)
        last_finished = -1
        try:
            while pending:
                self._check_cancel()
                now = time.monotonic()
                remaining = []
                speed = downloaded = known_total = 0
                for task in pending:
                    if task["retry_at"] is not None:
                        if now < task["retry_at"]:
                            remaining.append(task)
                            continue
                        try:
                            task["gid"] = client.add(
                                task["url"], task["destination"], task["include_xrw"]
                            )
                            task["retry_at"] = None
                            retried += 1
                        except Exception as exc:
                            failed += 1
                            record_failure(
                                task["url"],
                                task["destination"],
                                "重试提交失败: {}".format(exc),
                                task["cleanup_parent"],
                            )
                            self.report(
                                channel,
                                "重试提交失败: {}".format(exc),
                                level=logging.WARNING,
                            )
                            continue
                    status = client.status(task["gid"])
                    state = status.get("status")
                    downloaded += int(status.get("completedLength") or 0)
                    known_total += int(status.get("totalLength") or 0)
                    speed += int(status.get("downloadSpeed") or 0)
                    if state == "complete":
                        try:
                            if task["post_action"]:
                                task["post_action"](task["destination"])
                            completed += 1
                        except Exception as exc:
                            failed += 1
                            record_failure(
                                task["url"],
                                task["destination"],
                                "下载后处理失败: {}".format(exc),
                                task["cleanup_parent"],
                            )
                            self.report(
                                channel,
                                "下载后处理失败: {}".format(exc),
                                level=logging.WARNING,
                            )
                    elif state in ("error", "removed"):
                        error_code = int(status.get("errorCode") or 0)
                        if error_code == 3 and task["skip_not_found"]:
                            skipped += 1
                            self._cleanup_failed_download(
                                task["destination"], task["cleanup_parent"]
                            )
                        elif task["retries_left"] > 0:
                            task["retries_left"] -= 1
                            task["retry_at"] = time.monotonic() + self.retry_delay
                            remaining.append(task)
                            self.report(
                                channel,
                                "下载失败 {name}，{delay:.0f} 秒后自动重试（剩余 {left} 轮）".format(
                                    name=task["url"].rsplit("/", 1)[-1],
                                    delay=self.retry_delay,
                                    left=task["retries_left"],
                                ),
                                level=logging.WARNING,
                            )
                        else:
                            message = status.get("errorMessage") or "未知错误"
                            reason = "{} (错误码 {})".format(message, error_code)
                            diagnostics = self._probe_failure(task["url"])
                            failed += 1
                            record_failure(
                                task["url"],
                                task["destination"],
                                reason,
                                task["cleanup_parent"],
                                diagnostics,
                            )
                            self.report(
                                channel,
                                "下载失败: {}（错误码 {}），重试 {} 轮仍失败: {}".format(
                                    task["url"].rsplit("/", 1)[-1],
                                    error_code,
                                    self.retry_max,
                                    message,
                                ),
                                level=logging.WARNING,
                            )
                            _log_manager.debug(
                                "[游戏资源更新/{}] 失败诊断: {} | {}".format(
                                    channel, task["url"], diagnostics
                                )
                            )
                    else:
                        remaining.append(task)
                pending = remaining
                finished = completed + skipped + failed
                fraction = finished / total if total else 1.0
                if known_total:
                    fraction = max(fraction, min(0.99, downloaded / known_total))
                progress_text = "已完成 {}/{}，速度 {:.1f} MiB/s".format(
                    finished, total, speed / 1024 / 1024
                )
                if finished != last_finished:
                    self.report(channel, progress_text, fraction)
                    last_finished = finished
                elif self.progress_callback:
                    self.progress_callback(channel, progress_text, fraction)
                if pending:
                    time.sleep(0.5)
        except Exception:
            client.remove_all()
            for task in pending:
                self._cleanup_failed_download(
                    task["destination"], task["cleanup_parent"]
                )
            raise
        return {
            "completed": completed,
            "skipped": skipped,
            "failed": failed,
            "retried": retried,
            "failed_items": failed_items,
        }

    def _download_one_builtin(
        self,
        channel: str,
        url: str,
        destination: Path,
        include_xrw: bool,
        index: int,
        total: int,
        cleanup_parent: bool = False,
    ) -> None:
        def progress(done: int, size: Optional[int]) -> None:
            fraction = index / total if total else 0.0
            if size:
                fraction = (index + done / size) / total
            self.report(channel, "正在下载 {}".format(destination.name), min(fraction, 0.99))

        try:
            http_download(url, destination, include_xrw, self.cancel_event, progress)
        except Exception:
            self._cleanup_failed_download(destination, cleanup_parent)
            raise

    def _download_with_retry_builtin(
        self,
        channel: str,
        url: str,
        destination: Path,
        include_xrw: bool,
        index: int,
        total: int,
        cleanup_parent: bool = False,
    ) -> int:
        """内置下载器带退避重试，返回实际尝试次数（1 = 一次成功）。"""
        attempts = 1 + self.retry_max
        for attempt in range(attempts):
            try:
                self._download_one_builtin(
                    channel, url, destination, include_xrw, index, total, cleanup_parent
                )
                return attempt + 1
            except (DownloadCancelled, FileNotFoundError):
                raise
            except Exception:
                if attempt < self.retry_max:
                    self.report(
                        channel,
                        "下载失败 {name}，{delay:.0f} 秒后自动重试（第 {round}/{max} 轮）".format(
                            name=destination.name,
                            delay=self.retry_delay,
                            round=attempt + 1,
                            max=self.retry_max,
                        ),
                        level=logging.WARNING,
                    )
                    self._sleep_cancel(self.retry_delay)
                    continue
                raise
        raise DownloadError("下载失败: {}".format(destination.name))

    def _build_manifest(self, include_bundle: bool) -> Dict[str, Any]:
        self.report("manifest", "正在读取游戏 CDN 信息", 0.05)
        tokens = self.game.extract_tokens()
        token_dir = self.work_dir / "manifests" / "{}_{}".format(
            tokens["s"], tokens["l"]
        )
        token_dir.mkdir(parents=True, exist_ok=True)
        catalog_path = None
        bundle_names = []
        bundle_meta = {}
        if include_bundle:
            catalog_url = self.game.catalog_url()
            catalog_path = token_dir / "catalog_S1.bin"
            try:
                self.report("manifest", "正在获取远程 catalog", 0.35)
                try:
                    catalog_data = http_get(catalog_url, True, timeout=120)
                except Exception:
                    if self.retry_max > 0:
                        self.report(
                            "manifest",
                            "远程 catalog 获取失败，{:.0f} 秒后自动重试".format(
                                self.retry_delay
                            ),
                            level=logging.WARNING,
                        )
                        self._sleep_cancel(self.retry_delay)
                        catalog_data = http_get(catalog_url, True, timeout=120)
                    else:
                        raise
                temp_path = catalog_path.with_name(catalog_path.name + ".part")
                temp_path.write_bytes(catalog_data)
                temp_path.replace(catalog_path)
                bundle_names, bundle_meta = parse_catalog(catalog_path)
                if not bundle_names:
                    raise DownloadError("远程 catalog 中未解析到 Bundle")
                _log_manager.debug(
                    "[游戏资源更新/manifest] 远程 catalog 获取成功: {}，Bundle {} 个".format(
                        catalog_url, len(bundle_names)
                    )
                )
            except DownloadCancelled:
                raise
            except Exception as exc:
                catalog_path.with_name(catalog_path.name + ".part").unlink(missing_ok=True)
                _log_manager.log(
                    "[游戏资源更新/manifest] 远程 catalog 获取失败，回退游戏内文件: {}".format(
                        exc
                    )
                )
                shutil.copy2(self.game.catalog_path, catalog_path)
                self.report("manifest", "远程 catalog 获取失败，使用游戏内 catalog", 0.55)
                bundle_names, bundle_meta = parse_catalog(catalog_path)
            if not bundle_names:
                raise UpdateError("catalog 中未解析到任何 Bundle")
            self.report("manifest", "资源目录解析完成", 0.9)
        else:
            self.report("manifest", "CDN 信息读取完成", 1.0)
        return {
            "tokens": tokens,
            "catalog_path": catalog_path,
            "bundles": bundle_names,
            "bundle_meta": bundle_meta,
        }

    def update_localize(
        self, manifest: Dict[str, Any], languages: Sequence[str]
    ) -> Dict[str, Any]:
        selected = [language for language in languages if language in LOCALIZE_LANGUAGES]
        if not selected:
            return {"updated": 0, "failed": 0, "failed_items": []}
        zip_dir = self.work_dir / "downloads" / str(manifest["tokens"]["l"])
        zip_dir.mkdir(parents=True, exist_ok=True)
        tasks = []
        zip_paths = {}
        for language in selected:
            zip_path = zip_dir / "localize_{}.zip".format(language)
            zip_paths[language] = zip_path
            sidecar = Path(str(zip_path) + ".aria2")
            if not zip_path.is_file() or zip_path.stat().st_size == 0 or sidecar.exists():
                url = (
                    "https://downloadcommon.limbuscompanycdn.org/{}/Assets/LocalizePatch/"
                    "localize_{}.zip"
                ).format(manifest["tokens"]["l"], language)
                tasks.append((url, zip_path, False, False, None, False))
        localize_retried = 0
        if tasks:
            if self._resolved_engine() == "aria2":
                result = self._download_many_aria2("localize", tasks)
                localize_retried = result.get("retried", 0)
                if result["failed"]:
                    raise DownloadError(
                        "{} 个本地化压缩包下载失败".format(result["failed"])
                    )
            else:
                for index, task in enumerate(tasks):
                    attempts = self._download_with_retry_builtin(
                        "localize", task[0], task[1], task[2], index, len(tasks)
                    )
                    localize_retried += max(0, attempts - 1)

        updates = []
        for language, zip_path in zip_paths.items():
            self._check_cancel()
            if not zip_path.is_file():
                raise DownloadError("本地化压缩包不存在: {}".format(zip_path))
            try:
                with zipfile.ZipFile(zip_path) as archive:
                    invalid = archive.testzip()
                    if invalid:
                        raise zipfile.BadZipFile("损坏条目: {}".format(invalid))
                    prefix = "LocalizeTemp_{}/".format(language)
                    for info in archive.infolist():
                        if info.is_dir() or not info.filename.startswith(prefix):
                            continue
                        relative = PurePosixPath(info.filename[len(prefix):])
                        if (
                            not relative.parts
                            or relative.is_absolute()
                            or any(
                                part in ("", ".", "..") or ":" in part or "\\" in part
                                for part in relative.parts
                            )
                        ):
                            continue
                        destination = (
                            self.game.data_dir
                            / "Assets" / "Resources_moved" / "Localize" / language
                            / Path(*relative.parts)
                        )
                        content = archive.read(info)
                        if not destination.is_file() or destination.read_bytes() != content:
                            updates.append((destination, content))
            except zipfile.BadZipFile as exc:
                zip_path.unlink(missing_ok=True)
                Path(str(zip_path) + ".aria2").unlink(missing_ok=True)
                raise DownloadError("本地化压缩包损坏: {}".format(zip_path)) from exc

        failed = updated = 0
        failed_items = []
        for index, (destination, content) in enumerate(updates):
            self._check_cancel()
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                temp_path = destination.with_name(destination.name + ".part")
                temp_path.write_bytes(content)
                temp_path.replace(destination)
                updated += 1
            except OSError as exc:
                failed += 1
                failed_items.append({
                    "name": destination.name,
                    "url": str(destination),
                    "reason": str(exc),
                })
                self.report(
                    "localize",
                    "写入失败: {} ({})".format(destination, exc),
                    level=logging.WARNING,
                )
            self.report(
                "localize",
                "正在应用本地化文件 {}/{}".format(index + 1, len(updates)),
                (index + 1) / len(updates) if updates else 1.0,
            )
        self.report("localize", "本地化更新完成：{} 个文件".format(updated), 1.0)
        return {
            "updated": updated,
            "failed": failed,
            "failed_items": failed_items,
            "retried": localize_retried,
        }

    def _existing_bundle_mapping(self) -> Dict[str, str]:
        mapping = {}
        if not self.cache_dir.is_dir():
            return mapping
        try:
            for outer_dir in self.cache_dir.iterdir():
                if not outer_dir.is_dir():
                    continue
                try:
                    for inner_dir in outer_dir.iterdir():
                        if inner_dir.is_dir():
                            mapping[inner_dir.name] = outer_dir.name
                except OSError:
                    continue
        except OSError:
            pass
        return mapping

    @staticmethod
    def _write_bundle_info(destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        (destination.parent / "__info").write_text(
            "-1\n{}\n1\n__data\n".format(int(time.time())), encoding="utf-8"
        )

    def update_bundles(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        metadata = dict(manifest["bundle_meta"])
        existing = self._existing_bundle_mapping()
        for name in manifest["bundles"]:
            inner = _bundle_inner(name)
            if inner and inner in existing:
                metadata[name] = {"inner": inner, "outer": existing[inner]}
        tasks = []
        for name, item in metadata.items():
            entry_dir = self.cache_dir / item["outer"] / item["inner"]
            destination = entry_dir / "__data"
            if (
                destination.is_file()
                and destination.stat().st_size > 0
                and (entry_dir / "__info").is_file()
                and not Path(str(destination) + ".aria2").exists()
            ):
                continue
            url = "https://download.limbuscompanycdn.org/{}/{}".format(
                manifest["tokens"]["s"], name
            )
            tasks.append(
                (url, destination, True, True, self._write_bundle_info, True)
            )
        if not tasks:
            self.report("bundle", "Bundle 缓存已是最新", 1.0)
            return {
                "updated": 0,
                "skipped": 0,
                "failed": 0,
                "retried": 0,
                "failed_items": [],
            }

        if self._resolved_engine() == "aria2":
            result = self._download_many_aria2("bundle", tasks)
            return {
                "updated": result["completed"],
                "skipped": result["skipped"],
                "failed": result["failed"],
                "retried": result.get("retried", 0),
                "failed_items": result["failed_items"],
            }

        updated = skipped = failed = retried = 0
        failed_items = []
        retry_lock = threading.Lock()

        def worker(index: int, task) -> str:
            nonlocal retried
            try:
                attempts = self._download_with_retry_builtin(
                    "bundle",
                    task[0],
                    task[1],
                    task[2],
                    index,
                    len(tasks),
                    cleanup_parent=True,
                )
                task[4](task[1])
                with retry_lock:
                    retried += max(0, attempts - 1)
                return "updated"
            except FileNotFoundError:
                self._cleanup_failed_download(task[1], True)
                return "skipped"
            except DownloadCancelled:
                raise
            except Exception as exc:
                self._cleanup_failed_download(task[1], True)
                item = {
                    "name": task[0].rsplit("/", 1)[-1] or task[1].name,
                    "url": task[0],
                    "reason": str(exc),
                }
                diagnostics = self._probe_failure(task[0])
                if diagnostics:
                    item["diagnostics"] = diagnostics
                failed_items.append(item)
                self.report(
                    "bundle",
                    "Bundle 下载失败: {} ({})".format(
                        task[0].rsplit("/", 1)[-1], exc
                    ),
                    level=logging.WARNING,
                )
                return "failed"

        with ThreadPoolExecutor(max_workers=self.jobs) as executor:
            futures = [
                executor.submit(worker, index, task)
                for index, task in enumerate(tasks)
            ]
            for future in as_completed(futures):
                result = future.result()
                if result == "updated":
                    updated += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    failed += 1
        self.report(
            "bundle",
            "Bundle 更新完成：{} 成功，{} 跳过，{} 失败".format(
                updated, skipped, failed
            ),
            1.0,
        )
        return {
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "retried": retried,
            "failed_items": failed_items,
        }

    def run(
        self,
        update_localize: bool = True,
        update_bundle: bool = True,
        languages: Sequence[str] = LOCALIZE_LANGUAGES,
    ) -> Dict[str, Any]:
        self.game.validate()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        _log_manager.log(
            "[游戏资源更新] 开始任务: game_dir={}, localize={}, bundle={}, languages={}, engine={}, jobs={}, retry_max={}, retry_delay={}, connection_limit={}".format(
                self.game.game_dir,
                update_localize,
                update_bundle,
                list(languages),
                self.engine,
                self.jobs,
                self.retry_max,
                self.retry_delay,
                self.connection_limit,
            )
        )
        manifest = self._build_manifest(update_bundle)
        results = {}
        resolved_engine = self._resolved_engine()
        try:
            if update_localize:
                results["localize"] = self.update_localize(manifest, languages)
            if update_bundle:
                results["bundle"] = self.update_bundles(manifest)
        finally:
            if self.aria2:
                self.aria2.stop()
                self.aria2 = None
        failed = sum(item.get("failed", 0) for item in results.values())
        retried = sum(item.get("retried", 0) for item in results.values())
        failed_items = []
        for item in results.values():
            failed_items.extend(item.get("failed_items") or [])
        result = {
            "success": failed == 0,
            "engine": resolved_engine,
            "tokens": manifest["tokens"],
            "results": results,
            "retried": retried,
            "failed": failed,
            "failed_items": failed_items,
        }
        _log_manager.log("[游戏资源更新] 任务结束: {}".format(result))
        return result
