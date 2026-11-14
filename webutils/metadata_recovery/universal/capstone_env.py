#!/usr/bin/env python3
"""capstone_env.py - capstone 惰性加载与运行时自愈（纯标准库）。

## 为什么需要这个模块

`webutils/__init__.py` 在应用启动时就会导入 metadata_recovery 包，进而导入
init_locator / extract_disasm。若这两个模块在**模块级**执行
`try: from capstone import ... except ImportError: _CAPSTONE_OK = False`，
"capstone 缺失"这一状态就被固化在进程内存里：

    pip install capstone → importlib.util.find_spec("capstone") 立刻返回
    True（FileFinder 按目录 mtime 失效缓存），页面显示"已就绪"，
    但 _CAPSTONE_OK 仍是 False → 运行恢复时抛"缺少 capstone，请先安装"
    → 用户只能重启应用才能正常使用。

因此 capstone 的导入必须**推迟到真正反汇编时**，并且每次探测失败后清掉
导入缓存重试，让"页面内一键安装"在当前进程立即生效，无需重启。

## 设计要点

- 本模块只依赖标准库（保持 webutils 导入链轻量、可在任何时机导入）。
- 探测 = **真实导入 + 真实反汇编自检**（不是 find_spec）：只有能构造
  反汇编器、能反汇编一条 NOP 才算可用，避免"包在但原生库加载失败"的
  假阳性。
- `reset()` 在 pip 安装完成后调用，清缓存后重新探测。
- 全部状态访问加锁：安装回调跑在 pywebview 后台线程，页面轮询跑在
  主线程，二者会并发调用。
"""

from __future__ import annotations

import importlib
import sys
import threading
import time

# 探测失败后的节流窗口（秒）：页面刷新会反复调用 available()，
# 命中窗口时直接复用上次结论，避免反复 import 失败拖慢状态接口。
_PROBE_THROTTLE_SEC = 1.0

# 自检样本：一条 x86-64 NOP
_SELF_TEST_CODE = b"\x90"
_SELF_TEST_ADDR = 0x1000

# capstone 顶层 API（探测成功后缓存）：(Cs, CS_ARCH_X86, CS_MODE_64)
_api: tuple | None = None
# 最近一次探测是否成功（导入成功且反汇编自检通过）
_usable: bool = False
_last_error: str = ""
_last_probe_at: float = 0.0
_version: str = ""

_lock = threading.RLock()


def _purge_capstone_modules() -> None:
    """清掉 sys.modules 里残留的 capstone 模块。

    只在**探测失败**时清理：失败的导入可能留下部分初始化的子模块
    （如 capstone.x86），不清会给下一次 import 返回半成品对象。
    """
    stale = [name for name in list(sys.modules)
             if name == "capstone" or name.startswith("capstone.")]
    for name in stale:
        sys.modules.pop(name, None)


def _import_capstone() -> tuple:
    """真正导入 capstone，返回 (Cs, CS_ARCH_X86, CS_MODE_64)。

    导入前先 invalidate_caches()：pip 刚写进 site-packages 的目录需要
    刷新 finder 缓存才能被发现（新目录一般能靠 mtime 失效，但显式刷新
    更可靠，且对"父目录 mtime 未变"的边缘情况有效）。
    """
    importlib.invalidate_caches()
    from capstone import CS_ARCH_X86, CS_MODE_64, Cs  # noqa: WPS433 (延迟导入)
    return Cs, CS_ARCH_X86, CS_MODE_64


def _probe() -> bool:
    """真实探测：导入 + 构造反汇编器 + 反汇编一条 NOP。

    成功缓存 API 与版本；失败记录真实异常文本并清理残留模块。
    """
    global _api, _usable, _last_error, _version
    with _lock:
        try:
            api = _import_capstone()
            Cs, CS_ARCH_X86, CS_MODE_64 = api
            md = Cs(CS_ARCH_X86, CS_MODE_64)
            md.detail = False
            if not list(md.disasm(_SELF_TEST_CODE, _SELF_TEST_ADDR)):
                raise RuntimeError("反汇编自检失败：无法解析 NOP 指令")
        except Exception as exc:  # noqa: BLE001 - ImportError/OSError 均记录
            _api = None
            _usable = False
            _last_error = f"{type(exc).__name__}: {exc}"
            _version = ""
            _purge_capstone_modules()
            return False
        _api = api
        _usable = True
        _last_error = ""
        _version = _resolve_version()
        return True


def _resolve_version() -> str:
    """capstone 版本号（优先分发元数据，回退包内 __version__）。

    注意 capstone 包的 `__version__` 来自原生库版本号（如 5.0.7），可能与
    pip 安装的 wheel 版本（如 5.0.9）不一致，因此优先用 importlib.metadata。
    """
    try:
        from importlib.metadata import version as _dist_version
        return str(_dist_version("capstone"))
    except Exception:  # noqa: BLE001 - 元数据缺失（如手工复制）时回退
        pass
    try:
        return str(importlib.import_module("capstone").__version__)
    except Exception:  # noqa: BLE001 - 版本号只是展示用，取不到不影响可用性
        return ""


def reset() -> None:
    """清空缓存并解除节流，下一次 available() 会重新真实探测。

    pip 安装完成后必须调用；页面「重新检测」同样用它强制刷新。
    """
    global _api, _usable, _last_error, _last_probe_at, _version
    with _lock:
        _api = None
        _usable = False
        _last_error = ""
        _last_probe_at = 0.0
        _version = ""
        _purge_capstone_modules()


def available(force: bool = False) -> bool:
    """capstone 是否**真的可用**（真实导入 + 反汇编自检）。

    force=True 绕过节流（页面「重新检测」/安装后验证使用）。
    """
    global _last_probe_at
    with _lock:
        if _usable:
            return True
        now = time.monotonic()
        if not force and _last_probe_at and (now - _last_probe_at) < _PROBE_THROTTLE_SEC:
            return False
        _last_probe_at = now
        return _probe()


def require() -> tuple:
    """确保 capstone 可用并返回 (Cs, CS_ARCH_X86, CS_MODE_64)。

    失败时抛出带真实异常的可操作错误（每次调用都重新尝试探测，因此
    「刚在页面里装完就点运行」的路径不会被陈旧状态挡住）。
    """
    with _lock:
        if _usable and _api is not None:
            return _api
        if _probe():
            assert _api is not None
            return _api
        detail = _last_error or "未知原因"
        raise RuntimeError(
            "缺少 capstone 反汇编库（定位/提取需要）：请先在 Metadata 恢复页"
            "「步骤 1」点击「一键安装 capstone」后重试。\n"
            f"真实错误：{detail}")


def last_error() -> str:
    """最近一次探测失败的真实异常文本（可用时为空串）。"""
    with _lock:
        return _last_error


def version() -> str:
    """capstone 版本号（未知时为空串）。"""
    with _lock:
        return _version if _usable else ""


def new_disassembler(detail: bool = False):
    """构造 x86-64 反汇编器（唯一的 Cs 构造点）。

    把所有 Cs(CS_ARCH_X86, CS_MODE_64) 集中到此处，业务模块级不再持有
    capstone 引用，从而不会冻结"缺失"状态。
    """
    Cs, CS_ARCH_X86, CS_MODE_64 = require()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = detail
    return md


def smoke_test() -> bool:
    """安装后验证（等价于强制重新探测一次）。

    仅"能 import"不足以判定可用：.pyd 被安全软件锁住时会抛 OSError，
    残留包也可能导入成功而原生库加载失败，因此要实际反汇编一条指令。
    """
    return _probe()
