// ============================
// 快速上手：三步完成认知、必要设置与功能跳转
// ============================

class QuickStartManager {
    static GOALS = [
        {
            key: 'package',
            icon: 'fa-box-open',
            title: '安装现成汉化',
            badge: '多数新用户',
            description: '从 LLC、LCTA-AU 或 OurPlay 获取汉化包，再安装到游戏。',
        },
        {
            key: 'launcher',
            icon: 'fa-rocket',
            title: '自动更新并启动',
            badge: '长期使用',
            description: '通过 Steam 启动选项运行 LCTA，启动游戏前执行更新和可选处理。',
        },
        {
            key: 'translate',
            icon: 'fa-language',
            title: '自己翻译文本',
            badge: '需要翻译服务',
            description: '配置受支持的翻译服务，并在翻译工具中处理游戏语言文件。',
        },
        {
            key: 'customize',
            icon: 'fa-puzzle-piece',
            title: '模组与文本玩法',
            badge: '按需使用',
            description: '管理模组、应用文本美化规则，或导入调爪文本规则包。',
        },
    ];

    static UPDATE_MODES = [
        { value: 'LM-G', label: 'LLC + LCTA-AU（GitHub）' },
        { value: 'LM-A', label: 'LLC + LCTA-AU（API Beta）' },
        { value: 'LO', label: 'LLC + OurPlay' },
        { value: 'llc', label: '仅 LLC' },
        { value: 'LCTA-AU', label: '仅 LCTA-AU' },
        { value: 'ourplay', label: '仅 OurPlay' },
        { value: 'no', label: '不自动更新' },
    ];

    static CUSTOMIZE_OPTIONS = [
        { key: 'mods', icon: 'fa-cubes', title: '模组管理', description: '查看模组目录、刷新列表并管理已安装模组。', route: 'manage' },
        { key: 'fancy', icon: 'fa-magic', title: '文本美化', description: '启用内置或自定义文本规则，并应用到汉化文本。', route: 'fancy' },
        { key: 'tiaozhua', icon: 'fa-comment-dots', title: '调爪文本', description: '下载规则包并按下载页选项导入文本美化规则。', route: 'download' },
    ];

    init() {
        this.targetDiv = document.querySelector('.quick-start-content');
    }

    initPage() {
        this.targetDiv = document.querySelector('.quick-start-content');
        if (!this.targetDiv) return;

        this.step = 1;
        this.goal = 'package';
        this.gamePath = configManager.getCachedValue('game_path') || '';
        this.launcherUpdate = configManager.getCachedValue('launcher.work.update') || 'LM-G';
        this.launcherOptions = {
            mod: !!configManager.getCachedValue('launcher.work.mod'),
            fancy: !!configManager.getCachedValue('launcher.work.fancy'),
            tiaozhua: !!configManager.getCachedValue('launcher.work.tiaozhua'),
        };
        this.customizeOptions = new Set(['mods']);
        this.render();
    }

    render() {
        const content = this.step === 1
            ? this.renderGoalStep()
            : this.step === 2
                ? this.renderSetupStep()
                : this.renderFinishStep();

        this.targetDiv.innerHTML = `
            <div class="quick-start-shell">
                ${this.renderProgress()}
                <div class="quick-start-stage">${content}</div>
            </div>`;
        this.bindCurrentStep();
    }

    renderProgress() {
        const steps = [
            { number: 1, label: '选择目标' },
            { number: 2, label: '必要设置' },
            { number: 3, label: '立即开始' },
        ];
        return `
            <div class="quick-start-progress" aria-label="快速上手进度">
                ${steps.map(item => `
                    <div class="quick-start-progress-item ${item.number === this.step ? 'active' : ''} ${item.number < this.step ? 'done' : ''}">
                        <span>${item.number < this.step ? '<i class="fas fa-check"></i>' : item.number}</span>
                        <strong>${item.label}</strong>
                    </div>`).join('')}
            </div>`;
    }

