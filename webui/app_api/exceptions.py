"""webui 层异常定义：CancelRunning 实现在 globalManagers/exceptions.py（供业务层复用），此处 re-export。"""
from globalManagers.exceptions import CancelRunning

__all__ = ["CancelRunning"]
