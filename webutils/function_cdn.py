"""
CDN 优选模块 — 测试 Cloudflare / CloudFront 节点速度并写入系统 hosts 文件。
设计参考 LLC_BABEL（MIT License, Copyright (c) 2026 ZengXiaoPi），采用 Python 独立实现。
"""
import os
import sys
import re
import json
import time
import socket
import ssl
import struct
import uuid
import ctypes
import tempfile
import ipaddress
import subprocess
import threading
from pathlib import Path
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import Optional, Dict, List, Tuple, Callable, Any

# ---- 常量定义（对应 LLC_BABEL CdnTarget.cs） ----

_DEBUG = False

CF_START_MARKER = "# START-OF-LLC-BABEL-CF"
CF_END_MARKER   = "# END-OF-LLC-BABEL-CF"
CFA_START_MARKER = "# START-OF-LLC-BABEL-AMAZON"
CFA_END_MARKER   = "# END-OF-LLC-BABEL-AMAZON"

CLOUDFLARE_DOMAINS = [
    "download.limbuscompanycdn.org",
    "downloadcommon.limbuscompanycdn.org",
    "downloadfmod.limbuscompanycdn.org",
]

CLOUDFRONT_ENDPOINTS = {
    "www.limbuscompanyapi.com":    "https://www.limbuscompanyapi.com/",
    "notice.limbuscompanyapi.com": "https://notice.limbuscompanyapi.com/",
}

CFST_EXE = "cfst.exe"
IP_FILE = "ip.txt"
CFST_TEST_URL = "https://cf.xiu2.xyz/url"
CFST_VERSION = "v2.3.5"
CFST_DOWNLOAD_URL = (
    f"https://github.com/XIU2/CloudflareSpeedTest/releases/download/"
    f"{CFST_VERSION}/cfst_windows_amd64.zip"
)
IP_TXT_URL = "https://raw.githubusercontent.com/XIU2/CloudflareSpeedTest/master/ip.txt"

DOH_SOURCES = [
    ("阿里 DoH",   "https://dns.alidns.com/resolve"),
    ("DNSPod DoH", "https://doh.pub/dns-query"),
]

SOURCE_TIMEOUT = 3        # 每个 DNS 源的超时（秒）
PROBE_TIMEOUT = 4         # 每次 HTTPS 探测超时（秒）
MAX_CANDIDATES = 24
MAX_CONCURRENCY = 6
FINALIST_COUNT = 5
FINAL_ATTEMPTS = 3
REQUIRED_FINAL_SUCCESSES = 2
CLOUDFRONT_OVERALL_TIMEOUT = 45  # 匹配 LLC_BABEL DefaultOverallTimeout

# ---- CloudFront 探测失败分类（对应 LLC_BABEL CloudFrontProbeFailure 枚举） ----
# 每种失败类型都有对应的用户可读消息，方便日志诊断。
PROBE_FAILURE_NONE = None          # 探测成功
PROBE_FAILURE_CONNECTION = "Connection"
PROBE_FAILURE_TIMEOUT = "Timeout"
PROBE_FAILURE_TLS = "Tls"
PROBE_FAILURE_HTTP_STATUS = "HttpStatus"
PROBE_FAILURE_BUSINESS_CONTENT = "BusinessContent"
PROBE_FAILURE_CANCELED = "Canceled"
PROBE_FAILURE_NETWORK = "Network"

PROBE_FAILURE_MESSAGES = {
    PROBE_FAILURE_NONE: None,
    PROBE_FAILURE_CONNECTION: "无法连接到目标 IP（连接被拒绝或重置）。",
    PROBE_FAILURE_TIMEOUT: "探测超时（目标 IP 在规定时间内未响应）。",
    PROBE_FAILURE_TLS: "TLS 协商或证书验证失败。",
    PROBE_FAILURE_HTTP_STATUS: "目标端点返回了不可接受的 HTTP 状态码。",
    PROBE_FAILURE_BUSINESS_CONTENT: "目标端点响应未包含业务验证所需的关键内容。",
    PROBE_FAILURE_CANCELED: "探测已被取消。",
    PROBE_FAILURE_NETWORK: "探测因网络错误失败。",
}


def classify_probe_exception(exc: Exception) -> str:
    """将探测过程中的异常映射为 PROBE_FAILURE_* 常量。"""
    if isinstance(exc, ssl.SSLError):
        return PROBE_FAILURE_TLS
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return PROBE_FAILURE_TIMEOUT
    if isinstance(exc, (ConnectionRefusedError, ConnectionError, ConnectionAbortedError,
                        ConnectionResetError, OSError)):
        return PROBE_FAILURE_CONNECTION
    return PROBE_FAILURE_NETWORK


def get_failure_message(failure: Optional[str]) -> Optional[str]:
    """获取失败类型的用户可读消息。"""
    if failure is None:
        return None
    return PROBE_FAILURE_MESSAGES.get(failure, f"探测失败（{failure}）。")

# ---- 工具函数 ----

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


def _get_app_dir() -> str:
    """获取应用根目录。"""
    if os.getenv("is_frozen") == "true":
        return os.path.dirname(sys.executable)
    return str(Path(__file__).parent.parent)


def _get_cfst_dir() -> str:
    """获取 CFST 目录路径。"""
    return os.path.join(_get_app_dir(), "CFST")


