// ============================
// 伤害倍率模块
// ============================

class DamageHookPage {
    constructor() {
        this.pollTimer = null;
        this.pollInterval = 2000;
        this._eventsBound = false;
        this._initDomRefs();
    }

    _initDomRefs() {
        this.mainContent = document.getElementById('damage-hook-main-content');
        this.statusEl = document.getElementById('damage-hook-status');
        this.pidEl = document.getElementById('damage-hook-pid');
        this.injectedEl = document.getElementById('damage-hook-injected');
        this.gaEl = document.getElementById('damage-hook-ga');
        this.versionEl = document.getElementById('damage-hook-version');
        this.sourceEl = document.getElementById('damage-hook-source');
        this.installedEl = document.getElementById('damage-hook-installed');
        this.lastLogEl = document.getElementById('damage-hook-last-log');
        this.multiplierInput = document.getElementById('damage-hook-multiplier');
        this.logCheckbox = document.getElementById('damage-hook-log');
        this.apiUrlInput = document.getElementById('damage-hook-api-url');
        this.btnApply = document.getElementById('damage-hook-btn-apply');
        this.btnInject = document.getElementById('damage-hook-btn-inject');
        this.btnEject = document.getElementById('damage-hook-btn-eject');
        this.btnRefresh = document.getElementById('damage-hook-btn-refresh');
    }

    async init() {
        this._initDomRefs();
        this._bindEvents();
        // 风险服务门控：未同意风险须知时显示覆盖层，同意后解锁并启动轮询
        RiskGate.gatePage('damage_hook', {
            onAccepted: () => this._showMain(),
            onRejected: () => this._hideMain()
        });
    }

    _hideMain() {
        if (this.mainContent) this.mainContent.style.display = 'none';
    }

    _showMain() {
        if (this.mainContent) this.mainContent.style.display = '';
        this._startPolling();
    }

    _bindEvents() {
        if (this._eventsBound) return;
        this._eventsBound = true;

        if (this.btnApply) {
            this.btnApply.addEventListener('click', () => this.doApply());
        }
        if (this.btnInject) {
            this.btnInject.addEventListener('click', () => {
                if (!this._running) {
                    showMessage('提示', '请先启动 LimbusCompany.exe');
                    return;
                }
                this.doInject();
            });
        }
        if (this.btnEject) {
            this.btnEject.addEventListener('click', () => this.doEject());
        }
        if (this.btnRefresh) {
            this.btnRefresh.addEventListener('click', () => this.doRefreshOffsets());
        }
    }

    async _persistFields() {
        // 将当前页字段写入配置（与页面保存一致）
        const updates = {};
        if (this.multiplierInput) {
            updates['launcher.work.damage_hook_multiplier'] = this._val();
        }
        if (this.logCheckbox) {
            updates['launcher.work.damage_hook_log'] = this.logCheckbox.checked;
        }
        if (this.apiUrlInput && this.apiUrlInput.value.trim()) {
            updates['launcher.work.damage_hook_api'] = this.apiUrlInput.value.trim();
        }
        await pywebview.api.update_config_batch(updates);
    }

    _val() {
        const v = parseFloat(this.multiplierInput.value);
        return isNaN(v) ? '3.0' : String(v);
    }

    async doApply() {
        try {
            await this._persistFields();
            const result = await pywebview.api.damage_hook_apply();
            if (result.success) {
                addLogMessage(
                    `伤害倍率配置已应用 (倍率 ${result.data.multiplier}, ${result.data.enabled ? '已启用' : '未启用'})`,
                    'success'
                );
                this.refreshStatus();
            } else {
                showMessage('应用失败', result.message);
                addLogMessage('应用失败: ' + result.message, 'error');
            }
        } catch (e) {
            addLogMessage('应用配置时发生错误: ' + e, 'error');
        }
    }

