// cg.js - 加载页 CG 替换页面控制器
// 存档锁定注入（方案 A：forced 对象锁定人格 CG；方案 B：解锁池注入任意资源）+ 缓存 bundle 扫描/预览/贴图替换

class CgPage {
    constructor() {
        this._bound = false;
        this._running = false;
        this._model = null;        // 最近一次读取的 CG 模型
        this._scanItems = [];      // 扫描得到的 CG ID 列表（key 形式）
        this._scanUncached = new Set();  // catalog 有效但未缓存下载的 ID（仅可锁定）
        this._lockableIds = new Set();   // 可锁定（人格 CG，方案 A）ID 集合
        this._filteredItems = [];  // 过滤后的完整列表（供滚动追加）
        this._renderWindow = 200;  // 单次渲染窗口大小（滚动分块）
        this._renderedCount = 0;   // 已渲染行数
        this._filterTimer = null;  // 过滤输入防抖定时器
        this._modded = [];         // 已替换贴图的 CG ID 列表
        this._initDomRefs();
    }

    init() {
        this._initDomRefs();
        this._bindEvents();
        RiskGate.gatePage('cg', {
            onAccepted: () => this._showMain(),
            onRejected: () => this._hideMain(),
        });
    }

    stop() {}

    _initDomRefs() {
        this.mainContent = document.getElementById('cg-main-content');
        this.warningEl = document.getElementById('cg-game-warning');
        this.slotSelect = document.getElementById('cg-slot-select');
        this.keyStatusEl = document.getElementById('cg-key-status');
        this.cacheStatusEl = document.getElementById('cg-cache-status');
        this.saveDirEl = document.getElementById('cg-save-dir');
        this.unlockedEl = document.getElementById('cg-unlocked-list');
        this.forcedEl = document.getElementById('cg-forced-list');
        this.latestEl = document.getElementById('cg-latest');
        this.cgInput = document.getElementById('cg-input');
        this.replaceIdInput = document.getElementById('cg-replace-id');
        this.replaceImgInput = document.getElementById('cg-replace-img');
        this.previewImg = document.getElementById('cg-preview-img');
        this.scanInfoEl = document.getElementById('cg-scan-info');
        this.listFilter = document.getElementById('cg-list-filter');
        this.cacheFilter = document.getElementById('cg-cache-filter');
        this.lockableFilter = document.getElementById('cg-lockable-filter');
        this.listEl = document.getElementById('cg-list');
        this.replaceStatusEl = document.getElementById('cg-replace-status');
        this.btnScan = document.getElementById('cg-btn-scan');
        this.btnAdd = document.getElementById('cg-btn-add');
        this.btnClear = document.getElementById('cg-btn-clear');
        this.btnPreview = document.getElementById('cg-btn-preview');
        this.btnReplace = document.getElementById('cg-btn-replace');
        this.btnRestore = document.getElementById('cg-btn-restore');
    }

    _bindEvents() {
        if (this._bound) return;
        this._bound = true;

        if (this.slotSelect) {
            this.slotSelect.addEventListener('change', () => this.refreshModel());
        }
        if (this.btnAdd) this.btnAdd.addEventListener('click', () => this.addLock());
        if (this.btnClear) this.btnClear.addEventListener('click', () => this.clearLock());
        if (this.btnScan) this.btnScan.addEventListener('click', () => this.scanCgIds());
        if (this.btnPreview) this.btnPreview.addEventListener('click', () => this.previewSelected());
        if (this.btnReplace) this.btnReplace.addEventListener('click', () => this.replaceTexture());
        if (this.btnRestore) this.btnRestore.addEventListener('click', () => this.restoreTexture());
        if (this.listFilter) {
            this.listFilter.addEventListener('input', () => {
                clearTimeout(this._filterTimer);
                this._filterTimer = setTimeout(() => this._renderScanList(), 150);
            });
        }
        if (this.cacheFilter) {
            this.cacheFilter.addEventListener('change', () => this._renderScanList());
        }
        if (this.lockableFilter) {
            this.lockableFilter.addEventListener('change', () => this._renderScanList());
        }
        if (this.listEl) {
            this.listEl.addEventListener('scroll', () => {
                const el = this.listEl;
                if (el.scrollTop + el.clientHeight >= el.scrollHeight - 60) {
                    this._appendMore();
                }
            });
        }
        if (this.replaceIdInput) {
            this.replaceIdInput.addEventListener('input', () => this._updateRestoreButton());
        }
    }

