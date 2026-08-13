// metadata-recovery.js - Metadata 恢复页面控制器
// v2 全自动流水线：环境检查（capstone）→ 输入文件 → 运行（定位/提取/验证/求解/重建）

class MetadataRecoveryPage {
    constructor() {
        this._bound = false;
        this._running = false;
        this._installing = false;
    }

    init() {
        this._bindEvents();
        this.updateStepBadges(1);
        this.refreshStatus();
    }

    stop() {}

    // 步骤徽标动态状态：step 为当前步骤号（1-3）
    updateStepBadges(step) {
        const badgeIds = [
            'metadata-recovery-badge-1',
            'metadata-recovery-badge-2',
            'metadata-recovery-badge-3',
        ];
        for (let i = 0; i < badgeIds.length; i++) {
            const badge = document.getElementById(badgeIds[i]);
            if (!badge) continue;
            if (!badge.dataset.label) badge.dataset.label = badge.textContent.trim();
            badge.classList.remove('current');
            badge.style.cssText = '';
            badge.innerHTML = badge.dataset.label;
            if (i === step - 1) {
                badge.classList.add('current');
            } else if (i < step - 1) {
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
        runBtn.innerHTML = '<i class="fas fa-play"></i> 开始恢复';
    }

    _bindEvents() {
        if (this._bound) return;
        this._bound = true;
        const installBtn = document.getElementById('metadata-recovery-btn-install-capstone');
        if (installBtn) installBtn.addEventListener('click', () => this.installCapstone());
        const runBtn = document.getElementById('metadata-recovery-btn-run');
        if (runBtn) runBtn.addEventListener('click', () => this.run());
    }

    // ---- 步骤 1：环境检查（capstone） -----------------------------------

    refreshStatus() {
        if (!pywebview || !pywebview.api || !pywebview.api.metadata_recovery_status) return;
        pywebview.api.metadata_recovery_status().then((result) => {
            const statusEl = document.getElementById('metadata-recovery-capstone-status');
            const installBtn = document.getElementById('metadata-recovery-btn-install-capstone');
            const outEl = document.getElementById('metadata-recovery-out-dir');
            if (outEl && result && result.success) {
                outEl.textContent = result.data.out_dir;
                this._updateOpenDirButton();
            }
            if (result && result.success && result.data.derived) {
                this._applyDerived(result.data.derived);
            }
            if (!statusEl || !result || !result.success) return;
            if (result.data.capstone_available) {
                statusEl.innerHTML = '<i class="fas fa-check" style="color:#27ae60;"></i> '
                    + 'capstone 已就绪，可直接运行恢复。';
                if (installBtn) installBtn.style.display = 'none';
                this.updateStepBadges(2);
            } else {
                statusEl.innerHTML = '<i class="fas fa-times" style="color:#e74c3c;"></i> '
                    + '缺少 capstone 反汇编库（定位/提取需要）。点击下方按钮一键安装，'
                    + '或手动运行 <code>pip install capstone</code>。';
                if (installBtn) installBtn.style.display = '';
            }
        }).catch(() => {});
    }

    installCapstone() {
        if (this._installing) return;
        this._installing = true;
        const statusEl = document.getElementById('metadata-recovery-capstone-status');
        if (statusEl) statusEl.textContent = '正在安装 capstone...';

        const modal = new ProgressModal('安装 capstone');
        modal.addLog('正在安装 capstone...');
        pywebview.api.metadata_recovery_install_capstone(modal.id)
            .then((result) => {
                this._installing = false;
                if (!result) {
                    modal.complete(false, '安装失败：无返回结果');
                    return;
                }
                if (result.success) {
                    modal.complete(true, 'capstone 安装完成');
                    this.refreshStatus();
                } else {
                    modal.complete(false, '安装失败：' + (result.message || '未知错误'));
                    this.refreshStatus();
                }
            })
            .catch((error) => {
                this._installing = false;
                modal.complete(false, '安装过程中发生错误：' + error);
                this.refreshStatus();
            });
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

    // ---- 步骤 3：运行 ------------------------------------------------

    _collectConfig() {
        const val = (id) => {
            const el = document.getElementById(id);
            return el ? el.value.trim() : '';
        };
        return {
            metadata_path: val('metadata-recovery-metadata'),
            game_dll: val('metadata-recovery-dll'),
            expect_sha256: val('metadata-recovery-expect-sha'),
        };
    }

    _validate(config) {
        if (!config.metadata_path) return '请选择加密的 global-metadata.dat';
        if (!config.game_dll) return '请选择 GameAssembly.dll（定位/提取需要反汇编它）';
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
        this.updateStepBadges(3);
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
            'REVIEW': ['<i class="fas fa-exclamation-circle"></i>', '#f39c12', '有疑点，查看报告'],
            'PASS_WITH_REVIEW': ['<i class="fas fa-exclamation-circle"></i>', '#f39c12', '有疑点，查看报告'],
            'FAIL': ['<i class="fas fa-times-circle"></i>', '#e74c3c', '未通过'],
            'SKIP': ['<i class="fas fa-forward"></i>', '#7f8c8d', '已跳过'],
        };
        const [icon, color, label] = map[verdict] || map.SKIP;
        return `<span style="color:${color}; font-weight:600;">${icon} ${verdict}（${label}）</span>`;
    }

    // 存在 FAIL / REVIEW 时输出排查建议
    _troubleshootTips(verdicts) {
        const names = this._stageNames();
        const tips = [];
        if (verdicts.locate === 'FAIL') {
            tips.push('定位失败：GameAssembly.dll 中未找到解密入口特征。常见原因：DLL 版本异常或文件不完整、xorshift 算法变体（当前支持 xorshift64(13,7,17)）。');
        }
        if (verdicts.extract === 'FAIL') {
            tips.push('提取失败：常见原因：DLL 与游戏版本不匹配、capstone 反汇编异常。可查看 run-report.json 中 extract.errors。');
        }
        if (verdicts.verify === 'FAIL') {
            tips.push('验证失败：打开 run-report.md 查看哪道验证门未通过。常见原因：metadata 文件与 DLL 版本不一致（解密参数对不上）。');
        }
        if (verdicts.solve === 'REVIEW') {
            tips.push('求解有疑点：31 节映射存在待人工确认项，查看 run-report.json 中 solve.review 列表，凭证据判断。');
        }
        if (verdicts.solve === 'FAIL') {
            tips.push('求解失败：无法唯一确定 31 节映射，查看 run-report.json 中 solve 阶段错误信息。');
        }
        if (verdicts.rebuild === 'FAIL') {
            tips.push('重建自验证未通过：四重门有失败项，查看 run-report.json 中 rebuild.gates。');
        }
        if (verdicts.expect_sha === 'FAIL') {
            tips.push('期望 SHA 比对失败：重建结果与期望不一致，请核对期望值来源是否正确。');
        }
        for (const [stage, v] of Object.entries(verdicts)) {
            if (v === 'REVIEW') {
                tips.push(`阶段「${names[stage] || stage}」有疑点：查看报告中的 review 列表，凭证据人工判断后决定是否继续。`);
            }
        }
        return tips;
    }

    // 输出文件 key → 一句话用途
    _outputDescriptions() {
        return {
            standard_rebuilt: '★ 重建的标准文件（给 Il2CppDumper 用）',
            profile: '解密参数 profile（JSON，含 31 节映射）',
            report_json: '运行报告（JSON，各阶段详细证据）',
            report_md: '运行报告（Markdown）',
        };
    }

    _stageNames() {
        return {
            locate: '定位（解密入口）',
            extract: '参数提取',
            verify: '结构验证',
            solve: '31 节映射求解',
            rebuild: '标准文件重建',
            expect_sha: '期望 SHA 比对',
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
            + '<span style="color:#f39c12;">REVIEW=有疑点需人工判断</span> · '
            + '<span style="color:#e74c3c;">FAIL=未通过</span></div>';
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
