// ============================
// API 配置管理器
// ============================

// API配置管理器
class APIConfigManager {
    constructor() {
        this.apiServices = null;
        this.selectedService = null;
        this.currentSettings = {};
        this.initialized = false;
    }
    
    // 初始化API服务
    async init() {
        if (this.initialized) return;
        
        try {
            // 从后端获取API服务数据
            const tkitMachine = await pywebview.api.get_attr('TKIT_MACHINE_OBJECT');
            const LLM_TRANSLATOR = await pywebview.api.get_attr('LLM_TRANSLATOR');
            if (tkitMachine && LLM_TRANSLATOR) {
                this.apiServices = tkitMachine;
                this.llmTranslator = LLM_TRANSLATOR;
                this.initialized = true;
                console.log('API服务数据加载成功');
            };
            await this.loadSettings();
            return true;
        } catch (error) {
            console.error('加载API服务数据失败:', error);
            return false;
        }
    }
    
    // 加载API服务到下拉框
    loadAPIServices() {
        if (!this.initialized || !this.apiServices) {
            console.error('API服务未初始化');
            return;
        }
        
        const apiSelectContainer = document.querySelector('.api-select');
        if (!apiSelectContainer) {
            return;
        }
        
        // 清空容器
        apiSelectContainer.innerHTML = '';
        
        // 创建下拉框
        const selectElement = document.createElement('select');
        selectElement.id = 'api-service-select';
        selectElement.className = 'api-service-select';
        
        // 添加所有API服务选项
        Object.keys(this.apiServices).forEach(serviceName => {
            const option = document.createElement('option');
            option.value = serviceName;
            option.textContent = serviceName;
            selectElement.appendChild(option);
        });
        
        // 添加到容器
        apiSelectContainer.appendChild(selectElement);
        
        // 添加选择事件监听
        selectElement.addEventListener('change', (e) => {
            this.onServiceSelected(e.target.value);
        });
    }
    
    // 当服务被选中时
    onServiceSelected(serviceKey) {
        if (!serviceKey || !this.apiServices[serviceKey]) {
            this.clearSettingsForm();
            this.clearStatusGrid();
            this.selectedService = null;
            return;
        }
        
        this.selectedService = serviceKey;
        configManager.updateConfigValue('api-select', serviceKey);
        const service = this.apiServices[serviceKey];
        
        // 更新服务状态
        this.updateServiceStatus(serviceKey, service);
        
        // 生成设置表单
        this.generateSettingsForm(serviceKey, service);

        if (serviceKey === 'LLM通用翻译服务') {
            this.addLLMServiceSelector();
        }
    }
    
    // 添加LLM服务选择器到表单
    addLLMServiceSelector() {
        if (!this.initialized || !this.llmTranslator) {
            console.error('LLM翻译器未初始化');
            return;
        }
        
        const apiSettingsContainer = document.querySelector('.api-settings-form');
        if (!apiSettingsContainer) {
            return;
        }

        // 找到第一个设置字段容器，在其前面插入LLM选择器
        const firstField = apiSettingsContainer.querySelector('.api-setting-field');
        
        // 创建LLM选择器容器
        const selectorContainer = document.createElement('div');
        selectorContainer.className = 'api-setting-field';
        
        // 创建标签
        const label = document.createElement('label');
        label.htmlFor = 'api-llm-service-selector';
        label.textContent = '选择LLM服务';
        selectorContainer.appendChild(label);
        
        // 创建选择框
        const selectWrapper = document.createElement('div');
        selectWrapper.className = 'select-wrapper';
        
        const select = document.createElement('select');
        select.id = 'api-llm-service-selector';
        select.name = 'llm_service_selector';
        
        // 添加默认选项
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = '选择以使用预设LLM服务地址...';
        select.appendChild(defaultOption);
        
        // 添加所有LLM服务选项
        Object.keys(this.llmTranslator).forEach(serviceName => {
            const option = document.createElement('option');
            option.value = serviceName;
            option.textContent = serviceName;
            select.appendChild(option);
        });
        
        // 添加图标
        const chevronIcon = document.createElement('i');
        chevronIcon.className = 'fas fa-chevron-down';
        
        selectWrapper.appendChild(select);
        selectWrapper.appendChild(chevronIcon);
        selectorContainer.appendChild(selectWrapper);
        
        // 添加帮助文本
        const helpText = document.createElement('small');
        helpText.className = 'form-hint';
        helpText.textContent = '选择预设的LLM服务，将自动填充基础地址和模型名称参数';
        selectorContainer.appendChild(helpText);
        
        // 插入到表单顶部
        if (firstField) {
            apiSettingsContainer.insertBefore(selectorContainer, firstField);
        }
        
        // 添加选择事件监听
        select.addEventListener('change', (e) => {
            this.onLLMSelected(e.target.value);
        });
    }

