import os
from pathlib import Path
import UnityPy
import UnityPy.config
UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"
import logging
from UnityPy.enums import ClassIDType
from typing import Dict, Iterable, List, Optional, Tuple
from globalManagers.LogManager import LogManager
_log_manager = LogManager()

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
    found = []
    remaining = set(file_names)
    for obj in env.objects:
        if not remaining:
            break
        try:
            container = obj.container
        except (AttributeError, TypeError):
            continue
        if not isinstance(container, str):
            continue
        file_name = next((name for name in remaining if container.endswith(name)), None)
        if file_name is None:
            continue
        try:
            data = obj.read()
            raw_data = None
            if obj.type == ClassIDType.TextAsset:
                raw_data = data.script
            elif obj.type == ClassIDType.Texture2D:
                import io

                with io.BytesIO() as output:
                    data.image.save(output, format='PNG')
                    raw_data = output.getvalue()
            elif obj.type == ClassIDType.MonoBehaviour:
                raw_data = data.to_json().encode('utf-8')
            elif hasattr(data, 'bytes'):
                raw_data = data.bytes
            if raw_data is None:
                continue
            os.makedirs(output_dir, exist_ok=True)
            with open(os.path.join(output_dir, file_name), 'wb') as output_file:
                output_file.write(raw_data)
            found.append(file_name)
            remaining.remove(file_name)
        except Exception as exc:
            _log_manager.log_error(exc)

    return found


def get_limbus_resource_files() -> List[Path]:
    resource_path = Path.home() / 'AppData' / 'LocalLow' / 'Unity' / 'ProjectMoon_LimbusCompany'
    if not resource_path.exists():
        return []
    candidates = []
    for folder in resource_path.iterdir():
        if not folder.is_dir():
            continue
        for data_file in folder.glob('*/__data'):
            if not data_file.is_file():
                continue
            try:
                candidates.append((data_file.stat().st_ctime_ns, data_file))
            except OSError:
                continue
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in candidates]


def load_text_assets(
    file_names: Iterable[str],
    logger: logging.Logger = logging.getLogger('resourcer'),
    resource_files: Optional[Iterable[Path]] = None,
) -> Tuple[Dict[str, bytes], List[str]]:
    remaining = set(file_names)
    loaded: Dict[str, bytes] = {}
    candidates = list(resource_files) if resource_files is not None else get_limbus_resource_files()
    logger.debug('找到%s个资源文件', len(candidates))

    for resource_file in candidates:
        if not remaining:
            break
        try:
            env = UnityPy.load(str(resource_file))
        except Exception as exc:
            logger.debug('跳过无法加载的资源文件 %s: %s', resource_file, exc)
            continue
        found_here = []
        for obj in env.objects:
            if not remaining:
                break
            try:
                container = obj.container
            except (AttributeError, TypeError):
                continue
            if not isinstance(container, str):
                continue
            target_name = next((name for name in remaining if container.endswith(name)), None)
            if target_name is None or obj.type != ClassIDType.TextAsset:
                continue
            try:
                loaded[target_name] = bytes(obj.read().script)
            except Exception as exc:
                logger.warning('读取资源 %s 失败: %s', target_name, exc)
                continue
            remaining.remove(target_name)
            found_here.append(target_name)
        if found_here:
            logger.debug('在文件%s中找到文件%s', resource_file, found_here)

    if remaining:
        logger.warning('未完全找到文件，还差%s', sorted(remaining))
    return loaded, sorted(remaining)