    async doInject() {
        const modal = new ProgressModal('DLL 注入');
        modal.setStatus('正在注入伤害倍率 hook ...');
        modal.addLog('查找游戏进程并解析偏移...');
        try {
            const result = await pywebview.api.damage_hook_inject();
            if (result.success) {
                modal.addLog('DLL 注入成功');
                modal.updateProgress(100, '注入完成');
                modal.complete(true, 'DLL 注入成功');
                addLogMessage('DLL 注入成功', 'success');
                this.refreshStatus();
            } else {
                modal.addLog('注入失败: ' + result.message);
                modal.complete(false, '注入失败: ' + result.message);
                showMessage('注入失败', result.message);
            }
        } catch (e) {
            modal.addLog('注入时发生错误: ' + e);
            modal.complete(false, '注入时发生错误');
            addLogMessage('注入时发生错误: ' + e, 'error');
        }
    }

    async doEject() {
        try {
            const result = await pywebview.api.damage_hook_eject();
            if (result.success) {
                addLogMessage('hook 已弹出', 'success');
                this.refreshStatus();
            } else {
                addLogMessage('弹出失败: ' + result.message, 'error');
            }
        } catch (e) {
            addLogMessage('弹出时发生错误: ' + e, 'error');
        }
    }

    async doRefreshOffsets() {
        try {
            await this._persistFields();
            const result = await pywebview.api.damage_hook_refresh_offsets();
            if (result.success) {
                const stale = result.data.stale ? '（降级使用旧偏移，可能不生效）' : '';
                addLogMessage(`偏移刷新完成: ${result.data.message || ''}${stale}`, result.data.stale ? 'warning' : 'success');
                this.refreshStatus();
            } else {
                showMessage('刷新失败', result.message);
                addLogMessage('刷新失败: ' + result.message, 'error');
            }
        } catch (e) {
            addLogMessage('刷新偏移时发生错误: ' + e, 'error');
        }
    }

    _setValue(el, text, className) {
        if (!el) return;
        el.textContent = text;
        if (className) el.className = 'speed-status-value ' + className;
    }

    async refreshStatus() {
        try {
            const result = await pywebview.api.damage_hook_get_status();
            if (!result.success) return;
            const s = result.data;

            this._running = s.running;
            this._injected = s.injected;

            this._setValue(this.statusEl, s.running ? '● 运行中' : '○ 未运行', s.running ? 'active' : 'inactive');
            this._setValue(this.pidEl, s.pid ? String(s.pid) : '—');
            this._setValue(this.injectedEl, s.injected ? '● 已注入' : '○ 未注入', s.injected ? 'active' : 'inactive');

            let ga = '—';
            let gaClass = 'inactive';
            if (s.running) {
                ga = s.gameassembly_found ? '● 已装载' : '○ 未装载';
                gaClass = s.gameassembly_found ? 'active' : 'inactive';
            }
            this._setValue(this.gaEl, ga, gaClass);

            let version = '—';
            let verClass = 'inactive';
            if (s.game_version) {
                version = s.offsets_stale ? `${s.game_version} (已过期)` : s.game_version;
                verClass = s.offsets_stale ? 'warning' : 'active';
            }
            this._setValue(this.versionEl, version, verClass);

            const sourceText = s.offsets_source === 'api'
                ? 'API'
                : s.offsets_source === 'cache'
                    ? (s.offsets_stale ? '缓存（降级）' : '缓存')
                    : '—';
            this._setValue(this.sourceEl, sourceText, s.offsets_source ? 'active' : 'inactive');

            let installed = '× 未安装';
            let installedClass = 'inactive';
            if (s.verified) {
                installed = s.installed ? '● 已安装' : '○ 已验证，等待安装';
                installedClass = s.installed ? 'active' : '';
            } else if (s.gameassembly_found && s.injected) {
                installed = `× ${s.last_error_text}`;
                installedClass = 'warning';
            }
            this._setValue(this.installedEl, installed, installedClass);

            this._setValue(this.lastLogEl, s.last_log ? s.last_log : '—', s.last_log ? '' : 'inactive');

            if (s.log_count > 0 && s.log_count !== this._lastLogCount) {
                this._lastLogCount = s.log_count;
            }
        } catch (e) {
            console.error('refreshStatus error:', e);
        }
    }

    _startPolling() {
        this._stopPolling();
        this.refreshStatus();
        this.pollTimer = setInterval(() => this.refreshStatus(), this.pollInterval);
    }

    _stopPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }

    stop() {
        this._stopPolling();
    }
}

// 全局实例
let damageHookPage;

document.addEventListener('DOMContentLoaded', function () {
    damageHookPage = new DamageHookPage();
});
