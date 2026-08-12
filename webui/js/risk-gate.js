// ============================
// 风险服务统一门控模块
// ============================
// 对存在账号/使用风险的服务（游戏加速、输入反检测等）提供统一的前端门控：
//   - 源页面首次进入强制阅读风险须知并勾选同意后才解锁内容
//   - Launcher 配置页勾选此类服务时就地弹出同意弹窗
//   - 免责声明文本规范化并集中于此（单一事实来源），重读入口可随时查看
// 新增风险服务只需在 RISK_SERVICES 注册一条记录：
//   - 源页面：包一层 data-risk-overlay 容器 + init() 调 RiskGate.gatePage(id)
//   - Launcher 配置页：复选框加 data-risk-service 属性
//   门控与文本自动生效，无需再写内联逻辑。

const RISK_SERVICES = {
    speed: {
        id: 'speed',
        name: '游戏加速',
        consentKey: 'speed.disclaimer_accepted',
        specific: '游戏加速通过 DLL 注入的方式控制游戏进程的时间相关逻辑，从而改变游戏运行速度。',
        launcherCheckboxId: 'launcher-work-speed',
    },
    input_bypass: {
        id: 'input_bypass',
        name: '输入反检测',
        consentKey: 'input_bypass.disclaimer_accepted',
        specific: '输入反检测通过注入 hook 对游戏上报的输入数据进行调整，使其更接近真实输入特征。',
        launcherCheckboxId: 'launcher-work-input-bypass',
    },
    cheat: {
        id: 'cheat',
        name: '作弊工具箱',
        consentKey: 'cheat.disclaimer_accepted',
        specific: '作弊工具箱通过 MinHook 对游戏客户端进行原生 detour，修改游戏运行数值（如伤害倍率）。',
        consentLabel: '我已阅读并同意上述使用与分发协议及风险须知，并自愿承担相关风险',
        hideUntilConsent: true, // 未同意前在 Launcher 配置页隐藏该选项，须先在源页面同意
        // 仅作弊工具箱显示的协议章节（追加于公共风险须知之后）
        agreementSections: [
            {
                title: '作者承诺',
                items: [
                    '不向任何非 LCTA 开发者分发作弊者工具箱及其工作流源码。',
                    '不向任何人分发密钥数据。',
                    '不在任何平台分发密钥数据。',
                    '不进行任何出售密钥的行为。',
                    '不在任何平台将作弊者工具箱的功能作为卖点介绍。',
                ],
            },
            {
                title: '使用者义务',
                items: [
                    '不在任何平台分发密钥数据。',
                    '不向任何人分发密钥数据。',
                    '不进行任何出售密钥的行为。',
                    '不分发经过解密的 LCTA 工具箱。',
                    '不在任何公开平台宣传作弊者工具箱的功能。',
                ],
            },
            {
                title: '服务可用性说明',
                items: [
                    '作弊者工具箱的功能依赖作者的在线服务支持，该服务可能随时不可用或失效，敬请谅解。',
                    '如您具备相应技术能力并愿意参与维护，欢迎加入 QQ 交流群：1081988645。',
                ],
            },
        ],
    },
    cg: {
        id: 'cg',
        name: '加载页 CG 替换',
        consentKey: 'cg.disclaimer_accepted',
        specific: '加载页 CG 替换会直接修改游戏存档文件（锁定加载页背景图）并改写 Unity 缓存 bundle 中的贴图数据，操作需在游戏完全退出时进行。',
    },
};

