"""Hosts 文件管理。"""
from __future__ import annotations

import ipaddress
import os
import stat
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

# 原子替换 hosts 时的重试策略：权限类（WinError 5）或占用类（WinError 32/33）
# 失败会短暂重试，吸收杀软扫描/其他工具瞬时占用；全部失败后再分析占用进程。
REPLACE_MAX_ATTEMPTS = 3
REPLACE_RETRY_DELAY = 0.5

from .constants import (
    CFA_END_MARKER,
    CFA_START_MARKER,
    CF_END_MARKER,
    CF_START_MARKER,
    CLOUDFLARE_DOMAINS,
    CLOUDFRONT_ENDPOINTS,
)


def _is_permission_error(exc: Exception) -> bool:
    """判断异常是否为权限类错误（[WinError 5] / PermissionError / 拒绝访问）。"""
    err_str = str(exc)
    return isinstance(exc, PermissionError) or "WinError 5" in err_str or "拒绝访问" in err_str


def _is_lock_error(exc: Exception) -> bool:
    """判断异常是否为文件占用类错误（[WinError 32] / [WinError 33] / 文件正在使用）。"""
    err_str = str(exc)
    return (
        isinstance(exc, OSError)
        and (
            "WinError 32" in err_str
            or "WinError 33" in err_str
            or "另一个程序正在使用此文件" in err_str
        )
    )


def _is_retryable_replace_error(exc: Exception) -> bool:
    """替换 hosts 时可重试的错误：权限类（WinError 5）或占用类（WinError 32/33）。"""
    return _is_permission_error(exc) or _is_lock_error(exc)


def _format_hosts_error(exc: Exception, elevated: bool = False) -> str:
    """
    将 hosts 写入/移除时的异常转换为用户可读的错误描述。
    包含错误原因与解决建议；无法识别时退回原始错误信息。

    elevated: 是否为已提权（管理员）进程中的失败；用于区分引导文案。
    """
    err_str = str(exc)

    # 权限不足（[WinError 5] / PermissionError）
    if _is_permission_error(exc):
        if elevated:
            return (
                f"已以管理员权限运行，仍无法修改 hosts 文件。\n\n"
                f"原因：hosts 文件可能被其他程序占用（如杀毒软件的 hosts 保护、"
                f"hosts 管理/加速工具正在监听该文件），或被设置为只读属性，"
                f"或被安全软件（如 Windows Defender、火绒等）的 hosts 保护功能拦截。\n\n"
                f"解决方法：\n"
                f"1. 退出占用 hosts 文件的程序（见下方占用进程提示），或暂时关闭杀毒软件的 hosts 保护后重试；\n"
                f"2. 右键 hosts 文件 → 属性 → 取消勾选“只读”；\n"
                f"3. 将本程序添加到杀毒软件白名单/排除列表，或关闭其 hosts 保护功能。"
            )
        return (
            f"权限不足，无法修改 hosts 文件。\n\n"
            f"原因：hosts 位于系统保护目录 C:\\Windows\\System32\\drivers\\etc\\，"
            f"修改需要管理员权限，当前程序未以管理员身份运行。\n\n"
            f"解决方法：请重新操作并在 UAC 弹窗中选择“是”以授予权限。"
        )

    # 文件被占用（[WinError 32]）
    if isinstance(exc, OSError) and ("WinError 32" in err_str or "另一个程序正在使用此文件" in err_str):
        return (
            f"hosts 文件被其他程序锁定。\n\n"
            f"原因：杀毒软件或安全软件（如 Windows Defender、火绒等）"
            f"正在保护 hosts 文件，阻止了写入操作。\n\n"
            f"解决方法：\n"
            f"1. 暂时关闭杀毒软件的 hosts 保护 / 文件锁功能后重试；\n"
            f"2. 或将本程序添加到杀毒软件的白名单 / 排除列表中。"
        )

    # 找不到文件
    if isinstance(exc, FileNotFoundError) or "WinError 2" in err_str:
        return (
            f"未找到系统 hosts 文件。\n\n"
            f"原因：C:\\Windows\\System32\\drivers\\etc\\hosts 文件不存在。\n\n"
            f"解决方法：请确认该路径下 hosts 文件是否存在。如已丢失，"
            f"可新建一个空文本文件并命名为 hosts（无扩展名）。"
        )

    # 无法识别的错误 — 退回原始信息
    return f"hosts 操作失败。\n\n原始错误：{err_str}"