    // ---- 风险门 ----

    _hideMain() {
        if (this.mainContent) this.mainContent.style.display = 'none';
    }

    _showMain() {
        if (this.mainContent) this.mainContent.style.display = '';
        this.refreshStatus();
    }

    // ---- 状态刷新（导航进入时调用） ----

    refreshStatus() {
        if (!pywebview || !pywebview.api || !pywebview.api.cg_status) return;
        pywebview.api.cg_status().then((result) => {
            if (!result || !result.success) return;
            const d = result.data;

            if (this.warningEl) {
                this.warningEl.style.display = d.game_running ? '' : 'none';
            }

            // 存档槽下拉（保留当前选择）
            if (this.slotSelect) {
                const current = this.slotSelect.value;
                this.slotSelect.innerHTML = '';
                const slots = d.slots || [];
                if (!slots.length) {
                    const opt = document.createElement('option');
                    opt.value = '';
                    opt.textContent = '未找到存档（save_slot_*.json）';
                    this.slotSelect.appendChild(opt);
                }
                for (const s of slots) {
                    const opt = document.createElement('option');
                    opt.value = s.path;
                    opt.textContent = `槽位 ${s.slot} · ${s.mtime}（${(s.size / 1024).toFixed(1)} KB）`;
                    this.slotSelect.appendChild(opt);
                }
                if (current && [...this.slotSelect.options].some(o => o.value === current)) {
                    this.slotSelect.value = current;
                }
                this.slotSelect.disabled = !slots.length;
            }

            if (this.keyStatusEl) {
                this.keyStatusEl.innerHTML = d.key_available
                    ? '<i class="fas fa-check" style="color:#27ae60;"></i> 加密密钥可用（注册表 PlayerPrefs）'
                    : `<i class="fas fa-times" style="color:#e74c3c;"></i> 密钥不可用：${escapeHtml(d.key_error || '未找到注册表密钥')}`;
            }
            if (this.cacheStatusEl) {
                const b = d.bundle || {};
                const idxInfo = b.index_count
                    ? `，缓存索引 ${b.index_count} 个 CG / ${b.cached_bundles || 0} 个 bundle（${new Date(b.index_time * 1000).toLocaleString()}）`
                    : '';
                this.cacheStatusEl.innerHTML = b.cache_count
                    ? `<i class="fas fa-check" style="color:#27ae60;"></i> 缓存 bundle：${b.cache_count} 个${idxInfo}`
                    : '<i class="fas fa-times" style="color:#e74c3c;"></i> 未找到 Unity 缓存目录（游戏未下载过资源？）';
            }
            if (this.saveDirEl) {
                this.saveDirEl.innerHTML = `存档目录：<code>${escapeHtml(d.save_dir)}</code>`;
            }

            this._modded = (d.bundle && d.bundle.modded) || [];
            this._updateRestoreButton();

            this.refreshModel();
        }).catch(() => {});
    }

    _currentSlot() {
        return this.slotSelect ? this.slotSelect.value : '';
    }

    refreshModel() {
        const path = this._currentSlot();
        if (!path) {
            this._renderModel(null);
            return;
        }
        if (!pywebview || !pywebview.api || !pywebview.api.cg_read) return;
        pywebview.api.cg_read(path).then((result) => {
            if (!result || !result.success) {
                this._renderModel(null, result && result.message);
                return;
            }
            this._model = result.data;
            this._renderModel(result.data);
        }).catch((error) => {
            this._renderModel(null, String(error));
        });
    }

