/**
 * translate/page.js —— 翻译工具插件页面逻辑
 *
 * 通过 pagesManager.registerSwitchHook 注册页面切换事件。
 * onActivate: 页面激活时初始化翻译服务选择器、应用配置
 * onDeactivate: 页面离开时清理
 */

(function () {
    const PLUGIN_ID = 'translate';

    // ── 页面切换钩子 ──
    pagesManager.registerSwitchHook(PLUGIN_ID, {
        onActivate() {
            initTranslatePage();
        },
        onDeactivate() {
            // 离开翻译页时刷新待更新配置
            if (configManager) configManager.flushPendingUpdates();
        }
    });

    async function initTranslatePage() {
        // 应用配置到 UI
        if (configManager) {
            configManager.applyConfigToPage();
            toggleProper();
            toggleAutoProper();
            toggleDevelopSettings();
        }

        // 加载翻译服务选择器（依赖后端 TKIT_MACHINE）
        try {
            const services = await window.pywebview.api.get_attr('TKIT_MACHINE_OBJECT');
            if (services) {
                const container = document.querySelector('.translator-services');
                if (container) {
                    container.innerHTML = '';
                    const select = document.createElement('select');
                    select.id = 'translator-service-select';
                    select.className = 'translator-service-select';
                    Object.keys(services).forEach(name => {
                        const opt = document.createElement('option');
                        opt.value = name; opt.textContent = name;
                        select.appendChild(opt);
                    });
                    container.appendChild(select);

                    // 恢复已保存的选择
                    const saved = configManager.getCachedValue('ui_default.translator.translator');
                    if (saved) select.value = saved;
                }
            }
        } catch (e) {
            console.error('加载翻译服务列表失败:', e);
        }
    }
})();

// ── 页面内 UI 控制函数 ──

function toggleProper() {
    const group = document.getElementById('proper-settings');
    const enable = document.getElementById('enable-proper');
    if (group && enable) group.style.display = enable.checked ? 'block' : 'none';
}

function toggleAutoProper() {
    const group = document.getElementById('proper-path-text');
    const enable = document.getElementById('auto-fetch-proper');
    if (group && enable) group.style.display = enable.checked ? 'none' : 'block';
}

function toggleDevelopSettings() {
    const group = document.getElementById('dev-settings');
    const enable = document.getElementById('enable-dev-settings');
    if (group && enable) group.style.display = enable.checked ? 'block' : 'none';
}

async function startTranslation() {
    const modal = new ProgressModal('翻译工具');
    modal.addLog('正在启动翻译...');
    try {
        const result = await window.pywebview.api.run_translation(modal.id);
        if (result.success) {
            modal.complete(true, '翻译完成');
        } else {
            modal.complete(false, result.message || '翻译失败');
        }
    } catch (e) {
        modal.complete(false, '翻译出错: ' + e.message);
    }
}