def _ensure_cfst_available(log_cb=None) -> bool:
    """
    确保 CFST/ 目录包含 cfst.exe 和 ip.txt。
    如果缺失，运行时自动从 GitHub 下载（InitCode 仅在 build 时运行，
    开发调试时 CFST/ 不存在，需要懒加载）。
    返回是否可用。
    """
    cfst_dir = _get_cfst_dir()
    cfst_exe = os.path.join(cfst_dir, CFST_EXE)
    ip_txt = os.path.join(cfst_dir, IP_FILE)

    if os.path.isfile(cfst_exe) and os.path.isfile(ip_txt):
        return True

    if log_cb:
        log_cb("CFST 文件缺失，正在自动下载...")

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
            zip_path = os.path.join(cfst_dir, "cfst_windows_amd64.zip")
            urllib.request.urlretrieve(CFST_DOWNLOAD_URL, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extract("cfst.exe", cfst_dir)
            os.remove(zip_path)

        if log_cb:
            log_cb("CFST 下载完成")
        return True

    except Exception as e:
        if log_cb:
            log_cb(f"CFST 自动下载失败：{e}")
        return False


# ---- 1. Cloudflare cfst 测速 ----

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

        # 共享状态：daemon 线程更新当前 cfst 阶段，主循环每 1s 轮询更新进度
        cfst_phase = ["准备中"]

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

            # 上报进度
            matches = list(progress_re.finditer(line))
            if matches:
                m = matches[-1]
                current = int(m.group(1))
                total = int(m.group(2))
                pct = (current / total * 100) if total > 0 else 0
                if progress_cb:
                    progress_cb(pct, line)
            elif log_cb and not is_progress_bar:
                log_cb(line)

        t_stdout = threading.Thread(target=read_output, args=(proc.stdout,), daemon=True)
        t_stderr = threading.Thread(target=read_output, args=(proc.stderr,), daemon=True)
        t_stdout.start()
        t_stderr.start()

        # 等待进程结束（定期检查取消 + 推送阶段级进度计时器）
        t_phase_start = time.perf_counter()
        last_tick = t_phase_start
        while proc.poll() is None:
            if cancel_check:
                cancel_check()
            now = time.perf_counter()
            # 每秒更新一次进度文本，让用户知道程序在运行
            if progress_cb and now - last_tick >= 1.0:
                elapsed = int(now - t_phase_start)
                elapsed_str = f"{elapsed // 60}m{elapsed % 60:02d}s" if elapsed >= 60 else f"{elapsed}s"
                # 进度数值缓慢递增（0→95%，每 30s 一个循环），不倒退
                tick_pct = min(95, (elapsed % 30) * 3)
                progress_cb(tick_pct, f"Cloudflare {cfst_phase[0]}中... 已运行 {elapsed_str}")
                last_tick = now
            time.sleep(0.25)

        t_stdout.join(timeout=2)
        t_stderr.join(timeout=2)

        proc.wait()

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


def _parse_float(s: str) -> float:
    try:
        return float(s.strip())
    except (ValueError, AttributeError):
        return 0.0


# ---- 2. CloudFront DNS 候选发现 ----

def resolve_cloudfront_dns(
    domain: str,
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], None]] = None
) -> List[str]:
    """
    从多个 DNS 源并行获取 CloudFront 域名的 IPv4 候选地址。
    对应 LLC_BABEL CloudFrontDnsCandidateProvider。

    返回：去重后的公网 IPv4 地址列表（最多 MAX_CANDIDATES 个）。
    """
    all_results = []  # [(source_name, ips_list), ...]

    def query_system_dns():
        """系统 DNS 查询。"""
        ips = []
        try:
            addrinfo = socket.getaddrinfo(domain, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)
            for item in addrinfo:
                ip = item[4][0]
                if _is_public_ipv4(ip) and ip not in ips:
                    ips.append(ip)
        except socket.gaierror:
            pass
        return ("系统 DNS", ips)

    def query_doh(source_name, doh_url):
        """DoH JSON API 查询。"""
        ips = []
        try:
            import urllib.request
            params = f"?name={domain}&type=A"
            url = doh_url + params
            req = urllib.request.Request(url, headers={"Accept": "application/dns-json"})
            with urllib.request.urlopen(req, timeout=SOURCE_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                answers = data.get("Answer", [])
                for ans in answers:
                    if ans.get("type") == 1:  # A 记录
                        ip = ans.get("data", "")
                        if _is_public_ipv4(ip) and ip not in ips:
                            ips.append(ip)
        except Exception as e:
            if log_cb:
                log_cb(f"{source_name} 查询失败：{e}")
        return (source_name, ips)

    # 并行查询所有来源
    # 系统 DNS 用单独 executor + timeout 包装（getaddrinfo 无超时参数，Windows 可能阻塞 30-120s）
    # 注意：使用显式 shutdown(wait=False) 避免 context manager 退出时阻塞等待 DNS 线程完成
    if progress_cb:
        progress_cb(2, f"[{domain}] 系统 DNS 解析中...")
    sys_executor = ThreadPoolExecutor(max_workers=1)
    try:
        sys_future = sys_executor.submit(query_system_dns)
        try:
            source_name, ips = sys_future.result(timeout=SOURCE_TIMEOUT + 2)
            if log_cb:
                log_cb(f"{source_name} 返回 {len(ips)} 个 IPv4 候选")
            all_results.append((source_name, ips))
        except (FuturesTimeoutError, Exception):
            if log_cb:
                log_cb("系统 DNS 查询超时或失败，跳过")
    finally:
        sys_executor.shutdown(wait=False)  # 不等待未完成的 DNS 线程

    if progress_cb:
        progress_cb(5, f"[{domain}] DoH 解析中...")

    # DoH 源已有 urllib timeout，直接并行
    doh_executor = ThreadPoolExecutor(max_workers=len(DOH_SOURCES))
    try:
        futures = {doh_executor.submit(query_doh, name, url): name for name, url in DOH_SOURCES}
        deadline = time.perf_counter() + SOURCE_TIMEOUT + 2
        pending = set(futures.keys())
        doh_completed = 0
        doh_total = len(DOH_SOURCES)
        while pending and time.perf_counter() < deadline:
            done, pending = concurrent.futures.wait(
                pending, timeout=0.5,
                return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                doh_completed += 1
                if progress_cb:
                    progress_cb(5 + int(doh_completed / doh_total * 5),
                                f"[{domain}] DoH {doh_completed}/{doh_total}")
                if cancel_check:
                    cancel_check()
                try:
                    source_name, ips = future.result(timeout=0.1)
                    if log_cb:
                        log_cb(f"{source_name} 返回 {len(ips)} 个 IPv4 候选")
                    all_results.append((source_name, ips))
                except Exception as e:
                    if log_cb:
                        log_cb(f"DNS 源查询异常：{e}")

        if log_cb:
            if _DEBUG:

                log_cb(f"[DEBUG] DoH while 循环退出 | pending={len(pending)} | deadline_remaining={deadline - time.perf_counter():.1f}s")
    finally:
        if log_cb:
            if _DEBUG:

                log_cb(f"[DEBUG] DoH executor 退出 | all_results_count={len(all_results)}")
        doh_executor.shutdown(wait=False)  # 不等待未完成的 DoH 线程

    if log_cb:
        if _DEBUG:

            log_cb(f"[DEBUG] 开始合并去重 | all_results={[(name, len(ips)) for name, ips in all_results]}")

    # 轮询合并 + 去重
    seen = set()
    merged = []
    idx = 0
    while any(idx < len(ips) for _, ips in all_results) and len(merged) < MAX_CANDIDATES:
        for _, ips in all_results:
            if idx < len(ips):
                ip = ips[idx]
                if ip not in seen:
                    seen.add(ip)
                    merged.append(ip)
                    if len(merged) >= MAX_CANDIDATES:
                        break
        idx += 1

    if log_cb:
        log_cb(f"CloudFront 候选 IP 共 {len(merged)} 个")
        if _DEBUG:

            log_cb(f"[DEBUG] 合并完成 | merged={merged}")

    if log_cb:
        if _DEBUG:

            log_cb(f"[DEBUG] resolve_cloudfront_dns 返回 | domain={domain} | merged_count={len(merged)}")
    return merged


# ---- 3. CloudFront HTTPS 端点探测 ----

def probe_cloudfront_endpoint(
    domain: str,
    probe_url: str,
    ip: str,
    timeout: float = PROBE_TIMEOUT
) -> Dict[str, Any]:
    """
    通过原始 socket + SSL/TLS SNI 探测单个 CloudFront IP。
    对应 LLC_BABEL PinnedCloudFrontHttpTransport + CloudFrontEndpointProbe。

    返回: {"success": bool, "ip": str, "elapsed_ms": float,
           "status_code": int|None, "failure": str|None}
    """
    sock = None
    ssl_sock = None
    t_start = time.perf_counter()
    try:

        # 1. TCP 连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, 443))

        # 2. SSL/TLS 握手（SNI 使用真实域名）
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        ssl_sock = ctx.wrap_socket(sock, server_hostname=domain)
        ssl_sock.settimeout(timeout)

        # 3. 手动构造并发送 HTTPS GET 请求
        from urllib.parse import urlparse
        parsed = urlparse(probe_url)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {domain}\r\n"
            f"User-Agent: LCTA_CDN/1.0\r\n"
            f"Accept: */*\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        ssl_sock.sendall(request.encode("utf-8"))

        # 4. 读取响应头
        raw_response = b""
        while b"\r\n\r\n" not in raw_response:
            chunk = ssl_sock.recv(4096)
            if not chunk:
                break
            raw_response += chunk
            if len(raw_response) > 65536:
                break  # 防止异常响应导致无限读取

        header_end = raw_response.find(b"\r\n\r\n")
        if header_end == -1:
            elapsed = time.perf_counter() - t_start
            return {"success": False, "ip": ip, "elapsed_ms": elapsed * 1000,
                    "status_code": None, "failure": "Network"}

        header_bytes = raw_response[:header_end]
        body_bytes = raw_response[header_end + 4:]

        # 解析状态码
        header_text = header_bytes.decode("utf-8", errors="replace")
        status_match = re.match(r"HTTP/\d\.\d\s+(\d+)", header_text)
        status_code = int(status_match.group(1)) if status_match else 0

        # 检查 x-amz-apigw-id 响应头
        has_api_gateway = "x-amz-apigw-id" in header_text.lower()

        # 读取公告域名的响应体（最多 32KB）
        body = body_bytes.decode("utf-8", errors="replace")
        is_notice = domain == "notice.limbuscompanyapi.com"

        if is_notice:
            # 尝试读取更多响应体以验证业务内容（最多 32KB）
            # 注：不能用 while + 检查 \r\n\r\n（body 中不存在），直接单次 recv
            try:
                ssl_sock.settimeout(1.0)  # 短超时，只读已到达的数据
                while len(body_bytes) < 32 * 1024:
                    chunk = ssl_sock.recv(4096)
                    if not chunk:
                        break
                    body_bytes += chunk
            except socket.timeout:
                pass  # 没有更多数据可读，使用已有 body
            finally:
                ssl_sock.settimeout(timeout)  # 恢复原始超时
            body = body_bytes.decode("utf-8", errors="replace")

        elapsed = time.perf_counter() - t_start

        # 5. 业务验证
        if is_notice:
            if status_code != 200:
                return {"success": False, "ip": ip, "elapsed_ms": elapsed * 1000,
                        "status_code": status_code, "failure": PROBE_FAILURE_HTTP_STATUS}
            if len(body_bytes) > 32 * 1024:
                return {"success": False, "ip": ip, "elapsed_ms": elapsed * 1000,
                        "status_code": status_code, "failure": PROBE_FAILURE_BUSINESS_CONTENT}
            if "latestUpdateDate" in body and "noticeDetailList" in body:
                return {"success": True, "ip": ip, "elapsed_ms": elapsed * 1000,
                        "status_code": status_code, "failure": PROBE_FAILURE_NONE}
            return {"success": False, "ip": ip, "elapsed_ms": elapsed * 1000,
                    "status_code": status_code, "failure": PROBE_FAILURE_BUSINESS_CONTENT}

        # API 域名验证
        if status_code < 200 or status_code >= 500:
            return {"success": False, "ip": ip, "elapsed_ms": elapsed * 1000,
                    "status_code": status_code, "failure": PROBE_FAILURE_HTTP_STATUS}
        if has_api_gateway:
            return {"success": True, "ip": ip, "elapsed_ms": elapsed * 1000,
                    "status_code": status_code, "failure": PROBE_FAILURE_NONE}
        return {"success": False, "ip": ip, "elapsed_ms": elapsed * 1000,
                "status_code": status_code, "failure": PROBE_FAILURE_BUSINESS_CONTENT}

    except BaseException as exc:
        elapsed = time.perf_counter() - t_start
        return {"success": False, "ip": ip, "elapsed_ms": elapsed * 1000,
                "status_code": None, "failure": classify_probe_exception(exc)}
    finally:
        try:
            if ssl_sock:
                ssl_sock.close()
        except Exception:
            pass
        try:
            if sock:
                sock.close()
        except Exception:
            pass


# ---- 4. CloudFront 两阶段 IP 选择 ----

def select_cloudfront_ip(
    domain: str,
    probe_url: str,
    candidates: List[str],
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], None]] = None,
    overall_deadline: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    两阶段筛选 CloudFront 最优 IP。
    对应 LLC_BABEL CloudFrontEndpointSelector。

    overall_deadline: 整体截止时间（perf_counter 值），传入后内部阶段截止时间
                     会 clamp 到此值，避免超过整体超时（对应 LLC_BABEL
                     OptimizationTermination deadline）。

    返回: {"ip": str, "domain": str, "median_latency_ms": float, ...} 或 None
    """
    import statistics
    import math

    t_start = time.perf_counter()

    if log_cb:
        if _DEBUG:

            log_cb(f"[DEBUG] select_cloudfront_ip 入口: {domain} | candidates={len(candidates)} | probe_url={probe_url}")

    if not candidates:
        if log_cb:
            log_cb(f"[{domain}] 无候选 IP，跳过")
        return None

    # 立即发送 0% 进度脉冲，让用户知道探测已开始
    if progress_cb:
        progress_cb(0, f"[{domain}] 开始资格赛探测...")

    # 阶段 1：资格赛——所有候选各测 1 次
    n_batches = math.ceil(len(candidates) / MAX_CONCURRENCY)
    est_seconds = max(1, n_batches) * PROBE_TIMEOUT
    if log_cb:
        log_cb(f"[{domain}] 资格赛：探测 {len(candidates)} 个候选IP（预计最长 ~{est_seconds}s）")
        if _DEBUG:

            log_cb(f"[DEBUG] 资格赛参数: n_batches={n_batches} | PROBE_TIMEOUT={PROBE_TIMEOUT} | MAX_CONCURRENCY={MAX_CONCURRENCY}")

    successful = []
    fail_counts = {}  # failure -> count
    qual_deadline = time.perf_counter() + max(10, n_batches * PROBE_TIMEOUT * 2)
    if overall_deadline is not None:
        qual_deadline = min(qual_deadline, overall_deadline)

    if log_cb:
        if _DEBUG:

            log_cb(f"[DEBUG] 资格赛 提交 {len(candidates)} 个探测任务到 ThreadPoolExecutor(max_workers={MAX_CONCURRENCY})")
        if _DEBUG:

            log_cb(f"[DEBUG] 资格赛 qual_deadline={qual_deadline - t_start:.1f}s")
    qexecutor = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)
    try:
        future_set = {
            qexecutor.submit(probe_cloudfront_endpoint, domain, probe_url, ip): ip
            for ip in candidates
        }
        pending = set(future_set.keys())
        completed = 0
        last_tick = time.perf_counter()
        try:
            while pending and time.perf_counter() < qual_deadline:
                done, pending = concurrent.futures.wait(
                    pending, timeout=1.0,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                now = time.perf_counter()
                if not done:
                    if log_cb:
                        if _DEBUG:

                            log_cb(f"[DEBUG] 资格赛 wait返回空 | pending={len(pending)} | elapsed={now - t_start:.1f}s")
                # 每 2 秒推送"探测中"状态，防止用户以为卡死
                if not done and progress_cb and now - last_tick >= 2.0:
                    elapsed = int(now - t_start)
                    progress_cb(0, f"[{domain}] 资格赛探测中... 已运行 {elapsed}s")
                    last_tick = now
                for future in done:
                    completed += 1
                    ip = future_set[future]
                    try:
                        result = future.result(timeout=0.1)
                    except Exception as exc:
                        result = {"success": False,
                                  "failure": classify_probe_exception(exc)}

                    if log_cb:
                        if _DEBUG:

                            log_cb(f"[DEBUG] 资格赛 probe完成 {completed}/{len(candidates)}: ip={ip} | success={result.get('success')} | failure={result.get('failure')} | elapsed_ms={result.get('elapsed_ms', '?')}")

                    if progress_cb:
                        pct = completed / len(candidates) * 40
                        progress_cb(pct, f"[{domain}] 资格赛 {completed}/{len(candidates)}")

                    if result.get("success"):
                        successful.append(result)
                    else:
                        failure = result.get("failure", "Unknown")
                        fail_counts[failure] = fail_counts.get(failure, 0) + 1

                    if cancel_check:
                        cancel_check()
                    last_tick = now
        except BaseException as e:
            if log_cb:
                if _DEBUG:

                    log_cb(f"[DEBUG] 资格赛 BaseException: {type(e).__name__}: {e}")
            qexecutor.shutdown(wait=False)
            raise
    finally:
        if log_cb:
            if _DEBUG:

                log_cb(f"[DEBUG] 资格赛 finally: completed={completed} | successful={len(successful)} | pending={len(pending)} | elapsed={time.perf_counter() - t_start:.1f}s")
        qexecutor.shutdown(wait=False)

    t_phase1 = time.perf_counter() - t_start

    if not successful:
        if log_cb:
            log_cb(f"[{domain}] 资格赛：无可用 IP（{len(candidates)} 个候选全部失败，耗时 {t_phase1:.1f}s）")
        return None

    # 按延迟排序，取前 N
    successful.sort(key=lambda r: r["elapsed_ms"])
    finalists = successful[:FINALIST_COUNT]

    if log_cb:
        fail_summary = ", ".join(f"{k}:{v}" for k, v in sorted(fail_counts.items())) if fail_counts else "无"
        log_cb(f"[{domain}] 资格赛完成（{t_phase1:.1f}s）：{len(successful)} 存活 / {len(candidates)} 候选，"
               f"前 {len(finalists)} 进入决赛" +
               (f"；失败分布：{fail_summary}" if fail_counts else ""))
        if _DEBUG:

            log_cb(f"[DEBUG] 资格赛结束: successful_ips={[r['ip'] for r in successful]}")

    # 阶段 2：决赛——每个候选测 3 次
    if log_cb:
        if _DEBUG:

            log_cb(f"[DEBUG] 进入决赛: finalists={len(finalists)} | tasks_per_finalist={FINAL_ATTEMPTS} | total_tasks={len(finalists) * FINAL_ATTEMPTS}")
    if progress_cb:
        progress_cb(40, f"[{domain}] 决赛探测中...")

    final_results = {}  # ip -> [elapsed_ms, ...]

    tasks = [(ip, probe_url) for ip in [r["ip"] for r in finalists] for _ in range(FINAL_ATTEMPTS)]
    n_final_batches = math.ceil(len(tasks) / MAX_CONCURRENCY)
    final_deadline = time.perf_counter() + max(10, n_final_batches * PROBE_TIMEOUT * 2)
    if overall_deadline is not None:
        final_deadline = min(final_deadline, overall_deadline)

    if log_cb:
        if _DEBUG:

            log_cb(f"[DEBUG] 决赛 提交 {len(tasks)} 个探测任务 | final_deadline={final_deadline - t_start:.1f}s")
    fexecutor = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)
    try:
        future_set = {
            fexecutor.submit(probe_cloudfront_endpoint, domain, probe_url, ip): ip
            for ip, _ in tasks
        }
        pending = set(future_set.keys())
        completed = 0
        last_tick = time.perf_counter()
        try:
            while pending and time.perf_counter() < final_deadline:
                done, pending = concurrent.futures.wait(
                    pending, timeout=1.0,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                now = time.perf_counter()
                if not done and progress_cb and now - last_tick >= 2.0:
                    elapsed = int(now - t_start)
                    progress_cb(40, f"[{domain}] 决赛探测中... 已运行 {elapsed}s")
                    last_tick = now
                for future in done:
                    completed += 1
                    ip = future_set[future]
                    try:
                        result = future.result(timeout=0.1)
                    except Exception:
                        continue

                    if log_cb:
                        if _DEBUG:

                            log_cb(f"[DEBUG] 决赛 probe完成 {completed}/{len(tasks)}: ip={ip} | success={result.get('success')} | elapsed_ms={result.get('elapsed_ms', '?')}")

                    if progress_cb:
                        pct = 40 + (completed / len(tasks) * 55)
                        progress_cb(pct, f"[{domain}] 决赛 {completed}/{len(tasks)}")

                    if result.get("success"):
                        if ip not in final_results:
                            final_results[ip] = []
                        final_results[ip].append(result["elapsed_ms"])

                    if cancel_check:
                        cancel_check()
                    last_tick = now
        except BaseException as e:
            if log_cb:
                if _DEBUG:

                    log_cb(f"[DEBUG] 决赛 BaseException: {type(e).__name__}: {e}")
            fexecutor.shutdown(wait=False)
            raise
    finally:
        if log_cb:
            if _DEBUG:

                log_cb(f"[DEBUG] 决赛 finally: completed={completed} | final_results={len(final_results)} IPs | pending={len(pending)} | elapsed={time.perf_counter() - t_start:.1f}s")
        fexecutor.shutdown(wait=False)

    # 评选最佳
    eligible = []
    for ip, latencies in final_results.items():
        if len(latencies) >= REQUIRED_FINAL_SUCCESSES:
            latencies_sorted = sorted(latencies)
            eligible.append({
                "ip": ip,
                "median_latency_ms": statistics.median(latencies_sorted),
                "worst_latency_ms": max(latencies_sorted),
                "success_count": len(latencies),
                "domain": domain,
            })

    t_total = time.perf_counter() - t_start

    if not eligible:
        if log_cb:
            log_cb(f"[{domain}] 决赛：无候选满足要求（需至少 {REQUIRED_FINAL_SUCCESSES} 次成功，耗时 {t_total:.1f}s）")
        if progress_cb:
            progress_cb(95, f"[{domain}] 无合格IP")
        return None

    # 按中位延迟 → 最差延迟 → 成功次数排序
    eligible.sort(key=lambda r: (r["median_latency_ms"], r["worst_latency_ms"], -r["success_count"]))
    best = eligible[0]

    if log_cb:
        log_cb(f"[{domain}] 最优 IP：{best['ip']} 中位延迟：{best['median_latency_ms']:.1f}ms（总耗时 {t_total:.1f}s）")

    if progress_cb:
        progress_cb(95, f"[{domain}] {best['ip']} ({best['median_latency_ms']:.0f}ms)")

    return best


# ---- 5. Hosts 文件管理 ----

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


def write_hosts(
    cf_ip: Optional[str] = None,
    cloudfront_mappings: Optional[Dict[str, str]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    hosts_path: Optional[str] = None
) -> bool:
    """
    将优选 IP 写入系统 hosts 文件的受管标记块。
    对应 LLC_BABEL HostsWriter.UpdateAsync()。

    cf_ip: Cloudflare 优选 IP（None 表示不清除旧映射）
    cloudfront_mappings: {domain: ip, ...}
    """
    if hosts_path is None:
        hosts_path = _get_hosts_path()

    backup_path = hosts_path + ".llcbabel.bak"

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

    # 写入临时文件
    temp_path = hosts_path + f".{uuid.uuid4().hex[:8]}.tmp"
    try:
        newline = _detect_newline(lines)

        with open(temp_path, "w", encoding=encoding_name, newline="", errors="replace") as f:
            if bom and encoding_name not in ("utf-8-sig",):
                f.buffer.write(bom)

            for content, terminator in lines:
                f.write(content)
                f.write(terminator)

        # 原子替换
        if os.path.isfile(hosts_path):
            if os.path.isfile(backup_path):
                os.remove(backup_path)
            os.replace(hosts_path, backup_path)

        os.replace(temp_path, hosts_path)

        if log_cb:
            log_cb(f"hosts 已更新：{hosts_path}")
            if os.path.isfile(backup_path):
                log_cb(f"更新前内容已备份到：{backup_path}")

        return True

    except Exception as e:
        if log_cb:
            log_cb(f"写入 hosts 失败：{e}")
        return False
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


def restore_hosts_backup(
    log_cb: Optional[Callable[[str], None]] = None,
    hosts_path: Optional[str] = None
) -> bool:
    """
    从备份文件还原 hosts。
    对应 LLC_BABEL HostsWriter.RestoreBackupAsync()。
    """
    if hosts_path is None:
        hosts_path = _get_hosts_path()

    backup_path = hosts_path + ".llcbabel.bak"

    if not os.path.isfile(backup_path):
        if log_cb:
            log_cb(f"找不到 hosts 备份文件：{backup_path}")
        return False

    try:
        import shutil
        shutil.copy2(backup_path, hosts_path)
        if log_cb:
            log_cb(f"已从备份还原 hosts：{backup_path}")
        return True
    except Exception as e:
        if log_cb:
            log_cb(f"还原 hosts 失败：{e}")
        return False


def read_current_hosts_mappings(
    hosts_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    读取当前 hosts 文件中的受管映射。
    返回: {"cf_ip": str|None, "cloudfront": {domain: ip}, "backup_exists": bool}
    """
    if hosts_path is None:
        hosts_path = _get_hosts_path()

    result = {
        "cf_ip": None,
        "cloudfront": {},
        "backup_exists": os.path.isfile(hosts_path + ".llcbabel.bak"),
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


# ---- 6. 管理员提权写入 ----

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
) -> bool:
    """
    在必要时提权写入 hosts。
    对应 LLC_BABEL HostsWriteElevator。
    """
    if hosts_path is None:
        hosts_path = _get_hosts_path()

    os.makedirs(os.path.dirname(hosts_path), exist_ok=True)

    # 检查是否已经以管理员身份运行
    if _is_admin():
        # 已经是管理员，直接写入
        return write_hosts(cf_ip, cloudfront_mappings, log_cb, hosts_path)

    # 检查是否可以写入（普通用户权限下尝试创建一个临时文件）
    can_write = False
    try:
        test_path = hosts_path + f".{uuid.uuid4().hex[:8]}.test"
        with open(test_path, "w") as f:
            f.write("test")
        os.remove(test_path)
        can_write = True
    except (PermissionError, OSError):
        pass

    if can_write:
        # 不需要提权即可写入
        return write_hosts(cf_ip, cloudfront_mappings, log_cb, hosts_path)

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
            if log_cb:
                log_cb(result_data.get("message", ""))
            return success
        else:
            if log_cb:
                log_cb("未收到提权写入结果（等待超时）")
            return False

    except OSError as e:
        if log_cb:
            log_cb(f"提权失败：{e}")
        return False
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
                    success = write_hosts(
                        cf_ip=req.get("cf_ip"),
                        cloudfront_mappings=req.get("cloudfront_mappings"),
                        hosts_path=req.get("hosts_path"),
                    )

                    result = {
                        "success": success,
                        "message": "hosts 写入成功" if success else "hosts 写入失败",
                    }

                    result_path = request_path + ".result"
                    with open(result_path, "w", encoding="utf-8") as f:
                        json.dump(result, f)
            except Exception as e:
                result_path = request_path + ".result"
                with open(result_path, "w", encoding="utf-8") as f:
                    json.dump({"success": False, "message": str(e)}, f)

        sys.exit(0)