    onLLMSelected(serviceKey) {
        if (!serviceKey || !this.llmTranslator[serviceKey]) {
            return;
        }
        
        const service = this.llmTranslator[serviceKey];
        
        // 填充对应的表单字段
        const baseURLElement = document.getElementById('api-base_url');
        const modelElement = document.getElementById('api-model_name');
        
        if (baseURLElement) {
            baseURLElement.value = service.base_url || '';
        }
        if (modelElement) {
            modelElement.value = service.model || '';
        }
    }

    // 加载API服务到翻译下拉框
    loadAPIServicesTranslator() {
        if (!this.initialized || !this.apiServices) {
            console.error('API服务未初始化');
            return;
        }
        
        const apiSelectContainer = document.querySelector('.translator-services');
        if (!apiSelectContainer) {
            return;
        }
        
        // 清空容器
        apiSelectContainer.innerHTML = '';
        
        // 创建下拉框
        const selectElement = document.createElement('select');
        selectElement.id = 'translator-service-select';
        selectElement.className = 'translator-service-select';
        
        // 添加所有API服务选项
        Object.keys(this.apiServices).forEach(serviceName => {
            const option = document.createElement('option');
            option.value = serviceName;
            option.textContent = serviceName;
            selectElement.appendChild(option);
        });
        
        // 添加到容器
        apiSelectContainer.appendChild(selectElement);
    }
    
    // 生成API设置表单
    generateSettingsForm(serviceKey, service) {
        const apiSettingsContainer = document.querySelector('.api-settings');
        if (!apiSettingsContainer) {
            return;
        }
        
        // 清空容器
        apiSettingsContainer.innerHTML = '';
        
        // 获取API设置描述
        const apiSetting = service['api-setting'];
        if (!apiSetting || !Array.isArray(apiSetting)) {
            const noSettings = document.createElement('div');
            noSettings.className = 'no-settings';
            noSettings.innerHTML = '<p>此服务无需API配置</p>';
            apiSettingsContainer.appendChild(noSettings);
            return;
        }
        
        // 创建表单容器
        const form = document.createElement('div');
        form.className = 'api-settings-form';
        
        // 添加表单标题
        const title = document.createElement('h4');
        title.textContent = 'API参数配置';
        form.appendChild(title);
        
        // 为每个设置项创建表单字段
        apiSetting.forEach(setting => {
            const fieldGroup = this.createSettingField(setting);
            form.appendChild(fieldGroup);
        });
        
        apiSettingsContainer.appendChild(form);
        
        // 加载已保存的设置
        this.loadSavedSettings(serviceKey);
    }
    
    // 创建单个设置字段 - 简化版
    createSettingField(setting) {
        const fieldGroup = document.createElement('div');
        fieldGroup.className = 'api-setting-field';
        
        // 创建标签（boolean类型不需要单独的标签）
        if (setting.type !== 'boolean') {
            const label = document.createElement('label');
            label.htmlFor = `api-${setting.id}`;
            label.textContent = setting.name;
            if (setting.required) {
                const requiredSpan = document.createElement('span');
                requiredSpan.className = 'required';
                requiredSpan.textContent = ' *';
                label.appendChild(requiredSpan);
            }
            fieldGroup.appendChild(label);
        }
        
        // 根据类型创建输入控件
        let inputElement;
        
        switch(setting.type) {
            case 'boolean':
                // 创建复选框结构
                inputElement = document.createElement('label');
                inputElement.className = 'checkbox-container';
                inputElement.htmlFor = `api-${setting.id}`;
                
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.id = `api-${setting.id}`;
                checkbox.name = setting.id;
                
                const checkmark = document.createElement('span');
                checkmark.className = 'checkmark';
                
                const labelText = document.createElement('span');
                labelText.textContent = setting.name || '';
                
                inputElement.appendChild(checkbox);
                inputElement.appendChild(checkmark);
                inputElement.appendChild(labelText);
                break;
                
            default:
                // 默认文本输入框
                inputElement = document.createElement('input');
                inputElement.type = 'text';
                inputElement.id = `api-${setting.id}`;
                inputElement.name = setting.id;
                inputElement.placeholder = setting.description || '';
                break;
        }
        
        fieldGroup.appendChild(inputElement);

        // 添加帮助文本（非boolean类型）
        if (setting.description && setting.type !== 'boolean') {
            const helpText = document.createElement('small');
            helpText.className = 'form-hint';
            helpText.textContent = setting.description;
            fieldGroup.appendChild(helpText);
        }

        // 添加悬停提示（所有类型）
        if (setting.description) {
            if (setting.type === 'boolean') {
                // 布尔类型：提示放在 checkbox-container 上
                inputElement.setAttribute('data-tooltip', setting.description);
            } else {
                // 其他类型：提示放在 label 上
                const label = fieldGroup.querySelector('label:not(.checkbox-container)');
                if (label) {
                    label.setAttribute('data-tooltip', setting.description);
                }
            }
        }

        return fieldGroup;
    }
    
