// ============================
// 公告汉化模块
// ============================
// 客户端只把「官方公告文件名」交给用户自建的翻译服务，服务端负责查缓存 / 拉取 /
// 翻译，返回整篇译好的公告 JSON；本页负责发起同步、展示进度与逐条状态、还原原文。
// 落盘细节（官方同名文件、原子写入、与官方原文比对校验）全部在后端完成。

class NoticePage {
    constructor() {
        this.pollTimer = null;
        this.pollInterval = 1000;
        this._eventsBound = false;
        this._stopped = false;
        this._busy = false;
        this._lastStatus = '';
        this._initDomRefs();
    }

    _initDomRefs() {
        this.dirStatusEl = document.getElementById('notice-dir-status');
        this.langStatusEl = document.getElementById('notice-lang-status');
        this.countStatusEl = document.getElementById('notice-count-status');
        this.metaStatusEl = document.getElementById('notice-meta-status');
        this.langChip = document.getElementById('notice-lang-chip');
        this.dirNotice = document.getElementById('notice-dir-notice');
        this.serviceChip = document.getElementById('notice-service-chip');
        this.integrationChip = document.getElementById('notice-integration-chip');

        this.serviceUrlInput = document.getElementById('notice-service-url');
        this.urlTemplateInput = document.getElementById('notice-url-template');
        this.langSelect = document.getElementById('notice-lang');
        this.timeoutInput = document.getElementById('notice-timeout');

        this.badge = document.getElementById('notice-status-badge');
        this.description = document.getElementById('notice-status-description');
        this.progressText = document.getElementById('notice-progress-text');
        this.progressBar = document.getElementById('notice-progress-bar');
        this.progressMessage = document.getElementById('notice-progress-message');
        this.logPanel = document.getElementById('notice-log-panel');
        this.listEl = document.getElementById('notice-list');
        this.listSummary = document.getElementById('notice-list-summary');

        this.btnSync = document.getElementById('notice-sync');
        this.btnForce = document.getElementById('notice-force');
        this.btnCancel = document.getElementById('notice-cancel');
        this.btnRestore = document.getElementById('notice-restore');
        this.btnTest = document.getElementById('notice-test');
        this.btnRefresh = document.getElementById('notice-refresh');
        this.btnOpenDir = document.getElementById('notice-open-dir');
    }

    async init() {
        this._initDomRefs();
        this._bindEvents();
        this._stopped = false;
        this._refreshIntegrationChip();
        await this.loadInfo();
        this._startPolling();
    }

    stop() {
        this._stopped = true;
        this._stopPolling();
    }

    _bindEvents() {
        if (this._eventsBound) return;
        this._eventsBound = true;

        if (this.btnSync) this.btnSync.addEventListener('click', () => this.doSync(false));
        if (this.btnForce) {
            this.btnForce.addEventListener('click', () => {
                showConfirm(
                    '强制重新汉化',
                    '将对清单内所有公告重新请求翻译并覆盖本地文件（已汉化且未变更的也会重取）。继续？',
                    () => this.doSync(true)
                );
            });
        }
        if (this.btnCancel) this.btnCancel.addEventListener('click', () => this.doCancel());
        if (this.btnRestore) {
            this.btnRestore.addEventListener('click', () => {
                showConfirm(
                    '还原官方原文',
                    '将删除本工具写入的公告文件，游戏下次进入大厅时会自动下载官方原文。继续？',
                    () => this.doRestore()
                );
            });
        }
        if (this.btnTest) this.btnTest.addEventListener('click', () => this.doTest());
        if (this.btnRefresh) this.btnRefresh.addEventListener('click', () => this.loadInfo());
        if (this.btnOpenDir) this.btnOpenDir.addEventListener('click', () => this.doOpenDir());
    }

    async _refreshIntegrationChip() {
        if (!this.integrationChip) return;
        let enabled = false;
        try {
            enabled = !!(await pywebview.api.get_config_value('notice.enabled', false));
        } catch (e) {
            try {
                enabled = !!configManager.getCachedValue('notice.enabled');
            } catch (e2) { /* ignore */ }
        }
        this.integrationChip.className = 'resource-state-chip ' + (enabled ? 'success' : 'neutral');
        this.integrationChip.innerHTML = enabled
            ? '<i class="fas fa-check"></i> 已开启'
            : '<i class="fas fa-circle-info"></i> 未开启';
    }

    _setChip(el, text, cls, icon) {
        if (!el) return;
        el.className = 'resource-state-chip ' + (cls || 'neutral');
        el.innerHTML = (icon ? `<i class="fas fa-${icon}"></i> ` : '') + text;
    }

