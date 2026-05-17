/**
 * elder/page.js —— 老年人模式插件页面逻辑
 */

(function () {
    pagesManager.registerSwitchHook('elder', {
        onActivate() {
            configManager.applyConfigToPage();
            loadElderContent();
        }
    });

    async function loadElderContent() {
        try {
            const el = document.querySelector('.quetion-content');
            if (el) {
                const content = await loadMarkdownContent('webui/assets/elder.md');
                el.innerHTML = content;
            }
        } catch (e) { /* ignore */ }
        try {
            const result = await window.pywebview.api.get_elder_list();
            if (result && result.elderList) {
                renderElderQuestions(result.elderList);
            }
        } catch (e) { /* ignore */ }
    }

    function renderElderQuestions(list) {
        const container = document.getElementById('elder-container');
        if (!container) return;
        // render wizard questions dynamically
        container.innerHTML = '';
    }
})();