    // 加载已保存的设置
    loadSavedSettings(serviceKey) {
        try {
            const savedSettings = this.currentSettings[serviceKey];
            
            if (savedSettings) {
                Object.keys(savedSettings).forEach(key => {
                    const input = document.getElementById(`api-${key}`);
                    if (input) {
                        if (input.type === 'checkbox') {
                            input.checked = savedSettings[key];
                        } else {
                            input.value = savedSettings[key];
                        }
                    }
                });
            }
        } catch (error) {
            console.error('加载保存的设置失败:', error);
        }
    }
    
    // 保存当前设置
    saveCurrentSettings() {
        if (!this.selectedService) {
            showMessage('错误', '请先选择翻译服务');
            return false;
        }
        
        const service = this.apiServices[this.selectedService];
        if (!service) {
            showMessage('错误', '未找到选中的服务');
            return false;
        }
        
        // 检查是否有 api-setting 配置
        const apiSetting = service['api-setting'];
        if (!apiSetting || !Array.isArray(apiSetting) || apiSetting.length === 0) {
            showMessage('提示', '此服务无需配置');
            
            // 如果服务没有配置，保存空对象
            this.currentSettings[this.selectedService] = {};
            
            // 发送到后端
            this.updateSettings();
            return true;
        }
        
        const settings = {};
        let isValid = true;
        const missingFields = [];
        
        // 收集所有设置值
        apiSetting.forEach(setting => {
            const input = document.getElementById(`api-${setting.id}`);
            if (input) {
                let value;
                
                if (input.type === 'checkbox') {
                    value = input.checked;
                } else if (input.tagName === 'SELECT') {
                    value = input.value;
                } else {
                    value = input.value.trim();
                }
                
                // 验证必填字段
                if (setting.required && (!value || value === '')) {
                    isValid = false;
                    missingFields.push(setting.name);
                    
                    // 添加错误样式
                    input.classList.add('error');
                } else {
                    input.classList.remove('error');
                }
                
                settings[setting.id] = value;
            }
        });
        
        if (!isValid) {
            showMessage('错误', `以下必填字段未填写：${missingFields.join(', ')}`);
            return false;
        }
        
        // 保存到后端
        try {
            this.currentSettings[this.selectedService] = settings;
            
            // 发送到后端
            this.updateSettings();
            
            return true;
        } catch (error) {
            console.error('保存设置失败:', error);
            showMessage('错误', '保存设置时发生错误');
            return false;
        }
    }

    collectCurrentSettings() {
        if (!this.selectedService) {
            showMessage('错误', '请先选择翻译服务');
            return false;
        }
        
        const service = this.apiServices[this.selectedService];
        if (!service) {
            showMessage('错误', '未找到选中的服务');
            return false;
        }
        
        // 检查是否有 api-setting 配置
        const apiSetting = service['api-setting'];
        if (!apiSetting || !Array.isArray(apiSetting) || apiSetting.length === 0) {
            // 返回空对象表示没有配置
            return {};
        }
        
        const settings = {};
        let isValid = true;
        const missingFields = [];
        
        // 收集所有设置值
        apiSetting.forEach(setting => {
            const input = document.getElementById(`api-${setting.id}`);
            if (input) {
                let value;
                
                if (input.type === 'checkbox') {
                    value = input.checked;
                } else if (input.tagName === 'SELECT') {
                    value = input.value;
                } else {
                    value = input.value.trim();
                }
                
                // 验证必填字段
                if (setting.required && (!value || value === '')) {
                    isValid = false;
                    missingFields.push(setting.name);
                    
                    // 添加错误样式
                    input.classList.add('error');
                } else {
                    input.classList.remove('error');
                }
                
                settings[setting.id] = value;
            }
        });
        
        if (!isValid) {
            showMessage('错误', `以下必填字段未填写：${missingFields.join(', ')}`);
            return false;
        }
        
        return settings;
    }    
    async loadSettings() { 
        try {
            const savedSettings = configManager.getCachedValue('api_config');
            let api_settings
            if (configManager.getCachedValue('api_crypto')) {
                api_settings = JSON.parse(await decryptText("AutoTranslate", savedSettings));
            }
            else {
                api_settings = JSON.parse(savedSettings);
            };
            this.currentSettings = api_settings;
        } catch (error) {
            console.error('加载设置失败:', error);
            addLogMessage('加载api设置时发生错误，清空api设置');
            this.updateSettings();
            return false;
        }
    }