    _renderModel(model, error) {
        const unlockedEl = this.unlockedEl;
        const forcedEl = this.forcedEl;
        if (!unlockedEl && !forcedEl) return;

        if (!model) {
            const msg = error ? escapeHtml(error) : '未选择存档或读取失败';
            if (unlockedEl) unlockedEl.innerHTML = `<span class="form-hint">${msg}</span>`;
            if (forcedEl) forcedEl.innerHTML = `<span class="form-hint">${msg}</span>`;
            if (this.latestEl) this.latestEl.textContent = '—';
            return;
        }

        if (unlockedEl) {
            const list = model.cg_id_list || [];
            unlockedEl.innerHTML = list.length
                ? list.map(id => `<span class="cg-chip">${escapeHtml(id)}`
                    + ` <a href="javascript:void(0)" class="cg-chip-remove" title="从解锁池移除" data-cg="${encodeURIComponent(id)}"><i class="fas fa-times"></i></a></span>`).join('')
                : '<span class="form-hint">（空 — 加载页使用默认 CG）</span>';
            unlockedEl.querySelectorAll('.cg-chip-remove').forEach((a) => {
                a.addEventListener('click', () => this.removePoolLock(decodeURIComponent(a.dataset.cg)));
            });
        }
        if (forcedEl) {
            const list = model.forced_ids || [];
            forcedEl.innerHTML = list.length
                ? list.map(id => `<span class="cg-chip cg-chip-forced">${escapeHtml(id)}`
                    + ` <a href="javascript:void(0)" class="cg-chip-remove" title="移除锁定" data-cg="${encodeURIComponent(id)}"><i class="fas fa-times"></i></a></span>`).join('')
                : '<span class="form-hint">（空 — 加载页随机显示解锁池 CG）</span>';
            forcedEl.querySelectorAll('.cg-chip-remove').forEach((a) => {
                a.addEventListener('click', () => this.removeLock(decodeURIComponent(a.dataset.cg)));
            });
        }
        if (this.latestEl) {
            this.latestEl.textContent = model.latest_cg || '—';
        }
    }

    // ---- 锁定操作（即时写入，无备份） ----

    _applyForced(ids, okMsg) {
        const path = this._currentSlot();
        if (!path) {
            showMessage('提示', '请先选择存档槽');
            return Promise.resolve(false);
        }
        if (!pywebview || !pywebview.api || !pywebview.api.cg_apply) return Promise.resolve(false);
        return pywebview.api.cg_apply(path, ids).then((result) => {
            if (result && result.success) {
                this._model = result.data;
                this._renderModel(result.data);
                addLogMessage(okMsg || 'CG 锁定已更新', 'success');
                return true;
            }
            showMessage('操作失败', result ? result.message : '未知错误');
            return false;
        }).catch((error) => {
            showMessage('操作失败', String(error));
            return false;
        });
    }

    // 方案 B：解锁池注入（非人格资源），游戏保存后可能被重建
    _applyPool(cgId, okMsg) {
        const path = this._currentSlot();
        if (!path) {
            showMessage('提示', '请先选择存档槽');
            return Promise.resolve(false);
        }
        if (!pywebview || !pywebview.api || !pywebview.api.cg_inject_pool) return Promise.resolve(false);
        return pywebview.api.cg_inject_pool(path, cgId).then((result) => {
            if (result && result.success) {
                this._model = result.data;
                this._renderModel(result.data);
                addLogMessage(okMsg || `解锁池已注入：${cgId}`, 'success');
                return true;
            }
            showMessage('操作失败', result ? result.message : '未知错误');
            return false;
        }).catch((error) => {
            showMessage('操作失败', String(error));
            return false;
        });
    }

    // 人格 CG 命名判定（与后端 is_personality_name 一致）：<人格ID>_normal|_gacksung
    _isLockable(id) {
        return /^\d+_(normal|gacksung)$/.test((id || '').split('/').pop());
    }

