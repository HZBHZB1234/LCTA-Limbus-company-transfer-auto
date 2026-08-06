"""管理员提权写入/移除 hosts 与提权子进程入口。

elevate_write_hosts / elevate_remove_hosts 通过 helper_script = __file__ +
sys.executable <file> --cdn-write-hosts <json> 重启自身做 UAC 提权，
__main__ 块负责处理 --cdn-write-hosts 子进程参数。

提权策略：非管理员进程先真实尝试直接写入/移除；仅当权限类失败
（WinError 5 / PermissionError）时才触发 UAC 提权重试——不做“新建文件”
式权限探测，避免目录可新建但目标文件不可替换（ACL/只读/杀软拦截）
导致的假阳性短路提权路径。

提权子进程会以脚本方式直接运行本文件（无包上下文），此时相对导入不可用，
故根据 __package__ 判断：脚本模式将 webutils/ 加入 sys.path 后按包导入，
避免触发 webutils/__init__（其导入整包依赖）；两种模式导入内容一致。
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import tempfile
import time
from typing import Callable, Dict, List, Optional

if __package__ is None:
    # 脚本方式运行（UAC 提权子进程入口）：__file__ 位于 webutils/cdn/ 下
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cdn.constants import (
        CFA_END_MARKER,
        CFA_START_MARKER,
        CF_END_MARKER,
        CF_START_MARKER,
    )
    from cdn.hosts import (
        _format_hosts_error,
        _get_hosts_path,
        _is_permission_error,
        remove_hosts_block,
        write_hosts,
    )
else:
    from .constants import (
        CFA_END_MARKER,
        CFA_START_MARKER,
        CF_END_MARKER,
        CF_START_MARKER,
    )
    from .hosts import (
        _format_hosts_error,
        _get_hosts_path,
        _is_permission_error,
        remove_hosts_block,
        write_hosts,
    )


def _is_admin() -> bool:
    """检查当前进程是否以管理员权限运行。"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _run_as_admin(script_path: str, args: List[str]) -> int:
    """以管理员权限运行 Python 脚本。返回进程退出码。"""
    try:
        params = " ".join(f'"{a}"' for a in [script_path] + args)
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1  # SW_SHOWNORMAL
        )
        # ShellExecuteW 返回 > 32 表示成功
        if result <= 32:
            raise OSError(f"ShellExecuteW 返回错误码：{result}")
        return 0
    except Exception as e:
        raise OSError(f"提权失败（用户可能取消了 UAC 弹窗）：{e}")