const RiskGate = {
    _launcherBound: false,

    // 规范化免责声明（全部风险服务共用，按小节组织）
    _commonSections: [
        {
            title: '功能说明',
            items: [
                '本功能通过对游戏客户端进程进行注入与修改以实现效果，属于对游戏客户端的非官方改动，与游戏官方服务条款可能存在冲突。',
            ],
        },
        {
            title: '风险提示',
            items: [
                '游戏官方若实施检测机制，本功能的运行特征在原理上存在被识别的可能，由此可能导致游戏账号受到处罚或产生其他不利后果。',
                '游戏客户端随版本更新而变化，本功能在部分版本上可能失效或表现异常。',
            ],
        },
        {
            title: '免责声明',
            items: [
                '本功能按"现状（as-is）"及"可用（as-available）"提供，开发者不对其正确性、稳定性、安全性、时效性及与特定游戏版本的兼容性作出任何明示或默示的保证。',
                '使用者确认已充分知悉并自愿承担因使用本功能所引发的一切风险与后果，包括但不限于游戏账号受到限制或封禁、数据丢失、设备故障及其他任何直接、间接、附带或惩罚性损失；由此产生的任何主张、索赔或责任，均由使用者自行承担，开发者不承担任何形式的责任。',
                '因使用者使用本功能而违反游戏官方服务条款、相关法律法规或第三方权益所引发的任何争议、诉讼、索赔或损失，由使用者自行负责解决并承担全部责任，与开发者无关。',
            ],
        },
        {
            title: '使用须知',
            items: [
                '本功能仅供学习与研究使用，请勿将其用于违反游戏规则或法律法规的用途。',
                '使用前请充分了解功能原理及上述风险，并自行评估是否启用；启用即视为使用者已完整阅读、理解并同意本风险须知之全部内容。',
                '如对账号安全有所顾虑，建议不要启用本功能。',
            ],
        },
    ],

    consentLabel: '我已了解并自愿承担上述风险',

    getService(id) {
        return RISK_SERVICES[id] || null;
    },

    // 服务的同意文案：优先使用服务自身的 consentLabel，否则回退公共文案
    _consentLabel(service) {
        return (service && service.consentLabel) ? service.consentLabel : this.consentLabel;
    },

    // 读取某服务的同意状态（API 优先，失败回退配置缓存）
    async getConsent(id) {
        const svc = this.getService(id);
        if (!svc) return false;
        try {
            const value = await pywebview.api.get_config_value(svc.consentKey, false);
            return !!value;
        } catch (e) {
            console.error(`RiskGate.getConsent(${id}) error:`, e);
        }
        try {
            if (typeof configManager !== 'undefined') {
                return !!configManager.getCachedValue(svc.consentKey);
            }
        } catch (e) { /* ignore */ }
        return false;
    },

    // 写入同意状态并刷新配置缓存
    async acceptConsent(id) {
        const svc = this.getService(id);
        if (!svc) return false;
        try {
            await pywebview.api.update_config_value(svc.consentKey, true);
            if (typeof configManager !== 'undefined') {
                configManager.setCachedValue(svc.consentKey, true);
            }
            addLogMessage(`已同意「${svc.name}」风险须知`, 'info');
            this.refreshLauncherVisibility();
            return true;
        } catch (e) {
            console.error(`RiskGate.acceptConsent(${id}) error:`, e);
            return false;
        }
    },

    _disclaimerBody(service) {
        const sections = this._commonSections.slice();
        if (service.agreementSections && service.agreementSections.length) {
            sections.push(...service.agreementSections);
        }
        return sections.map(section => {
            const items = section.title === '功能说明'
                ? [service.specific].concat(section.items)
                : section.items;
            return `
                <p class="risk-section-title">${section.title}</p>
                <ul>${items.map(t => `<li>${t}</li>`).join('')}</ul>`;
        }).join('');
    },

    // 页面内覆盖层完整卡片（含勾选框与确认按钮）
    _overlayHTML(service) {
        return `
            <div class="disclaimer-card">
                <div class="disclaimer-icon">⚠️</div>
                <h2>风险须知 — ${service.name}</h2>
                <div class="disclaimer-body">
                    <ul>${this._disclaimerBody(service)}</ul>
                </div>
                <div class="disclaimer-agree">
                    <label class="checkbox-container">
                        <input type="checkbox" id="risk-gate-checkbox-${service.id}">
                        <span class="checkmark"></span>
                        ${this._consentLabel(service)}
                    </label>
                </div>
                <button id="risk-gate-confirm-${service.id}" class="primary-btn">
                    <i class="fas fa-check"></i> 确认
                </button>
            </div>`;
    },

    // 弹窗内容（同意弹窗带勾选框，重读弹窗不带）
    _modalBodyHTML(service, withConsent, modalId) {
        return `
            <div class="disclaimer-body" style="margin:0;">
                <ul>${this._disclaimerBody(service)}</ul>
            </div>
            ${withConsent ? `
            <label class="checkbox-container" style="margin-top:1rem;">
                <input type="checkbox" id="risk-gate-checkbox-${service.id}-${modalId}">
                <span class="checkmark"></span>
                ${this._consentLabel(service)}
            </label>` : ''}`;
    },

    // 源页面门控：未同意则渲染覆盖层并锁定内容，同意后回调 onAccepted
    async gatePage(id, hooks = {}) {
        const svc = this.getService(id);
        if (!svc) return;
        const overlay = document.querySelector(`[data-risk-overlay="${id}"]`);
        if (!overlay) return;
        const accepted = await this.getConsent(id);
        if (accepted) {
            overlay.style.display = 'none';
            if (hooks.onAccepted) hooks.onAccepted();
            return;
        }
        overlay.innerHTML = this._overlayHTML(svc);
        overlay.style.display = 'flex';
        if (hooks.onRejected) hooks.onRejected();
        const checkbox = overlay.querySelector(`#risk-gate-checkbox-${id}`);
        const confirmBtn = overlay.querySelector(`#risk-gate-confirm-${id}`);
        if (confirmBtn) {
            confirmBtn.addEventListener('click', async () => {
                if (checkbox && !checkbox.checked) {
                    showMessage('提示', `请先勾选"${this._consentLabel(svc)}"`);
                    return;
                }
                const ok = await this.acceptConsent(id);
                if (ok) {
                    overlay.style.display = 'none';
                    if (hooks.onAccepted) hooks.onAccepted();
                } else {
                    showMessage('错误', '保存同意状态失败，请重试');
                }
            });
        }
    },

    // 就地同意弹窗（Launcher 配置页勾选未同意服务时触发）
    showConsentModal(id, onAccept) {
        const svc = this.getService(id);
        if (!svc) return;
        const modal = new ModalWindow(`风险须知 — ${svc.name}`, {
            showProgress: false,
            showCancelButton: false,
            showMinimizeButton: false,
            showLog: false,
        });
        const statusEl = document.getElementById(`modal-status-${modal.id}`);
        if (statusEl) {
            statusEl.classList.add('risk-modal-scroll');
            statusEl.innerHTML = this._modalBodyHTML(svc, true, modal.id);
        }
        const footer = document.getElementById(`modal-footer-${modal.id}`);
        if (!footer) return;
        footer.innerHTML = `
            <button class="primary-btn" id="risk-gate-modal-confirm-${modal.id}">确认</button>
            <button class="action-btn" id="risk-gate-modal-cancel-${modal.id}">取消</button>`;
        document.getElementById(`risk-gate-modal-confirm-${modal.id}`).addEventListener('click', async () => {
            const checkbox = document.getElementById(`risk-gate-checkbox-${svc.id}-${modal.id}`);
            if (checkbox && !checkbox.checked) {
                showMessage('提示', `请先勾选"${this._consentLabel(svc)}"`);
                return;
            }
            const ok = await this.acceptConsent(svc.id);
            if (ok) {
                modal.close();
                if (onAccept) onAccept();
            } else {
                showMessage('错误', '保存同意状态失败，请重试');
            }
        });
        document.getElementById(`risk-gate-modal-cancel-${modal.id}`).addEventListener('click', () => modal.close());
    },

    // 重读入口：仅展示规范化文本，不改变同意状态
    showNoticeModal(id) {
        const svc = this.getService(id);
        if (!svc) return;
        const modal = new ModalWindow(`风险须知 — ${svc.name}`, {
            showProgress: false,
            showCancelButton: false,
            showMinimizeButton: false,
            showLog: false,
        });
        const statusEl = document.getElementById(`modal-status-${modal.id}`);
        if (statusEl) {
            statusEl.classList.add('risk-modal-scroll');
            statusEl.innerHTML = this._modalBodyHTML(svc, false, modal.id);
        }
        const footer = document.getElementById(`modal-footer-${modal.id}`);
        if (!footer) return;
        footer.innerHTML = `<button class="primary-btn" id="risk-gate-modal-close-${modal.id}">我已了解</button>`;
        document.getElementById(`risk-gate-modal-close-${modal.id}`).addEventListener('click', () => modal.close());
    },

    // 按同意态刷新 Launcher 配置页选项可见性（hideUntilConsent 服务未同意时隐藏）
    async refreshLauncherVisibility() {
        const tasks = Object.values(RISK_SERVICES)
            .filter(svc => svc.hideUntilConsent)
            .map(async svc => {
                const group = document.querySelector(`[data-risk-service="${svc.id}"]`);
                if (!group) return;
                const accepted = await this.getConsent(svc.id);
                group.style.display = accepted ? '' : 'none';
            });
        await Promise.all(tasks);
    },

    // Launcher 配置页门控：勾选未同意服务时回滚并就地弹出同意弹窗
    gateLauncherSection() {
        if (this._launcherBound) return;
        this._launcherBound = true;
        Object.values(RISK_SERVICES).forEach(svc => {
            const checkbox = document.getElementById(svc.launcherCheckboxId);
            if (!checkbox) return;
            checkbox.addEventListener('change', async () => {
                if (!checkbox.checked) return;
                const accepted = await this.getConsent(svc.id);
                if (accepted) return;
                checkbox.checked = false;
                this.showConsentModal(svc.id, () => {
                    checkbox.checked = true;
                });
            });
        });
        this.refreshLauncherVisibility();
    },
};