def _detect_encoding(file_path: str) -> Tuple[str, bytes]:
    """检测文件编码（对应 LLC_BABEL HostsWriter.DetectEncoding）。"""
    with open(file_path, "rb") as f:
        raw = f.read()

    if len(raw) >= 4 and raw[:4] == b"\x00\x00\xfe\xff":
        return "utf-32-be", b"\x00\x00\xfe\xff"
    if len(raw) >= 4 and raw[:4] == b"\xff\xfe\x00\x00":
        return "utf-32-le", b"\xff\xfe\x00\x00"
    if len(raw) >= 3 and raw[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig", b"\xef\xbb\xbf"
    if len(raw) >= 2 and raw[:2] == b"\xfe\xff":
        return "utf-16-be", b"\xfe\xff"
    if len(raw) >= 2 and raw[:2] == b"\xff\xfe":
        return "utf-16-le", b"\xff\xfe"

    return "utf-8", b""


def _read_hosts_lines(hosts_path: str) -> Tuple[List[Tuple[str, str]], str, bytes]:
    """
    读取 hosts 文件，返回 (lines, encoding_name, bom_bytes)。
    每行: (content, terminator)
    """
    encoding_name, bom = _detect_encoding(hosts_path)
    with open(hosts_path, "r", encoding=encoding_name, errors="replace") as f:
        text = f.read()

    # utf-16/utf-32 系列 codec 不消费 BOM，读取后首行残留 \ufeff；
    # 不去除会导致写回时与手动写入的 BOM 叠加成双 BOM，且受管块首行标记无法被 strip 匹配
    text = text.lstrip("\ufeff")

    # 去掉 BOM 头的文本（已由 codec 处理，但 utf-8-sig 会去掉）
    lines = []
    idx = 0
    line_start = 0
    while idx < len(text):
        if text[idx] == "\r":
            if idx + 1 < len(text) and text[idx + 1] == "\n":
                lines.append((text[line_start:idx], "\r\n"))
                idx += 2
            else:
                lines.append((text[line_start:idx], "\r"))
                idx += 1
            line_start = idx
        elif text[idx] == "\n":
            lines.append((text[line_start:idx], "\n"))
            idx += 1
            line_start = idx
        else:
            idx += 1

    if line_start < len(text):
        lines.append((text[line_start:], ""))

    return lines, encoding_name, bom


def _build_block(marker_start: str, marker_end: str, mappings: List[Tuple[str, str]]) -> List[str]:
    """构建 hosts 标记块。mappings: [(ip, domain), ...]"""
    block = [marker_start]
    for ip, domain in mappings:
        block.append(f"{ip}\t{domain}")
    block.append(marker_end)
    return block


def _clear_readonly(
    path: str,
    log_cb: Optional[Callable[[str], None]] = None
) -> None:
    """尝试清除目标文件的只读属性，供 os.replace 原子替换使用；失败记录日志。"""
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError as e:
        if log_cb:
            log_cb(f"清除 hosts 只读属性失败（{e}），后续替换可能被拒绝")


def _get_process_path(pid: int) -> Optional[str]:
    """通过 OpenProcess + QueryFullProcessImageNameW 获取进程可执行文件路径。"""
    try:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not h:
            return None
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = ctypes.c_ulong(ctypes.sizeof(buf))
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                h, 0, buf, ctypes.byref(size)
            ):
                return buf.value
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        return None
    return None


