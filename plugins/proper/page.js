/**
 * proper/page.js —— 专有词汇插件页面逻辑
 */

(function () {
    pagesManager.registerSwitchHook('proper', {
        onActivate() { configManager.applyConfigToPage(); }
    });
})();

async function fetchProperNouns() {
    const modal = new ProgressModal('抓取专有词汇');
    modal.addLog('正在抓取专有词汇...');
    try {
        const result = await window.pywebview.api.fetch_proper_nouns(modal.id);
        modal.complete(result.success, result.message);
    } catch (e) { modal.complete(false, e.message); }
}
