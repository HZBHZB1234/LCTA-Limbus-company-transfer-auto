// metadata-recovery.js - Metadata 恢复页面控制器
// 定位器 IDA 插件安装 + 离线恢复流水线（提取/验证/求解/提升）运行与结果展示

class MetadataRecoveryPage {
    constructor() {
        this._bound = false;
        this._running = false;
        this._loadExportSeq = 0;
    }

    init() {
        this._bindEvents();
        this.refreshStatus();
    }

    stop() {}

    _bindEvents() {
        if (this._bound) return;
        this._bound = true;
        const installBtn = document.getElementById('metadata-recovery-btn-install-plugin');
        if (installBtn) installBtn.addEventListener('click', () => this.installPlugin());
        const browseBtn = document.getElementById('metadata-recovery-btn-browse-ida');
        if (browseBtn) browseBtn.addEventListener('click', () => this.browseIdaDir());
        const runBtn = document.getElementById('metadata-recovery-btn-run');
        if (runBtn) runBtn.addEventListener('click', () => this.run());
        const loadBtn = document.getElementById('metadata-recovery-btn-load-export');
        if (loadBtn) loadBtn.addEventListener('click', () => this.loadExport());
        const rankSel = document.getElementById('metadata-recovery-candidate-rank');
        if (rankSel) rankSel.addEventListener('change', () => this.loadExport());
    }

    // ---- 步骤 3：导入定位器导出 ----------------------------------------

    loadExport() {
        if (!pywebview || !pywebview.api || !pywebview.api.metadata_recovery_load_export) return;
        const pathInput = document.getElementById('metadata-recovery-export-path');
        const rankSel = document.getElementById('metadata-recovery-candidate-rank');
        const infoEl = document.getElementById('metadata-recovery-export-info');
        const path = pathInput ? pathInput.value.trim() : '';
        if (!path) {
            if (infoEl) infoEl.innerHTML = '请先选择 locate_candidates.json 或导出目录。';
            return;
        }
        if (infoEl) infoEl.textContent = '正在载入导出...';
        const rank = rankSel && rankSel.value ? rankSel.value : 1;
        // 快速切换 rank 时并发请求，慢响应后到会覆盖新结果：只采纳最新一次请求
        const requestId = ++this._loadExportSeq;
        pywebview.api.metadata_recovery_load_export(path, rank)
            .then((result) => {
                if (requestId !== this._loadExportSeq) return;
                this.renderExport(result);
            })
            .catch((error) => {
                if (requestId !== this._loadExportSeq) return;
                if (infoEl) infoEl.innerHTML = `<i class="fas fa-times-circle" style="color:#e74c3c;"></i> 载入失败：${escapeHtml(String(error))}`;
            });
    }

    _fillRankSelect(candidates) {
        const rankSel = document.getElementById('metadata-recovery-candidate-rank');
        if (!rankSel) return;
        const current = rankSel.value;
        rankSel.innerHTML = '';
        for (const c of candidates || []) {
            const opt = document.createElement('option');
            opt.value = c.rank;
            opt.textContent = `#${c.rank} ${c.name || '?'} (score=${c.score != null ? c.score : '?'})`
                + (c.has_decompile ? '' : ' — 无反编译文本');
            rankSel.appendChild(opt);
        }
        if (current && [...rankSel.options].some(o => o.value === current)) {
            rankSel.value = current;
        }
    }

    renderExport(result) {
        const infoEl = document.getElementById('metadata-recovery-export-info');
        const textEl = document.getElementById('metadata-recovery-decompile-text');
        const hexEl = document.getElementById('metadata-recovery-table-hex');
        const fileEl = document.getElementById('metadata-recovery-decompile-file');
        if (!infoEl) return;
        if (!result || !result.success) {
            const errors = (result && result.errors || ['未知错误']).join('；');
            infoEl.innerHTML = `<i class="fas fa-times-circle" style="color:#e74c3c;"></i> 载入失败：${escapeHtml(errors)}`;
            return;
        }
        this._fillRankSelect(result.candidates);

        let html = '';
        if (result.verdict) {
            const ok = result.verdict === 'PASS';
            html += `<div><i class="fas ${ok ? 'fa-check-circle' : 'fa-exclamation-circle'}" style="color:${ok ? '#27ae60' : '#f39c12'};"></i> `
                + `定位器裁决：<b>${escapeHtml(result.verdict)}</b></div>`;
        }
        html += `<div>候选：<b>#${result.rank} ${escapeHtml(result.candidate_name || '')}</b>`
            + `（score=${result.score != null ? result.score : '?'}）</div>`;
        html += `<div>替换表 hex：${result.table_hex
            ? '<i class="fas fa-check" style="color:#27ae60;"></i> 已载入（256 字节）'
            : '<i class="fas fa-times" style="color:#e74c3c;"></i> 缺失'}</div>`;
        html += `<div>反编译文本：${result.decompile_text
            ? `<i class="fas fa-check" style="color:#27ae60;"></i> 已载入（${result.decompile_text.length} 字符）`
            : '<i class="fas fa-times" style="color:#e74c3c;"></i> 缺失'}</div>`;
        for (const err of result.errors || []) {
            html += `<div style="color:#f39c12;"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(err)}</div>`;
        }
        infoEl.innerHTML = html;

        if (textEl && result.decompile_text) textEl.value = result.decompile_text;
        if (hexEl && result.table_hex) hexEl.value = result.table_hex;
        if (fileEl && result.decompile_file) {
            fileEl.value = result.decompile_file;
        } else if (fileEl && result.decompile_text) {
            fileEl.value = ''; // 文本已直接载入，清空文件输入避免歧义
        }
    }