    renderGoalStep() {
        return `
            <div class="quick-start-heading">
                <span class="quick-start-eyebrow">第 1 步，共 3 步</span>
                <h3>你第一次想用 LCTA 做什么？</h3>
                <p>四张卡片就是工具箱的主要使用方式。先选一个目标，向导只处理它真正需要的内容。</p>
            </div>
            <div class="quick-start-goal-grid">
                ${QuickStartManager.GOALS.map(goal => `
                    <button type="button" class="quick-start-goal ${goal.key === this.goal ? 'selected' : ''}"
                            data-goal="${goal.key}" aria-pressed="${goal.key === this.goal}">
                        <span class="quick-start-goal-icon"><i class="fas ${goal.icon}"></i></span>
                        <span class="quick-start-goal-copy">
                            <span class="quick-start-goal-title">${goal.title}</span>
                            <span class="quick-start-goal-badge">${goal.badge}</span>
                            <span class="quick-start-goal-description">${goal.description}</span>
                        </span>
                        <i class="fas fa-check-circle quick-start-goal-check"></i>
                    </button>`).join('')}
            </div>
            <div class="quick-start-note">
                <i class="fas fa-info-circle"></i>
                <span>不确定时选择“安装现成汉化”。其他功能不会被关闭，之后仍可从侧边栏进入。</span>
            </div>
            ${this.renderActions({ nextLabel: '继续' })}`;
    }

    renderSetupStep() {
        const goal = QuickStartManager.GOALS.find(item => item.key === this.goal);
        let body = '';

        if (this.goal === 'package') {
            body = `
                ${this.renderGamePathField('安装汉化时需要游戏目录。可以现在设置，也可以进入安装页后再设置。')}
                <div class="quick-start-explain-grid">
                    <div class="quick-start-explain-card">
                        <span>1</span>
                        <div><strong>下载</strong><p>在下载页选择 LLC、LCTA-AU 或 OurPlay，并使用该来源自己的下载选项。</p></div>
                    </div>
                    <div class="quick-start-explain-card">
                        <span>2</span>
                        <div><strong>安装</strong><p>下载完成后，在安装页选择汉化包并写入游戏目录。</p></div>
                    </div>
                </div>`;
        } else if (this.goal === 'launcher') {
            body = `
                ${this.renderGamePathField('Launcher 需要知道游戏目录。Steam 默认安装通常可自动检测，其他位置建议手动选择。')}
                <div class="quick-start-panel">
                    <label class="quick-start-field-label" for="quick-start-update-mode">启动时更新方式</label>
                    <select id="quick-start-update-mode" class="quick-start-select">
                        ${QuickStartManager.UPDATE_MODES.map(mode => `
                            <option value="${mode.value}" ${mode.value === this.launcherUpdate ? 'selected' : ''}>${mode.label}</option>`).join('')}
                    </select>
                    <p class="quick-start-field-hint">组合模式会在所列来源之间按 Launcher 的版本判断逻辑选择更新内容。</p>
                    <div class="quick-start-toggle-list">
                        ${this.renderLauncherToggle('mod', '启用 MOD 支持', '启动游戏时处理模组目录中的内容。')}
                        ${this.renderLauncherToggle('fancy', '更新后应用文本美化', '使用“文本美化”页面中已启用的规则。')}
                        ${this.renderLauncherToggle('tiaozhua', '更新后处理调爪文本', '按下载页配置获取并导入调爪文本规则。')}
                    </div>
                </div>`;
        } else if (this.goal === 'translate') {
            const apiConfigured = this.isApiConfigured();
            body = `
                <div class="quick-start-status ${apiConfigured ? 'success' : 'warning'}">
                    <i class="fas ${apiConfigured ? 'fa-check-circle' : 'fa-key'}"></i>
                    <div>
                        <strong>${apiConfigured ? '已保存翻译服务配置' : '尚未保存翻译服务配置'}</strong>
                        <p>${apiConfigured
                            ? '可以直接进入翻译工具；需要更换服务或密钥时再进入 API 配置页。'
                            : '先在 API 配置页选择受支持的服务、填写所需参数并测试，再进入翻译工具。'}</p>
                    </div>
                </div>
                <div class="quick-start-panel">
                    <h4>翻译流程只需要记住三件事</h4>
                    <ol class="quick-start-list">
                        <li>翻译服务和密钥在“配置汉化 API”页面管理。</li>
                        <li>待翻译文件、源语言和翻译选项在“翻译工具”页面选择。</li>
                        <li>高级选项不是首次使用的必填项，不需要在这里提前理解。</li>
                    </ol>
                </div>`;
        } else {
            body = `
                <div class="quick-start-panel">
                    <h4>选择你现在要打开的工具</h4>
                    <p class="quick-start-field-hint">可以多选；完成页会为每项提供直接入口。</p>
                    <div class="quick-start-choice-list">
                        ${QuickStartManager.CUSTOMIZE_OPTIONS.map(option => `
                            <label class="quick-start-choice">
                                <input type="checkbox" data-customize="${option.key}" ${this.customizeOptions.has(option.key) ? 'checked' : ''}>
                                <span class="quick-start-choice-icon"><i class="fas ${option.icon}"></i></span>
                                <span><strong>${option.title}</strong><small>${option.description}</small></span>
                            </label>`).join('')}
                    </div>
                </div>
                <div class="quick-start-note">
                    <i class="fas fa-info-circle"></i>
                    <span>模组加载由 Launcher 的“启用 MOD 支持”控制；这里只负责带你进入对应管理页面。</span>
                </div>`;
        }

        return `
            <div class="quick-start-heading">
                <span class="quick-start-eyebrow">第 2 步，共 3 步</span>
                <h3>${goal.title}：只检查必要内容</h3>
                <p>这里不会展示网络、缓存、并发等高级设置；需要时再到对应功能页调整。</p>
            </div>
            ${body}
            ${this.renderActions({ back: true, nextLabel: '保存并继续' })}`;
    }