def _find_locking_processes(file_path: str) -> List[Dict[str, Any]]:
    """
    通过 Restart Manager API 查找占用指定文件的进程。
    返回: [{"pid": int, "name": str(可执行文件路径或进程名)}]
    无占用/查询失败/非 Windows 时返回空列表。
    """
    if os.name != "nt" or not os.path.isfile(file_path):
        return []
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return []

    class RM_UNIQUE_PROCESS(ctypes.Structure):
        _fields_ = [
            ("dwProcessId", wintypes.DWORD),
            ("ProcessStartTime", wintypes.FILETIME),
        ]

    class RM_PROCESS_INFO(ctypes.Structure):
        _fields_ = [
            ("Process", RM_UNIQUE_PROCESS),
            ("strAppName", ctypes.c_wchar * 256),
            ("strServiceShortName", ctypes.c_wchar * 64),
            ("ApplicationType", wintypes.DWORD),
            ("AppStatus", wintypes.DWORD),
            ("TSSessionId", wintypes.DWORD),
            ("bRestartable", wintypes.BOOL),
        ]

    try:
        rm = ctypes.WinDLL("rstrtmgr")
        rm.RmStartSession.argtypes = [
            ctypes.POINTER(wintypes.DWORD),
            wintypes.DWORD,
            ctypes.c_wchar_p,  # WCHAR strSessionKey[32]
        ]
        rm.RmStartSession.restype = wintypes.DWORD
        rm.RmRegisterResources.argtypes = [
            wintypes.DWORD,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_wchar_p),  # LPCWSTR rgsFilenames[]
            wintypes.UINT,
            ctypes.c_void_p,  # RM_UNIQUE_PROCESS rgsApplications[]
            wintypes.UINT,
            ctypes.c_void_p,  # LPCWSTR rgsServiceNames[]
        ]
        rm.RmRegisterResources.restype = wintypes.DWORD
        rm.RmGetList.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(RM_PROCESS_INFO),
            ctypes.POINTER(wintypes.DWORD),
        ]
        rm.RmGetList.restype = wintypes.DWORD
        rm.RmEndSession.argtypes = [wintypes.DWORD]
        rm.RmEndSession.restype = wintypes.DWORD

        session = wintypes.DWORD()
        # RmStartSession 会写入 32 字符的会话密钥并带终止符，需额外 1 个 WCHAR
        session_key = ctypes.create_unicode_buffer(33)

        err = rm.RmStartSession(ctypes.byref(session), 0, session_key)
        if err != 0:
            return []
        try:
            file_w = ctypes.c_wchar_p(file_path)
            err = rm.RmRegisterResources(
                session, 1, ctypes.byref(file_w), 0, None, 0, None
            )
            if err != 0:
                return []

            n_needed = wintypes.UINT()
            n_affected = wintypes.UINT()
            reboot_reasons = wintypes.DWORD()
            # 第一次调用仅获取进程数（返回 ERROR_MORE_DATA 属正常）
            rm.RmGetList(
                session,
                ctypes.byref(n_needed),
                ctypes.byref(n_affected),
                None,
                ctypes.byref(reboot_reasons),
            )
            if n_needed.value == 0:
                return []

            count = n_needed.value
            info_array = (RM_PROCESS_INFO * count)()
            n_affected = wintypes.UINT(count)
            err = rm.RmGetList(
                session,
                ctypes.byref(n_needed),
                ctypes.byref(n_affected),
                info_array,
                ctypes.byref(reboot_reasons),
            )
            if err != 0:
                return []

            result = []
            for i in range(n_affected.value):
                info = info_array[i]
                pid = int(info.Process.dwProcessId)
                name = (
                    _get_process_path(pid)
                    or info.strAppName
                    or info.strServiceShortName
                    or f"PID {pid}"
                )
                result.append({"pid": pid, "name": name})
            return result
        finally:
            rm.RmEndSession(session)
    except Exception:
        return []


