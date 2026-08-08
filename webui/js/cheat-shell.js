// ============================
// 作弊工具箱密钥门壳（公共仓库 · 通用插件宿主壳）
// ============================
// 工具箱功能实现（HTML/JS/管理器/DLL）位于私有仓库，构建期加密为 cheat_core.bin
// 分发。解锁后私有仓库的 cheatcore 包经注册表自动注册为插件，本壳负责：
//   - 未解锁：显示密钥输入门（webui/sections/cheat.html 内的密钥门）
//   - 已解锁：经 cheat_plugins_list 遍历插件，拉取各插件解密后的 HTML/JS 注入页面，
//     然后调用插件 JS 导出的 initCheatPage() 实例化工具箱页
//   - Launcher 配置页：按插件注册表的 launcher 元数据动态渲染集成开关
// 本壳不感知任何具体工具（工具名/API/配置键全部来自插件注册表）。

let cheatPage = {
    _real: null,
    _loading: null,
    _gateHtml: null,
    _gateBound: false,

    init() {
        if (this._real) {
            this._real.init();
            return;
        }
        if (this._loading) return this._loading;
        this._loading = this._doInit().finally(() => { this._loading = null; });
        return this._loading;
    },

    stop() {
        if (this._real && typeof this._real.stop === 'function') {
            this._real.stop();
        }
    },

    async _doInit() {
        // 首次进入时缓存密钥门 HTML（用于锁定后恢复）
        if (this._gateHtml === null) {
            const sectionEl = document.getElementById('cheat-section');
            if (sectionEl) this._gateHtml = sectionEl.innerHTML;
        }
        // 风险服务门控：与 speed/input-bypass 一致。未同意时显示风险须知覆盖层并
        // 隐藏内容区（#cheat-main-content 默认 display:none），同意后由 onAccepted
        // 恢复可见；覆盖层缺失时兜底直接显示，避免整页空白。
        if (typeof RiskGate !== 'undefined' && RiskGate.gatePage
                && document.querySelector('[data-risk-overlay="cheat"]')) {
            await RiskGate.gatePage('cheat', {
                onAccepted: () => this._showMainContent(),
                onRejected: () => this._hideMainContent(),
            });
        } else {
            this._showMainContent();
        }
        try {
            const st = await pywebview.api.cheat_core_status();
            if (st && st.success && st.data && st.data.unlocked) {
                await this._loadFullUI();
            } else {
                const reason = st && st.data ? st.data.reason : 'unknown';
                this._showGate(reason);
            }
        } catch (e) {
            console.error('cheat shell init error:', e);
            this._showGate('error');
        }
    },

    async _loadFullUI() {
        try {
            const pluginsRes = await pywebview.api.cheat_plugins_list();
            const plugins = (pluginsRes && pluginsRes.success && pluginsRes.data) ? pluginsRes.data : [];
            if (!plugins.length) throw new Error('no registered plugins');

            const sectionEl = document.getElementById('cheat-section');
            if (!sectionEl) throw new Error('section container missing');

            // 依次注入各插件的 section HTML
            let html = '';
            for (const p of plugins) {
                if (!p.webui || !p.webui.section) continue;
                const sectionHtml = await pywebview.api.cheat_core_get_section_html(p.webui.section);
                if (typeof sectionHtml === 'string' && sectionHtml.trim()) html += sectionHtml;
            }
            sectionEl.innerHTML = html;

            // 完整功能 UI 是动态注入的，onSectionLoaded 的配置回填/工具提示绑定
            // 不会自动执行，需在此补做（否则输入框显示默认值而非已保存配置）
            if (typeof configManager !== 'undefined' && configManager.applyConfigToUI) {
                configManager.applyConfigToUI();
            }
            if (typeof initTooltips === 'function') {
                initTooltips();
            }

            // 注入各插件 JS 并调用其入口（插件 js 约定挂载 window.initCheatPage）
            for (const p of plugins) {
                if (!p.webui || !p.webui.js) continue;
                const scriptJs = await pywebview.api.cheat_core_get_script_js(p.webui.js);
                if (typeof scriptJs !== 'string' || !scriptJs.trim()) continue;
                // 解密 JS 来自自有加密包，与打包源码同信任级，可用 new Function 执行
                (new Function(scriptJs))(); // eslint-disable-line no-new-func
                if (typeof window.initCheatPage === 'function') {
                    window.initCheatPage();
                }
            }
            this._real = window.cheatPage || null;
            if (this._real && typeof this._real.init === 'function') {
                this._real.init();
            }
        } catch (e) {
            console.error('cheat UI load error:', e);
            this._real = null;
            window.cheatPage = null;
            this._showGate('error');
        }
    },

    _showGate(reason) {
        // 密钥门/缺失卡片都在 #cheat-main-content 内（默认 display:none），必须先
        // 让父容器可见；风险覆盖层激活时保持内容隐藏（同意前只见风险须知）。
        const overlay = document.querySelector('[data-risk-overlay="cheat"]');
        const overlayActive = overlay && overlay.style.display !== 'none';
        if (!overlayActive) this._showMainContent();
        const keygate = document.getElementById('cheat-core-keygate');
        const missing = document.getElementById('cheat-core-missing');
        const msg = document.getElementById('cheat-core-keygate-msg');
        if (reason === 'blob_missing') {
            if (keygate) keygate.style.display = 'none';
            if (missing) missing.style.display = '';
            return;
        }
        if (keygate) keygate.style.display = '';
        if (missing) missing.style.display = 'none';
        if (msg) {
            if (reason === 'invalid_key') {
                msg.textContent = '密钥错误，请重试';
                msg.style.color = 'var(--danger-color, #e74c3c)';
            } else {
                msg.textContent = '';
                msg.style.color = '';
            }
        }
        this._bindGateEvents();
    },

    _showMainContent() {
        const main = document.getElementById('cheat-main-content');
        if (main) main.style.display = '';
    },

    _hideMainContent() {
        const main = document.getElementById('cheat-main-content');
        if (main) main.style.display = 'none';
    },

    _bindGateEvents() {
        if (this._gateBound) return;
        this._gateBound = true;
        const btn = document.getElementById('cheat-core-unlock-btn');
        const input = document.getElementById('cheat-core-key-input');
        const msg = document.getElementById('cheat-core-keygate-msg');
        const doUnlock = async () => {
            const key = input ? input.value.trim() : '';
            if (!key) {
                if (input) input.focus();
                return;
            }
            if (msg) {
                msg.textContent = '正在解锁...';
                msg.style.color = '';
            }
            try {
                const res = await pywebview.api.cheat_core_unlock(key);
                if (res && res.success) {
                    if (input) input.value = '';
                    await this._loadFullUI();
                } else {
                    this._showGate('invalid_key');
                }
            } catch (e) {
                console.error('cheat unlock error:', e);
                if (msg) {
                    msg.textContent = '解锁失败: ' + e;
                    msg.style.color = 'var(--danger-color, #e74c3c)';
                }
            }
        };
        if (btn) btn.addEventListener('click', doUnlock);
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') doUnlock();
            });
        }
    },

    _esc(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    },

    // Launcher 配置页：按插件注册表的 launcher 元数据动态渲染集成开关
    async renderLauncherPlugins() {
        const container = document.getElementById('cheat-plugin-launcher');
        if (!container) return;
        try {
            const res = await pywebview.api.cheat_plugins_list();
            const plugins = (res && res.success && res.data) ? res.data : [];
            container.innerHTML = '';
            let renderedAny = false;
            for (const p of plugins) {
                const lc = p.launcher;
                if (!lc || !lc.enabled_key) continue;
                renderedAny = true;
                const spec = (p.config || {})[lc.enabled_key] || {};
                const id = lc.checkbox_id || ('launcher-work-' + p.id);
                const consent = lc.consent || 'cheat';
                let checked = false;
                try {
                    checked = !!(await pywebview.api.get_config_value(lc.enabled_key, false));
                } catch (e) { /* ignore */ }

                const group = document.createElement('div');
                group.className = 'form-group';
                const label = document.createElement('label');
                label.className = 'checkbox-container';
                label.innerHTML = `<input type="checkbox" id="${id}" data-plugin-enabled-key="${lc.enabled_key}">
                    <span class="checkmark"></span> ${this._esc(spec.label || p.name)}`;
                group.appendChild(label);
                if (spec.hint) {
                    const hint = document.createElement('small');
                    hint.className = 'form-hint';
                    hint.textContent = spec.hint;
                    group.appendChild(hint);
                }
                container.appendChild(group);

                const checkbox = group.querySelector('input[type=checkbox]');
                checkbox.checked = checked;
                checkbox.addEventListener('change', async () => {
                    const want = checkbox.checked;
                    if (want) {
                        const accepted = await RiskGate.getConsent(consent);
                        if (!accepted) {
                            checkbox.checked = false;
                            RiskGate.showConsentModal(consent, async () => {
                                checkbox.checked = true;
                                try {
                                    await configManager.updateConfigValues({ [lc.enabled_key]: true });
                                } catch (e) { console.error('launcher plugin toggle error:', e); }
                            });
                            return;
                        }
                    }
                    try {
                        await configManager.updateConfigValues({ [lc.enabled_key]: want });
                    } catch (e) {
                        console.error('launcher plugin toggle error:', e);
                    }
                });
            }
            if (!renderedAny) {
                container.innerHTML = '<p class="form-hint">当前没有可集成到 Launcher 的功能。</p>';
            }
            if (renderedAny && typeof RiskGate !== 'undefined' && RiskGate.refreshLauncherVisibility) {
                RiskGate.refreshLauncherVisibility();
            }
        } catch (e) {
            console.error('renderLauncherPlugins error:', e);
        }
    },
};

// 解密功能页「锁定」按钮入口：清除密钥并恢复密钥门 UI
window.cheatCoreLockAndReload = async function () {
    try {
        await pywebview.api.cheat_core_lock();
    } catch (e) {
        console.error('cheat lock error:', e);
    }
    const sectionEl = document.getElementById('cheat-section');
    if (sectionEl && cheatPage && cheatPage._gateHtml) {
        sectionEl.innerHTML = cheatPage._gateHtml;
        cheatPage._real = null;
        cheatPage._gateBound = false;
        window.cheatPage = null;
        cheatPage._showGate('need_key');
    } else {
        location.reload();
    }
};
