"""
globalManagers/pending_pip_ops.py
延迟依赖操作（pending pip ops）——纯标准库模块。

更新流程中的新增/升级依赖会优先在 GUI 内安装。若安装因 DLL 占用、权限等
非网络原因失败，则写入 pending 文件
（%LOCALAPPDATA%/LCTA/pending_pip_ops.json），延迟到下次启动、加载任何第三方
库之前由 apply_pending_pip_ops() 重试安装。废弃依赖永久保留，不执行卸载。

!!! 本模块必须保持纯标准库导入 !!!
start_webui.py init_env() 在任何第三方库导入之前直接导入本模块执行 pending
操作。一旦本模块（或其导入链）引入第三方库，就可能在"上次更新残留库缺失"
时导入失败，导致 pending 永远无法执行、程序无法启动（进不去更新流程）。
globalManagers/__init__.py 仅导入 LogManager/ConfigManager（纯标准库），安全。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from globalManagers.LogManager import LogManager

_log_manager = LogManager()

_PENDING_OPS_FILENAME = "pending_pip_ops.json"
_TSINGHUA_PYPI_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"

_REQUIREMENT_PACKAGE_RE = re.compile(r"^\s*([A-Za-z0-9._-]+)")
_REQUIREMENT_NORMALIZE_RE = re.compile(r"[-_.]+")

_NETWORK_ERROR_MARKERS = (
    "cannot connect to proxy",
    "certificate verify failed",
    "connection aborted",
    "connection broken",
    "connection refused",
    "connection reset",
    "connection timed out",
    "could not fetch url",
    "failed to establish a new connection",
    "getaddrinfo failed",
    "max retries exceeded",
    "name or service not known",
    "network is unreachable",
    "proxy error",
    "proxyerror",
    "read timed out",
    "readtimeout",
    "remote end closed connection",
    "sslerror",
    "temporary failure in name resolution",
    "tunnel connection failed",
    "winerror 10054",
    "winerror 10060",
    "winerror 10061",
    "winerror 11001",
)


@dataclass(frozen=True)
class PipOperationResult:
    success: bool
    network_error: bool = False
    returncode: Optional[int] = None
    error: str = ""

    def __bool__(self) -> bool:
        return self.success


def _normalize_pkg_name(name: str) -> str:
    """PEP 503 归一化：小写、-_. 视为等价"""
    return _REQUIREMENT_NORMALIZE_RE.sub("-", name).lower()


def _normalize_spec(spec: str) -> str:
    """归一化 requirements spec 行，用于依赖变更的等价比较。

    仅归一化包名（PEP 503 大小写/分隔符）与行首尾空白——这两类差异不构成
    真实版本变动，避免误触发 pending 延迟；版本与其余约束原样比较。
    """
    spec = spec.strip()
    m = _REQUIREMENT_PACKAGE_RE.match(spec)
    if m:
        name = m.group(1)
        normalized = _normalize_pkg_name(name)
        if name != normalized:
            spec = spec[:m.start(1)] + normalized + spec[m.end(1):]
    return spec


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
            # 兼容读取旧格式，但永远不再执行依赖卸载。
            "uninstall": [],
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
        # 更新流程永久保留废弃依赖。即使读取到旧版本遗留的卸载任务，
        # 后续写回时也会将其清空，避免先卸载导致当前或新版本依赖缺失。
        "uninstall": [],
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


def _decode_pip_output(raw) -> str:
    if isinstance(raw, str):
        return raw
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk", errors="replace")


def _is_network_error(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _NETWORK_ERROR_MARKERS)


def _run_pip(args: List[str]) -> PipOperationResult:
    """执行 pip 子命令并返回可分类的结果。

    pip 子进程注入 PYTHONIOENCODING=utf-8，保证其输出为 UTF-8；
    stderr 解码失败时回退 GBK，避免中文 Windows 下乱码进日志。
    """
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip"] + args, capture_output=True, env=env)
        return PipOperationResult(success=True)
    except subprocess.TimeoutExpired as e:
        stderr = _decode_pip_output(e.stderr or b"")
        stdout = _decode_pip_output(e.stdout or b"")
        raw = f"{stderr}\n{stdout}".strip()
        error = raw or str(e)
        _log_manager.log(f"pip {' '.join(args)} 网络超时: {error}")
        return PipOperationResult(success=False, network_error=True, error=error)
    except subprocess.CalledProcessError as e:
        _log_manager.log(f"pip {' '.join(args)} 失败: {e}")
        stderr = _decode_pip_output(e.stderr or b"")
        stdout = _decode_pip_output(e.stdout or b"")
        err = f"{stderr}\n{stdout}".strip()
        _log_manager.log(f"退出码: {e.returncode}，错误输出: {err or '无'}")
        return PipOperationResult(
            success=False,
            network_error=_is_network_error(err),
            returncode=e.returncode,
            error=err,
        )
    except Exception as e:
        _log_manager.log(f"pip {' '.join(args)} 无法执行: {e}")
        return PipOperationResult(success=False, error=str(e))


def _run_pip_install(
    spec: str,
    index_url: Optional[str] = None,
) -> PipOperationResult:
    args = ["install"]
    if index_url:
        args.extend(["--index-url", index_url])
    args.append(spec)
    return _run_pip(args)


def apply_pending_pip_ops(
    path: Optional[Path] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """启动早期重试待处理的依赖安装。

    必须在加载任何第三方库之前调用（start_webui.py init_env() 启动钩子）：
    此时进程尚未加载第三方模块，GUI 更新会话中因 DLL 占用等非网络原因
    无法升级的包可以正常处理。废弃依赖不会卸载。全部成功后删除记录；部分失败
    保留剩余项，记日志并在下次启动时重试。异常不外抛，不阻塞启动。

    progress_callback: 可选，每个 pip 操作执行前后回调状态文本
    （供启动提示窗口展示进度）。
    """
    def _notify(text: str):
        if progress_callback:
            try:
                progress_callback(text)
            except Exception:
                pass

    ops = load_pending_ops(path)
    if not ops["uninstall"] and not ops["install"]:
        save_pending_ops(ops, path)
        return True
    for spec in list(ops["install"]):
        _notify(f"正在安装依赖 {spec}…")
        result = _run_pip_install(spec)
        if not result and result.network_error:
            _notify(f"默认源连接失败，正在通过清华源安装 {spec}…")
            result = _run_pip_install(spec, _TSINGHUA_PYPI_INDEX)
        if result:
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
        f"仍有依赖安装未完成，将在下次启动时重试: {ops['install']}"
    )
    return False
