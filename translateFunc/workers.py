"""
translateFunc/workers.py
WorkerPool —— 基于 ThreadPoolExecutor 的并发文件处理。
每个工作线程通过工厂函数获取独立的翻译器实例。
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from translateFunc.config import ProcessOutcome


class WorkerPool:
    """管理并发文件翻译，每线程独立翻译器实例。

    关键设计：translator_factory() 在每个线程内调用一次，
    创建独立的翻译器实例，避免 HTTP 连接竞争。
    """

    def __init__(
        self,
        translator_factory: Callable[[], Any],
        max_workers: int = 4,
    ):
        self._factory = translator_factory
        self._max_workers = max_workers

    def map(
        self,
        files: list,
        process_fn: Callable[[Any, Any], ProcessOutcome],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[ProcessOutcome]:
        """并发处理文件，保持输入顺序。

        Args:
            files: 待处理的文件配置/路径列表。
            process_fn: (file_item, translator) -> ProcessOutcome。
            on_progress: 可选回调 done, total, current_file_name。

        Returns:
            与输入文件顺序一致的 ProcessOutcome 列表。
        """
        total = len(files)
        if total == 0:
            return []

        # 将文件映射到原始索引以保持输出顺序
        indexed: list[tuple[int, Any]] = list(enumerate(files))
        results: list[ProcessOutcome | None] = [None] * total

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            import threading
            thread_local = threading.local()

            def worker(file_item):
                """在 Worker 线程内创建独立的 translator 实例。"""
                if not hasattr(thread_local, "translator"):
                    thread_local.translator = self._factory()
                return process_fn(file_item, thread_local.translator)

            # 提交所有任务
            future_to_idx = {}
            for idx, file_item in indexed:
                future = executor.submit(worker, file_item)
                future_to_idx[future] = idx

            completed = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                completed += 1
                try:
                    outcome = future.result()
                    results[idx] = outcome
                except Exception as e:
                    # 将未预期异常转换为错误结果
                    file_name = str(files[idx]) if idx < len(files) else f"index_{idx}"
                    from translateFunc.enums import ProcessResult
                    results[idx] = ProcessOutcome(
                        ProcessResult.SAVE_ERROR,
                        file_name,
                        {"reason": f"未处理的异常: {e}"},
                    )

                if on_progress:
                    fname = results[idx].file_name if results[idx] else str(files[idx])
                    on_progress(completed, total, fname)

        return [r for r in results if r is not None]
