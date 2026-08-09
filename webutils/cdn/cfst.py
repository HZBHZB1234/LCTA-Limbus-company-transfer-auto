"""Cloudflare cfst 测速。"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .constants import (
    CFST_DOWNLOAD_URL,
    CFST_EXE,
    CFST_OVERALL_TIMEOUT,
    CFST_TEST_URL,
    IP_FILE,
    IP_TXT_URL,
)


def _get_app_dir() -> str:
    """获取应用根目录。"""
    if os.getenv("is_frozen") == "true":
        return os.path.dirname(sys.executable)
    return str(Path(__file__).parent.parent.parent)


def _get_cfst_dir() -> str:
    """获取 CFST 目录路径（code 目录下 tools/cfst/）。"""
    return os.path.join(_get_app_dir(), "tools", "cfst")


def _ensure_cfst_available(log_cb=None) -> bool:
    """
    确保 tools/cfst/ 目录包含 cfst.exe 和 ip.txt。
    如果缺失，运行时自动从 GitHub 下载（InitCode 仅在 build 时运行，
    开发调试时 tools/cfst/ 不存在，需要懒加载）。
    返回是否可用。
    """
    cfst_dir = _get_cfst_dir()
    cfst_exe = os.path.join(cfst_dir, CFST_EXE)
    ip_txt = os.path.join(cfst_dir, IP_FILE)

    if os.path.isfile(cfst_exe) and os.path.isfile(ip_txt):
        return True

    if log_cb:
        log_cb("CFST 文件缺失，正在自动下载...")

    zip_path = os.path.join(cfst_dir, "cfst_windows_amd64.zip")
    try:
        import zipfile
        import urllib.request

        os.makedirs(cfst_dir, exist_ok=True)

        # 下载 ip.txt
        if not os.path.isfile(ip_txt):
            if log_cb:
                log_cb("下载 ip.txt...")
            urllib.request.urlretrieve(IP_TXT_URL, ip_txt)

        # 下载 cfst.exe
        if not os.path.isfile(cfst_exe):
            if log_cb:
                log_cb("下载 cfst.exe...")
            urllib.request.urlretrieve(CFST_DOWNLOAD_URL, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extract("cfst.exe", cfst_dir)
            os.remove(zip_path)

        if log_cb:
            log_cb("CFST 下载完成")
        return True

    except Exception as e:
        # 下载中断会残留 cfst_windows_amd64.zip（常见为 0 字节），删除避免残留垃圾文件
        try:
            if os.path.isfile(zip_path):
                os.remove(zip_path)
        except Exception:
            pass
        if log_cb:
            log_cb(f"CFST 自动下载失败：{e}")
        return False


def run_cfst(
    cfst_dir: Optional[str] = None,
    test_url: str = CFST_TEST_URL,
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], None]] = None
) -> Optional[Dict[str, Any]]:
    """
    运行 cfst.exe 进行 Cloudflare CDN 测速，返回最优 IP 信息。
    对应 LLC_BABEL CfstRunner.RunCloudflareAsync()。

    返回: {"ip": str, "avg_latency_ms": float, "download_mbps": float, "loss_rate": float} 或 None
    """
    if cfst_dir is None:
        cfst_dir = _get_cfst_dir()

    # 确保 CFST 文件存在（开发调试时 InitCode 未运行，需懒加载）
    if not _ensure_cfst_available(log_cb=log_cb):
        return None

    cfst_exe_path = os.path.join(cfst_dir, CFST_EXE)
    if not os.path.isfile(cfst_exe_path):
        if log_cb:
            log_cb(f"找不到 cfst.exe：{cfst_exe_path}")
        return None

    out_file = os.path.join(cfst_dir, "result_cf.csv")

    # 删除旧结果
    if os.path.isfile(out_file):
        os.remove(out_file)

    cmd_args = [
        cfst_exe_path,
        "-f", IP_FILE,
        "-url", test_url,
        "-t", "2",
        "-dn", "25",
        "-dt", "5",
        "-p", "0",
        "-o", out_file,
    ]
    if log_cb:
        log_cb(f"执行：cfst.exe -f \"{IP_FILE}\" -url \"{test_url}\" -t 2 -dn 25 -dt 5 -p 0 -o \"{out_file}\"")

    progress_re = re.compile(r"(\d+)\s*/\s*(\d+)")

    proc = None
    try:
        # 通过 subprocess 运行（Windows 隐藏窗口）
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            cmd_args,
            cwd=cfst_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            creationflags=creationflags
        )

        # 读取 stdout/stderr 线程
        # cfst.exe (Go) 使用 \r 输出进度行（无 \n），readline() 无法读取。
        # 必须逐字节读取（binary mode），避免 Python TextIOWrapper universal
        # newlines 模式将 \r 转为 \n 导致进度行无法正确分隔。
        # ANSI escape code 正则（cfst 可能输出 \x1b[2K \x1b[1G 等清屏序列）
        ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
        # cfst 进度条模式（[___---↘↙↖↗]），用于抑制日志噪音
        progress_bar_re = re.compile(r'\[[_\-↘↙↖↗]+]')

        def read_output(stream):
            buf = b""
            last_was_cr = False
            while True:
                ch = stream.read(1)
                if not ch:
                    if buf.strip():
                        _process_line(buf)
                    break
                if ch == b"\r":
                    if buf.strip():
                        _process_line(buf)
                    buf = b""
                    last_was_cr = True
                elif ch == b"\n":
                    if last_was_cr:
                        # \r\n 序列 —— 已在 \r 处处理过，跳过 \n
                        last_was_cr = False
                        continue
                    if buf.strip():
                        _process_line(buf)
                    buf = b""
                    last_was_cr = False
                else:
                    buf += ch
                    last_was_cr = False

        # 共享状态：daemon 线程更新当前 cfst 阶段与真实进度，主循环每 1s 轮询统一上报
        cfst_phase = ["准备中"]
        cfst_progress = [0.0]

        def _process_line(raw: bytes):
            # 解码并去除 ANSI escape codes
            line = raw.decode("utf-8", errors="replace")
            line = ansi_re.sub('', line).strip()
            if not line:
                return

            # 检测 cfst 阶段切换（基于 cfst 的 \n 日志消息）
            if "延迟测速" in line:
                cfst_phase[0] = "延迟测速"
            elif "下载测速" in line:
                cfst_phase[0] = "下载测速"

            # 检测是否为 cfst 进度条（抑制日志噪音）
            is_progress_bar = bool(progress_bar_re.search(line))

            # 上报进度：记录真实进度（已测 IP 数/总 IP 数），由主循环统一上报，
            # 避免与计时器兜底进度交替调用 progress_cb 导致进度条倒退
            matches = list(progress_re.finditer(line))
            if matches:
                m = matches[-1]
                current = int(m.group(1))
                total = int(m.group(2))
                pct = (current / total * 100) if total > 0 else 0
                if pct > cfst_progress[0]:
                    cfst_progress[0] = pct
            elif log_cb and not is_progress_bar:
                log_cb(line)

        t_stdout = threading.Thread(target=read_output, args=(proc.stdout,), daemon=True)
        t_stderr = threading.Thread(target=read_output, args=(proc.stderr,), daemon=True)
        t_stdout.start()
        t_stderr.start()

        # 等待进程结束（定期检查取消 + 推送阶段级进度计时器 + 总超时保护）
        t_phase_start = time.perf_counter()
        last_tick = t_phase_start
        timed_out = False
        while proc.poll() is None:
            if cancel_check:
                cancel_check()
            now = time.perf_counter()
            # 总超时保护：cfst 被安全软件/网络问题挂起时不能无限等待，超时后强制终止
            if now - t_phase_start >= CFST_OVERALL_TIMEOUT:
                timed_out = True
                if log_cb:
                    log_cb(f"CFST 测速超过 {CFST_OVERALL_TIMEOUT // 60} 分钟总超时，已强制终止。")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                break
            # 每秒更新一次进度文本，让用户知道程序在运行
            if progress_cb and now - last_tick >= 1.0:
                elapsed = int(now - t_phase_start)
                elapsed_str = f"{elapsed // 60}m{elapsed % 60:02d}s" if elapsed >= 60 else f"{elapsed}s"
                # 兜底进度按运行时长单调递增（0→95%，约 32s 后封顶），不回绕；
                # 与真实进度（已测 IP 数/总 IP 数）取较大值，保证进度条始终不倒退
                tick_pct = max(cfst_progress[0], min(95, elapsed * 3))
                progress_cb(tick_pct, f"Cloudflare {cfst_phase[0]}中... 已运行 {elapsed_str}")
                last_tick = now
            time.sleep(0.25)

        t_stdout.join(timeout=2)
        t_stderr.join(timeout=2)

        proc.wait()

        # 超时终止后结果文件必然缺失，直接返回并给出明确错误信息
        if timed_out:
            if log_cb:
                log_cb(f"CFST 测速超时（{CFST_OVERALL_TIMEOUT} 秒），未获得结果。")
            return None

        # 解析结果 CSV
        if not os.path.isfile(out_file):
            if log_cb:
                log_cb("CFST 未生成结果文件，可能本次测速结果为 0。")
            return None

        with open(out_file, "r", encoding="utf-8", errors="replace") as f:
            header = f.readline()  # 跳过表头
            first = f.readline().strip()

        if not first:
            if log_cb:
                log_cb("结果文件为空，没有可用 IP。")
            return None

        cols = first.split(",")
        if len(cols) < 6:
            if log_cb:
                log_cb(f"结果行格式异常：{first}")
            return None

        result = {
            "ip": cols[0].strip(),
            "loss_rate": _parse_float(cols[3]),
            "avg_latency_ms": _parse_float(cols[4]),
            "download_mbps": _parse_float(cols[5]),
        }

        if log_cb:
            log_cb(f"Cloudflare 最优 IP：{result['ip']} 延迟：{result['avg_latency_ms']:.1f}ms 下载：{result['download_mbps']:.1f}MB/s")

        return result

    except Exception as e:
        if log_cb:
            log_cb(f"cfst 运行出错：{e}")
        return None
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def _parse_float(s: str) -> float:
    try:
        return float(s.strip())
    except (ValueError, AttributeError):
        return 0.0