def elevate_write_hosts(
    cf_ip: Optional[str] = None,
    cloudfront_mappings: Optional[Dict[str, str]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    hosts_path: Optional[str] = None
):
    """
    在必要时提权写入 hosts。
    对应 LLC_BABEL HostsWriteElevator。

    策略：非管理员进程先真实尝试直接写入；仅权限类失败（WinError 5）
    才触发 UAC 提权重试，避免探测文件权限与实际替换权限不一致造成的
    “探针通过却写入失败、且不弹 UAC”的假阳性。

    返回: (success: bool, error_message: Optional[str])
    """
    if hosts_path is None:
        hosts_path = _get_hosts_path()

    os.makedirs(os.path.dirname(hosts_path), exist_ok=True)

    # 已经以管理员身份运行，直接写入
    if _is_admin():
        success, err = write_hosts(
            cf_ip, cloudfront_mappings, log_cb, hosts_path, elevated=True
        )
        return success, err

    # 非管理员：先真实尝试直接写入；权限类失败才走 UAC 提权
    try:
        success, err = write_hosts(
            cf_ip, cloudfront_mappings, log_cb, hosts_path,
            raise_on_permission_error=True,
        )
        return success, err
    except (PermissionError, OSError) as e:
        if not _is_permission_error(e):
            return False, _format_hosts_error(e)
        # 权限类失败，继续走提权路径

    # 需要提权：将请求写入临时 JSON 文件，然后以管理员身份重新运行
    request_json = {
        "action": "write_hosts",
        "cf_ip": cf_ip,
        "cloudfront_mappings": cloudfront_mappings or {},
        "hosts_path": hosts_path,
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="lcta_cdn_",
        delete=False,
        encoding="utf-8"
    ) as f:
        json.dump(request_json, f)
        request_path = f.name

    try:
        if log_cb:
            log_cb("请求管理员权限以写入 hosts...")

        # 以管理员身份运行自身的辅助函数
        # ShellExecuteW 不等待子进程退出，需要轮询等待 result 文件
        helper_script = __file__
        args = ["--cdn-write-hosts", request_path]
        _run_as_admin(helper_script, args)

        # 轮询等待结果文件（最久等 30 秒）
        result_path = request_path + ".result"
        waited = 0
        while not os.path.isfile(result_path) and waited < 30:
            time.sleep(1)
            waited += 1

        if os.path.isfile(result_path):
            with open(result_path, "r", encoding="utf-8") as f:
                result_data = json.load(f)
            success = result_data.get("success", False)
            msg = result_data.get("message", "")
            if log_cb:
                log_cb(msg)
            return success, None if success else msg
        else:
            timeout_msg = "未收到提权写入结果（等待超时）"
            if log_cb:
                log_cb(timeout_msg)
            return False, timeout_msg

    except OSError as e:
        # ShellExecuteW 返回 1223 = 用户取消了 UAC 弹窗
        if "1223" in str(e) or "取消" in str(e):
            user_msg = (
                f"写入 hosts 需要管理员权限。\n\n"
                f"原因：用户取消了管理员权限提升（UAC）弹窗。\n\n"
                f"解决方法：请重新操作并在 UAC 弹窗中选择\"是\"以授予权限。"
            )
        else:
            user_msg = (
                f"请求管理员权限失败。\n\n"
                f"原因：{e}\n\n"
                f"解决方法：请尝试以管理员身份手动运行程序后重试。"
            )
        if log_cb:
            log_cb(user_msg)
        return False, user_msg
    finally:
        # 清理临时请求文件
        try:
            if os.path.isfile(request_path):
                os.remove(request_path)
        except Exception:
            pass
        try:
            result_path = request_path + ".result"
            if os.path.isfile(result_path):
                os.remove(result_path)
        except Exception:
            pass


def elevate_remove_hosts(
    block_type: str,
    log_cb: Optional[Callable[[str], None]] = None,
    hosts_path: Optional[str] = None
):
    """
    在必要时提权移除单个 hosts 受管块。
    block_type: "cf" 或 "cfa"

    返回: (success: bool, error_message: Optional[str])
    """
    if hosts_path is None:
        hosts_path = _get_hosts_path()

    if block_type == "cf":
        marker_start, marker_end = CF_START_MARKER, CF_END_MARKER
        label = "Cloudflare"
    elif block_type == "cfa":
        marker_start, marker_end = CFA_START_MARKER, CFA_END_MARKER
        label = "CloudFront"
    else:
        error_msg = f"未知的移除类型：{block_type}"
        if log_cb:
            log_cb(error_msg)
        return False, error_msg

    os.makedirs(os.path.dirname(hosts_path), exist_ok=True)

    # 已经以管理员身份运行，直接移除
    if _is_admin():
        success, err = remove_hosts_block(
            marker_start, marker_end, hosts_path, log_cb, elevated=True
        )
        return success, err

    # 非管理员：先真实尝试直接移除；权限类失败才走 UAC 提权
    try:
        success, err = remove_hosts_block(
            marker_start, marker_end, hosts_path, log_cb,
            raise_on_permission_error=True,
        )
        return success, err
    except (PermissionError, OSError) as e:
        if not _is_permission_error(e):
            return False, _format_hosts_error(e)
        # 权限类失败，继续走提权路径

    # 需要提权
    request_json = {
        "action": "remove_hosts",
        "block_type": block_type,
        "hosts_path": hosts_path,
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="lcta_cdn_",
        delete=False,
        encoding="utf-8"
    ) as f:
        json.dump(request_json, f)
        request_path = f.name

    try:
        if log_cb:
            log_cb(f"请求管理员权限以移除 {label} hosts 条目...")

        helper_script = __file__
        args = ["--cdn-write-hosts", request_path]
        _run_as_admin(helper_script, args)

        # 轮询等待结果文件（最久等 30 秒）
        result_path = request_path + ".result"
        waited = 0
        while not os.path.isfile(result_path) and waited < 30:
            time.sleep(1)
            waited += 1

        if os.path.isfile(result_path):
            with open(result_path, "r", encoding="utf-8") as f:
                result_data = json.load(f)
            success = result_data.get("success", False)
            msg = result_data.get("message", "")
            if log_cb:
                log_cb(msg)
            return success, None if success else msg
        else:
            timeout_msg = f"移除 {label} hosts 超时"
            if log_cb:
                log_cb(timeout_msg)
            return False, timeout_msg

    except Exception as e:
        # ShellExecuteW 返回 1223 = 用户取消了 UAC 弹窗
        err_str = str(e)
        if "1223" in err_str or "取消" in err_str:
            user_msg = (
                f"移除 {label} hosts 条目需要管理员权限。\n\n"
                f"原因：用户取消了管理员权限提升（UAC）弹窗。\n\n"
                f"解决方法：请重新操作并在 UAC 弹窗中选择\"是\"以授予权限。"
            )
        else:
            user_msg = (
                f"请求管理员权限失败。\n\n"
                f"原因：{e}\n\n"
                f"解决方法：请尝试以管理员身份手动运行程序后重试。"
            )
        if log_cb:
            log_cb(user_msg)
        return False, user_msg


def _handle_helper_invocation():
    """
    处理提权辅助进程调用。
    当以 --cdn-write-hosts <request_json_path> 参数运行时，执行实际的 hosts 写入并返回结果。
    """
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--cdn-write-hosts":
        request_path = args[1]
        if os.path.isfile(request_path):
            try:
                with open(request_path, "r", encoding="utf-8") as f:
                    req = json.load(f)

                action = req.get("action")
                if action == "write_hosts":
                    success, err = write_hosts(
                        cf_ip=req.get("cf_ip"),
                        cloudfront_mappings=req.get("cloudfront_mappings"),
                        hosts_path=req.get("hosts_path"),
                        elevated=True,
                    )

                    result = {
                        "success": success,
                        "message": "hosts 写入成功" if success else (err or "hosts 写入失败"),
                    }

                elif action == "remove_hosts":
                    block_type = req.get("block_type", "")
                    if block_type == "cf":
                        marker_s, marker_e = CF_START_MARKER, CF_END_MARKER
                    else:
                        marker_s, marker_e = CFA_START_MARKER, CFA_END_MARKER

                    success, err = remove_hosts_block(
                        marker_s, marker_e,
                        hosts_path=req.get("hosts_path", _get_hosts_path()),
                        elevated=True,
                    )
                    result = {
                        "success": success,
                        "message": f"{block_type} hosts 移除成功" if success else (err or f"{block_type} hosts 移除失败"),
                    }

                result_path = request_path + ".result"
                with open(result_path, "w", encoding="utf-8") as f:
                    json.dump(result, f)
            except Exception as e:
                result_path = request_path + ".result"
                with open(result_path, "w", encoding="utf-8") as f:
                    json.dump({"success": False, "message": str(e)}, f)

        sys.exit(0)


# ---- 启动时检查是否为提权辅助调用 ----
if __name__ == "__main__" and len(sys.argv) >= 2 and sys.argv[1] == "--cdn-write-hosts":
    _handle_helper_invocation()
