"""完整优选流程编排。"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from .cfst import _ensure_cfst_available, _get_cfst_dir, run_cfst
from .cloudfront import resolve_cloudfront_dns
from .constants import (
    CLOUDFRONT_ENDPOINTS,
    CLOUDFRONT_OVERALL_TIMEOUT,
    CFST_TEST_URL,
    _DEBUG,
)
from .selector import select_cloudfront_ip


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
