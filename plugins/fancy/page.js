/**
 * fancy/page.js —— 文本美化插件页面逻辑
 */

(function () {
    let rulesets = [];
    let selectedIndex = -1;

    pagesManager.registerSwitchHook('fancy', {
        onActivate() { loadRulesets(); }
    });

    async function loadRulesets() {
        const el = document.getElementById('fancy-ruleset-list');
        if (!el) return;
        el.innerHTML = '<div class="list-empty"><i class="fas fa-spinner fa-spin"></i><p>加载中...</p></div>';
        try {
            const result = await window.pywebview.api.get_fancy_rulesets();
            if (result && result.rulesets) {
                rulesets = result.rulesets;
                renderRulesetList();
            }
        } catch (e) { el.innerHTML = `<div class="list-empty"><p>加载失败: ${e.message}</p></div>`; }
    }

    function renderRulesetList() {
        const el = document.getElementById('fancy-ruleset-list');
        if (!el) return;
        if (!rulesets.length) { el.innerHTML = '<div class="list-empty"><i class="fas fa-box-open"></i><p>无规则集</p></div>'; return; }
        el.innerHTML = rulesets.map((r, i) => `<div class="list-item ${i === selectedIndex ? 'selected' : ''}" data-index="${i}">
            <span>${r.name || '未命名'}</span>
            <span><input type="checkbox" ${r.enabled ? 'checked' : ''} onchange="toggleRuleset(${i}, this.checked)" ${r.builtin ? 'disabled' : ''}></span>
            <button class="action-btn small" onclick="selectRuleset(${i})">编辑</button>
        </div>`).join('');
    }

    window.selectRuleset = function (i) {
        selectedIndex = i;
        renderRulesetList();
        const r = rulesets[i];
        document.getElementById('fancy-ruleset-name').value = r.name || '';
        document.getElementById('fancy-ruleset-name').disabled = r.builtin || false;
        document.getElementById('fancy-ruleset-desc').value = r.description || '';
        document.getElementById('fancy-ruleset-desc').disabled = r.builtin || false;
        document.getElementById('fancy-ruleset-rules').value = JSON.stringify(r.rules || [], null, 2);
        document.getElementById('fancy-ruleset-rules').disabled = r.builtin || false;
        document.getElementById('fancy-save-current-btn').disabled = r.builtin || false;
    };

    window.toggleRuleset = function (i, enabled) {
        rulesets[i].enabled = enabled;
    };

    window.newRuleset = function () {
        rulesets.push({ name: '新规则集', description: '', rules: [], enabled: true, builtin: false });
        selectedIndex = rulesets.length - 1;
        renderRulesetList();
        window.selectRuleset(selectedIndex);
    };

    window.saveCurrentRuleset = function () {
        if (selectedIndex < 0 || selectedIndex >= rulesets.length) return;
        rulesets[selectedIndex].name = document.getElementById('fancy-ruleset-name').value;
        rulesets[selectedIndex].description = document.getElementById('fancy-ruleset-desc').value;
        try { rulesets[selectedIndex].rules = JSON.parse(document.getElementById('fancy-ruleset-rules').value); }
        catch (e) { showMessage('错误', 'JSON 格式错误: ' + e.message); return; }
        renderRulesetList();
    };

    window.saveAllRulesets = async function () {
        try {
            await window.pywebview.api.save_fancy_rulesets(rulesets);
            showMessage('成功', '规则集已保存');
        } catch (e) { showMessage('错误', e.message); }
    };

    window.deleteSelectedRuleset = function () {
        if (selectedIndex < 0) { showMessage('提示', '请先选择规则集'); return; }
        if (rulesets[selectedIndex].builtin) { showMessage('提示', '不能删除内置规则集'); return; }
        showConfirm('确认删除', `确定要删除 "${rulesets[selectedIndex].name}" 吗？`, () => {
            rulesets.splice(selectedIndex, 1);
            selectedIndex = -1;
            renderRulesetList();
            document.getElementById('fancy-ruleset-name').value = '';
            document.getElementById('fancy-ruleset-desc').value = '';
            document.getElementById('fancy-ruleset-rules').value = '';
            document.getElementById('fancy-save-current-btn').disabled = true;
        });
    };

    window.formatRulesetJson = function () {
        const ta = document.getElementById('fancy-ruleset-rules');
        try { ta.value = JSON.stringify(JSON.parse(ta.value), null, 2); }
        catch (e) { showMessage('错误', 'JSON 格式错误'); }
    };

    window.applyFancy = async function () {
        const modal = new ProgressModal('应用美化');
        modal.addLog('正在应用美化规则...');
        try {
            const result = await window.pywebview.api.apply_fancy(modal.id);
            modal.complete(result.success, result.message);
        } catch (e) { modal.complete(false, e.message); }
    };
})();
