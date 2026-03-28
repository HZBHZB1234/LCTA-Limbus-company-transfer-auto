import jsonpatch

def apply_changes_to_data(original_data, changes):
    """递归应用修改到数据 - 适配新的修改记录结构（包含id）"""

    print(f"应用用户自定义json修改: {type(original_data)}")

    # 处理包含dataList的修改记录结构
    if isinstance(changes, dict) and 'dataList' in changes:
        changes = changes['dataList']

    # 处理original_data是包含dataList键的字典，而changes是列表的情况
    if isinstance(original_data, dict) and 'dataList' in original_data and isinstance(changes, list):
        result = original_data.copy()
        result['dataList'] = apply_changes_to_data(original_data['dataList'], changes)
        return result

    if isinstance(original_data, dict) and isinstance(changes, dict):
        result = {}
        for key, value in original_data.items():
            if key in changes:
                # 如果changes中有对应的键，应用修改
                if isinstance(value, (dict, list)) and isinstance(changes[key], (dict, list)):
                    result[key] = apply_changes_to_data(value, changes[key])
                else:
                    result[key] = changes[key]
            else:
                result[key] = value
        return result
    
    elif isinstance(original_data, list) and isinstance(changes, list):
        result = []
        
        # 检查是否是包含id的字典列表的特殊修改记录
        if (len(original_data) > 0 and isinstance(original_data[0], dict) and 
            'id' in original_data[0] and len(changes) > 0 and 
            isinstance(changes[0], dict) and 'id' in changes[0]):
            
            # 对于包含id的字典列表，根据id进行匹配修改
            original_dict = {item['id']: item for item in original_data if 'id' in item}
            modified_ids = set()
            
            # 首先处理所有修改项
            for change_item in changes:
                if isinstance(change_item, dict) and 'id' in change_item:
                    change_id = change_item['id']
                    modified_ids.add(change_id)
                    
                    if change_id in original_dict:
                        # 找到对应的原始项
                        original_item = original_dict[change_id]
                        
                        # 普通修改，应用修改后添加
                        if 'changes' in change_item:
                            modified_item = apply_changes_to_data(original_item, change_item['changes'])
                            result.append(modified_item)
                        else:
                            # 如果没有changes字段，使用原始项
                            result.append(original_item)
                    else:
                        # 新增项（id不在原始数据中）
                        result.append(change_item.get('changes', change_item))
            
            # 处理未被修改的原始项
            for item in original_data:
                if isinstance(item, dict) and 'id' in item:
                    # 对于包含id的项，检查是否已被修改
                    if item['id'] not in modified_ids:
                        result.append(item)
                else:
                    # 对于不包含id的项，直接添加
                    result.append(item)
            
            return result
        else:
            # 对于普通的列表，使用原来的逻辑
            for i, item in enumerate(original_data):
                if i < len(changes):
                    if isinstance(item, (dict, list)) and isinstance(changes[i], (dict, list)):
                        result.append(apply_changes_to_data(item, changes[i]))
                    else:
                        result.append(changes[i])
                else:
                    result.append(item)
            return result
    else:
        return original_data

def get_LCTA_changes(original_data, changed_data):
    return 