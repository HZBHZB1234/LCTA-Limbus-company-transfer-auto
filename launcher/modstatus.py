"""模组处理任务状态注册表（多线程加载进度）。

移植自 FaustLauncher 多线程加载器的 loader_threads.txt 协议
（`{线程名: {stage, description, status}}`）：本工具的模组处理在
Launcher 进程内完成，无需落盘文件，GUI（launcher/gui_progress.py）
直接 300ms 轮询 snapshot() 差异渲染「活跃任务」列表。

- key：任务唯一键（调用方保证，通常为文件完整路径）
- name：展示名（文件名/目录名）
- stage：阶段标签（如 carra2 转换 / 解压展平 / 备份 / 重打包）
- description：当前动作简述
- status：waiting（已提交未开始）/ running

任务结束时调用 finish(key) 从注册表移除（GUI 检测 key 消失即删行），
与 FaustLoader「线程完成后自动从列表移除」行为一致。线程安全。
"""
from threading import Lock

STATUS_WAITING = "waiting"
STATUS_RUNNING = "running"


class TaskRegistry:

    def __init__(self) -> None:
        self._lock = Lock()
        self._tasks = {}

    def begin(self, key, name, stage="", description="",
              status=STATUS_RUNNING) -> None:
        with self._lock:
            self._tasks[key] = {
                "key": key,
                "name": name,
                "stage": stage,
                "description": description,
                "status": status,
            }

    def update(self, key, stage=None, description=None, status=None) -> None:
        with self._lock:
            task = self._tasks.get(key)
            if task is None:
                return
            if stage is not None:
                task["stage"] = stage
            if description is not None:
                task["description"] = description
            if status is not None:
                task["status"] = status

    def finish(self, key) -> None:
        with self._lock:
            self._tasks.pop(key, None)

    def snapshot(self):
        with self._lock:
            return [dict(task) for task in self._tasks.values()]

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()


_registry = TaskRegistry()


def begin(key, name, stage="", description="", status=STATUS_RUNNING) -> None:
    _registry.begin(key, name, stage, description, status)


def update(key, stage=None, description=None, status=None) -> None:
    _registry.update(key, stage, description, status)


def finish(key) -> None:
    _registry.finish(key)


def snapshot():
    return _registry.snapshot()


def clear() -> None:
    _registry.clear()
