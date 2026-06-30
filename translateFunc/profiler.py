"""性能剖析基础设施 —— TimingProfiler 单例。"""
from __future__ import annotations
from contextlib import contextmanager
import threading
import time
from typing import Dict


class TimingProfiler:
    """单例性能剖析器。context manager 用法：

        profiler = TimingProfiler.get()
        with profiler.phase("获取专有名词"):
            ...
        print(profiler.report())

    线程安全：_lock 保护 _records 的并发访问（per-file 计时在 worker 线程中运行）。
    嵌套支持：内层 phase 的耗时会从外层 phase 中扣除，确保 report() 的总时长为真实用时。
    """
    _instance: "TimingProfiler | None" = None

    def __init__(self):
        self._records: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._thread_local = threading.local()

    @classmethod
    def get(cls) -> "TimingProfiler":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reset(self) -> None:
        """清除所有记录。"""
        self._records.clear()

    def _get_stack(self):
        """获取当前线程的 phase 栈，首次访问时初始化。"""
        if not hasattr(self._thread_local, 'stack'):
            self._thread_local.stack = []
        return self._thread_local.stack

    @contextmanager
    def phase(self, name: str):
        """记录一个命名阶段的耗时。支持嵌套——内层耗时从外层扣除，避免重复计算。

        用法:
            with profiler.phase("阶段名称"):
                do_work()
        """
        stack = self._get_stack()
        start = time.perf_counter()
        # 栈元素: [name, start, accumulated_child_time]
        stack.append([name, start, 0.0])
        try:
            yield
        finally:
            name, phase_start, child_time = stack.pop()
            elapsed = time.perf_counter() - phase_start
            exclusive = elapsed - child_time  # 当前 phase 自身耗时（不含子 phase）
            with self._lock:
                self._records[name] = self._records.get(name, 0.0) + exclusive
            # 将当前 phase 的完整耗时累加到父 phase 的 child_time
            if stack:
                stack[-1][2] += elapsed

    def report(self) -> str:
        """生成格式化的耗时报告。

        仅显示独占时间 > 0 的阶段：嵌套中被完全分解到子阶段的包装阶段
        （独占时间为 0）不显示，避免无意义的 0.00s 行。
        """
        if not self._records:
            return "[性能报告] 无数据"

        # 过滤掉独占时间为 0 的包装阶段（完全由子阶段组成，无自身耗时）
        active = {k: v for k, v in self._records.items() if v > 0}
        if not active:
            return "[性能报告] 无有效数据"

        total = sum(active.values())
        lines = [
            "========== 性能报告 ==========",
            f"{'阶段':<24} {'耗时':>10}  {'占比':>8}",
            "-" * 44,
        ]
        for name, elapsed in active.items():
            pct = (elapsed / total * 100) if total > 0 else 0.0
            lines.append(f"{name:<24} {elapsed:>8.2f}s  {pct:>6.1f}%")
        lines.append("-" * 44)
        lines.append(f"{'总计':<24} {total:>8.2f}s")
        lines.append("=" * 33)
        return "\n".join(lines)
