/**
 * settings/page.js —— 基础设置插件页面逻辑
 * 含程序设置、Launcher配置、API配置
 */

(function () {
    const PLUGIN_ID = 'settings';

    // API 配置管理器（内嵌在 settings 插件中）
    const apiConfig = {
        services: null,
        llmTranslator: null,
        selectedService: null,
        currentSettings: {},

        async init() {
            try {
                const tkitMachine = await window.pywebview.api.get_attr('TKIT_MACHINE_OBJECT');
                const LLM_TRANSLATOR = await window.pywebview.api.get_attr('LLM_TRANSLATOR');
                if (tkitMachine && LLM_TRANSLATOR) {
                    this.services = tkitMachine;
                    this.llmTranslator = LLM_TRANSLATOR;
                    await this.loadSettings();
                    this.loadAPISelect();
                    this.loadStatus();
                    return true;
                }
                return false;
            } catch (e) { console.error('加载API服务失败:', e); return false; }
        },

        loadAPISelect() {
            const container = document.querySelector('.api-select');
            if (!container || !this.services) return;
            container.innerHTML = '';
            const select = document.createElement('select');
            select.id = 'api-service-select';
            select.className = 'api-service-select';
            Object.keys(this.services).forEach(name => {
                const opt = document.createElement('option');
                opt.value = name; opt.textContent = name;
                select.appendChild(opt);
            });
            container.appendChild(select);
            select.addEventListener('change', (e) => this.onServiceSelected(e.target.value));

            const saved = configManager.getCachedValue('ui_default.api_config.key');
            if (saved && this.services[saved]) select.value = saved;
            if (select.value) select.dispatchEvent(new Event('change', { bubbles: true }));
        },

        onServiceSelected(serviceKey) {
            if (!serviceKey || !this.services[serviceKey]) {
                document.querySelector('.api-settings').innerHTML = '';
                document.querySelector('.api-status-grid').innerHTML = '';
                this.selectedService = null;
                return;
            }
            this.selectedService = serviceKey;
            this.updateStatus(serviceKey, this.services[serviceKey]);
            this.generateForm(serviceKey, this.services[serviceKey]);
            if (serviceKey === 'LLM通用翻译服务') this.addLLMSelector();
        },

        generateForm(serviceKey, service) {
            const container = document.querySelector('.api-settings');
            if (!container) return;
            container.innerHTML = '';
            const apiSetting = service['api-setting'];
            if (!apiSetting || !Array.isArray(apiSetting)) {
                container.innerHTML = '<p>此服务无需API配置</p>';
                return;
            }
            const form = document.createElement('div');
            form.className = 'api-settings-form';
            form.innerHTML = '<h4>API参数配置</h4>';
            apiSetting.forEach(setting => {
                const field = document.createElement('div');
                field.className = 'api-setting-field';
                if (setting.type !== 'boolean') {
                    field.innerHTML = `<label for="api-${setting.id}">${setting.name}${setting.required ? '<span class="required"> *</span>' : ''}</label>`;
                }
                if (setting.type === 'boolean') {
                    field.innerHTML += `<label class="checkbox-container" for="api-${setting.id}">
                        <input type="checkbox" id="api-${setting.id}" name="${setting.id}">
                        <span class="checkmark"></span> ${setting.name || ''}</label>`;
                } else {
                    field.innerHTML += `<input type="text" id="api-${setting.id}" name="${setting.id}" placeholder="${setting.description || ''}">`;
                }
                if (setting.description && setting.type !== 'boolean') {
                    field.innerHTML += `<small class="form-hint">${setting.description}</small>`;
                }
                form.appendChild(field);
            });
            container.appendChild(form);
            this.loadSavedFields(serviceKey);
        },

        loadSavedFields(serviceKey) {
            const saved = this.currentSettings[serviceKey];
            if (!saved) return;
            Object.keys(saved).forEach(key => {
                const input = document.getElementById(`api-${key}`);
                if (input) {
                    if (input.type === 'checkbox') input.checked = saved[key];
                    else input.value = saved[key];
                }
            });
        },

        addLLMSelector() {
            if (!this.llmTranslator) return;
            const form = document.querySelector('.api-settings-form');
            if (!form) return;
            const div = document.createElement('div');
            div.className = 'api-setting-field';
            div.innerHTML = '<label for="api-llm-service-selector">选择LLM服务</label>';
            const wrapper = document.createElement('div');
            wrapper.className = 'select-wrapper';
            const select = document.createElement('select');
            select.id = 'api-llm-service-selector';
            select.innerHTML = '<option value="">选择以使用预设LLM服务地址...</option>';
            Object.keys(this.llmTranslator).forEach(name => {
                select.innerHTML += `<option value="${name}">${name}</option>`;
            });
            wrapper.appendChild(select);
            div.appendChild(wrapper);
            select.addEventListener('change', (e) => {
                const svc = this.llmTranslator[e.target.value];
                if (svc) {
                    const baseUrl = document.getElementById('api-base_url');
                    const model = document.getElementById('api-model_name');
                    if (baseUrl) baseUrl.value = svc.base_url || '';
                    if (model) model.value = svc.model || '';
                }
            });
            form.insertBefore(div, form.firstChild);
        },

        updateStatus(serviceKey, service) {
            const grid = document.querySelector('.api-status-grid');
            if (!grid) return;
            grid.innerHTML = `<div class="api-status-card">
                <h4>${serviceKey}</h4>
                ${service.metadata ? `<p class="api-description">${service.metadata.description || ''}</p>` : ''}
                ${service.metadata && service.metadata.documentation_url ? `<a href="${service.metadata.documentation_url}" target="_blank" class="api-link">文档</a>` : ''}
            </div>`;
        },

        async loadSettings() {
            try {
                const saved = configManager.getCachedValue('api_config');
                let parsed;
                if (configManager.getCachedValue('api_crypto')) {
                    parsed = JSON.parse(await decryptText('AutoTranslate', saved));
                } else {
                    parsed = JSON.parse(saved);
                }
                this.currentSettings = parsed || {};
            } catch (e) {
                console.error('加载API设置失败:', e);
                this.currentSettings = {};
            }
        },

        async saveSettings() {
            try {
                let data = JSON.stringify(this.currentSettings);
                if (configManager.getCachedValue('api_crypto')) {
                    data = await encryptText('AutoTranslate', data);
                }
                await configManager.updateConfigValue('api-configs', data);
                await configManager.flushPendingUpdates();
                showMessage('成功', 'API配置已保存');
            } catch (e) {
                showMessage('错误', '保存API配置失败: ' + e.message);
            }
        },

        collectCurrent() {
            if (!this.selectedService) return null;
            const service = this.services[this.selectedService];
            if (!service) return null;
            const apiSetting = service['api-setting'];
            if (!apiSetting || !Array.isArray(apiSetting) || apiSetting.length === 0) return {};
            const settings = {};
            apiSetting.forEach(setting => {
                const input = document.getElementById(`api-${setting.id}`);
                if (input) {
                    settings[setting.id] = input.type === 'checkbox' ? input.checked : input.value.trim();
                }
            });
            return settings;
        }
    };

    pagesManager.registerSwitchHook(PLUGIN_ID, {
        onActivate() {
            configManager.applyConfigToPage();
            toggleCachePathInput();
            toggleStoragePathInput();
            toggleSteamCommand();
            apiConfig.init();
        },
        onDeactivate() {
            configManager.flushPendingUpdates();
        }
    });
})();

