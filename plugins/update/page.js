/**
 * update/page.js —— 应用更新插件页面逻辑
 */

(function () {
    pagesManager.registerSwitchHook('update', {
        onActivate() {
            configManager.applyConfigToPage();
            loadAboutContent();
        }
    });

    async function loadAboutContent() {
        const targets = [
            { url: 'webui/assets/README.md', className: 'about-content' },
            { url: 'webui/assets/update.md', className: 'update-content' },
            { url: 'webui/assets/use-help.md', className: 'use-help' }
        ];
        for (const { url, className } of targets) {
            try {
                const el = document.querySelector('.' + className);
                if (el) {
                    const content = await loadMarkdownContent(url);
                    el.innerHTML = content;
                }
            } catch (e) { /* ignore */ }
        }
    }
})();

async function checkUpdate() {
    const modal = new ProgressModal('检查更新');
    modal.addLog('正在检查更新...');
    try {
        const result = await window.pywebview.api.manual_check_update();
        if (result.has_update) {
            modal.addLog(`发现新版本: ${result.version || '未知'}`);
            modal.complete(true, '发现可用更新');
        } else {
            modal.complete(true, '已是最新版本');
        }
    } catch (e) { modal.complete(false, e.message); }
}

async function doUpdate() {
    const modal = new ProgressModal('执行更新');
    modal.addLog('正在执行更新...');
    try {
        const result = await window.pywebview.api.perform_update_in_modal(modal.id);
        modal.complete(result.success, result.message || '更新完成');
    } catch (e) { modal.complete(false, e.message); }
}