def _build_occupancy_detail(
    file_path: str,
    log_cb: Optional[Callable[[str], None]] = None
) -> str:
    """重试全部失败后，尝试定位占用文件的进程，返回可追加到错误文案的提示。"""
    try:
        procs = _find_locking_processes(file_path)
    except Exception:
        procs = []

    if procs:
        proc_lines = "\n".join(f"  PID {p['pid']}: {p['name']}" for p in procs)
        detail = (
            f"\n\n检测到以下进程占用 hosts 文件：\n{proc_lines}\n"
            f"可尝试退出相关程序后重试。"
        )
    else:
        detail = (
            "\n\n未能检测到占用 hosts 文件的进程"
            "（可能是杀毒软件在后台保护该文件）。"
        )
    if log_cb:
        log_cb("[hosts]" + detail.replace("\n", " "))
    return detail


def write_hosts(
    cf_ip: Optional[str] = None,
    cloudfront_mappings: Optional[Dict[str, str]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    hosts_path: Optional[str] = None,
    raise_on_permission_error: bool = False,
    elevated: bool = False
):
    """
    将优选 IP 写入系统 hosts 文件的受管标记块。
    对应 LLC_BABEL HostsWriter.UpdateAsync()。

    cf_ip: Cloudflare 优选 IP（None 表示不清除旧映射）
    cloudfront_mappings: {domain: ip, ...}

    raise_on_permission_error: 权限类错误（WinError 5/PermissionError）时抛出原始异常，
        供提权流程判断是否升级权限重试（其余错误仍返回格式化描述）。
    elevated: 当前进程是否已提权；影响权限失败时的提示文案。

    权限/占用类替换失败会按 REPLACE_MAX_ATTEMPTS 次短间隔重试（吸收瞬时占用）；
    全部失败后尝试分析占用 hosts 文件的进程（PID 与路径）并附加到错误文案。

    返回: (success: bool, error_message: Optional[str])
    """
    if hosts_path is None:
        hosts_path = _get_hosts_path()

    # 读取现有 hosts
    if os.path.isfile(hosts_path):
        lines, encoding_name, bom = _read_hosts_lines(hosts_path)
    else:
        lines = []
        encoding_name = "utf-8"
        bom = b""

    # 准备 Cloudflare 映射
    cf_mappings = []
    if cf_ip:
        for domain in CLOUDFLARE_DOMAINS:
            cf_mappings.append((cf_ip, domain))

    # 准备 CloudFront 映射
    cfa_mappings = []
    if cloudfront_mappings:
        for domain, ip in cloudfront_mappings.items():
            if domain in CLOUDFRONT_ENDPOINTS:
                cfa_mappings.append((ip, domain))

    # 重写 Cloudflare 标记块
    _rewrite_block(lines, CF_START_MARKER, CF_END_MARKER, cf_mappings, log_cb)
    # 重写 CloudFront 标记块
    _rewrite_block(lines, CFA_START_MARKER, CFA_END_MARKER, cfa_mappings, log_cb)

    # 写入临时文件并原子替换；权限/占用类失败按 REPLACE_MAX_ATTEMPTS 次重试
    temp_path = hosts_path + f".{uuid.uuid4().hex[:8]}.tmp"
    last_error: Optional[Exception] = None
    try:
        newline = _detect_newline(lines)

        for attempt in range(1, REPLACE_MAX_ATTEMPTS + 1):
            try:
                with open(temp_path, "w", encoding=encoding_name, newline="", errors="replace") as f:
                    if bom and encoding_name not in ("utf-8-sig",):
                        f.buffer.write(bom)

                    for content, terminator in lines:
                        f.write(content)
                        f.write(terminator)

                # 清除目标只读属性后原子替换（MoveFileEx 拒绝替换只读目标）
                _clear_readonly(hosts_path, log_cb)
                os.replace(temp_path, hosts_path)

                if log_cb:
                    log_cb(f"hosts 已更新：{hosts_path}")

                return True, None

            except Exception as e:
                last_error = e
                if attempt >= REPLACE_MAX_ATTEMPTS or not _is_retryable_replace_error(e):
                    break
                if log_cb:
                    log_cb(
                        f"替换 hosts 失败（第 {attempt}/{REPLACE_MAX_ATTEMPTS} 次尝试），"
                        f"稍后重试：{e}"
                    )
                time.sleep(REPLACE_RETRY_DELAY)

        e = last_error
        error_msg = f"写入 hosts 失败：{e}"
        if log_cb:
            log_cb(error_msg)
        if raise_on_permission_error and _is_permission_error(e):
            raise e
        detail = (
            _build_occupancy_detail(hosts_path, log_cb)
            if _is_retryable_replace_error(e)
            else ""
        )
        return False, _format_hosts_error(e, elevated=elevated) + detail
    finally:
        if os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def _rewrite_block(
    lines: List[Tuple[str, str]],
    start_marker: str,
    end_marker: str,
    mappings: List[Tuple[str, str]],
    log_cb: Optional[Callable[[str], None]] = None
):
    """重写一个受管标记块。lines 会被原地修改。"""
    newline = _detect_newline(lines)

    # 查找已有标记块
    start_idx = None
    end_idx = None
    for i, (content, _) in enumerate(lines):
        if content.strip() == start_marker:
            start_idx = i
        elif start_idx is not None and content.strip() == end_marker:
            end_idx = i
            break

    # 构建新块
    new_block = []
    if mappings:
        new_block.append((start_marker, newline))
        for ip, domain in mappings:
            new_block.append((f"{ip}\t{domain}", newline))
        new_block[-1] = (new_block[-1][0], newline)
        new_block.append((end_marker, newline))

    if start_idx is not None and end_idx is not None:
        # 替换已有块
        if new_block:
            # 保留原始终止符
            orig_terminator = lines[end_idx][1] if end_idx < len(lines) else newline
            new_block[-1] = (new_block[-1][0], orig_terminator)
            lines[start_idx:end_idx + 1] = new_block
            if log_cb:
                log_cb(f"已替换受管标记块 {start_marker}")
        else:
            lines[start_idx:end_idx + 1] = []
            if log_cb:
                log_cb(f"已移除受管标记块 {start_marker}")
    elif new_block:
        # 追加新块
        if lines and lines[-1][1] == "":
            lines[-1] = (lines[-1][0], newline)
        if lines and lines[-1][0].strip() != "":
            lines.append(("", newline))
        lines.extend(new_block)
        if log_cb:
            log_cb(f"已追加受管标记块 {start_marker}")


def _detect_newline(lines: List[Tuple[str, str]]) -> str:
    for _, terminator in lines:
        if terminator:
            return terminator
    return "\r\n"


def remove_hosts_block(
    marker_start: str,
    marker_end: str,
    hosts_path: str,
    log_cb: Optional[Callable[[str], None]] = None,
    raise_on_permission_error: bool = False,
    elevated: bool = False
):
    """
    移除 hosts 文件中的单个受管标记块（CF 或 CFA）。

    raise_on_permission_error: 权限类错误（WinError 5/PermissionError）时抛出原始异常，
        供提权流程判断是否升级权限重试（其余错误仍返回格式化描述）。
    elevated: 当前进程是否已提权；影响权限失败时的提示文案。

    权限/占用类替换失败会按 REPLACE_MAX_ATTEMPTS 次短间隔重试（吸收瞬时占用）；
    全部失败后尝试分析占用 hosts 文件的进程（PID 与路径）并附加到错误文案。

    返回: (success: bool, error_message: Optional[str])
    """
    # 读取现有 hosts
    if os.path.isfile(hosts_path):
        lines, encoding_name, bom = _read_hosts_lines(hosts_path)
    else:
        return True, None  # 没有 hosts 文件，无需移除

    # 用空映射重写目标块（即移除）
    _rewrite_block(lines, marker_start, marker_end, [], log_cb)

    # 写入临时文件并原子替换；权限/占用类失败按 REPLACE_MAX_ATTEMPTS 次重试
    temp_path = hosts_path + f".{uuid.uuid4().hex[:8]}.tmp"
    last_error: Optional[Exception] = None
    try:
        newline = _detect_newline(lines)

        for attempt in range(1, REPLACE_MAX_ATTEMPTS + 1):
            try:
                with open(temp_path, "w", encoding=encoding_name, newline="", errors="replace") as f:
                    if bom and encoding_name not in ("utf-8-sig",):
                        f.buffer.write(bom)

                    for content, terminator in lines:
                        f.write(content)
                        f.write(terminator)

                # 清除目标只读属性后原子替换（MoveFileEx 拒绝替换只读目标）
                _clear_readonly(hosts_path, log_cb)
                os.replace(temp_path, hosts_path)

                if log_cb:
                    log_cb(f"已移除 hosts 受管标记块 {marker_start}")

                return True, None

            except Exception as e:
                last_error = e
                if attempt >= REPLACE_MAX_ATTEMPTS or not _is_retryable_replace_error(e):
                    break
                if log_cb:
                    log_cb(
                        f"替换 hosts 失败（第 {attempt}/{REPLACE_MAX_ATTEMPTS} 次尝试），"
                        f"稍后重试：{e}"
                    )
                time.sleep(REPLACE_RETRY_DELAY)

        e = last_error
        error_msg = f"移除 hosts 块失败：{e}"
        if log_cb:
            log_cb(error_msg)
        if raise_on_permission_error and _is_permission_error(e):
            raise e
        detail = (
            _build_occupancy_detail(hosts_path, log_cb)
            if _is_retryable_replace_error(e)
            else ""
        )
        return False, _format_hosts_error(e, elevated=elevated) + detail
    finally:
        if os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def read_current_hosts_mappings(
    hosts_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    读取当前 hosts 文件中的受管映射。
    返回: {"cf_ip": str|None, "cloudfront": {domain: ip}}
    """
    if hosts_path is None:
        hosts_path = _get_hosts_path()

    result = {
        "cf_ip": None,
        "cloudfront": {},
    }

    if not os.path.isfile(hosts_path):
        return result

    try:
        lines, _, _ = _read_hosts_lines(hosts_path)

        def read_block(start_marker, end_marker):
            in_block = False
            mappings = []
            for content, _ in lines:
                stripped = content.strip()
                if stripped == start_marker:
                    in_block = True
                    continue
                if stripped == end_marker:
                    in_block = False
                    continue
                if in_block and stripped and not stripped.startswith("#"):
                    parts = stripped.split()
                    if len(parts) >= 2:
                        mappings.append((parts[0], parts[1]))
            return mappings

        cf_mappings = read_block(CF_START_MARKER, CF_END_MARKER)
        if cf_mappings:
            result["cf_ip"] = cf_mappings[0][0]  # CF 所有域名共享同一个 IP

        cfa_mappings = read_block(CFA_START_MARKER, CFA_END_MARKER)
        for ip, domain in cfa_mappings:
            result["cloudfront"][domain] = ip

    except Exception:
        pass

    return result


def _get_hosts_path() -> str:
    """获取系统 hosts 文件路径。"""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(system_root, r"System32\drivers\etc\hosts")


def _is_public_ipv4(ip_str: str) -> bool:
    """判断一个 IPv4 地址是否为公网地址（对应 LLC_BABEL IsPublicIpv4）。"""
    try:
        addr = ipaddress.IPv4Address(ip_str)
    except ipaddress.AddressValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified)
