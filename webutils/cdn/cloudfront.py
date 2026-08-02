"""CloudFront DNS 候选发现与 HTTPS 端点探测。"""
from __future__ import annotations

import concurrent.futures
import json
import re
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Dict, List, Optional

from .classify import classify_probe_exception
from .constants import (
    DOH_SOURCES,
    MAX_CANDIDATES,
    PROBE_FAILURE_BUSINESS_CONTENT,
    PROBE_FAILURE_HTTP_STATUS,
    PROBE_FAILURE_NONE,
    PROBE_TIMEOUT,
    SOURCE_TIMEOUT,
    _DEBUG,
)
from .hosts import _is_public_ipv4


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
