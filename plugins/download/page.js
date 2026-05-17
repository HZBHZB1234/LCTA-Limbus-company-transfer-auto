/**
 * download/page.js —— 汉化包下载插件页面逻辑
 */

(function () {
    const PLUGIN_ID = 'download';

    pagesManager.registerSwitchHook(PLUGIN_ID, {
        onActivate() {
            configManager.applyConfigToPage();
        }
    });
})();

async function downloadOurplay() {
    const modal = new ProgressModal('下载OurPlay汉化包');
    modal.addLog('正在启动下载...');
    try {
        const result = await window.pywebview.api.download_ourplay(modal.id);
        modal.complete(result.success, result.message || '下载完成');
    } catch (e) {
        modal.complete(false, '下载出错: ' + e.message);
    }
}

async function downloadLLC() {
    const modal = new ProgressModal('下载零协汉化包');
    modal.addLog('正在启动下载...');
    try {
        const result = await window.pywebview.api.download_llc(modal.id);
        modal.complete(result.success, result.message || '下载完成');
    } catch (e) {
        modal.complete(false, '下载出错: ' + e.message);
    }
}

async function downloadMachine() {
    const modal = new ProgressModal('下载LCTA-AU汉化包');
    modal.addLog('正在启动下载...');
    try {
        const result = await window.pywebview.api.download_machine(modal.id);
        modal.complete(result.success, result.message || '下载完成');
    } catch (e) {
        modal.complete(false, '下载出错: ' + e.message);
    }
}

async function downloadBubble() {
    const modal = new ProgressModal('下载气泡文本');
    modal.addLog('正在启动下载...');
    try {
        const result = await window.pywebview.api.download_bubble(modal.id);
        modal.complete(result.success, result.message || '下载完成');
    } catch (e) {
        modal.complete(false, '下载出错: ' + e.message);
    }
}