    refreshStatus() {
        if (!pywebview || !pywebview.api || !pywebview.api.metadata_recovery_status) return;
        pywebview.api.metadata_recovery_status().then((result) => {
            const statusEl = document.getElementById('metadata-recovery-plugin-status');
            const outEl = document.getElementById('metadata-recovery-out-dir');
            if (outEl && result && result.success) outEl.textContent = result.data.out_dir;
            if (result && result.success && result.data.derived) {
                this._applyDerived(result.data.derived);
            }
            if (!statusEl || !result || !result.success) return;
            const dir = result.data.ida_plugins_dir || '未探测到';
            const installed = result.data.plugin_installed;
            statusEl.innerHTML = (installed
                ? '<i class="fas fa-check" style="color:#27ae60;"></i> 插件已安装：'
                : '<i class="fas fa-times" style="color:#e74c3c;"></i> 插件未安装（自动探测到）：')
                + `<code>${escapeHtml(dir)}</code>`;
        }).catch(() => {});
    }

    // 从设置页配置的游戏目录自动推导 metadata / GameAssembly.dll（输入为空时回填）
    _applyDerived(derived) {
        const hint = document.getElementById('metadata-recovery-derived-hint');
        const metaInput = document.getElementById('metadata-recovery-metadata');
        const dllInput = document.getElementById('metadata-recovery-dll');
        if (!derived.derived) {
            if (hint) hint.innerHTML = '未配置游戏路径：请先在「设置」页填写，或手动选择文件。';
            return;
        }
        if (metaInput && !metaInput.value) metaInput.value = derived.metadata_path;
        if (dllInput && !dllInput.value) dllInput.value = derived.dll_path;
        if (!hint) return;
        const missing = [];
        if (!derived.metadata_exists) missing.push('global-metadata.dat 不存在');
        if (!derived.dll_exists) missing.push('GameAssembly.dll 不存在');
        hint.innerHTML = missing.length
            ? `<i class="fas fa-exclamation-triangle" style="color:#f39c12;"></i> `
                + `已从游戏目录自动推导（${missing.join('；')}），请检查游戏目录或手动选择文件。`
            : '<i class="fas fa-check" style="color:#27ae60;"></i> 已从游戏目录自动推导（输入框为空时自动回填，可手动覆盖）。';
    }

    browseIdaDir() {
        if (pywebview && pywebview.api && pywebview.api.browse_folder) {
            pywebview.api.browse_folder('metadata-recovery-ida-dir');
        }
    }

    installPlugin() {
        const dir = document.getElementById('metadata-recovery-ida-dir').value.trim();
        const statusEl = document.getElementById('metadata-recovery-plugin-status');
        if (statusEl) statusEl.textContent = '正在安装插件...';
        pywebview.api.metadata_recovery_install_ida_plugin(dir)
            .then((result) => {
                if (!statusEl) return;
                if (result && result.success) {
                    statusEl.innerHTML = '<i class="fas fa-check" style="color:#27ae60;"></i> '
                        + `插件安装成功：<code>${escapeHtml(result.data.plugin_path)}</code>`
                        + '<br>重启 IDA 后按 Ctrl-Alt-Shift-M 运行定位器';
                } else {
                    statusEl.textContent = '安装失败：' + (result ? result.message : '未知错误');
                }
            })
            .catch((error) => {
                if (statusEl) statusEl.textContent = '安装失败：' + error;
            });
    }

