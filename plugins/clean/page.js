/**
 * clean/page.js —— 清除本地缓存插件页面逻辑
 */

(function () {
    pagesManager.registerSwitchHook('clean', {
        onActivate() { configManager.applyConfigToPage(); }
    });
})();

let customCleanFiles = [];

function browseCustomFile() { window.pywebview.api.browse_file('custom-file-path'); }
function browseCustomFolder() { window.pywebview.api.browse_folder('custom-file-path'); }

function addCustomFile() {
    const input = document.getElementById('custom-file-path');
    if (!input || !input.value.trim()) return;
    customCleanFiles.push(input.value.trim());
    input.value = '';
    renderCustomFilesList();
}

function clearCustomFilesList() {
    customCleanFiles = [];
    renderCustomFilesList();
}

function renderCustomFilesList() {
    const el = document.getElementById('custom-files-list');
    if (!el) return;
    el.innerHTML = customCleanFiles.map((f, i) => `<div class="file-item"><span>${f}</span><button class="action-btn small danger" onclick="customCleanFiles.splice(${i},1);renderCustomFilesList();"><i class="fas fa-times"></i></button></div>`).join('');
}

async function cleanCache() {
    const modal = new ProgressModal('清除缓存');
    modal.addLog('正在清理...');
    try {
        const result = await window.pywebview.api.clean_cache(modal.id);
        modal.complete(result.success, result.message || '清理完成');
    } catch (e) {
        modal.complete(false, '清理出错: ' + e.message);
    }
}