    addLock() {
        if (!this.cgInput) return;
        const raw = this.cgInput.value.trim();
        if (!raw) {
            showMessage('提示', '请输入 CG ID，如 10101_normal、CG/10101_normal 或 Dummy');
            return;
        }
        // 带前缀（CG/ BG/ Story_CG/ Unit_CG/）直接使用；裸名在扫描结果中解析
        const id = /^(CG|BG|Story_CG|Unit_CG)\//i.test(raw) ? raw : this._resolvePrefix(raw);
        if (!id) return;

        if (this._isLockable(id)) {
            // 方案 A（默认）：人格 CG → forced 锁定列表（稳定）
            const forced = (this._model && this._model.forced_ids) || [];
            if (forced.includes(id) || forced.includes(id.replace(/^Story_CG\//, 'CG/').replace(/^Unit_CG\//, 'CG/'))) {
                showMessage('提示', `「${id}」已在锁定列表中`);
                return;
            }
            this._applyForced(forced.concat(id), `已锁定：${id}`);
        } else {
            // 方案 B：非人格资源（Dummy/自定义等）→ 解锁池注入（游戏保存后可能被重建）
            showConfirm('解锁池注入（方案 B）',
                `「${id}」为非人格资源，无法写入锁定列表（forced 仅支持人格 CG）。`
                + '将注入解锁池 _cgIdList 使其成为唯一候选并固定显示。'
                + '注意：游戏保存时会重建解锁池，该条目可能失效，需重新注入。继续？',
                () => this._applyPool(id, `解锁池已注入：${id}`));
        }
    }

    // 在已扫描 CG 中按裸名解析；唯一命中自动补全，歧义/未找到时提示
    _resolvePrefix(name) {
        const matches = this._scanItems.filter(i => i.endsWith('/' + name));
        if (matches.length === 1) return matches[0];
        if (matches.length > 1) {
            showMessage('提示',
                `「${name}」同时存在于 ${matches.map(i => i.split('/')[0]).join('、')} 分类，请手动输入完整 CG ID`);
            return '';
        }
        showMessage('提示',
            `未在已扫描 CG 中找到「${name}」。可先「扫描可用 CG」，或手动输入完整 ID`
            + '（CG/10101_normal、BG/xxx 等存档形式或 Story_CG/… 键形式）');
        return '';
    }

    removeLock(cgId) {
        const forced = (this._model && this._model.forced_ids) || [];
        this._applyForced(forced.filter(i => i !== cgId), `已移除锁定：${cgId}`);
    }

    removePoolLock(cgId) {
        const path = this._currentSlot();
        if (!path) {
            showMessage('提示', '请先选择存档槽');
            return;
        }
        if (!pywebview || !pywebview.api || !pywebview.api.cg_remove_pool) return;
        pywebview.api.cg_remove_pool(path, cgId).then((result) => {
            if (result && result.success) {
                this._model = result.data;
                this._renderModel(result.data);
                addLogMessage(`已从解锁池移除：${cgId}`, 'success');
            } else {
                showMessage('操作失败', result ? result.message : '未知错误');
            }
        }).catch((error) => {
            showMessage('操作失败', String(error));
        });
    }

    clearLock() {
        showConfirm('清除全部锁定',
            '将清空锁定列表，加载页恢复随机显示解锁池 CG。此操作立即写入存档，不做备份。继续？',
            () => this._applyForced([], '已清除全部锁定'));
    }

    // ---- 扫描可用 CG ----

    scanCgIds() {
        if (this._running) return;
        this._running = true;
        const forceEl = document.getElementById('cg-scan-force');
        const force = !!(forceEl && forceEl.checked);
        const modal = new ProgressModal('扫描缓存 CG');
        modal.addLog(force
            ? '强制全量重扫：将重新打开全部缓存 bundle（较慢，可取消）...'
            : '正在增量扫描缓存 bundle（缓存命中自动跳过，可取消）...');
        pywebview.api.cg_scan_ids(modal.id, force)
            .then((result) => {
                this._running = false;
                if (!result) {
                    modal.complete(false, '扫描失败：无返回结果');
                    return;
                }
                if (result.message === '已取消') {
                    modal.cancel();
                    return;
                }
                if (!result.success) {
                    modal.complete(false, '扫描失败：' + (result.message || '未知错误'));
                    return;
                }
                modal.complete(true, `扫描完成：发现 ${result.data.count} 个加载页 CG`);
                this._scanItems = (result.data.items || []).sort();
                this._scanUncached = new Set(result.data.uncached || []);
                this._lockableIds = new Set(result.data.lockable || []);
                this._renderScanList();
                if (this.scanInfoEl) {
                    const uncached = (result.data.uncached || []).length;
                    const lockable = (result.data.lockable || []).length;
                    this.scanInfoEl.innerHTML = `<i class="fas fa-check" style="color:#27ae60;"></i> `
                        + `已发现 ${this._scanItems.length} 个可用 CG（点击条目选用；`
                        + `${lockable} 个可锁定·方案A，${uncached} 个未下载缓存，其余仅可注入解锁池·方案B）`;
                }
            })
            .catch((error) => {
                this._running = false;
                modal.complete(false, '扫描失败：' + error);
            });
    }

    _renderScanList() {
        if (!this.listEl) return;
        // 按缓存状态筛选（全部 / 仅已缓存 / 仅未缓存）
        const mode = this.cacheFilter ? this.cacheFilter.value : 'all';
        let items = this._scanItems;
        if (mode === 'cached') {
            items = items.filter(i => !(this._scanUncached && this._scanUncached.has(i)));
        } else if (mode === 'uncached') {
            items = items.filter(i => this._scanUncached && this._scanUncached.has(i));
        }
        // 仅可锁定（人格 CG，方案 A）
        if (this.lockableFilter && this.lockableFilter.checked) {
            items = items.filter(i => this._lockableIds && this._lockableIds.has(i));
        }
        // 按名称过滤
        const q = (this.listFilter ? this.listFilter.value : '').toLowerCase().trim();
        if (q) items = items.filter(i => i.toLowerCase().includes(q));
        this._filteredItems = items;
        this._renderWindow = 200;
        this._renderedCount = 0;

        const filterRow = this.listFilter ? this.listFilter.closest('.cg-scan-filter') : null;
        if (filterRow) filterRow.style.display = this._scanItems.length ? '' : 'none';
        this.listEl.style.display = '';

        if (!items.length) {
            this.listEl.innerHTML = '<div class="cg-list-empty">无匹配的 CG（调整筛选条件）</div>';
            return;
        }
        this._renderListRows(true);
    }

    // 渲染 _filteredItems 从 _renderedCount 起的窗口内容；reset 时清空重建
    _renderListRows(reset) {
        if (reset) {
            this.listEl.innerHTML = '';
            this._renderedCount = 0;
        }
        const items = this._filteredItems;
        const end = Math.min(this._renderWindow, items.length);
        const frag = document.createDocumentFragment();
        for (let i = this._renderedCount; i < end; i++) {
            const id = items[i];
            const uncached = this._scanUncached && this._scanUncached.has(id);
            const lockable = this._lockableIds && this._lockableIds.has(id);
            const row = document.createElement('div');
            row.className = 'cg-list-item';
            let tags = '';
            if (uncached) tags += ' <span class="cg-list-tag">未缓存</span>';
            if (!lockable) tags += ' <span class="cg-list-tag">仅解锁池·方案B</span>';
            row.innerHTML = `<i class="fas fa-image"></i> ${escapeHtml(id)}${tags}`;
            row.title = lockable
                ? (uncached ? '未下载缓存，可锁定（方案 A）' : '点击选用并预览（人格 CG，可锁定）')
                : '非人格资源，仅可注入解锁池（方案 B，游戏保存后可能被重建）';
            row.addEventListener('click', () => this._selectCg(id));
            frag.appendChild(row);
        }
        this._renderedCount = end;
        this.listEl.appendChild(frag);

        // 尾部状态行：还有更多时提示滚动加载
        const total = items.length;
        let statusEl = document.getElementById('cg-list-status');
        if (total > this._renderedCount) {
            if (!statusEl) {
                statusEl = document.createElement('div');
                statusEl.id = 'cg-list-status';
                statusEl.className = 'cg-list-status';
                this.listEl.appendChild(statusEl);
            }
            statusEl.textContent = `已显示 ${this._renderedCount} / ${total}，滚动加载更多`;
        } else if (statusEl) {
            statusEl.remove();
        }
    }

    _appendMore() {
        const total = (this._filteredItems || []).length;
        if (this._renderWindow >= total) return;
        this._renderWindow = Math.min(this._renderWindow + 200, total);
        this._renderListRows(false);
    }

    _selectCg(cgId) {
        if (this.cgInput) this.cgInput.value = cgId;
        if (this.replaceIdInput) this.replaceIdInput.value = cgId;
        this._updateRestoreButton();
        this.previewCg(cgId);
    }

    // ---- 预览 ----

    previewSelected() {
        const id = this.replaceIdInput ? this.replaceIdInput.value.trim() : '';
        if (!id) {
            showMessage('提示', '请输入 CG ID');
            return;
        }
        this.previewCg(id);
    }

    previewCg(cgId) {
        if (!pywebview || !pywebview.api || !pywebview.api.cg_preview) return;
        pywebview.api.cg_preview(cgId).then((result) => {
            if (!this.previewImg) return;
            if (result && result.success) {
                this.previewImg.src = result.data;
                this.previewImg.style.display = '';
                if (this.replaceStatusEl) this.replaceStatusEl.textContent = '';
            } else {
                this.previewImg.style.display = 'none';
                if (this.replaceStatusEl) {
                    this.replaceStatusEl.innerHTML = `<span style="color:#e74c3c;">${escapeHtml(result ? result.message : '预览失败')}</span>`;
                }
            }
        }).catch(() => {});
    }

    // ---- 贴图替换 / 还原 ----

    _updateRestoreButton() {
        if (!this.btnRestore) return;
        const id = this.replaceIdInput ? this.replaceIdInput.value.trim() : '';
        // modded 列表为键形式；输入可能为存档形式（CG/<名>），一并匹配
        let hit = this._modded.includes(id);
        if (!hit && id.startsWith('CG/')) {
            const name = id.slice(3);
            hit = this._modded.includes('Story_CG/' + name)
                || this._modded.includes('Unit_CG/' + name);
        }
        this.btnRestore.style.display = hit ? '' : 'none';
    }

    replaceTexture() {
        const cgId = this.replaceIdInput ? this.replaceIdInput.value.trim() : '';
        const imgPath = this.replaceImgInput ? this.replaceImgInput.value.trim() : '';
        if (!cgId) {
            showMessage('提示', '请输入目标 CG ID');
            return;
        }
        if (!imgPath) {
            showMessage('提示', '请先选择替换图片');
            return;
        }
        showConfirm('替换贴图',
            `将把缓存 bundle 中「${cgId}」的贴图替换为所选图片（保留原尺寸/格式）。`
            + '游戏更新重新下载缓存后会还原；原始贴图数据将留存用于「还原原图」。继续？',
            () => {
                const modal = new ProgressModal('替换贴图');
                modal.addLog(`开始替换 ${cgId} ...`);
                pywebview.api.cg_replace(cgId, imgPath, modal.id)
                    .then((result) => {
                        if (!result) {
                            modal.complete(false, '替换失败：无返回结果');
                            return;
                        }
                        if (result.success) {
                            modal.complete(true, result.message || '替换完成');
                            this._modded.push(result.key || cgId);
                            this._updateRestoreButton();
                            if (this.replaceStatusEl) {
                                this.replaceStatusEl.innerHTML = `<i class="fas fa-check" style="color:#27ae60;"></i> ${escapeHtml(result.message)}`;
                            }
                        } else {
                            modal.complete(false, '替换失败：' + (result.message || '未知错误'));
                            if (this.replaceStatusEl) {
                                this.replaceStatusEl.innerHTML = `<span style="color:#e74c3c;">${escapeHtml(result.message)}</span>`;
                            }
                        }
                    })
                    .catch((error) => {
                        modal.complete(false, '替换失败：' + error);
                    });
            });
    }

    restoreTexture() {
        const cgId = this.replaceIdInput ? this.replaceIdInput.value.trim() : '';
        if (!cgId) return;
        const modal = new ProgressModal('还原贴图');
        modal.addLog(`开始还原 ${cgId} 原始贴图...`);
        pywebview.api.cg_restore(cgId, modal.id)
            .then((result) => {
                if (!result) {
                    modal.complete(false, '还原失败：无返回结果');
                    return;
                }
                if (result.success) {
                    modal.complete(true, result.message || '还原完成');
                    this._modded = this._modded.filter(i => i !== (result.key || cgId));
                    this._updateRestoreButton();
                    if (this.replaceStatusEl) {
                        this.replaceStatusEl.innerHTML = `<i class="fas fa-check" style="color:#27ae60;"></i> ${escapeHtml(result.message)}`;
                    }
                } else {
                    modal.complete(false, '还原失败：' + (result.message || '未知错误'));
                }
            })
            .catch((error) => {
                modal.complete(false, '还原失败：' + error);
            });
    }
}

// 全局实例（与其它页面控制器一致：DOMContentLoaded 时创建）
let cgPage;

document.addEventListener('DOMContentLoaded', function () {
    cgPage = new CgPage();
});