    _setValue(el, text, cls) {
        if (!el) return;
        el.textContent = text;
        el.className = 'speed-status-value' + (cls ? ' ' + cls : '');
    }

    async loadInfo() {
        try {
            const result = await pywebview.api.notice_get_info();
            if (this._stopped) return;
            if (!result || !result.success) {
                if (this.listEl) {
                    this.listEl.innerHTML = `<p class="form-hint">读取公告清单失败：${this._esc((result && result.message) || '未知错误')}</p>`;
                }
                this._setChip(this.langChip, '读取失败', 'error', 'triangle-exclamation');
                return;
            }
            this._renderInfo(result);
        } catch (e) {
            console.error('notice loadInfo error:', e);
        }
    }

    _renderInfo(info) {
        const counts = info.counts || {};
        const exists = info.notice_dir_exists;
        this._setValue(this.dirStatusEl, exists ? '已就绪' : '未检测到', exists ? 'active' : 'inactive');
        this._setValue(this.langStatusEl, `${info.lang}${info.lang_mode === 'auto' ? '（自动）' : ''}`);
        this._setValue(
            this.countStatusEl,
            `${counts.translated || 0} / ${counts.total || 0}`,
            (counts.translated || 0) > 0 ? 'active' : ''
        );
        this._setValue(
            this.metaStatusEl,
            info.meta_source === 'official' ? '官方 CDN' : (info.meta_source === 'local' ? '本地缓存' : '—')
        );
        this._setChip(
            this.langChip,
            `${info.lang} · ${counts.total || 0} 篇`,
            (counts.missing || 0) === 0 && (counts.total || 0) > 0 ? 'success' : 'neutral',
            'bullhorn'
        );

        if (this.dirNotice) {
            if (!exists) {
                this.dirNotice.className = 'resource-inline-notice error';
                this.dirNotice.innerHTML =
                    '<i class="fas fa-circle-exclamation"></i><span>未检测到公告缓存目录 ' +
                    this._esc(info.notice_dir) +
                    '，请先启动一次游戏并进入大厅（或确认游戏使用的是新版公告系统）。</span>';
            } else if (info.meta_error) {
                this.dirNotice.className = 'resource-inline-notice error';
                this.dirNotice.innerHTML =
                    '<i class="fas fa-circle-exclamation"></i><span>' + this._esc(info.meta_error) + '</span>';
            } else {
                this.dirNotice.className = 'resource-inline-notice neutral';
                this.dirNotice.innerHTML =
                    '<i class="fas fa-circle-info"></i><span>' + this._esc(info.details_dir) + '</span>';
            }
        }

        this._renderList(info.items || []);
    }

    _renderList(items) {
        if (!this.listEl) return;
        if (!items.length) {
            this.listEl.innerHTML = '<p class="form-hint">官方公告清单中没有需要处理的公告。</p>';
            if (this.listSummary) this.listSummary.textContent = '0 篇';
            return;
        }
        const statusMap = {
            translated: { cls: 'success', text: '已汉化' },
            official: { cls: 'neutral', text: '官方原文' },
            missing: { cls: 'error', text: '未汉化' },
        };
        const rows = items.map((item) => {
            const meta = statusMap[item.status] || { cls: 'neutral', text: item.status };
            const title = item.title ? this._esc(item.title) : '（未汉化）';
            const expiry = item.valid ? '' : ' · 已过期';
            return `<div class="notice-row">
                <div class="notice-row-main">
                    <strong>${title}</strong>
                    <small>${this._esc(item.file)}${expiry}</small>
                </div>
                <span class="resource-state-chip ${meta.cls}">${meta.text}</span>
            </div>`;
        });
        this.listEl.innerHTML = rows.join('');
        if (this.listSummary) {
            const done = items.filter((i) => i.status === 'translated').length;
            this.listSummary.textContent = `${done} / ${items.length} 篇已汉化`;
        }
    }