    renderFinishStep() {
        const goal = QuickStartManager.GOALS.find(item => item.key === this.goal);
        return `
            <div class="quick-start-heading">
                <span class="quick-start-eyebrow">第 3 步，共 3 步</span>
                <h3>准备好了，直接开始</h3>
                <p>已完成“${goal.title}”所需的首次检查。下面的按钮会把你带到真正执行操作的页面。</p>
            </div>
            ${this.renderSummary()}
            <div class="quick-start-help">
                <i class="fas fa-question-circle"></i>
                <div><strong>进入功能页后看不懂某项？</strong><p>点击侧边栏条目旁的问号，或长按 W 两秒，打开当前页面的帮助。</p></div>
            </div>
            ${this.renderActions({ back: true, finish: true })}`;
    }

    renderSummary() {
        if (this.goal === 'package') {
            return `
                <div class="quick-start-result-card">
                    <i class="fas fa-box-open"></i>
                    <div><strong>先下载，再安装</strong><p>${this.gamePath ? '游戏目录已设置。' : '游戏目录尚未设置，可在安装页补充。'} 下载页不会替你决定汉化来源。</p></div>
                </div>
                <div class="quick-start-destination-grid">
                    ${this.renderDestination('download', 'fa-download', '去下载汉化包', '选择来源并开始下载', true)}
                    ${this.renderDestination('install', 'fa-box-open', '我已有汉化包', '直接进入安装页面')}
                </div>`;
        }

        if (this.goal === 'launcher') {
            const updateMode = QuickStartManager.UPDATE_MODES.find(mode => mode.value === this.launcherUpdate);
            const enabledOptions = [
                this.launcherOptions.mod ? 'MOD' : '',
                this.launcherOptions.fancy ? '文本美化' : '',
                this.launcherOptions.tiaozhua ? '调爪文本' : '',
            ].filter(Boolean);
            return `
                <div class="quick-start-result-card">
                    <i class="fas fa-rocket"></i>
                    <div>
                        <strong>${updateMode ? updateMode.label : this.launcherUpdate}</strong>
                        <p>${this.gamePath ? '游戏目录已设置。' : '游戏目录尚未设置。'}${enabledOptions.length ? ` 附加处理：${enabledOptions.join('、')}。` : ' 未启用附加处理。'}</p>
                    </div>
                </div>
                <div class="quick-start-note warning">
                    <i class="fas fa-terminal"></i>
                    <span>进入 Launcher 配置页后保存配置，复制页面生成的 Steam 命令，并粘贴到游戏的 Steam 启动选项。</span>
                </div>
                <div class="quick-start-destination-grid single">
                    ${this.renderDestination('launcher-config', 'fa-copy', '完成 Launcher 配置', '保存并复制 Steam 启动命令', true)}
                </div>`;
        }

        if (this.goal === 'translate') {
            const apiConfigured = this.isApiConfigured();
            return `
                <div class="quick-start-result-card">
                    <i class="fas ${apiConfigured ? 'fa-check-circle' : 'fa-key'}"></i>
                    <div><strong>${apiConfigured ? '翻译服务配置已存在' : '先配置翻译服务'}</strong><p>${apiConfigured ? '可以进入翻译工具选择文件和翻译选项。' : '保存并测试服务配置后，再进入翻译工具。'}</p></div>
                </div>
                <div class="quick-start-destination-grid">
                    ${this.renderDestination(apiConfigured ? 'translate' : 'config', apiConfigured ? 'fa-language' : 'fa-key', apiConfigured ? '开始翻译' : '配置汉化 API', apiConfigured ? '选择文件并执行翻译' : '选择服务、填写参数并测试', true)}
                    ${this.renderDestination(apiConfigured ? 'config' : 'translate', apiConfigured ? 'fa-cog' : 'fa-language', apiConfigured ? '检查 API 配置' : '查看翻译工具', apiConfigured ? '更换服务或更新密钥' : '了解后续文件与选项')}
                </div>`;
        }

        const selected = QuickStartManager.CUSTOMIZE_OPTIONS.filter(option => this.customizeOptions.has(option.key));
        return `
            <div class="quick-start-result-card">
                <i class="fas fa-puzzle-piece"></i>
                <div><strong>已选择 ${selected.length} 个工具</strong><p>这些入口彼此独立；只有需要随游戏启动自动处理时，才需要进一步配置 Launcher。</p></div>
            </div>
            <div class="quick-start-destination-grid">
                ${selected.map((option, index) => this.renderDestination(option.route, option.icon, option.title, option.description, index === 0)).join('')}
            </div>`;
    }

