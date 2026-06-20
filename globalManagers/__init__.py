"""
globalManagers/
Singleton managers for the LCTA application.
"""
from .LogManager import LogManager
from .ConfigManager import ConfigManager

__all__ = ["LogManager", "ConfigManager"]
