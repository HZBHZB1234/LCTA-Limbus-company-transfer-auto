"""性能剖析基础设施 —— TimingProfiler 单例。"""
from __future__ import annotations
from contextlib import contextmanager
import time
from typing import Dict


class TimingProfiler:
    """单例性能剖析器。context manager 用法：

        profiler = TimingProfiler.get()
        with profiler.phase("获取专有名词"):
            ...
        print(profiler.report())
    """
    _instance: "TimingProfiler | None" = None

    def __init__(self):
        self._records: Dict[str, float] = {}
        self._stack: list[tuple[str, float]] = []

    @classmethod
    def get(cls) -> "TimingProfiler":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reset(self) -> None:
        """清除所有记录。"""
        self._records.clear()
        self._stack.clear()

    @contextmanager
    def phase(self, name: str):
        """记录一个命名阶段的耗时。支持嵌套——内层阶段耗时计入外层。

        用法:
            with profiler.phase("阶段名称"):
                do_work()
        """
        start = time.perf_counter()
        self._stack.append((name, start))
        try:
            yield
        finally:
            end = time.perf_counter()
            elapsed = end - start
            self._stack.pop()
            # 累计耗时（支持同一阶段多次调用）
            prev = self._records.get(name, 0.0)
            self._records[name] = prev + elapsed

    def report(self) -> str:
        """生成格式化的耗时报告。"""
        if not self._records:
            return "[性能报告] 无数据"

        total = sum(self._records.values())
        lines = [
            "========== 性能报告 ==========",
            f"{'阶段':<24} {'耗时':>10}  {'占比':>8}",
            "-" * 44,
        ]
        for name, elapsed in self._records.items():
            pct = (elapsed / total * 100) if total > 0 else 0.0
            lines.append(f"{name:<24} {elapsed:>8.2f}s  {pct:>6.1f}%")
        lines.append("-" * 44)
        lines.append(f"{'总计':<24} {total:>8.2f}s")
        lines.append("=" * 33)
        return "\n".join(lines)
