def flatten_dict_enhanced(d, parent_key=(), ignore_types=None, max_depth=None):
    """
    扁平化嵌套字典，使用元组作为键
    
    参数:
        d: 要扁平化的字典
        parent_key: 父键的元组，默认为空元组
        ignore_types: 要忽略的值的类型列表，例如 [None, ''] 或 [type(None), str]
        max_depth: 最大递归深度，None表示无限制
    """
    items = []
    
    def _flatten(obj, current_key, depth=0):
        if max_depth and depth > max_depth:
            items.append((current_key, obj))
            return
        
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_key = current_key + (str(k),)
                _flatten(v, new_key, depth + 1)
        elif isinstance(obj, (list, tuple)):
            for i, item in enumerate(obj):
                new_key = current_key + (i,)
                _flatten(item, new_key, depth + 1)
        else:
            # 检查是否需要忽略该值
            should_ignore = False
            if ignore_types:
                for ignore_type in ignore_types:
                    # 如果ignore_type是类型本身
                    if isinstance(ignore_type, type):
                        if isinstance(obj, ignore_type):
                            should_ignore = True
                            break
                    # 如果ignore_type是具体的值（如None, ''等）
                    else:
                        if obj == ignore_type:
                            should_ignore = True
                            break
            
            if not should_ignore:
                items.append((current_key, obj))
    
    _flatten(d, parent_key)
    return dict(items)

def update_dict_with_flattened(original_dict, flat_updates):
    """
    使用扁平化字典更新原始字典
    
    参数:
        original_dict: 要更新的原始字典
        flat_updates: 扁平化字典，键为元组形式的路径，值为要更新的值
    
    返回:
        更新后的原始字典（原地更新）
    """
    for path, value in flat_updates.items():
        # 确保路径是元组
        if not isinstance(path, tuple):
            path = (path,)
        
        # 遍历到路径的倒数第二个元素
        current = original_dict
        for i, key in enumerate(path[:-1]):
            # 如果是列表/元组索引
            if isinstance(key, int):
                # 确保当前位置是列表或元组
                if isinstance(current, (list, tuple)):
                    # 如果是元组，需要转换为列表才能修改
                    if isinstance(current, tuple):
                        # 这里假设我们不允许修改元组，跳过或抛异常
                        # 但为了通用性，我们可以转换为列表
                        raise TypeError(f"Cannot update tuple at path {path[:i+1]}")
                    # 确保索引有效
                    if key < len(current):
                        current = current[key]
                    else:
                        raise IndexError(f"Index {key} out of range at path {path[:i+1]}")
                else:
                    raise TypeError(f"Expected list/tuple at {path[:i+1]}, got {type(current)}")
            # 如果是字典键
            else:
                if isinstance(current, dict):
                    if key not in current:
                        # 如果键不存在，创建新字典
                        current[key] = {}
                    current = current[key]
                else:
                    raise TypeError(f"Expected dict at {path[:i+1]}, got {type(current)}")
        
        # 设置最终值
        last_key = path[-1]
        if isinstance(last_key, int):
            if isinstance(current, (list, tuple)):
                if isinstance(current, tuple):
                    raise TypeError(f"Cannot update tuple at path {path}")
                if last_key < len(current):
                    current[last_key] = value
                else:
                    # 如果索引超出范围，扩展列表
                    if last_key >= len(current):
                        current.extend([None] * (last_key - len(current) + 1))
                    current[last_key] = value
            else:
                raise TypeError(f"Expected list/tuple at {path[:-1]}, got {type(current)}")
        else:
            if isinstance(current, dict):
                current[last_key] = value
            else:
                raise TypeError(f"Expected dict at {path[:-1]}, got {type(current)}")
    
    return original_dict

def get_value_by_path(data, path):
    """
    根据元组路径从嵌套的字典/列表中获取值。

    参数:
        data: 嵌套的字典/列表结构（通常是 JSON 解析后的数据）
        path: 由字符串和整数组成的元组，表示访问路径。
              例如 ('a', 'b', 0) 表示 data['a']['b'][0]。

    返回:
        路径对应的值。

    异常:
        KeyError: 如果字典键不存在。
        IndexError: 如果列表索引越界。
        TypeError: 如果路径中的某部分与数据类型不匹配
                   （例如在列表上使用字符串键，或在字典上使用整数索引）。
    """
    if not path:  # 空路径返回原数据
        return data

    current = data
    for key in path:
        if isinstance(key, int):
            # 预期当前节点是列表或元组
            if isinstance(current, (list, tuple)):
                try:
                    current = current[key]
                except IndexError:
                    raise IndexError(f"Index {key} out of range for path {path}")
            else:
                raise TypeError(f"Expected list/tuple at path segment {key}, got {type(current)}")
        else:
            # 预期当前节点是字典
            if isinstance(current, dict):
                try:
                    current = current[key]
                except KeyError:
                    raise KeyError(f"Key '{key}' not found at path {path}")
            else:
                raise TypeError(f"Expected dict at path segment {key}, got {type(current)}")
    return current