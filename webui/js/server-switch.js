class ServerSwitchPage {
    constructor() {
        this.initialized = false;
        this.initializing = false;
    }

    element(id) {
        return document.getElementById(id);
    }

    async init() {
        if (this.initializing || !this.element('server-switch-page')) return;
        if (!window.pywebview || !window.pywebview.api) {
            window.addEventListener('pywebviewready', () => this.init(), { once: true });
            return;
        }

        if (this.initialized) {
            await this.refreshState();
            return;
        }

        this.initializing = true;
        this.bindEvents();
        try {
            await this.refreshState();
            this.initialized = true;
        } catch (error) {
            this.showToast('初始化失败：' + (error.message || String(error)), 'error');
        } finally {
            this.initializing = false;
        }
    }

    async refreshState() {
        const state = await pywebview.api.server_switch_get_initial_state();
        this.applyInitialState(state);
    }

    bindEvents() {
        if (this._bound) return;
        this._bound = true;
        this.element('ss-go-settings').addEventListener('click', () => goAndShow('settings'));
        this.element('ss-browse-lethe').addEventListener('click', () => browseFolder('ss-lethe-dir'));
        this.element('ss-probe-lethe').addEventListener('click', () => this.probeLethe());
        this.element('ss-go-launcher').addEventListener('click', () => goAndShow('launcher-config', 'lc-card-server-switch'));
        this.element('ss-create-shortcut').addEventListener('click', () => this.createShortcut());
        this.element('ss-lethe-dir').addEventListener('change', () => this.onLetheDirChange());
    }

    applyInitialState(state) {
        const config = state.config || {};
        const official = state.official_dir || '';
        this.element('ss-official-dir').value = official;
        this.element('ss-lethe-dir').value = config.lethe_dir || '';
        this.setIntegrationChip(!!config.enabled);
        this.updatePathState();
        this.renderCandidates(state.lethe_candidates || []);
    }

    collectOptions() {
        let official = '';
        let enabled = false;
        if (typeof configManager !== 'undefined' && configManager) {
            official = configManager.getCachedValue('game_path') || '';
            enabled = !!configManager.getCachedValue('launcher.server_switch.enabled');
        }
        if (!official) official = this.element('ss-official-dir').value || '';
        const lethe = this.element('ss-lethe-dir').value || '';
        return {
            official_dir: official,
            lethe_dir: lethe,
            enabled: enabled,
        };
    }

    async saveOptions() {
        try {
            const options = this.collectOptions();
            const result = await pywebview.api.server_switch_save_options(options);
            if (result && result.success) {
                if (typeof configManager !== 'undefined' && configManager) {
                    configManager.setCachedValue('launcher.server_switch.lethe_dir', options.lethe_dir);
                }
            }
        } catch (error) {
            console.error('保存服务器切换配置失败:', error);
        }
    }

    onLetheDirChange() {
        this.updatePathState();
        this.saveOptions();
    }

    updatePathState() {
        const official = this.element('ss-official-dir').value.trim();
        const lethe = this.element('ss-lethe-dir').value.trim();
        const chip = this.element('ss-path-chip');
        const notice = this.element('ss-probe-result');
        if (!official) {
            chip.className = 'resource-state-chip error';
            chip.textContent = '缺少官服目录';
            notice.className = 'resource-inline-notice error';
            notice.querySelector('span').textContent = '官服目录为空，请先在设置页配置游戏目录（与主程序共用）。';
        } else if (!lethe) {
            chip.className = 'resource-state-chip neutral';
            chip.textContent = '缺少 lethe 目录';
            notice.className = 'resource-inline-notice neutral';
            notice.querySelector('span').textContent = '官服目录已配置，请选择 lethe 私服分发包目录。';
        } else {
            chip.className = 'resource-state-chip neutral';
            chip.textContent = '等待检测';
            notice.className = 'resource-inline-notice neutral';
            notice.querySelector('span').textContent = '两个目录均已填写，可点击「检测」验证 lethe 目录，或直接发送快捷方式。';
        }
    }

    renderCandidates(candidates) {
        const container = this.element('ss-lethe-candidates');
        if (!container) return;
        if (!candidates || !candidates.length) {
            container.style.display = 'none';
            container.innerHTML = '';
            return;
        }
        const existing = this.element('ss-lethe-dir').value.trim();
        const filtered = candidates.filter((path) => path !== existing);
        if (!filtered.length) {
            container.style.display = 'none';
            container.innerHTML = '';
            return;
        }
        container.style.display = 'block';
        container.innerHTML = filtered.map((path) =>
            `<button type="button" class="action-btn secondary" style="margin:2px 4px 2px 0; padding:4px 10px; font-size:12px;" data-candidate="${this.escapeHtml(path)}">
                <i class="fas fa-folder"></i> ${this.escapeHtml(path)}
            </button>`
        ).join('');
        container.querySelectorAll('button[data-candidate]').forEach((button) => {
            button.addEventListener('click', () => {
                this.element('ss-lethe-dir').value = button.getAttribute('data-candidate');
                this.onLetheDirChange();
                this.renderCandidates([]);
            });
        });
    }

    async probeLethe() {
        const lethe = this.element('ss-lethe-dir').value.trim();
        if (!lethe) {
            this.setProbeState('error', '目录缺失', '请先填写 lethe 分发包目录。');
            return false;
        }
        this.setProbeState('running', '检测中', '正在验证 lethe 分发包目录…');
        try {
            const result = await pywebview.api.server_switch_probe_lethe_dir(lethe);
            this.setProbeState(
                result.success ? 'success' : 'error',
                result.success ? '目录有效' : '检测失败',
                result.message
            );
            return !!result.success;
        } catch (error) {
            this.setProbeState('error', '检测失败', error.message || String(error));
            return false;
        }
    }

    async createShortcut() {
        const lethe = this.element('ss-lethe-dir').value.trim();
        if (!lethe) {
            this.setShortcutState('error', '缺少目录');
            this.showToast('请先填写 lethe 分发包目录。', 'error');
            return;
        }
        this.setShortcutState('running', '创建中');
        try {
            const result = await pywebview.api.server_switch_create_shortcut(lethe);
            if (result.success) {
                this.setShortcutState('success', '已创建');
                this.showToast(result.message + '：' + result.lnk + '（双击将先同步 lethe 资源再启动私服）', 'success', 6000);
            } else {
                this.setShortcutState('error', '创建失败');
                this.showToast(result.message || '快捷方式创建失败，请查看日志。', 'error');
            }
        } catch (error) {
            this.setShortcutState('error', '创建失败');
            this.showToast(error.message || String(error), 'error');
        }
    }

    setIntegrationChip(enabled) {
        const chip = this.element('ss-integration-chip');
        if (!chip) return;
        chip.className = `resource-state-chip ${enabled ? 'success' : 'neutral'}`;
        chip.innerHTML = enabled
            ? '<i class="fas fa-check"></i> 已开启'
            : '<i class="fas fa-circle-info"></i> 未开启';
    }

    setShortcutState(type, label) {
        const chip = this.element('ss-shortcut-chip');
        if (!chip) return;
        chip.className = `resource-state-chip ${type}`;
        chip.textContent = label;
    }

    setProbeState(type, label, message) {
        const chip = this.element('ss-path-chip');
        chip.className = `resource-state-chip ${type}`;
        chip.textContent = label;

        const notice = this.element('ss-probe-result');
        notice.className = `resource-inline-notice ${type}`;
        notice.querySelector('span').textContent = message;
    }

    showToast(message, type, duration) {
        if (typeof showToast === 'function') {
            showToast(message, type || 'info', duration);
        }
    }

    escapeHtml(value) {
        const element = document.createElement('span');
        element.textContent = value || '';
        return element.innerHTML;
    }
}

const serverSwitchPage = new ServerSwitchPage();
