"""CloudFront 两阶段 IP 选择。"""
from __future__ import annotations

import concurrent.futures
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from .classify import classify_probe_exception
from .cloudfront import probe_cloudfront_endpoint
from .constants import (
    FINALIST_COUNT,
    FINAL_ATTEMPTS,
    MAX_CONCURRENCY,
    PROBE_TIMEOUT,
    REQUIRED_FINAL_SUCCESSES,
    _DEBUG,
)


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