# ---- 7. 完整优选流程 ----

def cdn_optimize_cloudflare(
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], None]] = None
) -> Optional[Dict[str, Any]]:
    """
    Cloudflare CDN 优选。
    供 webui/app.py LCTA_API 方法调用。
    """
    cfst_dir = _get_cfst_dir()

    # 确保 CFST 文件存在（开发调试时 InitCode 未运行，需懒加载）
    if not _ensure_cfst_available(log_cb=log_cb):
        return None

    result = run_cfst(cfst_dir, log_cb=log_cb, progress_cb=progress_cb, cancel_check=cancel_check)
    return result


def cdn_optimize_cloudfront(
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], None]] = None
) -> Dict[str, Any]:
    """
    CloudFront API 优选。
    供 webui/app.py LCTA_API 方法调用。
    """
    t_start = time.perf_counter()
    overall_deadline = t_start + CLOUDFRONT_OVERALL_TIMEOUT
    results = {}
    domains = list(CLOUDFRONT_ENDPOINTS.items())
    n_domains = len(domains)
    timed_out = False

    if log_cb:
        if _DEBUG:

            log_cb(f"[DEBUG] cdn_optimize_cloudfront 入口 | domains={domains} | overall_deadline={CLOUDFRONT_OVERALL_TIMEOUT}s")

    # LLC_BABEL 风格的 per-domain 完成度追踪
    # 每个域名: DNS 完成=0.10, 资格赛=0.10-0.70, 决赛=0.70-1.0, 完成=1.0
    domain_fractions = {domain: 0.0 for domain, _ in domains}
    last_global_pct = 0.0  # 单调性保护

    def report_global_progress(message):
        nonlocal last_global_pct
        if not progress_cb:
            if log_cb:
                if _DEBUG:

                    log_cb(f"[DEBUG] report_global_progress 跳过(无progress_cb): {message}")
            return
        avg_fraction = sum(domain_fractions.values()) / n_domains
        global_pct = avg_fraction * 100
        # 单调性保护：仅拒绝真的倒退，允许相同百分比不同消息通过
        if global_pct < last_global_pct:
            if log_cb:
                if _DEBUG:

                    log_cb(f"[DEBUG] report_global_progress 拒绝(倒退): {global_pct:.1f}% < {last_global_pct:.1f}% | {message}")
            return
        if log_cb:
            if _DEBUG:

                log_cb(f"[DEBUG] report_global_progress 发送: {global_pct:.1f}% | fractions={dict(domain_fractions)} | {message}")
        last_global_pct = global_pct
        progress_cb(global_pct, message)

    for idx, (domain, probe_url) in enumerate(domains):
        t_domain_start = time.perf_counter()
        if log_cb:
            if _DEBUG:

                log_cb(f"[DEBUG] 域名 {idx+1}/{n_domains}: {domain} | overall_deadline剩余={overall_deadline - t_domain_start:.1f}s")
        # 检查总超时
        if time.perf_counter() >= overall_deadline:
            if log_cb:
                log_cb(f"CloudFront 总超时（{CLOUDFRONT_OVERALL_TIMEOUT}s），跳过剩余域名")
            timed_out = True
            break

        if cancel_check:
            cancel_check()

        if log_cb:
            log_cb(f"开始优选 CloudFront 域名：{domain}")

        # DNS 候选发现（进度: 0% → 10%）
        # 先设置初始进度，避免 DNS 解析期间进度条冻结
        domain_fractions[domain] = 0.02
        report_global_progress(f"[{domain}] 开始 DNS 解析...")

        # 构建 DNS 阶段的 progress_cb（进度映射：domain 内部 DNS 占 0%-10%）
        def make_dns_progress_cb(d):
            def cb(pct, msg):
                # DNS 内部进度 0-100 映射到此域名的 0.02-0.10
                domain_fractions[d] = 0.02 + 0.08 * (pct / 100.0)
                report_global_progress(msg)
            return cb

        t_dns_start = time.perf_counter()
        candidates = resolve_cloudfront_dns(
            domain,
            log_cb=log_cb,
            progress_cb=make_dns_progress_cb(domain),
            cancel_check=cancel_check
        )
        t_dns_elapsed = time.perf_counter() - t_dns_start
        if log_cb:
            if _DEBUG:

                log_cb(f"[DEBUG] DNS 完成: {domain} | candidates={len(candidates)} | 耗时={t_dns_elapsed:.1f}s | ips={candidates[:5]}...")
        domain_fractions[domain] = 0.10
        report_global_progress(f"[{domain}] DNS 候选发现完成（{len(candidates)} 个）")

        # 选择阶段（进度: 10% → 100% per domain）
        # select_cloudfront_ip 内部进度: 0-40=资格赛, 40-95=决赛, 95=完成
        def make_domain_progress_cb(d):
            def cb(pct, msg):
                if pct <= 40:
                    ratio = pct / 40.0
                    domain_fractions[d] = 0.10 + 0.60 * ratio
                elif pct < 95:
                    ratio = (pct - 40) / 55.0
                    domain_fractions[d] = 0.70 + 0.30 * ratio
                else:
                    domain_fractions[d] = 1.0
                report_global_progress(f"[{d}] {msg}")
            return cb

        if log_cb:
            if _DEBUG:

                log_cb(f"[DEBUG] 进入 select_cloudfront_ip: {domain} | candidates={len(candidates)}")
        t_sel_start = time.perf_counter()
        best = select_cloudfront_ip(
            domain, probe_url, candidates,
            log_cb=log_cb,
            progress_cb=make_domain_progress_cb(domain),
            cancel_check=cancel_check,
            overall_deadline=overall_deadline
        )
        t_sel_elapsed = time.perf_counter() - t_sel_start
        if log_cb:
            if _DEBUG:

                log_cb(f"[DEBUG] select_cloudfront_ip 返回: {domain} | best={best is not None} | 耗时={t_sel_elapsed:.1f}s")

        # 标记端点完成
        domain_fractions[domain] = 1.0
        if best:
            results[domain] = best
            report_global_progress(f"[{domain}] 优选完成")
        elif log_cb:
            log_cb(f"[{domain}] 未找到可用 IP")
            report_global_progress(f"[{domain}] 无可用 IP，使用 DNS 回退")

    t_total = time.perf_counter() - t_start
    if log_cb:
        status = "超时" if timed_out else "完成"
        log_cb(f"CloudFront 优选{status}，共 {n_domains} 个域名，{len(results)} 个成功（耗时 {t_total:.1f}s）")

    return results


