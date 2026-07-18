const loadedSections = new Set();

async function preloadAllSections() {
    await loadSection('dashboard');
}

async function loadSection(name) {
    if (loadedSections.has(name)) return;
    try {
        const response = await fetch(`sections/${name}.html`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const html = await response.text();
        const container = document.getElementById(`${name}-section`);
        if (container) container.innerHTML = html;
        loadedSections.add(name);
        onSectionLoaded(name);
    } catch (err) {
        console.error(`Failed to load section ${name}:`, err);
    }
}

function isSectionLoaded(name) {
    return loadedSections.has(name);
}

function onSectionLoaded(name) {
    if (configManager) configManager.applyConfigToUI();
    initTooltips();
    initPasswordToggles();

    switch (name) {
        case 'settings':
            toggleCachePathInput();
            toggleStoragePathInput();
            break;
        case 'translate':
            toggleDevelopSettings();
            toggleAutoProper();
            break;
        case 'launcher-config':
            toggleSteamCommand();
            if (typeof onLauncherOurplaySourceChange === 'function')
                onLauncherOurplaySourceChange();
            break;
        case 'download':
            if (typeof onOurplaySourceChange === 'function')
                onOurplaySourceChange();
            break;
        case 'fancy':
            if (typeof fancyManager !== 'undefined' && fancyManager) {
                fancyManager.listManager = new ToggleItemListManager(
                    'fancy-ruleset-list', {
                        emptyMessage: '暂无规则集',
                        itemIcon: 'fa-paint-brush',
                        defaultEnabled: false,
                        onSelect: function(item) { fancyManager.onSelectRuleset(item); },
                        onToggle: function(item, enabled) { fancyManager.onToggleRuleset(item, enabled); }
                    });
                fancyManager.loadRulesets();
            }
            break;
        case 'install':
            if (typeof packageItemManager !== 'undefined') {
                packageItemManager.containerElement = document.getElementById('install-package-list');
            }
            break;
        case 'manage':
            if (typeof installedPackageItemManager !== 'undefined') {
                installedPackageItemManager.containerElement = document.getElementById('installed-package-list');
            }
            if (typeof modItemManager !== 'undefined') {
                modItemManager.containerElement = document.getElementById('install-mod-list');
            }
            toggleCustomLangGui();
            break;
        case 'config':
            if (typeof apiConfigManager !== 'undefined' && apiConfigManager.apiServices) {
                apiConfigManager.loadAPIServices();
            }
            break;
        case 'elder':
            if (typeof elderManager !== 'undefined') {
                elderManager.targetDiv = document.querySelector('.quetion-content');
                elderManager._setupEventDelegation();
            }
            break;
    }
}
