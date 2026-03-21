import os
from pathlib import Path
import tempfile
import UnityPy
from copy import deepcopy
import logging
from UnityPy.enums import ClassIDType
from typing import List

def extract_files_from_resource(resource_path: str, file_names: List[str], output_dir: str) -> List[str]:
    """
    从 Unity 资源文件中提取指定名称列表的文件，并保存到目标目录。

    Args:
        resource_path: Unity 资源文件路径（.assets、.bundle 等）
        file_names:    要提取的资源内部名称列表（完全匹配后缀）
        output_dir:    保存目录

    Returns:
        List[str]: 成功提取的文件名称列表（与传入列表中实际找到的对应）

    Raises:
        FileNotFoundError: 当 resource_path 不存在时抛出
    """
    if not os.path.exists(resource_path):
        raise FileNotFoundError(f"资源文件不存在: {resource_path}")

    env = UnityPy.load(resource_path)
    objects = list(env.objects)  # 缓存对象列表，避免多次加载

    found = []

    for file_name in file_names:
        extracted = False
        for obj in objects:
            try:
                if not obj.container.endswith(file_name):
                    continue
            except:
                continue

            data = obj.read()
            raw_data = None

            # 根据不同类型提取二进制数据
            if obj.type == ClassIDType.TextAsset:
                raw_data = data.script          # bytes
            elif obj.type == ClassIDType.Texture2D:
                # 将图片转为 PNG 字节流，文件名仍使用原名（不加 .png）
                img = data.image
                import io
                with io.BytesIO() as output:
                    img.save(output, format='PNG')
                    raw_data = output.getvalue()
            elif obj.type == ClassIDType.MonoBehaviour:
                # 对于 MonoBehaviour 可导出为 JSON 字符串
                raw_data = data.to_json().encode('utf-8')
            else:
                # 其他类型尝试获取原始数据（如果有 bytes 属性）
                if hasattr(data, 'bytes'):
                    raw_data = data.bytes
                else:
                    print(f"警告: 对象 '{file_name}' 类型 {obj.type.name} 不支持直接提取")
                    continue

            if raw_data is None:
                continue

            # 保存文件（文件名不加任何扩展名）
            os.makedirs(output_dir, exist_ok=True)
            out_path = os.path.join(output_dir, file_name)
            try:
                with open(out_path, 'wb') as f:
                    f.write(raw_data)
                extracted = True
                found.append(file_name)
                break  # 找到第一个匹配即停止处理该文件
            except Exception as e:
                print(f"错误: 保存文件 {file_name} 失败: {e}")
                continue

    return found

def function_resources(target: list, logger: logging.Logger= logging.getLogger('resourcer')):
    _tmp = tempfile.mkdtemp()
    resourcePath = Path.home() / 'AppData' / 'LocalLow' / 'Unity' / 'ProjectMoon_LimbusCompany'
    files = resourcePath.rglob('__data')
    files = sorted(files, key=lambda a: a.stat().st_atime, reverse=True)
    logger.debug(f'找到{len(files)}个文件')
    customTarget = deepcopy(target)
    for file in files:
        result = extract_files_from_resource(str(file), customTarget, _tmp)
        if result:
            logger.debug(f'在文件{file}中找到文件{result}')
        customTarget = [i for i in customTarget if i not in result]
        if not customTarget:
            break
    if customTarget:
        logger.warning(f'未完全找到文件，还差{customTarget}')
    return _tmp, customTarget