    _collectConfig() {
        const val = (id) => {
            const el = document.getElementById(id);
            return el ? el.value.trim() : '';
        };
        return {
            metadata_path: val('metadata-recovery-metadata'),
            reference_path: val('metadata-recovery-reference'),
            decompile_file: val('metadata-recovery-decompile-file'),
            decompile_text: val('metadata-recovery-decompile-text'),
            game_dll: val('metadata-recovery-dll'),
            table_hex: val('metadata-recovery-table-hex'),
            expect_sha256: val('metadata-recovery-expect-sha'),
            candidate_profile: val('metadata-recovery-candidate-profile'),
        };
    }

    _validate(config) {
        if (!config.metadata_path) return '请选择加密的 global-metadata.dat';
        if (!config.decompile_file && !config.decompile_text && !config.candidate_profile) {
            return '请提供反编译文本（文件或粘贴）或已有 candidate_profile.json';
        }
        if (config.table_hex && !/^[0-9a-fA-F]{512}$/.test(config.table_hex)) {
            return '替换表 hex 应为 512 位十六进制字符（256 字节）';
        }
        if (config.expect_sha256 && !/^[0-9a-fA-F]{64}$/.test(config.expect_sha256)) {
            return '期望 SHA-256 应为 64 位十六进制字符';
        }
        return '';
    }

    run() {
        if (this._running) return;
        const config = this._collectConfig();
        const error = this._validate(config);
        if (error) {
            showMessage('输入不完整', error);
            return;
        }
        this._running = true;

        const modal = new ProgressModal('Metadata 恢复');
        modal.addLog('正在启动恢复流水线...');
        pywebview.api.metadata_recovery_run(config, modal.id)
            .then((result) => {
                this._running = false;
                if (!result) {
                    modal.complete(false, '恢复失败：无返回结果');
                    return;
                }
                if (result.message === '已取消') {
                    modal.cancel();
                    return;
                }
                if (!result.success && !result.verdicts) {
                    modal.complete(false, '恢复失败：' + (result.message || '未知错误'));
                    return;
                }
                modal.complete(result.success,
                    result.success ? '恢复完成，结果已生成' : '恢复完成，部分阶段未通过');
                this.renderResult(result);
            })
            .catch((error) => {
                this._running = false;
                modal.complete(false, '恢复过程中发生错误：' + error);
            });
    }

    _verdictBadge(verdict) {
        const map = {
            'PASS': ['<i class="fas fa-check-circle"></i>', '#27ae60'],
            'PASS_WITH_REVIEW': ['<i class="fas fa-exclamation-circle"></i>', '#f39c12'],
            'FAIL': ['<i class="fas fa-times-circle"></i>', '#e74c3c'],
            'SKIP': ['<i class="fas fa-forward"></i>', '#7f8c8d'],
        };
        const [icon, color] = map[verdict] || map.SKIP;
        return `<span style="color:${color}; font-weight:600;">${icon} ${verdict}</span>`;
    }

    _stageNames() {
        return {
            extract: '参数提取',
            verify: '参数验证',
            solve: '31 段映射求解',
            apply: '正式 profile 提升',
        };
    }

    renderResult(result) {
        const box = document.getElementById('metadata-recovery-result');
        const verdictsEl = document.getElementById('metadata-recovery-verdicts');
        const outputsEl = document.getElementById('metadata-recovery-outputs');
        const outEl = document.getElementById('metadata-recovery-out-dir');
        if (!box || !verdictsEl || !outputsEl) return;

        box.style.display = 'block';
        if (outEl && result.run_dir) outEl.textContent = result.run_dir;

        const names = this._stageNames();
        let verdictHtml = '';
        for (const [stage, verdict] of Object.entries(result.verdicts || {})) {
            verdictHtml += `<div style="margin: 2px 0;">${names[stage] || stage}：${this._verdictBadge(verdict)}</div>`;
        }
        verdictsEl.innerHTML = verdictHtml;

        let outputsHtml = '';
        for (const [key, path] of Object.entries(result.outputs || {})) {
            outputsHtml += `<div><code style="word-break: break-all;">${escapeHtml(path)}</code></div>`;
        }
        outputsEl.innerHTML = outputsHtml || '<div>（无输出文件）</div>';

        // 滚动到结果卡片
        box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// 全局实例（与其它页面控制器一致：DOMContentLoaded 时创建）
let metadataRecoveryPage;

document.addEventListener('DOMContentLoaded', function () {
    metadataRecoveryPage = new MetadataRecoveryPage();
});