    _esc(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    _renderLogs(logs) {
        if (!this.logPanel) return;
        if (!logs || !logs.length) {
            this.logPanel.innerHTML = '<div class="notice-log-empty">暂无日志</div>';
            return;
        }
        this.logPanel.innerHTML = logs
            .map((line) => `<div class="notice-log-line">${this._esc(line)}</div>`)
            .join('');
        this.logPanel.scrollTop = this.logPanel.scrollHeight;
    }

    _applyStatus(status) {
        const badgeMap = {
            idle: { cls: 'idle', icon: 'pause', text: '等待操作' },
            running: { cls: 'running', icon: 'spinner fa-spin', text: '进行中' },
            success: { cls: 'success', icon: 'check', text: '已完成' },
            error: { cls: 'error', icon: 'triangle-exclamation', text: '有失败项' },
            cancelled: { cls: 'cancelled', icon: 'ban', text: '已取消' },
            // 服务端未命中缓存且等待预算耗尽：不是失败，剩余公告留待下次同步
            pending: { cls: 'pending', icon: 'hourglass-half', text: '等待服务端' },
            timed_out: { cls: 'timed_out', icon: 'clock', text: '预算用尽' },
        };
        const meta = badgeMap[status.status] || badgeMap.idle;
        if (this.badge) {
            this.badge.className = 'resource-status-badge ' + meta.cls;
            this.badge.innerHTML = `<i class="fas fa-${meta.icon}"></i><span>${meta.text}</span>`;
        }
        if (this.description) this.description.textContent = status.text || '';

        const percent = status.total ? Math.round((status.done * 100) / status.total) : 0;
        if (this.progressBar) this.progressBar.style.width = percent + '%';
        if (this.progressText) this.progressText.textContent = percent + '%';
        if (this.progressMessage) {
            this.progressMessage.textContent = status.total
                ? `${status.done} / ${status.total} — ${status.text || ''}`
                : (status.text || '等待开始');
        }

        const running = !!status.running;
        this._busy = running;
        if (this.btnSync) this.btnSync.disabled = running;
        if (this.btnForce) this.btnForce.disabled = running;
        if (this.btnRestore) this.btnRestore.disabled = running;
        if (this.btnTest) this.btnTest.disabled = running;
        if (this.btnCancel) this.btnCancel.disabled = !running;

        this._renderLogs(status.logs || []);

        // 任务结束时刷新一次清单（状态指纹已更新）
        if (this._lastStatus === 'running' && !running) {
            this.loadInfo();
        }
        this._lastStatus = status.status;
    }

    async refreshStatus() {
        try {
            const result = await pywebview.api.notice_get_status();
            if (this._stopped || !result || !result.success) return;
            this._applyStatus(result.data || {});
        } catch (e) {
            console.error('notice refreshStatus error:', e);
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

    async doSync(force) {
        try {
            const result = await pywebview.api.notice_start_sync(!!force);
            if (!result || !result.success) {
                showMessage('无法开始同步', (result && result.message) || '未知错误');
                return;
            }
            addLogMessage('公告汉化同步已启动', 'info');
            this.refreshStatus();
        } catch (e) {
            addLogMessage('启动公告汉化同步失败: ' + e, 'error');
        }
    }

    async doCancel() {
        try {
            const result = await pywebview.api.notice_cancel_sync();
            if (!result || !result.success) {
                showToast((result && result.message) || '当前没有运行中的任务', 'warning');
                return;
            }
            showToast('已请求取消', 'info');
        } catch (e) {
            addLogMessage('取消公告汉化失败: ' + e, 'error');
        }
    }

    async doRestore() {
        try {
            const result = await pywebview.api.notice_restore();
            if (!result || !result.success) {
                showMessage('还原失败', (result && result.message) || '未知错误');
                return;
            }
            showToast(result.message || '已还原', 'success');
            await this.loadInfo();
            this.refreshStatus();
        } catch (e) {
            addLogMessage('还原公告失败: ' + e, 'error');
        }
    }

    async doTest() {
        this._setChip(this.serviceChip, '测试中...', 'running', 'spinner fa-spin');
        try {
            const result = await pywebview.api.notice_test_service('');
            if (result && result.success) {
                if (result.pending) {
                    // 连接是通的，只是服务端还没译好这一篇；同步时会自动等待重试
                    this._setChip(this.serviceChip, '可用（待缓存）', 'neutral', 'hourglass-half');
                    showToast(
                        `服务可用，但该公告尚未命中缓存（${result.elapsed}s）。同步时会自动等待重试。`,
                        'info'
                    );
                } else {
                    this._setChip(this.serviceChip, '服务可用', 'success', 'check');
                    showToast(
                        `服务可用：${result.title || result.file}（${result.elapsed}s）`,
                        'success'
                    );
                }
            } else {
                this._setChip(this.serviceChip, '连接失败', 'error', 'triangle-exclamation');
                showMessage('翻译服务不可用', (result && result.message) || '未知错误');
            }
        } catch (e) {
            this._setChip(this.serviceChip, '连接失败', 'error', 'triangle-exclamation');
            addLogMessage('测试翻译服务失败: ' + e, 'error');
        }
    }

    async doOpenDir() {
        try {
            const result = await pywebview.api.notice_open_dir('notice');
            if (!result || !result.success) {
                showMessage('打开目录失败', (result && result.message) || '未知错误');
            }
        } catch (e) {
            addLogMessage('打开公告缓存目录失败: ' + e, 'error');
        }
    }
}

let noticePage;

document.addEventListener('DOMContentLoaded', function () {
    noticePage = new NoticePage();
});