def cdn_full_optimization(
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], None]] = None
) -> Dict[str, Any]:
    """
    全流程 CDN 优选（Cloudflare + CloudFront）。
    供 webui/app.py LCTA_API 方法调用。
    """
    result = {
        "cloudflare": None,
        "cloudfront": {},
        "success": False,
    }

    # 进度权重对齐 LLC_BABEL：CF 2-45%，CFront 50-95%
    if progress_cb:
        progress_cb(0, "准备测速")
        progress_cb(2, "Cloudflare 准备中")

    # Phase 1: Cloudflare（2% → 45%，宽度 43%）
    if log_cb:
        log_cb("=" * 40)
        log_cb("Phase 1/2: Cloudflare 下载 CDN 优选")
        log_cb("=" * 40)

    cf_result = cdn_optimize_cloudflare(
        log_cb=log_cb,
        progress_cb=lambda p, m: progress_cb(2 + p * 0.43, m) if progress_cb else None,
        cancel_check=cancel_check
    )
    result["cloudflare"] = cf_result

    if progress_cb:
        progress_cb(45, "Cloudflare 完成")

    if cancel_check:
        cancel_check()

    # Phase 2: CloudFront（50% → 95%，宽度 45%）
    if progress_cb:
        progress_cb(50, "CloudFront 准备中")

    if log_cb:
        log_cb("=" * 40)
        log_cb("Phase 2/2: CloudFront API 优选")
        log_cb("=" * 40)

    cfa_result = cdn_optimize_cloudfront(
        log_cb=log_cb,
        progress_cb=lambda p, m: progress_cb(50 + p * 0.45, m) if progress_cb else None,
        cancel_check=cancel_check
    )
    result["cloudfront"] = cfa_result

    if progress_cb:
        progress_cb(100, "测速完成")

    result["success"] = bool(cf_result or cfa_result)

    return result


