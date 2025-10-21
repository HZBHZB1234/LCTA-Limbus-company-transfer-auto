def check_custom_script(module, default_service_list_):
    """检查自定义脚本模块可用性"""
    # 检查 SERVICE_DEFINITION 是否存在
    if not hasattr(module, 'SERVICE_DEFINITION'):
        return False, '配置参数不存在'
    
    service_definition_ = module.SERVICE_DEFINITION
    
    # 检查 SERVICE_DEFINITION 是否为列表
    if not isinstance(service_definition_, list):
        return False, 'SERVICE_DEFINITION 必须是列表类型'
    
    # 检查列表是否为空
    if len(service_definition_) == 0:
        return False, 'SERVICE_DEFINITION 列表不能为空'
    
    # 检查每个服务定义
    for i, service_def in enumerate(service_definition_):
        # 检查是否为字典类型
        if not isinstance(service_def, dict):
            return False, f'第 {i+1} 个服务定义必须是字典类型'
        
        # 检查必要字段
        required_fields = ['name', 'service', 'description', 'api_params', 
                          'accept', 'term', 'layer', 'method']
        for field in required_fields:
            if field not in service_def:
                return False, f'第 {i+1} 个服务定义缺少必要字段: {field}'
        
        # 检查服务名称
        name = service_def.get('name', '')
        if not name or name == 'error':
            return False, f'第 {i+1} 个服务定义名称未定义或为保留名称'
        
        # 检查服务名称是否重复
        if name in default_service_list_:
            return False, f'服务名称 "{name}" 与默认服务重复'
        
        # 检查服务标识符
        service_id = service_def.get('service', '')
        reserved_ids = ['baidu', 'tencent', 'caiyun', 'youdao', 'xiaoniu', 
                       'aliyun', 'huoshan', 'google', 'deepl', 'custom', 'error']
        if not service_id or service_id in reserved_ids:
            return False, f'第 {i+1} 个服务标识符未定义或为保留标识符'
        
        # 检查 api_params 是否为列表
        api_params = service_def.get('api_params', [])
        if not isinstance(api_params, list):
            return False, f'第 {i+1} 个服务的 api_params 必须是列表类型'
        
        # 检查每个 api_param
        for j, param in enumerate(api_params):
            if not isinstance(param, dict):
                return False, f'第 {i+1} 个服务的第 {j+1} 个 api_param 必须是字典类型'
            
            param_required = ['key', 'label', 'type']
            for field in param_required:
                if field not in param:
                    return False, f'第 {i+1} 个服务的第 {j+1} 个 api_param 缺少字段: {field}'
            
            # 检查参数类型是否合法
            param_type = param.get('type', '')
            if param_type not in ['entry', 'password', 'checkbox']:
                return False, f'第 {i+1} 个服务的第 {j+1} 个 api_param 类型不合法: {param_type}'
        
        # 检查 accept 类型
        accept_type = service_def.get('accept', '')
        if accept_type not in ['text', 'json']:
            return False, f'第 {i+1} 个服务的 accept 类型不合法: {accept_type}'
        
        # 检查 term 类型
        term = service_def.get('term')
        if not isinstance(term, bool):
            return False, f'第 {i+1} 个服务的 term 必须是布尔类型'
        
        # 检查 layer 配置
        layer = service_def.get('layer', {})
        if not isinstance(layer, dict):
            return False, f'第 {i+1} 个服务的 layer 必须是字典类型'
        
        # 检查必要的 layer 字段
        layer_required = ['split', 'need_transfer', 'using_inner_pool', 
                         'using_inner_test', 'need_init', 'max_text', 
                         'max_requests', 'retry_set']
        for field in layer_required:
            if field not in layer:
                return False, f'第 {i+1} 个服务的 layer 缺少字段: {field}'
        
        # 检查 split 配置
        split = layer.get('split', [])
        if not isinstance(split, list) or len(split) != 2:
            return False, f'第 {i+1} 个服务的 split 配置格式错误'
        if not isinstance(split[0], bool):
            return False, f'第 {i+1} 个服务的 split 第一个元素必须是布尔类型'
        
        # 检查 need_transfer, using_inner_pool, using_inner_test, need_init
        for field in ['need_transfer', 'using_inner_pool', 'using_inner_test', 'need_init']:
            if not isinstance(layer.get(field), bool):
                return False, f'第 {i+1} 个服务的 {field} 必须是布尔类型'
        
        # 检查 max_text
        max_text = layer.get('max_text', {})
        if not isinstance(max_text, dict):
            return False, f'第 {i+1} 个服务的 max_text 必须是字典类型'
        if 'able' not in max_text or 'split_file' not in max_text or 'type' not in max_text or 'value' not in max_text:
            return False, f'第 {i+1} 个服务的 max_text 配置不完整'
        if not isinstance(max_text.get('able'), bool) or not isinstance(max_text.get('split_file'), bool):
            return False, f'第 {i+1} 个服务的 max_text able 和 split_file 必须是布尔类型'
        if max_text.get('type') not in ['character', 'byte']:
            return False, f'第 {i+1} 个服务的 max_text type 不合法'
        if not isinstance(max_text.get('value'), int) or max_text.get('value') <= 0:
            return False, f'第 {i+1} 个服务的 max_text value 必须是正整数'
        
        # 检查 max_requests
        max_requests = layer.get('max_requests', {})
        if not isinstance(max_requests, dict):
            return False, f'第 {i+1} 个服务的 max_requests 必须是字典类型'
        if 'able' not in max_requests or 'value' not in max_requests:
            return False, f'第 {i+1} 个服务的 max_requests 配置不完整'
        if not isinstance(max_requests.get('able'), bool):
            return False, f'第 {i+1} 个服务的 max_requests able 必须是布尔类型'
        if not isinstance(max_requests.get('value'), int) or max_requests.get('value') <= 0:
            return False, f'第 {i+1} 个服务的 max_requests value 必须是正整数'
        
        # 检查 retry_set
        retry_set = layer.get('retry_set', {})
        if not isinstance(retry_set, dict):
            return False, f'第 {i+1} 个服务的 retry_set 必须是字典类型'
        if 'able' not in retry_set or 'value' not in retry_set or 'fall_lang' not in retry_set:
            return False, f'第 {i+1} 个服务的 retry_set 配置不完整'
        if not isinstance(retry_set.get('able'), bool):
            return False, f'第 {i+1} 个服务的 retry_set able 必须是布尔类型'
        if not isinstance(retry_set.get('value'), int) or retry_set.get('value') <= 0:
            return False, f'第 {i+1} 个服务的 retry_set value 必须是正整数'
        
        # 检查 method 是否为可调用函数
        method = service_def.get('method')
        if not callable(method):
            return False, f'第 {i+1} 个服务的 method 必须是可调用函数'
        
        # 检查可选的 test_function
        test_function = service_def.get('test_function')
        if not layer.get('using_inner_test') and not callable(test_function):
            return False, f'第 {i+1} 个服务的 test_function 在需要使用的情况下必须是可调用函数'
        
        # 检查可选的 init_function
        init_function = service_def.get('init_function')
        if layer.get('need_init') and not callable(init_function):
            return False, f'第 {i+1} 个服务的 init_function 在需要使用的情况下必须是可调用函数'
    
    return True, '检查通过'