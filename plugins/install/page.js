/**
 * install/page.js —— 安装已有汉化插件页面逻辑
 */

(function () {
    const PLUGIN_ID = 'install';

    pagesManager.registerSwitchHook(PLUGIN_ID, {
        onActivate() {
            configManager.applyConfigToPage();
            refreshInstallPackageList();
        }
    });
})();

async function browseInstallPackageDirectory() {
    const result = await window.pywebview.api.browse_folder('install-package-directory');
    const input = document.getElementById('install-package-directory');
    if (input && result) {
        input.value = result;
        await configManager.updateConfigValue('install-package-directory', result);
        await configManager.flushPendingUpdates();
        refreshInstallPackageList();
    }
}

async function clearPackageDirectory() {
    const input = document.getElementById('install-package-directory');
    if (input) {
        input.value = '';
        await configManager.updateConfigValue('install-package-directory', '');
        await configManager.flushPendingUpdates();
        refreshInstallPackageList();
    }
}

async function refreshInstallPackageList() {
    const listEl = document.getElementById('install-package-list');
    if (!listEl) return;
    listEl.innerHTML = '<div class="list-empty"><i class="fas fa-spinner fa-spin"></i><p>加载中...</p></div>';
    try {
        const result = await window.pywebview.api.get_install_package_list();
        if (result && result.packages) {
            if (result.packages.length === 0) {
                listEl.innerHTML = '<div class="list-empty"><i class="fas fa-box-open"></i><p>未找到可用的汉化包</p></div>';
                return;
            }
            listEl.innerHTML = result.packages.map(p => `
                <div class="list-item" data-package="${p.name}">
                    <span>${p.name}</span>
                    <button class="action-btn small" onclick="selectPackage('${p.name}')">选择</button>
                </div>`).join('');
        }
    } catch (e) {
        listEl.innerHTML = '<div class="list-empty"><p>加载失败: ' + e.message + '</p></div>';
    }
}

function selectPackage(name) {
    document.querySelectorAll('#install-package-list .list-item').forEach(i => i.classList.remove('selected'));
    const item = document.querySelector(`#install-package-list .list-item[data-package="${name}"]`);
    if (item) item.classList.add('selected');
}

async function installSelectedPackage() {
    const selected = document.querySelector('#install-package-list .list-item.selected');
    if (!selected) { showMessage('提示', '请先选择要安装的汉化包'); return; }
    const modal = new ProgressModal('安装汉化包');
    modal.addLog('正在安装: ' + selected.dataset.package);
    try {
        const result = await window.pywebview.api.install_package(selected.dataset.package, modal.id);
        modal.complete(result.success, result.message);
        if (result.success) refreshInstallPackageList();
    } catch (e) {
        modal.complete(false, '安装出错: ' + e.message);
    }
}

async function deleteSelectedPackage() {
    const selected = document.querySelector('#install-package-list .list-item.selected');
    if (!selected) { showMessage('提示', '请先选择要删除的汉化包'); return; }
    showConfirm('确认删除', `确定要删除 "${selected.dataset.package}" 吗？`, async () => {
        const result = await window.pywebview.api.delete_package(selected.dataset.package);
        if (result.success) refreshInstallPackageList();
    });
}

async function changeFontForPackage() {
    const selected = document.querySelector('#install-package-list .list-item.selected');
    if (!selected) { showMessage('提示', '请先选择汉化包'); return; }
    try {
        const result = await window.pywebview.api.change_font_for_package(selected.dataset.package);
        showMessage('结果', result.message || '操作完成');
    } catch (e) {
        showMessage('错误', e.message);
    }
}

async function getFontFromInstalled() {
    try {
        const result = await window.pywebview.api.get_font_from_installed();
        showMessage('结果', result.message || '操作完成');
    } catch (e) {
        showMessage('错误', e.message);
    }
}
