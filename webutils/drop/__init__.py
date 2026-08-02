"""拖放文件处理包：按文件类型分支的处理器类（检测 + 执行 + 显示名）。

- handler: DropFileHandler 接口与处理器注册表
- context: 执行上下文 FileExecutionContext
- inspect: 容器只读快照（zip / folder / json）
- handlers: 每个 NAMEREFER 类别一个处理器类
- detect: evalZip / evalFolder / eval7zip / evalJson / evalFile 门面
- message: 确认弹窗 HTML 组装（makeMessage）
- eval_files: evalFiles 主流程
"""

from .detect import evalZip, evalFolder, eval7zip, evalJson, evalFile
from .message import makeMessage
from .eval_files import evalFiles

__all__ = [
    'evalZip',
    'evalFolder',
    'eval7zip',
    'evalJson',
    'evalFile',
    'makeMessage',
    'evalFiles',
]
