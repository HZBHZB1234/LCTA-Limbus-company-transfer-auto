"""TimingProfiler 单元测试。"""
import time
import pytest
from translateFunc.profiler import TimingProfiler


class TestTimingProfiler:
    """TimingProfiler 基础功能测试。"""

    def test_singleton(self):
        """多次获取返回同一实例。"""
        a = TimingProfiler.get()
        b = TimingProfiler.get()
        assert a is b

    def test_phase_records_elapsed(self):
        """phase context manager 正确记录耗时。"""
        profiler = TimingProfiler.get()
        profiler.reset()
        with profiler.phase("test_phase"):
            time.sleep(0.01)
        report = profiler.report()
        assert "test_phase" in report
        assert profiler._records["test_phase"] >= 0.01

    def test_multiple_phases(self):
        """多个阶段的耗时分别记录。"""
        profiler = TimingProfiler.get()
        profiler.reset()
        with profiler.phase("phase_a"):
            time.sleep(0.01)
        with profiler.phase("phase_b"):
            time.sleep(0.01)
        assert "phase_a" in profiler._records
        assert "phase_b" in profiler._records
        report = profiler.report()
        assert "phase_a" in report
        assert "phase_b" in report

    def test_nested_phases(self):
        """嵌套 phase：外层耗时不含内层，总时长为外层真实用时。"""
        profiler = TimingProfiler.get()
        profiler.reset()
        with profiler.phase("outer"):
            time.sleep(0.01)
            with profiler.phase("inner"):
                time.sleep(0.01)
        assert profiler._records["inner"] >= 0.01
        # 外层只包含自己的 sleep(0.01)，不包含 inner
        assert profiler._records["outer"] >= 0.01
        # 总和应为 ~0.02，而非旧行为的 ~0.03（验证无重复计算）
        total = sum(profiler._records.values())
        assert total < 0.03

    def test_report_format(self):
        """report() 输出包含表头和关键列。"""
        profiler = TimingProfiler.get()
        profiler.reset()
        with profiler.phase("test"):
            time.sleep(0.005)
        report = profiler.report()
        assert "性能报告" in report
        assert "test" in report
        assert "耗时" in report or "s" in report

    def test_reset_clears_all(self):
        """reset() 清除所有记录。"""
        profiler = TimingProfiler.get()
        profiler.reset()
        with profiler.phase("test"):
            time.sleep(0.01)
        profiler.reset()
        assert len(profiler._records) == 0
