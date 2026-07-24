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
        console.log('[LCTA] Section loaded:', name);
        onSectionLoaded(name);
    } catch (err) {
        console.error(`Failed to load section ${name}:`, err);
    }
}

function isSectionLoaded(name) {
    return loadedSections.has(name);
}

function onSectionLoaded(name) {
    switch (name) {
        case 'settings':
            console.log('[LCTA] Init section: settings');
            toggleCachePathInput();
            toggleStoragePathInput();
            break;
        case 'translate':
            console.log('[LCTA] Init section: translate');
            toggleDevelopSettings();
            toggleAutoProper();
            if (typeof apiConfigManager !== 'undefined' && apiConfigManager.initialized) {
                apiConfigManager.loadAPIServicesTranslator();
                var tKey = null;
                try { tKey = configManager.getCachedValue('ui_default.translator.translator'); } catch (e) {}
                if (!tKey) tKey = Object.keys(apiConfigManager.apiServices)[0];
                var tBox = document.querySelector('.translator-service-select');
                if (tBox && tKey) {
                    tBox.value = tKey;
                    tBox.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                }
            }
            break;
        case 'launcher-config':
            console.log('[LCTA] Init section: launcher-config');
            toggleSteamCommand();
            if (typeof onLauncherOurplaySourceChange === 'function')
                onLauncherOurplaySourceChange();
            break;
        case 'download':
            console.log('[LCTA] Init section: download');
            if (typeof onOurplaySourceChange === 'function')
                onOurplaySourceChange();
            break;
        case 'fancy':
            console.log('[LCTA] Init section: fancy');
            if (typeof fancyManager !== 'undefined' && fancyManager) {
                fancyManager.listManager.containerElement = document.getElementById('fancy-ruleset-list');
                fancyManager.loadRulesets();
            }
            break;
        case 'install':
            console.log('[LCTA] Init section: install');
            if (typeof packageItemManager !== 'undefined') {
                packageItemManager.containerElement = document.getElementById('install-package-list');
            }
            break;
        case 'manage':
            console.log('[LCTA] Init section: manage');
            if (typeof installedPackageItemManager !== 'undefined') {
                installedPackageItemManager.containerElement = document.getElementById('installed-package-list');
            }
            if (typeof modItemManager !== 'undefined') {
                modItemManager.containerElement = document.getElementById('install-mod-list');
            }
            toggleCustomLangGui();
            break;
        case 'about':
            console.log('[LCTA] Init section: about');
            loadAndRenderMarkdown();
            break;
        case 'config':
            console.log('[LCTA] Init section: config');
            if (typeof apiConfigManager !== 'undefined' && apiConfigManager.apiServices) {
                apiConfigManager.loadAPIServices();
                var cKey = null;
                try { cKey = configManager.getCachedValue('ui_default.api_config.key'); } catch (e) {}
                if (!cKey) cKey = Object.keys(apiConfigManager.apiServices)[0];
                var cBox = document.querySelector('.api-service-select');
                if (cBox && cKey) {
                    cBox.value = cKey;
                    cBox.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                }
            }
            break;
        case 'elder':
            console.log('[LCTA] Init section: elder');
            if (typeof elderManager !== 'undefined') {
                elderManager.targetDiv = document.querySelector('.quetion-content');
                elderManager._setupEventDelegation();
            }
            break;
        case 'welcome':
            console.log('[LCTA] Init section: welcome');
            if (window._pendingWelcomeContent) {
                var pc = window._pendingWelcomeContent;
                if (pc.type === 'markdown') {
                    loadMarkdownContent(pc.url, 'welcome-content');
                } else if (pc.type === 'html') {
                    var targetDiv = document.querySelector('.welcome-content');
                    if (targetDiv) targetDiv.innerHTML = pc.html;
                }
                window._pendingWelcomeContent = null;
            }
            break;
        case 'speed':
            console.log('[LCTA] Init section: speed');
            if (typeof speedPage !== 'undefined' && speedPage) {
                speedPage._initDomRefs();
                speedPage.init();
            }
            break;
    }

    if (configManager) configManager.applyConfigToUI();
    initTooltips();
    initPasswordToggles();
}
