// ============================
// 游戏加速模块
// ============================

class SpeedPage {
    constructor() {
        this.pollTimer = null;
        this.pollInterval = 2000; // 状态轮询间隔（毫秒）
        this._injected = false;   // 缓存注入状态，供 toggle 按钮判断
        this._running = false;    // 缓存游戏运行状态
        this._initDomRefs();
    }

    _initDomRefs() {
        // 缓存常用 DOM 引用
        this.overlay = document.getElementById('speed-disclaimer-overlay');
        this.mainContent = document.getElementById('speed-main-content');
        this.disclaimerCheckbox = document.getElementById('speed-disclaimer-checkbox');
        this.disclaimerConfirmBtn = document.getElementById('speed-disclaimer-confirm');

        this.statusRunning = document.getElementById('speed-status-running');
        this.statusPid = document.getElementById('speed-status-pid');
        this.statusInjected = document.getElementById('speed-status-injected');
        this.statusSpeed = document.getElementById('speed-status-speed');

        this.speedSlider = document.getElementById('speed-slider');
        this.speedInput = document.getElementById('speed-input');
        this.btnToggle = document.getElementById('speed-btn-toggle');
        this.btnApply = document.getElementById('speed-btn-apply');

        // 预设按钮列表
        this.presetBtns = document.querySelectorAll('.speed-preset-btn');

        this.launcherSection = document.getElementById('speed-launcher-section');
        this.launcherSwitch = document.getElementById('launcher-work-speed');
    }

    async init() {
        // 检查免责声明
        try {
            const accepted = await pywebview.api.get_config_value('speed.disclaimer_accepted', false);
            if (accepted) {
                this._showMain();
            } else {
                this._showDisclaimer();
            }
        } catch (e) {
            console.error('SpeedPage init error:', e);
            this._showDisclaimer();
        }

        // 初始化事件
        this._bindEvents();
    }

    _showDisclaimer() {
        if (this.overlay) this.overlay.style.display = 'flex';
        if (this.mainContent) this.mainContent.style.display = 'none';
        if (this.launcherSection) this.launcherSection.style.display = 'none';
    }

    _showMain() {
        if (this.overlay) this.overlay.style.display = 'none';
        if (this.mainContent) this.mainContent.style.display = '';
        if (this.launcherSection) this.launcherSection.style.display = '';
        this._startPolling();
    }

    async acceptDisclaimer() {
        if (!this.disclaimerCheckbox || !this.disclaimerCheckbox.checked) {
            showMessage('提示', '请先勾选"我已了解上述风险"');
            return;
        }
        try {
            await pywebview.api.update_config_value('speed.disclaimer_accepted', true);
            addLogMessage('已同意游戏加速免责声明', 'info');
            this._showMain();
        } catch (e) {
            console.error('acceptDisclaimer error:', e);
            showMessage('错误', '保存设置失败: ' + e);
        }
    }

