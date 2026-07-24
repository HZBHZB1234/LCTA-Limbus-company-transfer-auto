(function () {
    'use strict';

    const FILE_PREFIX_RULES = [
        ['BattleSpeechBubbleDlg', '战斗气泡'], ['BattleResultHint', '战斗结果提示'],
        ['BattleKeywords', '战斗关键词'], ['BattlePass', '通行证'],
        ['BattleUIText', '战斗UI'], ['BossRaidUI', '战斗映射UI'],
        ['BattleHint', '战斗提示'], ['BuffAbilities', '战斗Buff'],
        ['Bufs_Mirror', '镜牢Buff'], ['MirrorDungeon', '镜牢'],
        ['DailyLoginEvent', '签到'], ['CultivationEvent', '惜春养成'],
        ['CouponUIText', '兑换码UI'], ['ChoiceEvent', '事件选择'],
        ['DanteAbility', '但丁能力'], ['ActionEvents', '镜牢事件'],
        ['AbEventsResultLog', '事件效果'], ['AbnormalityGuides', '异想体线索/提示'],
        ['AttributeText', '七大罪'], ['AbEvents', '异想体事件'],
        ['AbDlg', '事件判定'], ['Announcer', '播报相关内容'],
        ['Assist', '援助相关'], ['ErrorCodeMsg', '错误代码'],
        ['UnitKeyword', '关键词'], ['Personalities', '人格'],
        ['Characters', '角色'], ['EGOgift', 'EGO饰品'],
        ['Dungeon', '地牢'], ['Enemies', '敌人'],
        ['PanicInfo', '效果'], ['Passives', '被动'],
        ['Railway', '轨道线'], ['Egos', '角色EGO'],
        ['Skill', '技能'], ['Stage', '舞台'],
        ['Story', '故事'], ['Event', '活动'], ['Bufs', '通用Buff'],
    ];
    const CATEGORY_ORDER = FILE_PREFIX_RULES.map(function (r) { return r[1]; }).concat(['Other']);

    const state = {
        langFiles: [],
        currentFile: null,
        currentFileRaw: null,
        currentFileParsed: null,
        currentFileCategory: null,
        currentFilePrefix: null,
        currentRuleset: null,
        rulesetList: [],
        mode: 'simple',
        activeTab: 'file-list',
        searchResults: null,
        searchTotal: 0,
        fileCache: new Map(),
        advancedContentView: null,
        selectedFieldPath: null,
        selectedItemId: null
    };

    function $i(id) { return document.getElementById(id); }

    function getApi() {
        return (typeof window !== 'undefined' && window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
    }

    function warnNoApi() {
        console.warn('[rule-editor] pywebview.api 不可用（开发模式或后端未就绪）');
        return false;
    }

    function classifyPath(relativePath) {
        for (let i = 0; i < FILE_PREFIX_RULES.length; i++) {
            const prefix = FILE_PREFIX_RULES[i][0];
            const category = FILE_PREFIX_RULES[i][1];
            if (relativePath.startsWith(prefix) || relativePath.indexOf(prefix) !== -1) {
                return { prefix: prefix, category: category };
            }
        }
        return { prefix: null, category: 'Other' };
    }

    function groupFilesByCategory(files) {
        const groups = {};
        for (let i = 0; i < files.length; i++) {
            const f = files[i];
            const info = classifyPath(f);
            if (!groups[info.category]) groups[info.category] = [];
            groups[info.category].push(f);
        }
        return groups;
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function escapeAttr(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    /** init — bind events, prime UI, then load data once pywebview is ready. */
    function init() {
        bindEvents();
        populateSimpleFileSelect();
        switchTab('file-list');
        if (getApi()) {
            onApiReady();
        } else {
            window.addEventListener('pywebviewready', onApiReady);
        }
    }

    async function onApiReady() {
        setMode('simple', true);
        await Promise.all([loadLangFiles(), loadRulesets()]);
    }

    async function loadLangFiles() {
        const api = getApi();
        if (!api) return warnNoApi();
        try {
            const files = await api.get_lang_files();
            state.langFiles = Array.isArray(files) ? files : [];
        } catch (e) {
            console.error('[rule-editor] loadLangFiles failed:', e);
            state.langFiles = [];
        }
        renderFileList();
    }

    async function loadRulesets() {
        const api = getApi();
        if (!api) return warnNoApi();
        try {
            const list = await api.get_ruleset_list();
            state.rulesetList = Array.isArray(list) ? list : [];
        } catch (e) {
            console.error('[rule-editor] loadRulesets failed:', e);
            state.rulesetList = [];
        }
        renderRulesetSelect();
    }

    async function loadRulesetByName(name) {
        const api = getApi();
        if (!api || !name) return;
        try {
            const rs = await api.get_ruleset(name);
            if (rs && rs.error) {
                console.warn('[rule-editor] load ruleset error:', rs.error);
                state.currentRuleset = null;
            } else {
                state.currentRuleset = rs;
            }
        } catch (e) {
            console.error('[rule-editor] loadRulesetByName failed:', e);
            state.currentRuleset = null;
        }
        renderRulesPreview();
    }

    async function openFile(relativePath) {
        if (!relativePath) return;
        const api = getApi();
        if (!api) return warnNoApi();
        if (state.fileCache.has(relativePath)) {
            const cached = state.fileCache.get(relativePath);
            applyFileContent(relativePath, cached.raw, cached.parsed, cached.category);
            return;
        }
        try {
            const res = await api.get_file_content(relativePath);
            if (res && res.error) {
                console.warn('[rule-editor] openFile error:', res.error);
                $i('re-current-file').textContent = relativePath;
                $i('re-content-simple').innerHTML = '<div class="re-empty-state">⚠️ ' + escapeHtml(res.error) + '</div>';
                return;
            }
            const raw = res ? res.raw : null;
            const parsed = res ? res.parsed : null;
            const category = (res && res.file_classification) || classifyPath(relativePath).category;
            state.fileCache.set(relativePath, { raw: raw, parsed: parsed, category: category });
            applyFileContent(relativePath, raw, parsed, category);
        } catch (e) {
            console.error('[rule-editor] openFile failed:', e);
        }
    }

    function applyFileContent(relativePath, raw, parsed, category) {
        state.currentFile = relativePath;
        state.currentFileRaw = raw;
        state.currentFileParsed = parsed;
        state.currentFileCategory = category;
        state.currentFilePrefix = classifyPath(relativePath).prefix;
        const cur = $i('re-current-file');
        if (cur) cur.textContent = relativePath || '未选择文件';
        const fileSel = $i('re-simple-file');
        if (fileSel && state.currentFilePrefix) fileSel.value = state.currentFilePrefix;
        refreshContentPanel();
    }

    function renderFileList() {
        const container = $i('re-file-list-container');
        if (!container) return;
        if (!state.langFiles.length) {
            container.innerHTML = '<div class="re-empty-state">未找到 Lang 文件，请先在主应用配置游戏路径。</div>';
            return;
        }
        const groups = groupFilesByCategory(state.langFiles);
        let html = '';
        for (let ci = 0; ci < CATEGORY_ORDER.length; ci++) {
            const category = CATEGORY_ORDER[ci];
            const files = groups[category];
            if (!files || !files.length) continue;
            html += '<div class="re-file-group"><div class="re-file-group-title">' + escapeHtml(category) +
                ' <span class="re-file-group-count">(' + files.length + ')</span></div>';
            for (let fi = 0; fi < files.length; fi++) {
                const f = files[fi];
                html += '<div class="re-file-item" data-path="' + escapeAttr(f) +
                    '" title="双击打开: ' + escapeAttr(f) + '">' + escapeHtml(f) + '</div>';
            }
            html += '</div>';
        }
        container.innerHTML = html;
        const items = container.querySelectorAll('.re-file-item');
        for (let i = 0; i < items.length; i++) {
            items[i].addEventListener('dblclick', (function (el) {
                return function () { openFile(el.dataset.path); };
            })(items[i]));
        }
    }

    function populateSimpleFileSelect() {
        const sel = $i('re-simple-file');
        if (!sel) return;
        let opts = ['<option value="">-- 选择文件分类 --</option>'];
        for (let i = 0; i < FILE_PREFIX_RULES.length; i++) {
            opts.push('<option value="' + escapeAttr(FILE_PREFIX_RULES[i][0]) + '">' +
                escapeHtml(FILE_PREFIX_RULES[i][1]) + '</option>');
        }
        sel.innerHTML = opts.join('');
    }

    function refreshContentPanel() {
        if (state.mode === 'simple') renderSimpleContent();
        else renderAdvancedContent();
    }

    /** renderSimpleContent — parse cached JSON into structured data cards for the bottom panel. */
    function renderSimpleContent() {
        const container = $i('re-content-simple');
        if (!container) return;
        if (!state.currentFile) {
            container.innerHTML = '<div class="re-empty-state">双击左侧文件以查看内容</div>';
            return;
        }
        const parsed = state.currentFileParsed;
        if (parsed == null) {
            container.innerHTML = '<div class="re-empty-state">⚠️ 文件格式异常（无法解析为 JSON）</div>';
            return;
        }
        let entries = [];
        if (Array.isArray(parsed.dataList)) {
            entries = parsed.dataList.map(function (item, idx) { return { item: item, idx: idx }; });
        } else if (Array.isArray(parsed)) {
            entries = parsed.map(function (item, idx) { return { item: item, idx: idx }; });
        } else if (parsed && typeof parsed === 'object') {
            entries = [{ item: parsed, idx: 0 }];
        }
        if (!entries.length) {
            container.innerHTML = '<div class="re-empty-state">无 dataList 条目</div>';
            return;
        }
        let html = '<div class="re-data-cards">';
        for (let i = 0; i < entries.length; i++) {
            html += renderDataCard(entries[i].item, entries[i].idx);
        }
        html += '</div>';
        container.innerHTML = html;
    }

    function renderDataCard(item, idx) {
        if (item == null || typeof item !== 'object') {
            return '<div class="re-data-card"><div class="re-card-header">[' + idx + '] ' +
                escapeHtml(String(item)) + '</div></div>';
        }
        const id = (item.id != null) ? String(item.id) : '';
        const name = (item.name != null) ? String(item.name) : '';
        let html = '<div class="re-data-card" data-card-idx="' + idx + '">';
        html += '<div class="re-card-header"><span class="re-card-id">🎯 id:' + escapeHtml(id) +
            '</span> <span class="re-card-name">' + escapeHtml(name) + '</span></div>';
        html += '<div class="re-card-body">';
        const keys = Object.keys(item);
        for (let k = 0; k < keys.length; k++) {
            if (keys[k] === 'id' || keys[k] === 'name') continue;
            html += renderFieldLine(keys[k], item[keys[k]], id);
        }
        html += '</div>';
        html += '<div class="re-card-footer"><button class="re-btn re-btn-sm re-add-item-btn" data-item-id="' +
            escapeAttr(id) + '">＋ 将此条目加入规则</button></div>';
        html += '</div>';
        return html;
    }

    function renderFieldLine(key, value, itemId) {
        const isComplex = (typeof value === 'object' && value !== null);
        let valueHtml;
        let nestedHtml = '';
        if (isComplex) {
            const isArr = Array.isArray(value);
            const count = isArr ? value.length : Object.keys(value).length;
            valueHtml = '<span class="re-field-value-muted">' + (isArr ? '[' + count + ']' : '{…}') + '</span>';
            nestedHtml = '<div class="re-nested-toggle">▸ 展开查看</div><pre class="re-nested-list" style="display:none;">' +
                escapeHtml(JSON.stringify(value, null, 2)) + '</pre>';
        } else {
            valueHtml = '<span class="re-field-value">' + escapeHtml(value == null ? '' : String(value)) + '</span>';
        }
        const sel = '<button class="re-btn re-btn-sm re-select-field-btn" data-field="' + escapeAttr(key) +
            '" data-item-id="' + escapeAttr(itemId) + '">选中此字段</button>';
        return '<div class="re-field-line" data-field="' + escapeAttr(key) + '" data-item-id="' + escapeAttr(itemId) +
            '"><div class="re-field-row"><span class="re-field-name">' + escapeHtml(key) + ':</span> ' +
            valueHtml + ' ' + sel + '</div>' + nestedHtml + '</div>';
    }

    /** renderAdvancedContent — show raw JSON in a read-only CodeMirror 6 viewer. */
    function renderAdvancedContent() {
        const container = $i('re-content-advanced');
        if (!container) return;
        if (!state.currentFile) {
            if (state.advancedContentView) {
                state.advancedContentView.destroy();
                state.advancedContentView = null;
            }
            container.innerHTML = '<div class="re-empty-state">双击左侧文件以查看内容</div>';
            return;
        }
        const view = ensureAdvancedContentViewer();
        if (view) {
            const doc = state.currentFileRaw || '';
            view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: doc } });
        } else {
            container.textContent = state.currentFileRaw || '';
        }
    }

    function ensureAdvancedContentViewer() {
        if (state.advancedContentView) return state.advancedContentView;
        const container = $i('re-content-advanced');
        if (!container) return null;
        if (!window.CodeMirror) {
            console.warn('[rule-editor] CodeMirror not loaded; falling back to plain text');
            return null;
        }
        const CM = window.CodeMirror;
        const EditorView = CM.EditorView;
        if (!EditorView) return null;
        state.advancedContentView = new EditorView({
            doc: '',
            extensions: [CM.basicSetup, CM.json(), EditorView.editable.of(false)],
            parent: container
        });
        return state.advancedContentView;
    }

    function renderRulesetSelect() {
        const sel = $i('re-ruleset-select');
        if (!sel) return;
        let opts = ['<option value="">-- 选择规则集 --</option>'];
        for (let i = 0; i < state.rulesetList.length; i++) {
            const rs = state.rulesetList[i];
            const nm = rs.name || '';
            const count = (rs.rule_count != null) ? rs.rule_count : 0;
            opts.push('<option value="' + escapeAttr(nm) + '">' + escapeHtml(nm) + ' (' + count + ')</option>');
        }
        sel.innerHTML = opts.join('');
    }

    function renderRulesPreview() {
        const container = $i('re-rules-preview-list');
        if (!container) return;
        if (!state.currentRuleset || !Array.isArray(state.currentRuleset.rules) || !state.currentRuleset.rules.length) {
            container.innerHTML = '<div class="re-empty-state">暂无规则</div>';
            return;
        }
        const rules = state.currentRuleset.rules;
        let html = '';
        for (let i = 0; i < rules.length; i++) {
            const rule = rules[i];
            const aimFile = rule.aimFile || '?';
            const actionCount = Array.isArray(rule.action) ? rule.action.length : 0;
            let conds = rule.conditions;
            if (!conds && (rule.trigger || rule.aim)) conds = [rule];
            const targetField = (conds && conds[0]) ? (conds[0].aim || '?') : '?';
            html += '<div class="re-rule-summary">#' + (i + 1) + ' ' + escapeHtml(aimFile) + ' → ' +
                escapeHtml(targetField) + ' [' + actionCount + ' ops]</div>';
        }
        container.innerHTML = html;
    }

    async function performSearch() {
        const api = getApi();
        const input = $i('re-file-search');
        const keyword = input ? input.value : '';
        const cb = $i('re-case-sensitive');
        const caseSensitive = !!(cb && cb.checked);
        if (!api) return warnNoApi();
        if (!keyword.trim()) { clearSearch(); return; }
        try {
            const res = await api.search_files(keyword, caseSensitive);
            if (res && res.results_by_category) {
                state.searchResults = res.results_by_category;
                state.searchTotal = res.total_matches || 0;
            } else {
                state.searchResults = {};
                state.searchTotal = 0;
            }
        } catch (e) {
            console.error('[rule-editor] performSearch failed:', e);
            state.searchResults = {};
            state.searchTotal = 0;
        }
        renderSearchCategories();
        switchTab('search-results');
    }

    function renderSearchCategories() {
        const container = $i('re-search-results-container');
        if (!container) return;
        if (!state.searchResults) {
            container.innerHTML = '<div class="re-empty-state">输入关键词后点击搜索</div>';
            return;
        }
        const entries = Object.keys(state.searchResults);
        let any = false;
        for (let i = 0; i < entries.length; i++) {
            if (state.searchResults[entries[i]] && state.searchResults[entries[i]].length) { any = true; break; }
        }
        if (!any) {
            container.innerHTML = '<div class="re-empty-state">未找到匹配（共 0 处）</div>';
            return;
        }
        let html = '<div class="re-search-summary">共 ' + state.searchTotal + ' 处匹配</div>';
        for (let ci = 0; ci < CATEGORY_ORDER.length; ci++) {
            const category = CATEGORY_ORDER[ci];
            const list = state.searchResults[category];
            if (!list || !list.length) continue;
            html += '<div class="re-file-group"><div class="re-file-group-title">' + escapeHtml(category) + '</div>';
            for (let li = 0; li < list.length; li++) {
                const entry = list[li];
                const path = Array.isArray(entry) ? entry[0] : (entry.file || entry.path || '');
                const count = Array.isArray(entry) ? entry[1] : (entry.matches || 0);
                html += '<div class="re-file-item re-search-item" data-path="' + escapeAttr(path) +
                    '" title="双击打开"><span>' + escapeHtml(path) + '</span> <span class="re-match-count">' +
                    count + ' 处</span></div>';
            }
            html += '</div>';
        }
        container.innerHTML = html;
        const items = container.querySelectorAll('.re-search-item');
        for (let i = 0; i < items.length; i++) {
            items[i].addEventListener('dblclick', (function (el) {
                return function () { openFile(el.dataset.path); };
            })(items[i]));
        }
    }

    function clearSearch() {
        state.searchResults = null;
        state.searchTotal = 0;
        const input = $i('re-file-search');
        if (input) input.value = '';
        renderSearchCategories();
        switchTab('file-list');
    }

    function switchTab(tab) {
        state.activeTab = tab;
        const tabs = document.querySelectorAll('.re-tab');
        for (let i = 0; i < tabs.length; i++) {
            tabs[i].classList.toggle('active', tabs[i].dataset.tab === tab);
        }
        const fileListC = $i('re-file-list-container');
        const searchC = $i('re-search-results-container');
        if (fileListC) fileListC.style.display = tab === 'file-list' ? '' : 'none';
        if (searchC) searchC.style.display = tab === 'search-results' ? '' : 'none';
    }

    function setMode(mode, skipContentRefresh) {
        state.mode = mode;
        const btns = document.querySelectorAll('.re-mode-btn');
        for (let i = 0; i < btns.length; i++) {
            btns[i].classList.toggle('active', btns[i].dataset.mode === mode);
        }
        const simpleMain = $i('re-simple-mode');
        const advMain = $i('re-advanced-mode');
        if (simpleMain) simpleMain.style.display = mode === 'simple' ? '' : 'none';
        if (advMain) advMain.style.display = mode === 'advanced' ? '' : 'none';
        const simpleContent = $i('re-content-simple');
        const advContent = $i('re-content-advanced');
        if (simpleContent) simpleContent.style.display = mode === 'simple' ? '' : 'none';
        if (advContent) advContent.style.display = mode === 'advanced' ? '' : 'none';
        if (!skipContentRefresh) refreshContentPanel();
    }

    function bindEvents() {
        const searchBtn = $i('re-search-btn');
        if (searchBtn) searchBtn.addEventListener('click', performSearch);
        const searchClear = $i('re-search-clear-btn');
        if (searchClear) searchClear.addEventListener('click', clearSearch);
        const searchInput = $i('re-file-search');
        if (searchInput) searchInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') performSearch();
        });

        const tabs = document.querySelectorAll('.re-tab');
        for (let i = 0; i < tabs.length; i++) {
            tabs[i].addEventListener('click', (function (el) {
                return function () { switchTab(el.dataset.tab); };
            })(tabs[i]));
        }

        const rsSelect = $i('re-ruleset-select');
        if (rsSelect) rsSelect.addEventListener('change', onRulesetSelectChange);
        const newBtn = $i('re-new-ruleset-btn');
        if (newBtn) newBtn.addEventListener('click', onNewRuleset);
        const saveBtn = $i('re-save-ruleset-btn');
        if (saveBtn) saveBtn.addEventListener('click', onSaveRuleset);
        const delBtn = $i('re-delete-ruleset-btn');
        if (delBtn) delBtn.addEventListener('click', onDeleteRuleset);

        const modeBtns = document.querySelectorAll('.re-mode-btn');
        for (let i = 0; i < modeBtns.length; i++) {
            modeBtns[i].addEventListener('click', (function (el) {
                return function () { setMode(el.dataset.mode); };
            })(modeBtns[i]));
        }

        const addCond = $i('re-add-condition-btn');
        if (addCond) addCond.addEventListener('click', stubTask6('add condition'));
        const addOp = $i('re-add-op-btn');
        if (addOp) addOp.addEventListener('click', stubTask6('add operation'));
        const previewBtn = $i('re-preview-rule-btn');
        if (previewBtn) previewBtn.addEventListener('click', stubTask6('preview rule'));
        const genBtn = $i('re-generate-rule-btn');
        if (genBtn) genBtn.addEventListener('click', stubTask6('generate rule'));
        const applyBtn = $i('re-apply-btn');
        if (applyBtn) applyBtn.addEventListener('click', stubTask6('apply ruleset'));
        const smartBtn = $i('re-smart-gen-btn');
        if (smartBtn) smartBtn.addEventListener('click', stubTask6('smart generate'));

        const simpleContent = $i('re-content-simple');
        if (simpleContent) simpleContent.addEventListener('click', onContentPanelClick);
    }

    function stubTask6(label) {
        return function () { console.log('[rule-editor] ' + label + ' — Task 6 wires this'); };
    }

    function onContentPanelClick(e) {
        const selectBtn = e.target.closest('.re-select-field-btn');
        if (selectBtn) {
            selectField(selectBtn.dataset.field, selectBtn.dataset.itemId);
            return;
        }
        const addBtn = e.target.closest('.re-add-item-btn');
        if (addBtn) {
            addItemToRule(addBtn.dataset.itemId);
            return;
        }
        const toggle = e.target.closest('.re-nested-toggle');
        if (toggle) {
            const nested = toggle.nextElementSibling;
            if (nested) nested.style.display = nested.style.display === 'none' ? '' : 'none';
        }
    }

    async function onRulesetSelectChange() {
        const sel = $i('re-ruleset-select');
        if (!sel) return;
        const name = sel.value;
        if (!name) {
            state.currentRuleset = null;
            renderRulesPreview();
            return;
        }
        await loadRulesetByName(name);
    }

    async function onNewRuleset() {
        const api = getApi();
        if (!api) return warnNoApi();
        const name = window.prompt('请输入新规则集名称：');
        if (!name || !name.trim()) return;
        const trimmed = name.trim();
        try {
            const res = await api.create_ruleset(trimmed);
            if (res && res.success === false) {
                console.warn('[rule-editor] create_ruleset failed:', res.error);
                return;
            }
        } catch (e) {
            console.error('[rule-editor] create_ruleset error:', e);
            return;
        }
        await loadRulesets();
        const sel = $i('re-ruleset-select');
        if (sel) sel.value = trimmed;
        await loadRulesetByName(trimmed);
    }

    function onSaveRuleset() {
        console.log('[rule-editor] save ruleset — Task 6 wires form-aware save');
    }

    function onDeleteRuleset() {
        console.log('[rule-editor] delete ruleset — Task 6 wires confirm + delete');
    }

    /** selectField — store user's field selection into state and fill the simple-mode form targeting inputs. */
    function selectField(field, itemId) {
        state.selectedFieldPath = field;
        state.selectedItemId = itemId;
        const idEl = $i('re-simple-item-id');
        if (idEl) idEl.value = itemId != null ? String(itemId) : '';
        const fieldEl = $i('re-simple-field');
        if (fieldEl) fieldEl.value = field || '';
        const useId = $i('re-simple-use-id');
        if (useId && itemId != null && String(itemId) !== '') useId.checked = true;
        highlightSelectedField(field, itemId);
    }

    /** addItemToRule — fill file matching + id + default field so Task 6 form logic can read them. */
    function addItemToRule(itemId) {
        if (state.currentFilePrefix) {
            const fileSel = $i('re-simple-file');
            if (fileSel) fileSel.value = state.currentFilePrefix;
        }
        const field = state.selectedFieldPath || 'desc';
        selectField(field, itemId);
    }

    function highlightSelectedField(field, itemId) {
        const container = $i('re-content-simple');
        if (!container) return;
        const prev = container.querySelectorAll('.re-field-line.is-selected');
        for (let i = 0; i < prev.length; i++) prev[i].classList.remove('is-selected');
        const btns = container.querySelectorAll('.re-select-field-btn');
        const targetId = itemId != null ? String(itemId) : '';
        for (let i = 0; i < btns.length; i++) {
            if (btns[i].dataset.field === field && btns[i].dataset.itemId === targetId) {
                const line = btns[i].closest('.re-field-line');
                if (line) line.classList.add('is-selected');
            }
        }
    }

    document.addEventListener('DOMContentLoaded', init);
})();