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
        this.updateStepBadges(1);
        this.refreshStatus();
    }

    stop() {}

    // 步骤徽标动态状态：step 为当前步骤号（1-6）
    updateStepBadges(step) {
        const badgeIds = [
            'metadata-recovery-badge-1',
            'metadata-recovery-badge-2',
            'metadata-recovery-badge-3',
            'metadata-recovery-badge-4',
            'metadata-recovery-badge-5',
        ];
        // 徽标覆盖区间：步骤 1-2 → badge0，步骤 3/4/5/6 → badge1~4
        const currentIdx = Math.max(0, Math.min(badgeIds.length - 1, step - 2));
        for (let i = 0; i < badgeIds.length; i++) {
            const badge = document.getElementById(badgeIds[i]);
            if (!badge) continue;
            if (!badge.dataset.label) badge.dataset.label = badge.textContent.trim();
            badge.classList.remove('current');
            badge.style.cssText = '';
            badge.innerHTML = badge.dataset.label;
            if (i === currentIdx) {
                badge.classList.add('current');
            } else if (i < currentIdx) {
                // 已完成步骤：绿色填充 + 对勾（内联样式，不依赖 CSS 类）
                badge.style.cssText = 'background:#27ae60; border-color:#27ae60; color:#fff; opacity:0.9;';
                badge.innerHTML = badge.dataset.label + ' <i class="fas fa-check" style="font-size:0.85em;"></i>';
            }
        }
    }

    // 输入框后追加/移除「已自动填充」小标签
    _setFillTag(anchorId, tagId, labelText, show) {
        const anchor = document.getElementById(anchorId);
        if (!anchor) return;
        let tag = document.getElementById(tagId);
        if (show) {
            if (!tag) {
                tag = document.createElement('small');
                tag.id = tagId;
                tag.className = 'form-hint';
                tag.style.cssText = 'color:#27ae60; font-weight:600; margin-top:4px;';
                anchor.insertAdjacentElement('afterend', tag);
            }
            tag.innerHTML = `<i class="fas fa-check-circle"></i> ${labelText}`;
            tag.style.display = 'block';
        } else if (tag) {
            tag.style.display = 'none';
        }
    }

    // 卡片短暂高亮提示（2 秒后移除，内联样式，不依赖 CSS 类）
    _highlightCard(cardId) {
        const card = document.getElementById(cardId);
        if (!card) return;
        card.style.boxShadow = '0 0 0 2px #27ae60, 0 4px 12px rgba(39,174,96,0.25)';
        card.style.transition = 'box-shadow 0.3s ease';
        setTimeout(() => { card.style.boxShadow = ''; }, 2000);
    }

    // 「打开输出目录」按钮：输出目录为「—」或空时禁用
    _updateOpenDirButton() {
        const openBtn = document.getElementById('metadata-recovery-btn-open-out');
        const outEl = document.getElementById('metadata-recovery-out-dir');
        if (!openBtn) return;
        const text = outEl ? outEl.textContent.trim() : '';
        openBtn.disabled = !text || text === '—';
    }

    // 运行按钮恢复可点状态
    _restoreRunButton() {
        const runBtn = document.getElementById('metadata-recovery-btn-run');
        if (!runBtn) return;
        runBtn.disabled = false;
        runBtn.innerHTML = '<i class="fas fa-play"></i> 开始完整恢复';
    }

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
        if (!candidates || !candidates.length) {
            rankSel.innerHTML = '<option value="">请先在上方载入导出</option>';
            rankSel.disabled = true;
            return;
        }
        for (const c of candidates) {
            const opt = document.createElement('option');
            opt.value = c.rank;
            opt.textContent = `候选 #${c.rank}：${c.name || '?'}（匹配分 ${c.score != null ? c.score : '?'}）`
                + (c.has_decompile ? '' : '（该候选无反编译文本，需在步骤 5 手动粘贴）');
            rankSel.appendChild(opt);
        }
        rankSel.disabled = false;
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
            this._fillRankSelect(null);
            this._setFillTag('metadata-recovery-decompile-text', 'metadata-recovery-tag-decompile-text', '', false);
            this._setFillTag('metadata-recovery-table-hex', 'metadata-recovery-tag-table-hex', '', false);
            const errors = (result && result.errors || ['未知错误']).join('；');
            infoEl.innerHTML = `<i class="fas fa-times-circle" style="color:#e74c3c;"></i> 载入失败：${escapeHtml(errors)}`;
            return;
        }
        this._fillRankSelect(result.candidates);
        this.updateStepBadges(6);

        let html = '<div style="margin-bottom:6px; padding:6px 10px; background:rgba(39,174,96,0.1); border-left:3px solid #27ae60; border-radius:4px;">'
            + `<i class="fas fa-check-circle" style="color:#27ae60;"></i> 载入成功：候选 #${escapeHtml(result.rank)} 已就绪，替换表与反编译文本已自动填入步骤 5</div>`;
        if (result.verdict) {
            const ok = result.verdict === 'PASS';
            html += `<div><i class="fas ${ok ? 'fa-check-circle' : 'fa-exclamation-circle'}" style="color:${ok ? '#27ae60' : '#f39c12'};"></i> `
                + `定位器裁决：<b>${escapeHtml(result.verdict)}</b></div>`;
        }
        html += `<div>候选：<b>#${result.rank} ${escapeHtml(result.candidate_name || '')}</b>`
            + `（匹配分 ${result.score != null ? result.score : '?'}）</div>`;
        html += `<div>替换表 hex：${result.table_hex
            ? '<i class="fas fa-check" style="color:#27ae60;"></i> 已载入（256 字节）'
            : '<i class="fas fa-times" style="color:#e74c3c;"></i> 缺失'}</div>`;
        html += `<div>反编译文本：${result.decompile_text
            ? `<i class="fas fa-check" style="color:#27ae60;"></i> 已载入（${result.decompile_text.length} 字符）`
            : '<i class="fas fa-times" style="color:#e74c3c;"></i> 缺失'}</div>`;
        for (const err of result.errors || []) {
            html += `<div style="color:#f39c12;"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(err)}</div>`;
        }
        if (fileEl && result.decompile_file) {
            fileEl.value = result.decompile_file;
        } else if (fileEl && result.decompile_text) {
            fileEl.value = ''; // 文本已直接载入，清空文件输入避免歧义
            html += '<div class="form-hint" style="margin-top:4px;"><i class="fas fa-info-circle" style="color:#27ae60;"></i> '
                + '反编译文本已直接载入步骤 5，原文件路径已清空，无需重复选择</div>';
        }
        infoEl.innerHTML = html;

        if (textEl && result.decompile_text) {
            textEl.value = result.decompile_text;
            this._setFillTag('metadata-recovery-decompile-text', 'metadata-recovery-tag-decompile-text', '已自动填充（来源：IDA 导出）', true);
        } else {
            this._setFillTag('metadata-recovery-decompile-text', 'metadata-recovery-tag-decompile-text', '', false);
        }
        if (hexEl && result.table_hex) {
            hexEl.value = result.table_hex;
            this._setFillTag('metadata-recovery-table-hex', 'metadata-recovery-tag-table-hex', '已自动填充（来源：IDA 导出）', true);
        } else {
            this._setFillTag('metadata-recovery-table-hex', 'metadata-recovery-tag-table-hex', '', false);
        }
        this._highlightCard('metadata-recovery-card-input');
        this._highlightCard('metadata-recovery-card-decompile');
    }

    refreshStatus() {
        if (!pywebview || !pywebview.api || !pywebview.api.metadata_recovery_status) return;
        pywebview.api.metadata_recovery_status().then((result) => {
            const statusEl = document.getElementById('metadata-recovery-plugin-status');
            const outEl = document.getElementById('metadata-recovery-out-dir');
            if (outEl && result && result.success) {
                outEl.textContent = result.data.out_dir;
                this._updateOpenDirButton();
            }
            if (result && result.success && result.data.derived) {
                this._applyDerived(result.data.derived);
            }
            if (!statusEl || !result || !result.success) return;
            const dir = result.data.ida_plugins_dir || '';
            const installed = result.data.plugin_installed;
            if (!dir) {
                statusEl.innerHTML = '<i class="fas fa-exclamation-circle" style="color:#f39c12;"></i> '
                    + '未找到 IDA 安装。若没有 IDA Pro，可跳过本卡：手动从 locate_candidates.json 复制 table_hex 粘贴到步骤 5，并粘贴反编译文本。';
            } else if (!installed) {
                statusEl.innerHTML = '<i class="fas fa-times" style="color:#e74c3c;"></i> '
                    + `检测到 IDA plugins 目录：<code>${escapeHtml(dir)}</code>。点击下方按钮一键安装，然后重启 IDA。`;
            } else {
                statusEl.innerHTML = '<i class="fas fa-check" style="color:#27ae60;"></i> '
                    + `插件已安装：<code>${escapeHtml(dir)}</code>`;
            }
        }).catch(() => {});
    }

    // 从设置页配置的游戏目录自动推导 metadata / GameAssembly.dll（输入为空时回填）
    _applyDerived(derived) {
        const hint = document.getElementById('metadata-recovery-derived-hint');
        const metaInput = document.getElementById('metadata-recovery-metadata');
        const dllInput = document.getElementById('metadata-recovery-dll');
        if (!derived.derived) {
            if (hint) hint.innerHTML = '未配置游戏路径，无法自动推导文件。 '
                + `<button class="action-btn secondary" style="margin:4px 6px; padding:4px 10px; font-size:12px;" onclick="goAndShow('settings')">去设置页配置游戏路径</button>`
                + '或手动选择文件。';
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
                    this.updateStepBadges(3);
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
        this.updateStepBadges(6);
        const runBtn = document.getElementById('metadata-recovery-btn-run');
        if (runBtn) {
            runBtn.disabled = true;
            runBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 运行中…';
        }

        const modal = new ProgressModal('Metadata 恢复');
        modal.addLog('正在启动恢复流水线...');
        pywebview.api.metadata_recovery_run(config, modal.id)
            .then((result) => {
                this._running = false;
                this._restoreRunButton();
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
                this._restoreRunButton();
                modal.complete(false, '恢复过程中发生错误：' + error);
            });
    }

    _verdictBadge(verdict) {
        const map = {
            'PASS': ['<i class="fas fa-check-circle"></i>', '#27ae60', '通过'],
            'PASS_WITH_REVIEW': ['<i class="fas fa-exclamation-circle"></i>', '#f39c12', '有疑点，查看报告'],
            'FAIL': ['<i class="fas fa-times-circle"></i>', '#e74c3c', '未通过'],
            'SKIP': ['<i class="fas fa-forward"></i>', '#7f8c8d', '已跳过'],
        };
        const [icon, color, label] = map[verdict] || map.SKIP;
        return `<span style="color:${color}; font-weight:600;">${icon} ${verdict}（${label}）</span>`;
    }

    // 存在 FAIL / PASS_WITH_REVIEW / 求解 SKIP 时输出排查建议
    _troubleshootTips(verdicts) {
        const names = this._stageNames();
        const tips = [];
        if (verdicts.extract === 'FAIL') {
            tips.push('提取失败：常见原因：反编译文本未载入或内容不完整、替换表 hex 格式错误。');
        }
        if (verdicts.verify === 'FAIL') {
            tips.push('验证失败：1) 打开 verify-report.md 查看哪道验证门未通过；2) 常见原因：反编译文本不完整（只复制了部分函数体）、替换表 hex 错误、参考文件版本与目标不匹配。');
        }
        if (verdicts.solve === 'SKIP') {
            tips.push('SKIP：未提供参考标准文件，仅执行了提取与验证，31 段映射求解未运行。');
        }
        for (const [stage, v] of Object.entries(verdicts)) {
            if (v === 'PASS_WITH_REVIEW') {
                tips.push(`阶段「${names[stage] || stage}」有疑点：查看对应报告中的「需复核项」，凭证据人工判断后决定是否继续。`);
            }
        }
        return tips;
    }

    // 输出文件 key → 一句话用途
    _outputDescriptions() {
        return {
            candidate_profile: '候选参数',
            extract_report_json: '提取报告（JSON）',
            verify_report_json: '验证报告（JSON）',
            verify_report_md: '验证报告',
            section_map: '数据区映射',
            solve_report_json: '求解报告（JSON）',
            solve_report_md: '求解报告',
            standard_rebuilt: '重建的标准文件',
            profile: '★ 正式 profile（给 Il2CppDumper 用）',
            apply_report_json: '提升报告（JSON）',
            apply_report_md: '提升报告',
        };
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
        if (outEl && result.run_dir) {
            outEl.textContent = result.run_dir;
        } else if (outEl) {
            outEl.textContent = '—';
        }
        this._updateOpenDirButton();

        const names = this._stageNames();
        let verdictHtml = '<div class="form-hint" style="margin:0 0 6px;">图例：'
            + '<span style="color:#27ae60;">PASS=通过</span> · '
            + '<span style="color:#f39c12;">PASS_WITH_REVIEW=基本通过有疑点</span> · '
            + '<span style="color:#e74c3c;">FAIL=未通过</span> · '
            + '<span style="color:#7f8c8d;">SKIP=未执行（缺前置输入）</span></div>';
        for (const [stage, verdict] of Object.entries(result.verdicts || {})) {
            verdictHtml += `<div style="margin: 2px 0;">${names[stage] || stage}：${this._verdictBadge(verdict)}</div>`;
        }
        const tips = this._troubleshootTips(result.verdicts || {});
        if (tips.length) {
            verdictHtml += '<div class="form-hint" style="margin:8px 0 0; padding:8px 10px; background:rgba(231,76,60,0.07); border-left:3px solid #e74c3c; border-radius:4px; line-height:1.8;">'
                + `<b>排查建议</b><br>${tips.join('<br>')}</div>`;
        }
        verdictsEl.innerHTML = verdictHtml;

        const desc = this._outputDescriptions();
        let outputsHtml = '';
        for (const [key, path] of Object.entries(result.outputs || {})) {
            const label = desc[key] || key;
            const fileName = String(path).split(/[\\/]/).pop();
            outputsHtml += `<div>${label}：<code title="${escapeHtml(path)}" style="word-break: break-all;">${escapeHtml(fileName)}</code></div>`;
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