    _bindEvents() {
        // 滑块 ↔ 输入框双向绑定
        if (this.speedSlider && this.speedInput) {
            this.speedSlider.addEventListener('input', () => {
                this.speedInput.value = this.speedSlider.value;
            });
            this.speedInput.addEventListener('input', () => {
                let v = parseFloat(this.speedInput.value);
                if (!isNaN(v)) {
                    v = Math.max(0.1, Math.min(10.0, v));
                    this.speedSlider.value = v;
                }
            });
        }

        // 预设按钮 —— 仅更新 UI 值，不触发 API 调用
        this.presetBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const factor = parseFloat(btn.dataset.speed);
                if (!isNaN(factor)) {
                    if (this.speedSlider) this.speedSlider.value = factor;
                    if (this.speedInput) this.speedInput.value = factor;
                }
            });
        });

        // Toggle 按钮 —— 根据注入状态执行注入或弹出，
        // 游戏未运行时弹窗提示而非静默忽略。
        if (this.btnToggle) {
            this.btnToggle.addEventListener('click', () => {
                if (!this._running) {
                    showMessage('提示', '请先启动 LimbusCompany.exe');
                    return;
                }
                if (this._injected) {
                    this.doEject();
                } else {
                    this.doInject();
                }
            });
        }

        // 应用速度按钮 —— 未注入时弹窗提示
        if (this.btnApply) {
            this.btnApply.addEventListener('click', () => {
                if (!this._injected) {
                    showMessage('提示', '请先注入 DLL');
                    return;
                }
                const factor = parseFloat(this.speedSlider.value);
                if (!isNaN(factor)) {
                    this._applySpeed(factor);
                }
            });
        }
    }

    async doInject() {
        console.log('开始注入 DLL');
        // 使用 ProgressModal 展示注入进度，防止用户不知道程序是否响应
        const modal = new ProgressModal('DLL 注入');
        modal.setStatus('正在注入 DLL 到 LimbusCompany.exe ...');
        modal.addLog('查找游戏进程...');
        modal.updateProgress(10, '正在注入...');

        try {
            const result = await pywebview.api.speed_inject();
            if (result.success) {
                modal.addLog('DLL 注入成功');
                modal.updateProgress(100, '注入完成');
                modal.complete(true, 'DLL 注入成功');
                addLogMessage('DLL 注入成功', 'success');
                this.refreshStatus();
            } else {
                modal.addLog('注入失败: ' + result.message);
                modal.complete(false, '注入失败: ' + result.message);
                addLogMessage('注入失败: ' + result.message, 'error');
                showMessage('注入失败', result.message);
            }
        } catch (e) {
            modal.addLog('注入时发生错误: ' + e);
            modal.complete(false, '注入时发生错误');
            addLogMessage('注入时发生错误: ' + e, 'error');
        }
    }

    async doEject() {
        console.log('开始弹出 DLL');
        const modal = new ProgressModal('弹出 DLL');
        modal.setStatus('正在从 LimbusCompany.exe 弹出 DLL ...');
        modal.addLog('开始弹出...');
        modal.updateProgress(10, '正在弹出...');

        try {
            const result = await pywebview.api.speed_eject();
            if (result.success) {
                modal.addLog('DLL 已弹出');
                modal.complete(true, 'DLL 已弹出');
                addLogMessage('DLL 已弹出', 'success');
                this.refreshStatus();
            } else {
                modal.addLog('弹出失败: ' + result.message);
                modal.complete(false, '弹出失败: ' + result.message);
                addLogMessage('弹出失败: ' + result.message, 'error');
                showMessage('弹出失败', result.message);
            }
        } catch (e) {
            modal.addLog('弹出时发生错误: ' + e);
            modal.complete(false, '弹出时发生错误');
            addLogMessage('弹出时发生错误: ' + e, 'error');
        }
    }

    async _applySpeed(factor) {
        if (this.speedSlider) this.speedSlider.value = factor;
        if (this.speedInput) this.speedInput.value = factor;

        try {
            const result = await pywebview.api.speed_set(factor);
            if (result.success) {
                addLogMessage(`速度已设置为 ${factor}x`, 'success');
                this.refreshStatus();
            } else {
                addLogMessage('设置速度失败: ' + result.message, 'error');
                showMessage('设置失败', result.message);
            }
        } catch (e) {
            addLogMessage('设置速度时发生错误: ' + e, 'error');
        }
    }

    async refreshStatus() {
        try {
            const result = await pywebview.api.speed_get_status();
            if (!result.success) {
                return;
            }
            const s = result.data;

            // 缓存关键状态
            this._injected = s.injected;
            this._running = s.running;

            // 运行状态
            if (this.statusRunning) {
                this.statusRunning.textContent = s.running ? '● 运行中' : '○ 未运行';
                this.statusRunning.className = 'speed-status-value ' + (s.running ? 'active' : 'inactive');
            }

            // PID
            if (this.statusPid) {
                this.statusPid.textContent = s.pid ? String(s.pid) : '—';
            }

            // 注入状态
            if (this.statusInjected) {
                this.statusInjected.textContent = s.injected ? '● 已注入' : '○ 未注入';
                this.statusInjected.className = 'speed-status-value ' + (s.injected ? 'active' : 'inactive');
            }

            // 速度
            if (this.statusSpeed) {
                this.statusSpeed.textContent = s.speed ? `${s.speed}x` : '—';
            }

            // ---- 按钮 / 控件状态联动 ----
            // Toggle / 应用 / 预设按钮保持可点击，
            // 点击时通过 showMessage 弹窗引导用户，
            // 仅滑块和输入框在未注入时禁用（无操作意义）。

            // Toggle 按钮外观（始终可点击）
            if (this.btnToggle) {
                if (s.injected) {
                    this.btnToggle.innerHTML = '<i class="fas fa-eject"></i> 弹出 DLL';
                    this.btnToggle.className = 'action-btn danger';
                } else {
                    this.btnToggle.innerHTML = '<i class="fas fa-syringe"></i> 注入';
                    this.btnToggle.className = 'primary-btn';
                }
            }

            // 滑块 / 输入框仅在注入后可用
            const canAdjust = s.running && s.injected;
            if (this.speedSlider) {
                this.speedSlider.disabled = !canAdjust;
            }
            if (this.speedInput) {
                this.speedInput.disabled = !canAdjust;
            }

            if (s.error) {
                addLogMessage('状态检测: ' + s.error, 'warning');
            }
        } catch (e) {
            console.error('refreshStatus error:', e);
        }
    }

    _startPolling() {
        // 防止重复调用产生多个并发 interval
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
let speedPage;

// DOM 加载时初始化
document.addEventListener('DOMContentLoaded', function () {
    speedPage = new SpeedPage();
});
