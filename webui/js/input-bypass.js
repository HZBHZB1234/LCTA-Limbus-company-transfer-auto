// ============================
// 输入反检测模块
// ============================

class InputBypassPage {
    constructor() {
        this.pollTimer = null;
        this.pollInterval = 2000;
        this._eventsBound = false;
        this._initDomRefs();
    }

    _initDomRefs() {
        this.statusEl = document.getElementById('input-bypass-status');
        this.pidEl = document.getElementById('input-bypass-pid');
        this.injectedEl = document.getElementById('input-bypass-injected');
        this.commonlibEl = document.getElementById('input-bypass-commonlib');
        this.installedEl = document.getElementById('input-bypass-installed');
        this.installedRealEl = document.getElementById('input-bypass-installed-real');
        this.modeSelect = document.getElementById('input-bypass-mode');
        this.manualFields = document.getElementById('input-bypass-manual-fields');
        this.btnApply = document.getElementById('input-bypass-btn-apply');
        this.btnInject = document.getElementById('input-bypass-btn-inject');
        this.btnEject = document.getElementById('input-bypass-btn-eject');
    }

    async init() {
        this._initDomRefs();
        this._bindEvents();
        this._syncManualVisibility();
        this.refreshStatus();
    }

    _bindEvents() {
        if (this._eventsBound) return;
        this._eventsBound = true;

        if (this.modeSelect) {
            this.modeSelect.addEventListener('change', () => this._syncManualVisibility());
        }
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
    }

    _syncManualVisibility() {
        if (!this.manualFields || !this.modeSelect) return;
        this.manualFields.style.display = this.modeSelect.value === 'manual' ? '' : 'none';
    }

    async _persistFields() {
        // 将当前页的 5 个字段与模式写入配置（与页面保存一致）
        const updates = {
            'launcher.work.input_bypass_mode': this.modeSelect ? this.modeSelect.value : 'auto',
            'launcher.work.input_bypass_mouse_real': this._val('input-bypass-mouse-real'),
            'launcher.work.input_bypass_key_real': this._val('input-bypass-key-real'),
            'launcher.work.input_bypass_mouse_synth': this._val('input-bypass-mouse-synth'),
            'launcher.work.input_bypass_key_synth': this._val('input-bypass-key-synth'),
            'launcher.work.input_bypass_volatility': this._val('input-bypass-volatility'),
        };
        await pywebview.api.update_config_batch(updates);
    }

    _val(id) {
        const el = document.getElementById(id);
        if (!el) return '0';
        const v = parseFloat(el.value);
        return isNaN(v) ? '0' : String(v);
    }

    async doApply() {
        try {
            await this._persistFields();
            const result = await pywebview.api.input_bypass_apply();
            if (result.success) {
                addLogMessage(
                    `输入反检测配置已应用 (${result.data.mode} 模式, ${result.data.armed ? '已启用' : '未启用'})`,
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
        modal.setStatus('正在注入输入反检测 hook ...');
        modal.addLog('查找游戏进程...');
        try {
            const result = await pywebview.api.input_bypass_inject();
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
            const result = await pywebview.api.input_bypass_eject();
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

    _setValue(el, text, className) {
        if (!el) return;
        el.textContent = text;
        if (className) el.className = 'speed-status-value ' + className;
    }

    async refreshStatus() {
        try {
            const result = await pywebview.api.input_bypass_get_status();
            if (!result.success) return;
            const s = result.data;

            this._running = s.running;
            this._injected = s.injected;

            this._setValue(this.statusEl, s.running ? '● 运行中' : '○ 未运行', s.running ? 'active' : 'inactive');
            this._setValue(this.pidEl, s.pid ? String(s.pid) : '—');
            this._setValue(this.injectedEl, s.injected ? '● 已注入' : '○ 未注入', s.injected ? 'active' : 'inactive');

            let cl = s.commonlib_found
                ? (s.installed ? '● 已就绪' : '○ 已装载，等待 detour 安装')
                : '○ 未找到';
            this._setValue(this.commonlibEl, cl, s.commonlib_found ? 'active' : 'inactive');

            this._setValue(this.installedEl, s.installed ? '● 已安装' : '× 未安装', s.installed ? 'active' : 'inactive');
            this._setValue(this.installedRealEl, s.installed_real ? '● 已安装' : '× 未安装', s.installed_real ? 'active' : 'inactive');

            // 当前生效模式回填到下拉框
            if (this.modeSelect && this.modeSelect.value !== s.mode) {
                this.modeSelect.value = s.mode;
                this._syncManualVisibility();
            }

            if (s.error) {
                addLogMessage('状态检测: ' + s.error, 'warning');
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
let inputBypassPage;

document.addEventListener('DOMContentLoaded', function () {
    inputBypassPage = new InputBypassPage();
});