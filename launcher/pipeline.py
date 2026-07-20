import threading
from typing import Any, Callable, Dict, List, Optional

PHASE_INIT         = "init"
PHASE_CHECK_UPDATE = "check_update"
PHASE_CDN          = "cdn_optimize"
PHASE_PREPARE_MOD  = "prepare_mod"
PHASE_LAUNCH       = "launch_game"
PHASE_RUNNING      = "game_running"
PHASE_EXIT         = "game_exit"

_PHASE_ORDER = [
    PHASE_INIT,
    PHASE_CHECK_UPDATE,
    PHASE_CDN,
    PHASE_PREPARE_MOD,
    PHASE_LAUNCH,
    PHASE_RUNNING,
    PHASE_EXIT,
]

Callback = Callable[..., None]


class LaunchPipeline:
    """阶段化启动管线。

    各模块（GUI、mod 处理、快捷键等）通过 `on(phase, callback)` 注册回调，
    由 main() 依次 emit 各阶段。PHASE_EXIT 即为"游戏退出管线"，
    mod 清理、GUI 关闭、快捷键注销等均注册至此。

    通过 `cancel_event` 支持 GUI 关闭事件中断主循环。
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callback]] = {p: [] for p in _PHASE_ORDER}
        self.cancel_event = threading.Event()
        self.context: Dict[str, Any] = {}

    def on(self, phase: str, callback: Callback) -> None:
        """注册阶段回调。"""
        handlers = self._handlers.get(phase)
        if handlers is None:
            handlers = []
            self._handlers[phase] = handlers
        handlers.append(callback)

    def emit(self, phase: str, **kwargs: Any) -> bool:
        """触发指定阶段的所有回调。

        返回 True 表示正常执行完毕，False 表示被 cancel_event 中断。
        """
        if self.cancel_event.is_set():
            return False
        for cb in self._handlers.get(phase, []):
            try:
                cb(**kwargs)
            except Exception:
                pass
        return True

    def cancel(self) -> None:
        self.cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()