    // 发送设置到后端
    async updateSettings() {
        try {
            let api_settings
            if (configManager.getCachedValue('api_crypto')) {
                api_settings = await encryptText("AutoTranslate", JSON.stringify(this.currentSettings));
            }
            else {
                api_settings = JSON.stringify(this.currentSettings);
            };
            configManager.updateConfigValue('api-configs', api_settings);
            configManager.flushPendingUpdates();
            return true;
        } catch (error) {
            console.error('发送到后端失败:', error);
            showMessage('错误', '保存到后端时发生错误');
            return false;
        }
    }
    
    // 更新服务状态网格
    updateServiceStatus(serviceKey, service) {
        const statusGrid = document.querySelector('.api-status-grid');
        if (!statusGrid) {
            return;
        }
        
        // 清空容器
        statusGrid.innerHTML = '';
        
        // 获取metadata
        const metadata = service.metadata || {};
        
        // 创建状态卡片
        const statusCard = document.createElement('div');
        statusCard.className = 'api-status-card';
        
        // 服务名称
        const nameElement = document.createElement('h4');
        nameElement.textContent = serviceKey;
        statusCard.appendChild(nameElement);
        
        // 服务描述
        if (metadata.description) {
            const descElement = document.createElement('p');
            descElement.className = 'api-description';
            descElement.textContent = metadata.description;
            statusCard.appendChild(descElement);
        }

        // 使用说明
        if (metadata.usage_documentation) {
            const shortDescElement = document.createElement('p');
            shortDescElement.className = 'api-usage-documentation';
            shortDescElement.textContent = metadata.usage_documentation;
            statusCard.appendChild(shortDescElement);
        }

        // 短描述
        if (metadata.short_description) {
            const shortDescElement = document.createElement('p');
            shortDescElement.className = 'api-short-desc';
            shortDescElement.textContent = metadata.short_description;
            statusCard.appendChild(shortDescElement);
        }
        
        // 链接
        const linksContainer = document.createElement('div');
        linksContainer.className = 'api-links';
        
        if (metadata.console_url) {
            const consoleLink = document.createElement('a');
            consoleLink.href = metadata.console_url;
            consoleLink.target = '_blank';
            consoleLink.textContent = '控制台';
            consoleLink.className = 'api-link';
            linksContainer.appendChild(consoleLink);
        }
        
        if (metadata.documentation_url) {
            const docLink = document.createElement('a');
            docLink.href = metadata.documentation_url;
            docLink.target = '_blank';
            docLink.textContent = '文档';
            docLink.className = 'api-link';
            linksContainer.appendChild(docLink);
        }
        
        if (linksContainer.children.length > 0) {
            statusCard.appendChild(linksContainer);
        }
        
        // 语言代码
        if (service.langCode) {
            const langContainer = document.createElement('div');
            langContainer.className = 'api-lang-codes';
            
            const langTitle = document.createElement('h5');
            langTitle.textContent = '支持的语言代码:';
            langContainer.appendChild(langTitle);
            
            const langList = document.createElement('div');
            langList.className = 'lang-list';
            
            Object.entries(service.langCode).forEach(([key, value]) => {
                const langItem = document.createElement('span');
                langItem.className = 'lang-item';
                langItem.textContent = `${key} → ${value}`;
                langList.appendChild(langItem);
            });
            
            langContainer.appendChild(langList);
            statusCard.appendChild(langContainer);
        }
        
        // 添加到网格
        statusGrid.appendChild(statusCard);
    }
    
    // 清空设置表单
    clearSettingsForm() {
        const apiSettingsContainer = document.querySelector('.api-settings');
        if (apiSettingsContainer) {
            apiSettingsContainer.innerHTML = '';
        }
    }
    
    // 清空状态网格
    clearStatusGrid() {
        const statusGrid = document.querySelector('.api-status-grid');
        if (statusGrid) {
            statusGrid.innerHTML = '';
        }
    }
    
    // 获取所有服务的设置
    getAllSettings() {
        return this.currentSettings;
    }
    
    // 获取特定服务的设置
    getServiceSettings(serviceKey) {
        return this.currentSettings[serviceKey] || {};
    }

    async testAPIConfig() {
        const modal = new ProgressModal('测试API配置');
        modal.addLog('正在测试API配置...')
        const apiConfig = this.collectCurrentSettings();

        if (apiConfig === false) {
            modal.complete(false, '测试失败');
            return;
        }
        const result = await pywebview.api.test_api(
            this.selectedService, apiConfig
        )

        if (result.success) {
            modal.addLog('API配置测试成功！');
            modal.addLog('测试信息如下');
            const result_json = result.message;
            modal.addLog(`韩文：안녕 -> ${result_json.kr}`);
            modal.addLog(`英文：hello -> ${result_json.en}`);
            modal.addLog(`日文：こんにちは -> ${result_json.jp}`);
            modal.complete(true, '测试成功');
        } else {
            modal.addLog('API配置测试失败！');
            modal.addLog(result.message);
            modal.complete(false, '测试失败');
        }
    }
}