    renderGamePathField(hint) {
        return `
            <div class="quick-start-panel">
                <label class="quick-start-field-label" for="quick-start-game-path">游戏安装目录</label>
                <p class="quick-start-field-hint">${hint}</p>
                <div class="quick-start-path-row">
                    <input type="text" id="quick-start-game-path" value="${this.escapeAttribute(this.gamePath)}" placeholder="选择包含 LimbusCompany.exe 的文件夹">
                    <button type="button" class="action-btn secondary" id="quick-start-browse-path"><i class="fas fa-folder-open"></i> 浏览</button>
                </div>
            </div>`;
    }

    renderLauncherToggle(key, title, description) {
        return `
            <label class="quick-start-toggle checkbox-container">
                <input type="checkbox" data-launcher-option="${key}" ${this.launcherOptions[key] ? 'checked' : ''}>
                <span class="checkmark"></span>
                <span><strong>${title}</strong><small>${description}</small></span>
            </label>`;
    }

    renderDestination(route, icon, title, description, primary = false) {
        return `
            <button type="button" class="quick-start-destination ${primary ? 'primary' : ''}" data-route="${route}">
                <i class="fas ${icon}"></i>
                <span><strong>${title}</strong><small>${description}</small></span>
                <i class="fas fa-arrow-right"></i>
            </button>`;
    }

    renderActions({ back = false, nextLabel = '', finish = false }) {
        return `
            <div class="quick-start-actions">
                <div>
                    ${back ? '<button type="button" class="action-btn" id="quick-start-back"><i class="fas fa-arrow-left"></i> 返回</button>' : ''}
                    <button type="button" class="action-btn" id="quick-start-exit"><i class="fas fa-times"></i> 退出快速上手</button>
                </div>
                ${finish
                    ? '<button type="button" class="action-btn" id="quick-start-dashboard"><i class="fas fa-home"></i> 回到首页</button>'
                    : `<button type="button" class="primary-btn" id="quick-start-next">${nextLabel} <i class="fas fa-arrow-right"></i></button>`}
            </div>`;
    }

