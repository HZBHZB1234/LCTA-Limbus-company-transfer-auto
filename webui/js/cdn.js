// ============================
// CDN 优选模块
// ============================

class CdnManager {
    constructor() {
        this.cloudflareResult = null;     // {ip, avg_latency_ms, download_mbps, loss_rate}
        this.cloudfrontResults = {};      // {domain: {ip, median_latency_ms, ...}}
        this.statusLoaded = false;
    }

    async init() {
        await this.loadStatus();
    }

    async loadStatus() {
        try {
            const result = await pywebview.api.cdn_get_status();
            if (result.success) {
                const data = result.data;
                // 更新 Cloudflare 状态徽章
                const cfBadge = document.getElementById('cdn-cf-status');
                const cfIpEl = document.getElementById('cdn-cf-current-ip');
                if (cfBadge && cfIpEl) {
                    if (data.cf_ip) {
                        cfIpEl.textContent = data.cf_ip;
                        cfBadge.className = 'cdn-status-badge active';
                    } else {
                        cfIpEl.textContent = '未设置';
                        cfBadge.className = 'cdn-status-badge inactive';
                    }
                }

                // 更新 CloudFront 状态徽章（支持多域名）
                const cfaBadge = document.getElementById('cdn-cfa-status');
                if (cfaBadge) {
                    if (Object.keys(data.cloudfront).length > 0) {
                        cfaBadge.className = 'cdn-status-badge active';
                        let html = '';
                        for (const [domain, ip] of Object.entries(data.cloudfront)) {
                            html += `<div class="cdn-ip-row"><span class="cdn-ip-domain">${domain}</span><span class="cdn-ip-value">${ip}</span></div>`;
                        }
                        cfaBadge.innerHTML = html;
                    } else {
                        cfaBadge.className = 'cdn-status-badge inactive';
                        cfaBadge.innerHTML = '<span class="cdn-ip-value">未设置</span>';
                    }
                }

                // 更新还原按钮状态
                const restoreBtn = document.getElementById('cdn-restore-btn');
                if (restoreBtn) {
                    restoreBtn.disabled = !data.backup_exists;
                }

                this.statusLoaded = true;
            }
        } catch (error) {
            console.error('加载CDN状态出错:', error);
        }
    }

    updateResultDisplay() {
        // Cloudflare 结果
        const cfResultSection = document.getElementById('cdn-cf-result');
        const cfCard = cfResultSection ? cfResultSection.querySelector('.cdn-result-card') : null;
        if (cfResultSection && cfCard) {
            if (this.cloudflareResult) {
                cfResultSection.style.display = 'block';
                cfCard.innerHTML = `
                    <div class="result-row"><span class="result-label">IP地址</span><span class="result-value">${this.cloudflareResult.ip}</span></div>
                    <div class="result-row"><span class="result-label">平均延迟</span><span class="result-value">${this.cloudflareResult.avg_latency_ms.toFixed(1)} ms</span></div>
                    <div class="result-row"><span class="result-label">下载速度</span><span class="result-value">${this.cloudflareResult.download_mbps.toFixed(1)} MB/s</span></div>
                    <div class="result-row"><span class="result-label">丢包率</span><span class="result-value">${(this.cloudflareResult.loss_rate * 100).toFixed(1)}%</span></div>`;
            } else {
                cfResultSection.style.display = 'none';
                cfCard.innerHTML = '';
            }
        }

        // CloudFront 结果
        const cfaResultSection = document.getElementById('cdn-cfa-result');
        const cfaCard = cfaResultSection ? cfaResultSection.querySelector('.cdn-result-card') : null;
        if (cfaResultSection && cfaCard) {
            if (Object.keys(this.cloudfrontResults).length > 0) {
                cfaResultSection.style.display = 'block';
                let html = '';
                for (const [domain, info] of Object.entries(this.cloudfrontResults)) {
                    html += `
                        <div class="cdn-result-domain"><i class="fas fa-globe"></i>${domain}</div>
                        <div class="cdn-result-row"><span class="cdn-result-label">IP地址</span><span class="cdn-result-value">${info.ip}</span></div>
                        <div class="cdn-result-row"><span class="cdn-result-label">中位延迟</span><span class="cdn-result-value">${info.median_latency_ms.toFixed(1)} ms</span></div>`;
                }
                cfaCard.innerHTML = html;
            } else {
                cfaResultSection.style.display = 'none';
                cfaCard.innerHTML = '';
            }
        }

        // 有结果则启用写入按钮
        const writeBtn = document.getElementById('cdn-write-btn');
        if (writeBtn) {
            writeBtn.disabled = !(this.cloudflareResult || Object.keys(this.cloudfrontResults).length > 0);
        }
    }

    async _runTask(taskName, apiMethod, onSuccess) {
        addLogMessage(`开始${taskName}`, 'info');
        const modal = new ProgressModal(taskName);
        try {
            const result = await pywebview.api[apiMethod](modal.id);
            if (result.success) {
                onSuccess(result);
                modal.complete(true, `${taskName}完成`);
            } else {
                if (result.message === '已取消') {
                    addLogMessage(`${taskName}已取消`, 'warning');
                    modal.cancel();
                } else {
                    addLogMessage(`${taskName}失败: ` + result.message, 'error');
                    modal.complete(false, '优选失败: ' + result.message);
                }
            }
        } catch (error) {
            addLogMessage(`${taskName}发生错误: ` + error, 'error');
            modal.complete(false, '优选过程发生错误: ' + error);
        }
    }

