/**
 * bubble/page.js —— 气泡模组插件页面逻辑
 */

(function () {
    pagesManager.registerSwitchHook('bubble', {
        onActivate() { configManager.applyConfigToPage(); }
    });
})();

async function downloadBubble() {
    const modal = new ProgressModal('下载气泡模组');
    modal.addLog('正在下载气泡模组...');
    try {
        const result = await window.pywebview.api.download_bubble(modal.id);
        modal.complete(result.success, result.message);
    } catch (e) { modal.complete(false, e.message); }
}
