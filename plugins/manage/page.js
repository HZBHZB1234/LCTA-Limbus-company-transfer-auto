/**
 * manage/page.js —— 已安装数据管理插件页面逻辑
 */

(function () {
    pagesManager.registerSwitchHook('manage', {
        onActivate() {
            configManager.applyConfigToPage();
            refreshInstalledPackageList();
            refreshInstalledModList();
            refreshSymlink();
            toggleCustomLangGui();
        }
    });
})();

async function toggleCustomLang() {
    const cb = document.getElementById('enable-lang');
    const result = await window.pywebview.api.toggle_installed_package(cb.checked);
    toggleCustomLangGui();
    if (result.success && result.changed && cb.checked) refreshInstalledPackageList();
}

function toggleCustomLangGui() {
    const cb = document.getElementById('enable-lang');
    const group = document.getElementById('installed-package-group');
    if (!cb || !group) return;
    const overlayClass = 'installed-package-overlay';
    let overlay = group.querySelector('.' + overlayClass);
    if (!cb.checked) {
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = overlayClass;
            overlay.innerHTML = '<i class="fas fa-lock"></i><p>客制化翻译已禁用</p><small>勾选上方选项以启用此区域</small>';
            group.appendChild(overlay);
        }
    } else {
        if (overlay) overlay.remove();
    }
}

async function browseInstallModDirectory() {
    const result = await window.pywebview.api.browse_folder('installed-mod-directory');
    const input = document.getElementById('installed-mod-directory');
    if (input && result) {
        input.value = result;
        await configManager.updateConfigValue('installed-mod-directory', result);
        await configManager.flushPendingUpdates();
        refreshInstalledModList();
    }
}

async function clearModDirectory() {
    const input = document.getElementById('installed-mod-directory');
    if (input) {
        input.value = '';
        await configManager.updateConfigValue('installed-mod-directory', '');
        await configManager.flushPendingUpdates();
        refreshInstalledModList();
    }
}

async function refreshInstalledPackageList() {
    const el = document.getElementById('installed-package-list');
    if (!el) return;
    try {
        const result = await window.pywebview.api.get_installed_list();
        if (result && result.packages && result.packages.length) {
            el.innerHTML = result.packages.map(p => `<div class="list-item" data-package="${p}"><span>${p}</span><button class="action-btn small" onclick="selectInstalledPkg('${p}')">选择</button></div>`).join('');
        } else {
            el.innerHTML = '<div class="list-empty"><i class="fas fa-box-open"></i><p>未找到已安装汉化包</p></div>';
        }
    } catch (e) { el.innerHTML = `<div class="list-empty"><p>加载失败: ${e.message}</p></div>`; }
}

function selectInstalledPkg(name) {
    document.querySelectorAll('#installed-package-list .list-item').forEach(i => i.classList.remove('selected'));
    const item = document.querySelector(`#installed-package-list .list-item[data-package="${name}"]`);
    if (item) item.classList.add('selected');
}

async function useSelectedPackage() {
    const sel = document.querySelector('#installed-package-list .list-item.selected');
    if (!sel) { showMessage('提示', '请先选择汉化包'); return; }
    const result = await window.pywebview.api.use_package(sel.dataset.package);
    showMessage('结果', result.message || '操作完成');
}

async function deleteInstalledPackage() {
    const sel = document.querySelector('#installed-package-list .list-item.selected');
    if (!sel) { showMessage('提示', '请先选择汉化包'); return; }
    showConfirm('确认删除', `确定要删除 "${sel.dataset.package}" 吗？`, async () => {
        const result = await window.pywebview.api.delete_installed(sel.dataset.package);
        if (result.success) refreshInstalledPackageList();
    });
}

async function refreshInstalledModList() {
    const el = document.getElementById('install-mod-list');
    if (!el) return;
    try {
        const result = await window.pywebview.api.get_mod_list();
        if (result && result.mods && result.mods.length) {
            el.innerHTML = result.mods.map(m => `<div class="list-item" data-mod="${m}"><span>${m}</span><button class="action-btn small" onclick="selectMod('${m}')">选择</button></div>`).join('');
        } else {
            el.innerHTML = '<div class="list-empty"><i class="fas fa-box-open"></i><p>未找到可用的模组</p></div>';
        }
    } catch (e) { el.innerHTML = `<div class="list-empty"><p>加载失败: ${e.message}</p></div>`; }
}

function selectMod(name) {
    document.querySelectorAll('#install-mod-list .list-item').forEach(i => i.classList.remove('selected'));
    const item = document.querySelector(`#install-mod-list .list-item[data-mod="${name}"]`);
    if (item) item.classList.add('selected');
}

async function openModPath() { await window.pywebview.api.open_mod_path(); }

async function deleteSelectedMod() {
    const sel = document.querySelector('#install-mod-list .list-item.selected');
    if (!sel) { showMessage('提示', '请先选择模组'); return; }
    showConfirm('确认删除', `确定要删除 "${sel.dataset.mod}" 吗？`, async () => {
        await window.pywebview.api.delete_mod(sel.dataset.mod);
        refreshInstalledModList();
    });
}

async function refreshSymlink() {
    const el = document.getElementById('symlink-list');
    if (!el) return;
    try {
        const result = await window.pywebview.api.get_symlink_list();
        if (result && result.links && result.links.length) {
            el.innerHTML = result.links.map(l => `<div class="list-item" data-link="${l.path}"><span>${l.name || l.path}</span><span>${l.status || ''}</span></div>`).join('');
        } else {
            el.innerHTML = '<div class="list-empty"><i class="fas fa-box-open"></i><p>无数据</p></div>';
        }
    } catch (e) { el.innerHTML = `<div class="list-empty"><p>加载失败: ${e.message}</p></div>`; }
}

async function createSymlink() { await window.pywebview.api.create_symlink(); refreshSymlink(); }
async function removeSymlink() { await window.pywebview.api.remove_symlink(); refreshSymlink(); }