def cdn_full_optimization_simple(
    cfst_dir: Optional[str] = None,
    test_url: str = CFST_TEST_URL,
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], None]] = None
) -> Dict[str, Any]:
    """
    无头模式全流程优选（供启动器调用，不依赖 modal_id）。
    """
    if cfst_dir is None:
        cfst_dir = _get_cfst_dir()

    result = {
        "cf_ip": None,
        "cloudfront_mappings": {},
        "success": False,
    }

    # Cloudflare
    if log_cb:
        log_cb("开始 Cloudflare CDN 优选...")

    cf_result = run_cfst(
        cfst_dir, test_url=test_url,
        log_cb=log_cb, progress_cb=progress_cb, cancel_check=cancel_check
    )
    if cf_result:
        result["cf_ip"] = cf_result["ip"]

    if cancel_check:
        cancel_check()

    # CloudFront
    if log_cb:
        log_cb("开始 CloudFront API 优选...")

    cfa_result = cdn_optimize_cloudfront(
        log_cb=log_cb, progress_cb=progress_cb, cancel_check=cancel_check
    )
    for domain, info in cfa_result.items():
        result["cloudfront_mappings"][domain] = info["ip"]

    result["success"] = bool(result["cf_ip"] or result["cloudfront_mappings"])

    return result


# ---- 启动时检查是否为提权辅助调用 ----
if __name__ == "__main__" and len(sys.argv) >= 2 and sys.argv[1] == "--cdn-write-hosts":
    _handle_helper_invocation()
