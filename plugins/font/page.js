/**
 * font/page.js —— 字体管理插件页面逻辑
 */

(function () {
    pagesManager.registerSwitchHook('font', {
        onActivate() { configManager.applyConfigToPage(); }
    });
})();

let systemFonts = [];

async function refreshFontList() {
    const el = document.getElementById('font-list');
    if (!el) return;
    el.innerHTML = '<div class="list-empty"><i class="fas fa-spinner fa-spin"></i><p>加载中...</p></div>';
    try {
        const result = await window.pywebview.api.get_system_fonts_list();
        if (result && result.fonts && result.fonts.length) {
            systemFonts = result.fonts;
            el.innerHTML = systemFonts.map((f, i) => `<div class="list-item" data-index="${i}">
                <span>${f.name || f}</span>
                <button class="action-btn small" onclick="selectFont(${i})">选择</button>
            </div>`).join('');
        } else {
            el.innerHTML = '<div class="list-empty"><i class="fas fa-font"></i><p>未找到系统字体</p></div>';
        }
    } catch (e) { el.innerHTML = `<div class="list-empty"><p>加载失败: ${e.message}</p></div>`; }
}

function selectFont(i) {
    document.querySelectorAll('#font-list .list-item').forEach(item => item.classList.remove('selected'));
    const item = document.querySelector(`#font-list .list-item[data-index="${i}"]`);
    if (item) item.classList.add('selected');
}

async function exportSelectedFont() {
    const sel = document.querySelector('#font-list .list-item.selected');
    if (!sel) { showMessage('提示', '请先选择字体'); return; }
    const idx = parseInt(sel.dataset.index);
    const font = systemFonts[idx];
    const fontName = typeof font === 'string' ? font : (font.name || font.fullName || '');
    try {
        const result = await window.pywebview.api.browse_folder('font-export-dest');
        if (!result) return;
        const exportResult = await window.pywebview.api.export_selected_font(fontName, result);
        showMessage(exportResult.success ? '成功' : '失败', exportResult.message || '导出完成');
    } catch (e) { showMessage('错误', e.message); }
}

async function changeFontForPackage() {
    // reuses the installed package selection from manage page flow
    try {
        const result = await window.pywebview.api.browse_file('font-file-path');
        if (!result) return;
        showMessage('提示', '请在已安装数据管理页面选择汉化包后使用此功能');
    } catch (e) { showMessage('错误', e.message); }
}

async function getFontFromInstalled() {
    try {
        const result = await window.pywebview.api.browse_folder('font-export-dest');
        if (!result) return;
        showMessage('提示', '请在已安装数据管理页面选择汉化包后使用此功能');
    } catch (e) { showMessage('错误', e.message); }
}
