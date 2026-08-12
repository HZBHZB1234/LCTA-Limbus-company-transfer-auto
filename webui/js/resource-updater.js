class ResourceUpdaterPage {
    constructor() {
        this.initialized = false;
        this.initializing = false;
        this.running = false;
        this._bound = false;
        this._starting = false;
        this.channelProgress = {};
    }

    element(id) {
        return document.getElementById(id);
    }

    async init() {
        if (this.initializing || !this.element('resource-updater-page')) return;
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
            this.setStatus('初始化失败', 'error', error.message || String(error));
        } finally {
            this.initializing = false;
        }
    }

    async refreshState() {
        const state = await pywebview.api.resource_updater_get_initial_state();
        this.applyInitialState(state);
    }

    bindEvents() {
        // 幂等保护：init() 失败重进时只绑定一次，避免重复监听叠加
        if (this._bound) return;
        this._bound = true;
        this.element('ru-go-settings').addEventListener('click', () => goAndShow('settings'));
        this.element('ru-path-missing-go-settings').addEventListener('click', () => goAndShow('settings'));
        this.element('ru-probe').addEventListener('click', () => this.probe());
        this.element('ru-start').addEventListener('click', () => this.start());
        this.element('ru-cancel').addEventListener('click', () => this.cancel());
        this.element('ru-go-launcher').addEventListener('click', () => goAndShow('launcher-config', 'lc-card-resource-update'));
        this.element('ru-open-downloader').addEventListener('click', () => pywebview.api.open_aria2_downloader());

        this.element('ru-localize').addEventListener('change', () => this.syncScopeState());
        this.element('ru-bundle').addEventListener('change', () => this.syncScopeState());

        this.element('resource-updater-page').querySelectorAll('input, select').forEach((element) => {
            if (element.id === 'ru-game-path') return;
            element.addEventListener('change', () => {
                this.syncScopeState();
                this.saveOptions();
            });
        });
    }

    applyInitialState(state) {
        const config = state.config || {};
        this.element('ru-game-path').value = state.game_path || '';
        ['localize', 'bundle', 'lang_jp', 'lang_en', 'lang_kr'].forEach((key) => {
            const element = this.element(`ru-${key.replace('_', '-')}`);
            if (element) element.checked = !!config[key];
        });
        this.element('ru-jobs').value = config.jobs || 8;
        this.element('ru-engine').value = config.engine || 'auto';
        this.setIntegrationChip(!!config.enabled);

        const ariaMessage = state.aria2_available
            ? '已找到 aria2c，自动模式将优先使用。'
            : '未找到 aria2c，自动模式将回退到内置下载器。';
        this.element('ru-aria-status').textContent = ariaMessage;
        this.setEngineChip(state.aria2_available);
        this.syncScopeState();

        const running = state.status === 'running';
        this.setRunning(running);
        this.setStatus(
            state.status_text || '等待操作',
            state.status || 'idle',
            running ? '资源更新正在后台执行，请保持工具箱开启。' : '配置更新范围后即可开始手动预下载。'
        );
        this.updatePathMissingState();
        if (this.element('ru-game-path').value && !running) this.probe();
    }

    // 游戏目录为空时：禁用「开始更新」并展示前往设置页的提示
    updatePathMissingState() {
        const missing = !this.element('ru-game-path').value.trim();
        const notice = this.element('ru-path-missing-notice');
        if (notice) notice.style.display = missing ? 'flex' : 'none';
        this.element('ru-start').disabled = missing || this.running;
    }

    collectOptions() {
        let gamePath = '';
        let enabled = false;
        if (typeof configManager !== 'undefined' && configManager) {
            gamePath = configManager.getCachedValue('game_path') || '';
            enabled = !!configManager.getCachedValue('launcher.resource_update.enabled');
        }
        return {
            game_path: gamePath,
            enabled: enabled,
            localize: this.element('ru-localize').checked,
            bundle: this.element('ru-bundle').checked,
            lang_jp: this.element('ru-lang-jp').checked,
            lang_en: this.element('ru-lang-en').checked,
            lang_kr: this.element('ru-lang-kr').checked,
            jobs: parseInt(this.element('ru-jobs').value, 10) || 8,
            engine: this.element('ru-engine').value,
        };
    }

    async saveOptions() {
        try {
            const options = this.collectOptions();
            const result = await pywebview.api.resource_updater_save_options(options);
            if (result.success) this.syncConfigCache(options);
        } catch (error) {
            console.error('保存资源更新配置失败:', error);
        }
    }

    syncConfigCache(options) {
        const values = {
            'launcher.resource_update.enabled': options.enabled,
            'launcher.resource_update.localize': options.localize,
            'launcher.resource_update.bundle': options.bundle,
            'launcher.resource_update.lang_jp': options.lang_jp,
            'launcher.resource_update.lang_en': options.lang_en,
            'launcher.resource_update.lang_kr': options.lang_kr,
            'launcher.resource_update.jobs': options.jobs,
            'launcher.resource_update.engine': options.engine,
        };
        if (typeof configManager !== 'undefined' && configManager) {
            Object.entries(values).forEach(([key, value]) => configManager.setCachedValue(key, value));
        }
    }

    async probe() {
        const gamePath = this.element('ru-game-path').value.trim();
        if (!gamePath) {
            this.setProbeState('error', '目录缺失', '请先在设置页配置游戏目录。');
            return false;
        }

        this.setProbeState('running', '检测中', '正在验证游戏文件并识别游戏当前资源版本…');
        try {
            const result = await pywebview.api.resource_updater_probe_game_dir(gamePath);
            this.setProbeState(
                result.success ? 'success' : 'error',
                result.success ? '目录有效' : '检测失败',
                result.success
                    ? `${result.message} 已就绪，勾选更新范围后点击右侧「开始更新」。`
                    : result.message
            );
            return !!result.success;
        } catch (error) {
            this.setProbeState('error', '检测失败', error.message || String(error));
            return false;
        }
    }

    async start() {
        // 防连点/并发启动：运行中或探测中忽略重复点击（setRunning(true) 在
        // probe 之后才执行，需额外标记探测窗口期）
        if (this.running || this._starting) return;
        this._starting = true;
        try {
            if (!(await this.probe())) return;
            this.resetProgress();
            this.setRunning(true);
            this.setStatus('正在启动更新', 'running', '正在创建资源清单并准备下载任务。');

            try {
                const result = await pywebview.api.resource_updater_start_update(this.collectOptions());
                if (!result.success) {
                    this.setRunning(false);
                    this.setStatus(result.message, 'error', '请检查更新范围、游戏目录和下载设置。');
                }
            } catch (error) {
                this.setRunning(false);
                this.setStatus('启动失败', 'error', error.message || String(error));
            }
        } finally {
            this._starting = false;
        }
    }

    async cancel() {
        try {
            const result = await pywebview.api.resource_updater_cancel_update();
            // complete 事件先到时 running 已为 false（终态），不再用"正在取消"覆盖终态
            if (result.success && this.running) {
                this.setStatus('正在取消', 'running', '正在等待当前下载任务安全停止。');
            }
        } catch (error) {
            if (this.running) this.setStatus('取消失败', 'error', error.message || String(error));
        }
    }

    handleEvent(event) {
        if (!event) return;
        if (event.type === 'progress') {
            this.setProgress(event.channel, event.fraction, event.message);
            this.setStatus(event.message, 'running', '资源更新正在后台执行，请保持工具箱开启。');
            return;
        }

        if (event.type === 'complete') {
            this.setRunning(false);
            const status = event.status || 'error';
            const failedItems = (event.result && event.result.failed_items) || [];
            let description;
            if (status === 'success') {
                description = this.formatResult(event.result);
            } else if (status === 'cancelled') {
                description = '任务已停止，已完成的文件会保留并可在下次继续使用。';
            } else if (failedItems.length) {
                description = `以下 ${failedItems.length} 个文件下载失败：${failedItems.map((item) => item.name).join('、')}。日志位于程序安装目录下 logs 文件夹的 app.log。`;
            } else {
                description = '部分资源未能完成，请重试。日志位于程序安装目录下 logs 文件夹的 app.log。';
            }
            this.setStatus(event.message, status, description);
        }
    }

    formatResult(result) {
        if (!result || !result.results) return '';
        const parts = [];
        const localize = result.results.localize;
        const bundle = result.results.bundle;
        if (localize) parts.push(`Localize：${localize.updated || 0} 个已更新，${localize.failed || 0} 个失败`);
        if (bundle) parts.push(`Bundle：${bundle.updated || 0} 个已更新，${bundle.skipped || 0} 个跳过，${bundle.failed || 0} 个失败`);
        return parts.join('；');
    }

    setEngineChip(available) {
        const chip = this.element('ru-engine-chip');
        chip.className = `resource-state-chip ${available ? 'success' : 'neutral'}`;
        chip.innerHTML = available
            ? '<i class="fas fa-bolt"></i> aria2c 已就绪'
            : '<i class="fas fa-download"></i> 使用内置下载器';
    }

    setIntegrationChip(enabled) {
        const chip = this.element('ru-integration-chip');
        if (!chip) return;
        chip.className = `resource-state-chip ${enabled ? 'success' : 'neutral'}`;
        chip.innerHTML = enabled
            ? '<i class="fas fa-check"></i> 已开启'
            : '<i class="fas fa-circle-info"></i> 未开启';
    }

    setProbeState(type, label, message) {
        const chip = this.element('ru-path-chip');
        chip.className = `resource-state-chip ${type}`;
        chip.textContent = label;

        const notice = this.element('ru-probe-result');
        notice.className = `resource-inline-notice ${type}`;
        notice.querySelector('span').textContent = message;
    }

    setStatus(text, type, description) {
        const normalized = ['idle', 'running', 'success', 'error', 'cancelled'].includes(type) ? type : 'idle';
        const icons = {
            idle: 'fa-pause',
            running: 'fa-spinner fa-spin',
            success: 'fa-check',
            error: 'fa-triangle-exclamation',
            cancelled: 'fa-ban',
        };
        const badge = this.element('ru-status-badge');
        badge.className = `resource-status-badge ${normalized}`;
        badge.innerHTML = `<i class="fas ${icons[normalized]}"></i><span>${this.escapeHtml(text)}</span>`;
        this.element('ru-status-description').textContent = description || '';

        // 失败状态时「开始更新」按钮变为「重试更新」，其他状态恢复
        const startBtn = this.element('ru-start');
        if (startBtn) {
            startBtn.innerHTML = normalized === 'error'
                ? '<i class="fas fa-rotate-right"></i> 重试更新'
                : '<i class="fas fa-cloud-arrow-down"></i> 开始更新';
        }
    }

    setProgress(channel, fraction, message) {
        if (!['manifest', 'localize', 'bundle'].includes(channel)) return;
        if (fraction != null) {
            this.channelProgress[channel] = fraction;
            const percent = Math.max(0, Math.min(100, Math.round(fraction * 100)));
            this.element(`ru-${channel}-bar`).style.width = `${percent}%`;
            this.element(`ru-${channel}-text`).textContent = `${percent}%`;
            this.updateTotalProgress();
        }
        if (channel === 'manifest') {
            this.element('ru-manifest-message').textContent = message
                ? `${message}（网络慢时可能需要数分钟）`
                : '正在解析资源清单，网络慢时可能需要数分钟';
        } else if (message) {
            this.element(`ru-${channel}-message`).textContent = message;
        }
    }

    // 总进度 = 三个 channel 的加权平均（manifest 轻量 10%，Localize 45%，Bundle 45%）
    updateTotalProgress() {
        const weights = { manifest: 0.1, localize: 0.45, bundle: 0.45 };
        let sum = 0;
        ['manifest', 'localize', 'bundle'].forEach((channel) => {
            if (this.channelProgress[channel] != null) sum += this.channelProgress[channel] * weights[channel];
        });
        const percent = Math.max(0, Math.min(100, Math.round(sum * 100)));
        this.element('ru-total-bar').style.width = `${percent}%`;
        this.element('ru-total-text').textContent = `${percent}%`;
    }

    resetProgress() {
        this.channelProgress = {};
        ['manifest', 'localize', 'bundle', 'total'].forEach((channel) => {
            this.element(`ru-${channel}-bar`).style.width = '0%';
            this.element(`ru-${channel}-text`).textContent = '0%';
        });
        this.element('ru-manifest-message').textContent = '正在解析资源清单，网络慢时可能需要数分钟';
        this.element('ru-localize-message').textContent = '等待下载本地化资源';
        this.element('ru-bundle-message').textContent = '等待下载 Bundle 缓存';
    }

    setRunning(value) {
        this.running = value;
        this.element('ru-start').disabled = value || !this.element('ru-game-path').value.trim();
        this.element('ru-cancel').disabled = !value;
        this.element('ru-go-settings').disabled = value;
        this.element('ru-probe').disabled = value;
        this.element('resource-updater-page').querySelectorAll('input, select').forEach((element) => {
            element.disabled = value;
        });
        if (!value) this.syncScopeState();
    }

    syncScopeState() {
        const localizeEnabled = this.element('ru-localize').checked;
        ['ru-lang-jp', 'ru-lang-en', 'ru-lang-kr'].forEach((id) => {
            this.element(id).disabled = this.running || !localizeEnabled;
        });
        this.element('ru-language-options').classList.toggle('disabled', !localizeEnabled);

        const scopes = [];
        if (localizeEnabled) scopes.push('Localize');
        if (this.element('ru-bundle').checked) scopes.push('Bundle');
        this.element('ru-selection-summary').textContent = scopes.length ? scopes.join(' + ') : '未选择更新内容';
        this.element('ru-selection-summary').classList.toggle('warning', scopes.length === 0);
    }

    escapeHtml(value) {
        const element = document.createElement('span');
        element.textContent = value || '';
        return element.innerHTML;
    }
}

const resourceUpdaterPage = new ResourceUpdaterPage();

window.onResourceUpdaterEvent = function (event) {
    resourceUpdaterPage.handleEvent(event);
};
