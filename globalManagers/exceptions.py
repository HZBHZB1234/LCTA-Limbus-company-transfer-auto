"""
globalManagers/exceptions.py
全局共享异常定义。

CancelRunning 定义在此（而非 webui 层），使 webutils / translateFunc / launcher
等业务层无需反向依赖表现层；webui/app_api/exceptions.py 保留 re-export 兼容。
"""


class CancelRunning(Exception):
    pass
