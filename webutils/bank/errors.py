class BankToolError(RuntimeError):
    """bank 工具链通用错误。"""


class BankDllMissingError(BankToolError):
    """FMOD/FSBANK DLL 缺失。"""
