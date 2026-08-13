"""universal - 版本无关的 metadata 解密管线（v2）。

输入：GameAssembly.dll + 加密 global-metadata.dat
输出：candidate profile + 31 节映射 + 标准 v39 重建文件 + 分阶段报告。

无参考标准文件依赖（唯一依赖：IL2CPP 版本表 versions.py）。

LCTA 副本：移植自 upstream metadata-recovery 仓库的 universal/（含未提交
工作树），`pipeline.py` 增加了 on_log / cancel_check 回调钩子供 WebUI 使用。
"""

__version__ = "2.0.0"
