# -*- coding: utf-8 -*-
"""泛用高速下载器 — 基于随包 aria2c 的 JSON-RPC 封装与任务管理器。

独立窗口「高速下载器」的后端：粘贴 URL / 磁力链接批量下载、.torrent 文件、
多任务队列、暂停/继续/删除、后台轮询进度快照推送。
与 resource_updater 的 aria2 实例相互独立（各自进程与随机端口）。
"""
import base64
import hashlib
import json
import logging
import os
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from globalManagers.LogManager import LogManager
from resource_updater.core import Aria2Error, resolve_aria2_binary

_log_manager = LogManager()
logger = logging.getLogger(__name__)

VALID_SCHEMES = ("http://", "https://", "ftp://", "magnet:?")
MAGNET_PREFIX = "magnet:?"

DEFAULT_JOBS = 8
DEFAULT_CONNECTION_LIMIT = 16
DEFAULT_SEED_TIME = 0  # 0 = 下载完成后不继续做种

POLL_INTERVAL = 1.0

TERMINAL_STATES = ("complete", "error", "removed")


class Aria2DlClient:
    """aria2c JSON-RPC 封装（仅监听本机 loopback，secret 认证）。

    下载选项面向泛用场景：断点续传、多连接分段、
    做种时间可配（seed_time=0 表示完成后立即停止做种）。
    """

    def __init__(
        self,
        binary: Path,
        jobs: int,
        connection_limit: int,
        seed_time: int = DEFAULT_SEED_TIME,
    ):
        self.binary = binary
        self.jobs = max(1, jobs)
        self.connection_limit = max(1, min(16, connection_limit))
        self.seed_time = max(0, seed_time)
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
            "--continue=true", "--file-allocation=none",
            "--max-tries=5", "--retry-wait=3",
            "--seed-time={}".format(self.seed_time),
            "--console-log-level=error", "--quiet=true",
        ]
        try:
            _log_manager.debug(
                "[高速下载器/aria2] 启动 {}，并发数 {}，连接数 {}，做种 {} 分钟".format(
                    self.binary, self.jobs, self.connection_limit, self.seed_time
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
                    "[高速下载器/aria2] RPC 已就绪: {}".format(self.endpoint)
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
        _log_manager.debug("[高速下载器/aria2] 进程已停止")

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

    def add_uri(self, url: str, save_dir: Path, out: Optional[str]) -> str:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        options = {"dir": str(save_dir)}
        if out:
            options["out"] = out
        gid = str(self.call("addUri", [[url], options]))
        _log_manager.debug(
            "[高速下载器/aria2] 已提交 {} -> {} (gid={})".format(url, save_dir, gid)
        )
        return gid

    def add_torrent(self, torrent_b64: str, save_dir: Path) -> str:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        options = {"dir": str(save_dir)}
        gid = str(self.call("addTorrent", [torrent_b64, [], options]))
        _log_manager.debug(
            "[高速下载器/aria2] 已提交 torrent -> {} (gid={})".format(save_dir, gid)
        )
        return gid

    def status(self, gid: str) -> Dict[str, Any]:
        return self.call("tellStatus", [gid, [
            "status", "totalLength", "completedLength", "downloadSpeed",
            "errorCode", "errorMessage", "dir", "files", "bittorrent",
        ]])

    def tell_active(self) -> List[Dict[str, Any]]:
        return self.call("tellActive", [[
            "gid", "dir", "status", "totalLength", "completedLength",
            "downloadSpeed",
        ]])

    def pause(self, gid: str) -> None:
        self.call("pause", [gid])

    def force_pause(self, gid: str) -> None:
        self.call("forcePause", [gid])

    def unpause(self, gid: str) -> None:
        self.call("unpause", [gid])

    def remove(self, gid: str) -> None:
        self.call("remove", [gid])

    def force_remove(self, gid: str) -> None:
        self.call("forceRemove", [gid])

    def remove_result(self, gid: str) -> None:
        self.call("removeDownloadResult", [gid])

    def pause_all(self) -> None:
        try:
            self.call("pauseAll", [])
        except Aria2Error:
            try:
                self.call("forcePauseAll", [])
            except Aria2Error:
                pass

    def unpause_all(self) -> None:
        try:
            self.call("unpauseAll", [])
        except Aria2Error:
            pass

    def purge_results(self) -> None:
        try:
            self.call("purgeDownloadResult", [])
        except Aria2Error:
            pass

    def change_global_option(self, options: Dict[str, str]) -> None:
        self.call("changeGlobalOption", [options])


def derive_display_name(url: str) -> Optional[str]:
    """从 URL 推导用于显示/落盘的默认文件名（去除查询串与路径遍历段）。"""
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return None
    name = Path(parsed.path).name
    if not name or name in (".", ".."):
        return None
    return urllib.parse.unquote(name)


class Aria2DownloaderManager:
    """泛用下载任务管理器（模块级单例 aria2_manager）。

    持有 aria2 子进程、任务表与后台轮询线程；快照经
    set_snapshot_callback 推送给窗口前端。
    """

    def __init__(self):
        self._client: Optional[Aria2DlClient] = None
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._on_snapshot: Optional[Callable[[dict], None]] = None

    # ---- 生命周期 ----

    def _settings(self) -> Dict[str, int]:
        from globalManagers.ConfigManager import ConfigManager
        cfg = ConfigManager().get('ui_default.aria2_dl', {}) or {}
        try:
            jobs = int(cfg.get('jobs') or DEFAULT_JOBS)
        except (TypeError, ValueError):
            jobs = DEFAULT_JOBS
        try:
            connection_limit = int(cfg.get('connection_limit') or DEFAULT_CONNECTION_LIMIT)
        except (TypeError, ValueError):
            connection_limit = DEFAULT_CONNECTION_LIMIT
        try:
            seed_time = int(cfg.get('seed_time') or DEFAULT_SEED_TIME)
        except (TypeError, ValueError):
            seed_time = DEFAULT_SEED_TIME
        return {
            "jobs": max(1, jobs),
            "connection_limit": max(1, min(16, connection_limit)),
            "seed_time": max(0, seed_time),
        }

    def is_running(self) -> bool:
        return self._client is not None and self._client.endpoint is not None

    def start_server(self) -> dict:
        """启动 aria2c 子进程与轮询线程（幂等）。"""
        with self._lock:
            if self.is_running():
                return {"success": True, "message": "下载服务已在运行"}
            binary = resolve_aria2_binary()
            if binary is None:
                return {
                    "success": False,
                    "message": "找不到 aria2c.exe（未随包捆绑，也未在 PATH 中找到）",
                }
            settings = self._settings()
            client = Aria2DlClient(
                binary,
                settings["jobs"],
                settings["connection_limit"],
                settings["seed_time"],
            )
            try:
                client.start()
            except Aria2Error as exc:
                _log_manager.log_error(exc)
                return {"success": False, "message": str(exc)}
            self._client = client
            self._stop_event = threading.Event()
            self._poll_thread = threading.Thread(
                target=self._poll_loop, daemon=True
            )
            self._poll_thread.start()
        return {"success": True, "message": "下载服务已启动"}

    def stop(self) -> None:
        """停止轮询线程与 aria2 子进程（窗口关闭/程序退出时调用）。"""
        with self._lock:
            self._stop_event.set()
            thread, self._poll_thread = self._poll_thread, None
            client, self._client = self._client, None
            self._on_snapshot = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        if client is not None:
            try:
                client.stop()
            except Exception:
                pass
        self._tasks.clear()

    def set_snapshot_callback(self, callback: Optional[Callable[[dict], None]]) -> None:
        with self._lock:
            self._on_snapshot = callback

    def _require_client(self) -> Aria2DlClient:
        client = self._client
        if client is None or not client.endpoint:
            raise Aria2Error("下载服务尚未启动")
        return client

    # ---- 任务操作 ----

    def add_urls(self, urls: List[str], save_dir: str) -> dict:
        """批量提交 URL（http/https/ftp/magnet），返回新增任务与错误明细。"""
        with self._lock:
            client = self._require_client()
            save_path = Path(save_dir)
            save_path.mkdir(parents=True, exist_ok=True)
            added = []
            errors = []
            seen = set()
            for raw in urls:
                url = (raw or "").strip()
                if not url:
                    continue
                if not url.startswith(VALID_SCHEMES):
                    errors.append({"url": url, "error": "不支持的链接（需 http/https/ftp 或 magnet:? 磁力链接）"})
                    continue
                if url in seen:
                    continue
                seen.add(url)
                kind = "magnet" if url.startswith(MAGNET_PREFIX) else "http"
                out = None if kind == "magnet" else derive_display_name(url)
                try:
                    gid = client.add_uri(url, save_path, out)
                except Aria2Error as exc:
                    _log_manager.log_error(exc)
                    errors.append({"url": url, "error": "提交失败: {}".format(exc)})
                    continue
                self._tasks[gid] = {
                    "url": url,
                    "save_dir": str(save_path),
                    "out": out,
                    "kind": kind,
                    "status": "waiting",
                    "total": 0,
                    "completed": 0,
                    "speed": 0,
                    "error_code": 0,
                    "error_message": "",
                }
                added.append({"gid": gid, "url": url, "out": out, "kind": kind})
            return {"success": True, "added": added, "errors": errors}

    def add_torrent(self, torrent_path: str, save_dir: str) -> dict:
        """提交 .torrent 文件（base64 传参 addTorrent）。"""
        path = Path(torrent_path)
        if not path.is_file():
            return {"success": False, "message": "torrent 文件不存在: {}".format(torrent_path)}
        if path.suffix.lower() != ".torrent":
            return {"success": False, "message": "仅支持 .torrent 文件"}
        with self._lock:
            client = self._require_client()
            save_path = Path(save_dir)
            save_path.mkdir(parents=True, exist_ok=True)
            try:
                torrent_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
                gid = client.add_torrent(torrent_b64, save_path)
            except Aria2Error as exc:
                _log_manager.log_error(exc)
                return {"success": False, "message": "提交失败: {}".format(exc)}
            self._tasks[gid] = {
                "url": path.name,
                "save_dir": str(save_path),
                "out": None,
                "kind": "torrent",
                "status": "waiting",
                "total": 0,
                "completed": 0,
                "speed": 0,
                "error_code": 0,
                "error_message": "",
            }
            return {"success": True, "gid": gid, "message": "已提交 {}".format(path.name)}

    def pause(self, gid: str) -> dict:
        with self._lock:
            if gid not in self._tasks:
                return {"success": False, "message": "任务不存在"}
            client = self._require_client()
            try:
                client.pause(gid)
            except Aria2Error:
                try:
                    client.force_pause(gid)
                except Aria2Error as exc:
                    return {"success": False, "message": "暂停失败: {}".format(exc)}
            return {"success": True}

    def resume(self, gid: str) -> dict:
        with self._lock:
            if gid not in self._tasks:
                return {"success": False, "message": "任务不存在"}
            client = self._require_client()
            try:
                client.unpause(gid)
            except Aria2Error as exc:
                return {"success": False, "message": "继续失败: {}".format(exc)}
            return {"success": True}

    def remove(self, gid: str) -> dict:
        """删除任务（活动/等待 remove → forceRemove 兜底 → 结果清理）。"""
        with self._lock:
            task = self._tasks.get(gid)
            if task is None:
                return {"success": False, "message": "任务不存在"}
            client = self._require_client()
            try:
                client.remove(gid)
            except Aria2Error:
                try:
                    client.force_remove(gid)
                except Aria2Error:
                    try:
                        client.remove_result(gid)
                    except Aria2Error as exc:
                        return {"success": False, "message": "删除失败: {}".format(exc)}
            self._tasks.pop(gid, None)
            return {"success": True}

    def pause_all(self) -> dict:
        with self._lock:
            if not self._tasks:
                return {"success": True}
            client = self._require_client()
            try:
                client.pause_all()
            except Aria2Error as exc:
                return {"success": False, "message": "暂停全部失败: {}".format(exc)}
            return {"success": True}

    def resume_all(self) -> dict:
        with self._lock:
            if not self._tasks:
                return {"success": True}
            client = self._require_client()
            try:
                client.unpause_all()
            except Aria2Error as exc:
                return {"success": False, "message": "继续全部失败: {}".format(exc)}
            return {"success": True}

    def purge_completed(self) -> dict:
        """清除已完成/出错/已删除任务及其下载结果。"""
        with self._lock:
            client = self._require_client()
            for gid, task in list(self._tasks.items()):
                if task.get("status") in TERMINAL_STATES:
                    try:
                        client.remove_result(gid)
                    except Aria2Error:
                        pass
                    self._tasks.pop(gid, None)
            try:
                client.purge_results()
            except Aria2Error:
                pass
            return {"success": True}

    # ---- 快照 / 轮询 ----

    def _poll_loop(self) -> None:
        while not self._stop_event.wait(POLL_INTERVAL):
            try:
                snapshot = self.snapshot()
            except Exception:
                continue
            with self._lock:
                callback = self._on_snapshot
            if callback is not None:
                try:
                    callback(snapshot)
                except Exception:
                    pass

    def snapshot(self) -> dict:
        """聚合全部任务状态与全局统计。"""
        with self._lock:
            client = self._client
            tasks = list(self._tasks.items())
        available = client is not None
        running = available and client.endpoint is not None
        result_tasks = []
        counts = {
            "active": 0, "waiting": 0, "paused": 0,
            "complete": 0, "error": 0, "removed": 0,
        }
        total_speed = 0
        if running:
            try:
                active_list = client.tell_active()
            except Aria2Error:
                active_list = []
            active_gids = {str(d.get("gid")) for d in active_list}
            for gid, task in tasks:
                try:
                    status = client.status(gid)
                except Aria2Error:
                    continue
                state = status.get("status") or "waiting"
                if state == "active" and gid not in active_gids:
                    state = "waiting"
                total = int(status.get("totalLength") or 0)
                completed = int(status.get("completedLength") or 0)
                speed = int(status.get("downloadSpeed") or 0)
                task.update({
                    "status": state,
                    "total": total,
                    "completed": completed,
                    "speed": speed if state == "active" else 0,
                    "error_code": int(status.get("errorCode") or 0),
                    "error_message": status.get("errorMessage") or "",
                })
                name = task.get("out") or task.get("url") or ""
                bittorrent = status.get("bittorrent") or {}
                info = bittorrent.get("info") or {}
                if info.get("name"):
                    name = info["name"]
                elif task.get("kind") in ("torrent", "magnet"):
                    files = status.get("files") or []
                    if files:
                        try:
                            name = Path(files[0].get("path", "")).name or name
                        except Exception:
                            pass
                pct = 0 if total <= 0 else min(100.0, completed * 100.0 / total)
                result_tasks.append({
                    "gid": gid,
                    "name": name,
                    "url": task.get("url", ""),
                    "kind": task.get("kind", "http"),
                    "status": state,
                    "total": total,
                    "completed": completed,
                    "speed": task["speed"],
                    "pct": round(pct, 1),
                    "error_code": task["error_code"],
                    "error_message": task["error_message"],
                })
                bucket = state if state in counts else "waiting"
                counts[bucket] += 1
                total_speed += task["speed"]
            self._adopt_magnet_children(client, active_list)
        else:
            for gid, task in tasks:
                result_tasks.append({
                    "gid": gid,
                    "name": task.get("out") or task.get("url", ""),
                    "url": task.get("url", ""),
                    "kind": task.get("kind", "http"),
                    "status": task.get("status", "waiting"),
                    "total": 0, "completed": 0, "speed": 0, "pct": 0,
                    "error_code": 0, "error_message": "",
                })
                counts[task.get("status", "waiting") if task.get("status") in counts else "waiting"] += 1
        counts["total"] = len(result_tasks)
        return {
            "available": resolve_aria2_binary() is not None,
            "server_running": running,
            "counts": counts,
            "total_speed": total_speed,
            "tasks": result_tasks,
        }

    def _adopt_magnet_children(
        self, client: Aria2DlClient, active_list: List[Dict[str, Any]]
    ) -> None:
        """磁力链接取回元数据后 aria2 会以新 gid 派生真正的文件下载任务。

        若发现不属于任何任务的活动 gid，且目录匹配某已完成元数据的磁力任务，
        则将其收养进同一任务记录，保持任务列表连续显示。
        """
        known = set(self._tasks.keys())
        candidates = {}
        for gid, task in self._tasks.items():
            if task.get("kind") == "magnet" and task.get("status") in TERMINAL_STATES:
                candidates.setdefault(task.get("save_dir"), []).append(gid)
        for entry in active_list:
            gid = str(entry.get("gid"))
            if gid in known:
                continue
            directory = str(entry.get("dir") or "")
            parents = candidates.get(directory) or candidates.get(str(Path(directory).parent))
            if not parents:
                continue
            parent_gid = parents[0]
            parent = self._tasks[parent_gid]
            self._tasks[gid] = {
                "url": parent.get("url", ""),
                "save_dir": parent.get("save_dir", ""),
                "out": None,
                "kind": "magnet",
                "status": entry.get("status") or "active",
                "total": 0, "completed": 0, "speed": 0,
                "error_code": 0, "error_message": "",
            }
            self._tasks.pop(parent_gid, None)
            _log_manager.debug(
                "[高速下载器] 磁力任务派生下载已收养: {} -> {} (gid={})".format(
                    parent.get("url"), directory, gid
                )
            )
            break


aria2_manager = Aria2DownloaderManager()