// ── 页面内函数 ──

function saveAPIConfig() {
    const settings = apiConfig.collectCurrent();
    if (settings === null) { showMessage('错误', '请先选择翻译服务'); return; }
    if (settings === false) return;
    apiConfig.currentSettings[apiConfig.selectedService] = settings;
    apiConfig.saveSettings();
}

async function testAPIConfig() {
    if (!apiConfig.selectedService) { showMessage('错误', '请先选择翻译服务'); return; }
    const settings = apiConfig.collectCurrent();
    if (settings === false) return;
    const modal = new ProgressModal('测试API配置');
    modal.addLog('正在测试API配置...');
    try {
        const result = await window.pywebview.api.test_api(apiConfig.selectedService, settings);
        if (result.success) {
            modal.addLog('API配置测试成功！');
            modal.complete(true, '测试通过');
        } else {
            modal.addLog('测试失败: ' + result.message);
            modal.complete(false, '测试失败');
        }
    } catch (e) {
        modal.complete(false, '测试出错: ' + e.message);
    }
}

function toggleCachePathInput() {
    const cb = document.getElementById('enable-cache');
    const group = document.getElementById('cache-path-group');
    if (cb && group) group.style.display = cb.checked ? 'block' : 'none';
}

function toggleStoragePathInput() {
    const cb = document.getElementById('enable-storage');
    const group = document.getElementById('storage-path-group');
    if (cb && group) group.style.display = cb.checked ? 'block' : 'none';
}

function toggleSteamCommand() {
    window.pywebview.api.run_func('get_steam_command').then(cmd => {
        const el = document.getElementById('steam-cmd');
        if (el) el.value = cmd;
    }).catch(e => {
        const el = document.getElementById('steam-cmd');
        if (el) el.value = '获取失败 ' + e;
    });
}

function copySteamPath() {
    const el = document.getElementById('steam-cmd');
    if (el) { el.select(); el.setSelectionRange(0, 99999); navigator.clipboard.writeText(el.value); }
}

function goToTestPage() { pagesManager.switchPage('test'); }
function goToCleanPage() { pagesManager.switchPage('clean'); }

async function saveSettings() {
    const updates = {};
    const schema = configManager._schema || {};
    for (const [path, meta] of Object.entries(schema)) {
        if (meta.plugin_id !== 'settings' && meta.plugin_id !== 'update') continue;
        const el = document.getElementById(meta.html_id);
        if (!el) continue;
        let value;
        if (el.type === 'checkbox') value = el.checked;
        else if (el.tagName === 'SELECT') value = el.value;
        else value = el.value;
        updates[path] = value;
    }
    for (const [path, value] of Object.entries(updates)) {
        configManager.setCachedValue(path, value);
    }
    await configManager.flushPendingUpdates();
    showMessage('成功', '设置已保存');
}

async function useDefaultConfig() {
    showConfirm('确认', '确定要使用默认配置吗？', async () => {
        await window.pywebview.api.use_default();
        showMessage('提示', '已使用默认配置，请重新加载');
    });
}

async function resetConfig() {
    showConfirm('确认重置', '确定要重置配置吗？这将清除所有设置！', async () => {
        await window.pywebview.api.reset_config();
        showMessage('提示', '配置已重置，请重新加载');
    });
}

async function manualCheckUpdates() {
    const modal = new ProgressModal('检查更新');
    modal.addLog('正在检查更新...');
    try {
        const result = await window.pywebview.api.check_update();
        modal.complete(result.success, result.message || '检查完成');
    } catch (e) {
        modal.complete(false, '检查失败: ' + e.message);
    }
}

async function doUpdate() {
    const modal = new ProgressModal('强制更新');
    modal.addLog('正在执行更新...');
    try {
        const result = await window.pywebview.api.do_update(modal.id);
        modal.complete(result.success, result.message || '更新完成');
    } catch (e) {
        modal.complete(false, '更新失败: ' + e.message);
    }
}