    bindCurrentStep() {
        this.targetDiv.querySelectorAll('[data-goal]').forEach(button => {
            button.addEventListener('click', () => {
                this.goal = button.dataset.goal;
                this.render();
            });
        });

        const next = document.getElementById('quick-start-next');
        if (next) next.addEventListener('click', () => this.next());

        const back = document.getElementById('quick-start-back');
        if (back) back.addEventListener('click', () => {
            this.readCurrentControls();
            this.step -= 1;
            this.render();
        });

        const exit = document.getElementById('quick-start-exit');
        if (exit) exit.addEventListener('click', () => goAndShow('dashboard'));

        const dashboard = document.getElementById('quick-start-dashboard');
        if (dashboard) dashboard.addEventListener('click', () => goAndShow('dashboard'));

        const browse = document.getElementById('quick-start-browse-path');
        if (browse) browse.addEventListener('click', () => this.browseGamePath());

        this.targetDiv.querySelectorAll('[data-route]').forEach(button => {
            button.addEventListener('click', () => this.openRoute(button.dataset.route));
        });
    }

    async next() {
        this.readCurrentControls();

        if (this.step === 2) {
            if (this.goal === 'customize' && this.customizeOptions.size === 0) {
                if (typeof showMessage === 'function') {
                    showMessage('请选择工具', '请至少选择一个要打开的工具，或返回选择其他目标。');
                }
                return;
            }
            const saved = await this.saveSetup();
            if (!saved) return;
        }

        this.step += 1;
        this.render();
    }

    readCurrentControls() {
        const pathInput = document.getElementById('quick-start-game-path');
        if (pathInput) this.gamePath = pathInput.value.trim();

        const updateMode = document.getElementById('quick-start-update-mode');
        if (updateMode) this.launcherUpdate = updateMode.value;

        this.targetDiv.querySelectorAll('[data-launcher-option]').forEach(input => {
            this.launcherOptions[input.dataset.launcherOption] = input.checked;
        });

        this.targetDiv.querySelectorAll('[data-customize]').forEach(input => {
            if (input.checked) {
                this.customizeOptions.add(input.dataset.customize);
            } else {
                this.customizeOptions.delete(input.dataset.customize);
            }
        });
    }

    async saveSetup() {
        const updates = {};
        if (this.goal === 'package' || this.goal === 'launcher') {
            updates['game-path'] = this.gamePath;
        }
        if (this.goal === 'launcher') {
            updates['launcher-work-update'] = this.launcherUpdate;
            updates['launcher-work-mod'] = this.launcherOptions.mod;
            updates['launcher-work-fancy'] = this.launcherOptions.fancy;
            updates['launcher-work-tiaozhua'] = this.launcherOptions.tiaozhua;
        }
        if (Object.keys(updates).length === 0) return true;

        const result = await configManager.updateConfigValues(updates);
        if (result && result.success) return true;

        if (typeof showMessage === 'function') {
            showMessage('保存失败', result && result.message ? result.message : '无法保存快速上手中的设置，请稍后重试。');
        }
        return false;
    }

    async browseGamePath() {
        const path = await pywebview.api.browse_folder('');
        if (!path) return;
        this.gamePath = path.replace(/\\/g, '/');
        const input = document.getElementById('quick-start-game-path');
        if (input) input.value = this.gamePath;
    }

    async openRoute(route) {
        await configManager.flushPendingUpdates();
        goAndShow(route);
    }

    isApiConfigured() {
        const apiConfig = configManager.getCachedValue('api_config');
        return apiConfig !== undefined && apiConfig !== null && String(apiConfig).trim() !== '';
    }

    escapeAttribute(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }
}

quickStartManager = new QuickStartManager();