    async runCloudflare() {
        this.cloudflareResult = null;
        this.updateResultDisplay();
        await this._runTask('Cloudflare CDN优选', 'cdn_optimize_cloudflare', (result) => {
            this.cloudflareResult = result.data;
            this.updateResultDisplay();
            addLogMessage(`Cloudflare优选完成 — IP: ${result.data.ip} 延迟: ${result.data.avg_latency_ms.toFixed(1)}ms 下载: ${result.data.download_mbps.toFixed(1)}MB/s`, 'success');
        });
    }

    async runCloudFront() {
        this.cloudfrontResults = {};
        this.updateResultDisplay();
        await this._runTask('CloudFront API优选', 'cdn_optimize_cloudfront', (result) => {
            this.cloudfrontResults = result.data;
            this.updateResultDisplay();
            const summary = Object.entries(result.data)
                .map(([domain, info]) => `${domain}: ${info.ip}`)
                .join(', ');
            addLogMessage(`CloudFront优选完成 — ${summary}`, 'success');
        });
    }

    async runFullOptimization() {
        // 清除上一次结果
        this.cloudflareResult = null;
        this.cloudfrontResults = {};
        this.updateResultDisplay();
        addLogMessage('开始全流程CDN优选', 'info');
        const modal = new ProgressModal('全流程CDN优选');

        try {
            const result = await pywebview.api.cdn_full_optimization(modal.id);
            if (result.success) {
                if (result.data.cloudflare) {
                    this.cloudflareResult = result.data.cloudflare;
                }
                if (result.data.cloudfront) {
                    this.cloudfrontResults = result.data.cloudfront;
                }
                this.updateResultDisplay();
                addLogMessage('全流程CDN优选完成', 'success');
                modal.complete(true, '全流程CDN优选完成');
            } else {
                if (result.message === '已取消') {
                    addLogMessage('CDN优选已取消', 'warning');
                    modal.cancel();
                } else {
                    // 即使失败也可能有部分结果
                    if (result.data) {
                        if (result.data.cloudflare) this.cloudflareResult = result.data.cloudflare;
                        if (result.data.cloudfront) this.cloudfrontResults = result.data.cloudfront;
                        this.updateResultDisplay();
                    }
                    addLogMessage('CDN优选未获得完整结果: ' + result.message, 'warning');
                    modal.complete(false, result.message);
                }
            }
        } catch (error) {
            addLogMessage('CDN优选发生错误: ' + error, 'error');
            modal.complete(false, '优选过程发生错误: ' + error);
        }
    }

    async writeToHosts() {
        const hasResults = this.cloudflareResult || Object.keys(this.cloudfrontResults).length > 0;
        if (!hasResults) {
            showMessage('提示', '请先运行CDN优选获取结果');
            return;
        }

        const confirmed = await new Promise((resolve) => {
            const confirmModal = new ConfirmModal(
                '确认写入Hosts',
                '将优选IP写入系统hosts文件需要管理员权限。\n\n写入仅修改CDN优选管理的标记块，不会影响其他hosts条目。\n\n确定要继续吗？',
                () => resolve(true),
                () => resolve(false)
            );
        });

        if (!confirmed) return;

        addLogMessage('正在写入CDN优选结果到hosts...', 'info');
        const cfIp = this.cloudflareResult ? this.cloudflareResult.ip : null;
        const cloudfrontMappings = {};
        for (const [domain, info] of Object.entries(this.cloudfrontResults)) {
            cloudfrontMappings[domain] = info.ip;
        }

        try {
            const result = await pywebview.api.cdn_write_hosts(cfIp, cloudfrontMappings);
            if (result.success) {
                addLogMessage('CDN优选结果已写入hosts', 'success');
                showMessage('成功', 'hosts 写入成功！');
                await this.loadStatus();
            } else {
                addLogMessage('hosts写入失败: ' + result.message, 'error');
                showMessage('失败', 'hosts 写入失败: ' + result.message);
            }
        } catch (error) {
            addLogMessage('hosts写入发生错误: ' + error, 'error');
            showMessage('错误', '写入过程发生错误: ' + error);
        }
    }

    async restoreBackup() {
        const confirmed = await new Promise((resolve) => {
            const confirmModal = new ConfirmModal(
                '确认还原Hosts',
                '将从最近一次备份还原hosts文件。\n\n此操作将撤销最近一次CDN优选写入的内容。\n\n确定要继续吗？',
                () => resolve(true),
                () => resolve(false)
            );
        });

        if (!confirmed) return;

        addLogMessage('正在还原hosts备份...', 'info');
        try {
            const result = await pywebview.api.cdn_restore_backup();
            if (result.success) {
                addLogMessage('hosts已从备份还原', 'success');
                showMessage('成功', 'hosts 已从备份还原');
                await this.loadStatus();
            } else {
                addLogMessage('hosts还原失败: ' + result.message, 'error');
                showMessage('失败', result.message);
            }
        } catch (error) {
            addLogMessage('hosts还原发生错误: ' + error, 'error');
            showMessage('错误', '还原过程发生错误: ' + error);
        }
    }
}

// 全局实例
let cdnManager;

// DOM 加载时初始化
document.addEventListener('DOMContentLoaded', function () {
    cdnManager = new CdnManager();
});
