const translationLogViewer = {
    selectedFileInfo: null,
    page: 1,
    pageSize: 50,
    totalPages: 1,
    selectedLine: null,
    currentRecord: null,
    detailRequestSeq: 0,
    toastTimer: null,

    async init() {
        this.bindEvents();
        try {
            const theme = await pywebview.api.get_config_value('theme', 'light');
            applyTheme(theme || 'light');
        } catch (error) {
            this.showError(error);
        }
    },

    bindEvents() {
        document.getElementById('tlv-choose-dump').addEventListener('click', () => this.chooseDump());
        document.getElementById('tlv-refresh').addEventListener('click', () => this.queryRecords(true));
        document.getElementById('tlv-open-folder').addEventListener('click', async () => {
            const result = await pywebview.api.open_selected_folder();
            if (!result.success) this.showError(result.message);
        });
        document.getElementById('tlv-export').addEventListener('click', () => this.exportFiltered());
        document.getElementById('tlv-apply-filter').addEventListener('click', () => {
            this.page = 1;
            this.queryRecords(false);
        });
        document.getElementById('tlv-clear-filter').addEventListener('click', () => this.clearFilters());
        document.getElementById('tlv-page-size').addEventListener('change', event => {
            this.pageSize = Number(event.target.value);
            this.page = 1;
            this.queryRecords(false);
        });
        document.getElementById('tlv-prev-page').addEventListener('click', () => {
            if (this.page > 1) {
                this.page -= 1;
                this.queryRecords(false);
            }
        });
        document.getElementById('tlv-next-page').addEventListener('click', () => {
            if (this.page < this.totalPages) {
                this.page += 1;
                this.queryRecords(false);
            }
        });
        document.getElementById('tlv-copy-record').addEventListener('click', () => this.copyCurrentRecord());
    },

    async chooseDump() {
        const button = document.getElementById('tlv-choose-dump');
        button.disabled = true;
        let result;
        try {
            result = await pywebview.api.choose_dump();
        } finally {
            button.disabled = false;
        }
        if (result.cancelled) return;
        if (!result.success) {
            this.showError(result.message);
            return;
        }

        this.selectedFileInfo = result.data;
        this.page = 1;
        this.selectedLine = null;
        this.currentRecord = null;
        this.clearDetail();
        document.getElementById('tlv-selected-file').textContent =
            `${result.data.path} · ${result.data.record_count} 条 · ${this.formatBytes(result.data.size)}`;
        document.getElementById('tlv-open-folder').disabled = false;
        document.getElementById('tlv-refresh').disabled = false;
        document.getElementById('tlv-export').disabled = false;
        await this.queryRecords(false);
    },

    async queryRecords(forceRefresh) {
        if (!this.selectedFileInfo) return;
        this.setBusy(true, '正在读取日志记录...');
        let result;
        try {
            result = await pywebview.api.query_records(
                this.getFilters(), this.page, this.pageSize, forceRefresh,
            );
        } finally {
            this.setBusy(false);
        }
        if (!result.success) {
            this.showError(result.message);
            this.renderEmptyRecords(result.message || '日志读取失败');
            return;
        }
        const data = result.data;
        this.totalPages = data.total_pages || 1;
        if (this.page > this.totalPages) {
            this.page = this.totalPages;
            return this.queryRecords(false);
        }
        this.updateFacetOptions(data.facets || {});
        this.renderRecords(data.records || []);
        document.getElementById('tlv-result-summary').textContent =
            `匹配 ${data.total} 条${data.invalid_count ? ` · 损坏行 ${data.invalid_count} 条` : ''}`;
        document.getElementById('tlv-page-label').textContent = `第 ${this.page} / ${this.totalPages} 页`;
        document.getElementById('tlv-prev-page').disabled = this.page <= 1;
        document.getElementById('tlv-next-page').disabled = this.page >= this.totalPages;
    },

    renderRecords(records) {
        const tbody = document.getElementById('tlv-record-list');
        tbody.replaceChildren();
        if (!records.length) {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.colSpan = 7;
            cell.className = 'tlv-empty';
            cell.textContent = '当前筛选条件下没有记录';
            row.appendChild(cell);
            tbody.appendChild(row);
            return;
        }
        records.forEach(record => {
            const row = document.createElement('tr');
            if (record.line_number === this.selectedLine) row.classList.add('active');
            row.dataset.lineNumber = String(record.line_number);
            this.appendCell(row, this.formatDate(record.timestamp));
            this.appendCell(row, record.file_name || '-');
            const outcomeCell = this.appendCell(row, '');
            outcomeCell.appendChild(this.badge(record.outcome || '-', this.outcomeClass(record)));
            this.appendCell(row, this.formatElapsed(record.elapsed_seconds));
            this.appendCell(row, String(record.api_call_count ?? 0));
            this.appendCell(row, String(record.failed_call_count ?? 0));
            const exceptionText = record.parse_error || [record.exception_type, record.exception_message].filter(Boolean).join(': ');
            this.appendCell(row, exceptionText || '-').title = exceptionText || '';
            row.addEventListener('click', () => this.loadRecord(record.line_number));
            tbody.appendChild(row);
        });
    },

    async loadRecord(lineNumber) {
        if (!this.selectedFileInfo) return;
        const requestId = ++this.detailRequestSeq;
        this.selectedLine = lineNumber;
        document.querySelectorAll('#tlv-record-list tr').forEach(row => {
            row.classList.toggle('active', Number(row.dataset.lineNumber) === lineNumber);
        });
        const detail = document.getElementById('tlv-detail');
        detail.replaceChildren(this.emptyNode('正在读取完整记录...', 'fas fa-spinner fa-spin'));
        const result = await pywebview.api.get_record(lineNumber);
        if (requestId !== this.detailRequestSeq) return;
        if (!result.success) {
            this.showError(result.message);
            detail.replaceChildren(this.emptyNode(result.message || '记录读取失败'));
            return;
        }
        this.currentRecord = result.data;
        document.getElementById('tlv-copy-record').disabled = false;
        this.renderDetail(result.data);
    },

    renderDetail(record) {
        const detail = document.getElementById('tlv-detail');
        detail.replaceChildren();
        const header = document.createElement('div');
        header.className = 'tlv-detail-header';
        const title = document.createElement('h2');
        title.textContent = record.file_name || `第 ${record.line_number} 行`;
        const subtitle = document.createElement('p');
        subtitle.textContent = `${this.formatDate(record.timestamp)} · 行 ${record.line_number}`;
        header.append(title, subtitle);
        detail.appendChild(header);
        if (record.invalid) {
            detail.appendChild(this.jsonSection('格式错误', {parse_error: record.parse_error, raw_line: record.raw_line}, true));
            return;
        }
        detail.appendChild(this.metaSection('结果概览', [
            ['结果', record.outcome],
            ['耗时', this.formatElapsed(record.elapsed_seconds)],
            ['调用总数', record.call_summary?.total ?? record.api_calls?.length ?? 0],
            ['失败调用', record.call_summary?.failed ?? 0],
            ['附加信息', record.outcome_extra, 'code'],
        ]));
        if (record.exception) detail.appendChild(this.jsonSection('活动异常与堆栈', record.exception, true));
        detail.appendChild(this.jsonSection(`输入文本 (${record.text_blocks?.length || 0})`, record.text_blocks || []));
        detail.appendChild(this.jsonSection('参考数据', record.reference || {}));
        const calls = Array.isArray(record.api_calls) ? record.api_calls : [];
        calls.forEach((call, index) => detail.appendChild(this.callSection(call, index)));
        detail.appendChild(this.jsonSection('完整原始记录', record));
    },

    callSection(call, index) {
        const section = document.createElement('details');
        section.className = 'tlv-detail-card';
        if (call.status !== 'success') section.open = true;
        const summary = document.createElement('summary');
        const heading = document.createElement('span');
        heading.className = 'tlv-call-heading';
        heading.append(
            document.createTextNode(`AI 调用 ${index + 1} · ${call.stage || 'unknown'}`),
            this.badge(call.status || 'unknown', call.status === 'success' ? 'success' : 'error'),
        );
        if (call.failure_kind) heading.appendChild(this.badge(call.failure_kind, 'warning'));
        summary.appendChild(heading);
        section.appendChild(summary);

        const body = document.createElement('div');
        body.className = 'tlv-detail-card-body';
        body.appendChild(this.metaGrid([
            ['Call ID', call.call_id],
            ['阶段 / 分片', `${call.stage || '-'} / ${call.part ?? '-'}`],
            ['尝试 / 格式', `${call.attempt ?? '-'} / ${call.format || '-'}`],
            ['状态', call.status],
            ['失败类型', call.failure_kind],
            ['耗时', this.formatElapsed(call.elapsed_seconds)],
            ['开始', call.started_at],
            ['结束', call.finished_at],
        ]));
        this.appendCodeField(body, 'System Prompt', call.system_prompt);
        this.appendCodeField(body, 'User Prompt', call.user_prompt);
        this.appendCodeField(body, 'AI 原始响应', call.raw_response);
        this.appendCodeField(body, '解析后响应', call.parsed_response);
        this.appendCodeField(body, '解析 / 校验错误', call.parse_errors || call.validation_errors);
        this.appendCodeField(body, 'HTTP 请求与响应', call.http_attempts);
        this.appendCodeField(body, '异常链', call.exception);
        this.appendCodeField(body, '调用元数据', call.metadata);
        section.appendChild(body);
        return section;
    },

    metaSection(title, rows) {
        const card = document.createElement('section');
        card.className = 'tlv-detail-card';
        const heading = document.createElement('div');
        heading.className = 'tlv-detail-card-title';
        heading.textContent = title;
        const body = document.createElement('div');
        body.className = 'tlv-detail-card-body';
        body.appendChild(this.metaGrid(rows));
        card.append(heading, body);
        return card;
    },

    metaGrid(rows) {
        const grid = document.createElement('div');
        grid.className = 'tlv-meta-grid';
        rows.forEach(([key, value, displayMode]) => {
            if (value === null || value === undefined || value === '') return;
            const keyNode = document.createElement('div');
            keyNode.className = 'tlv-meta-key';
            keyNode.textContent = key;
            const valueNode = document.createElement(displayMode === 'code' ? 'pre' : 'div');
            valueNode.className = displayMode === 'code'
                ? 'tlv-code-block tlv-code-block-compact'
                : 'tlv-meta-value';
            valueNode.textContent = this.stringify(value);
            grid.append(keyNode, valueNode);
        });
        return grid;
    },

    jsonSection(title, value, open = false) {
        const section = document.createElement('details');
        section.className = 'tlv-detail-card';
        section.open = open;
        const summary = document.createElement('summary');
        summary.textContent = title;
        const body = document.createElement('div');
        body.className = 'tlv-detail-card-body';
        const pre = document.createElement('pre');
        pre.className = 'tlv-code-block';
        pre.textContent = this.stringify(value);
        body.appendChild(pre);
        section.append(summary, body);
        return section;
    },

    appendCodeField(container, title, value) {
        if (value === null || value === undefined || value === '' ||
            (Array.isArray(value) && value.length === 0)) return;
        container.appendChild(this.jsonSection(title, value));
    },

    getFilters() {
        return {
            outcome: document.getElementById('tlv-outcome').value,
            stage: document.getElementById('tlv-stage').value,
            call_status: document.getElementById('tlv-call-status').value,
            failure_kind: document.getElementById('tlv-failure-kind').value,
            has_exception: document.getElementById('tlv-has-exception').value,
        };
    },

    clearFilters() {
        [
            'tlv-outcome', 'tlv-stage', 'tlv-call-status',
            'tlv-failure-kind', 'tlv-has-exception',
        ].forEach(id => { document.getElementById(id).value = ''; });
        this.page = 1;
        this.queryRecords(false);
    },

    updateFacetOptions(facets) {
        this.fillSelect('tlv-outcome', facets.outcomes || []);
        this.fillSelect('tlv-stage', facets.stages || []);
        this.fillSelect('tlv-call-status', facets.call_statuses || []);
        this.fillSelect('tlv-failure-kind', facets.failure_kinds || []);
    },

    fillSelect(id, values) {
        const select = document.getElementById(id);
        const current = select.value;
        select.replaceChildren(new Option('全部', ''));
        values.forEach(value => select.appendChild(new Option(value, value)));
        if ([...select.options].some(option => option.value === current)) select.value = current;
    },

    async exportFiltered() {
        if (!this.selectedFileInfo) return;
        const button = document.getElementById('tlv-export');
        button.disabled = true;
        let result;
        try {
            result = await pywebview.api.export_filtered(this.getFilters());
        } finally {
            button.disabled = false;
        }
        if (result.cancelled) return;
        if (!result.success) {
            this.showError(result.message);
            return;
        }
        const data = result.data;
        this.showToast(`已导出 ${data.exported} 条记录${data.skipped_invalid ? `，跳过 ${data.skipped_invalid} 条损坏记录` : ''}`);
    },

    async copyCurrentRecord() {
        if (!this.currentRecord) return;
        try {
            await navigator.clipboard.writeText(JSON.stringify(this.currentRecord, null, 2));
            this.showToast('完整记录已复制');
        } catch (error) {
            this.showError(`复制失败: ${error}`);
        }
    },

    clearDetail() {
        this.currentRecord = null;
        document.getElementById('tlv-copy-record').disabled = true;
        const detail = document.getElementById('tlv-detail');
        detail.replaceChildren(this.emptyNode(
            '选择一条记录查看提示词、AI 响应和异常详情',
            'fas fa-arrow-pointer',
        ));
    },

    setBusy(busy, message = '') {
        const refresh = document.getElementById('tlv-refresh');
        refresh.disabled = busy;
        refresh.querySelector('i').className = busy ? 'fas fa-spinner fa-spin' : 'fas fa-rotate';
        if (busy && message) document.getElementById('tlv-result-summary').textContent = message;
    },

    renderEmptyRecords(message) {
        const tbody = document.getElementById('tlv-record-list');
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 7;
        cell.className = 'tlv-empty';
        cell.textContent = message;
        row.appendChild(cell);
        tbody.replaceChildren(row);
    },

    emptyNode(message, iconClass = '') {
        const node = document.createElement('div');
        node.className = 'tlv-empty';
        if (iconClass) {
            const icon = document.createElement('i');
            icon.className = iconClass;
            node.append(icon, document.createTextNode(` ${message}`));
        } else {
            node.textContent = message;
        }
        return node;
    },

    appendCell(row, text) {
        const cell = document.createElement('td');
        cell.textContent = text;
        cell.title = text;
        row.appendChild(cell);
        return cell;
    },

    badge(text, className = '') {
        const badge = document.createElement('span');
        badge.className = `tlv-badge ${className}`.trim();
        badge.textContent = text;
        return badge;
    },

    outcomeClass(record) {
        if (record.invalid || record.has_exception || record.failed_call_count > 0) return 'error';
        if ((record.outcome || '').includes('SUCCESS')) return 'success';
        if ((record.outcome || '').includes('SKIP') || (record.outcome || '').includes('ALREADY')) return 'warning';
        return '';
    },

    stringify(value) {
        if (typeof value === 'string') return value;
        try {
            return JSON.stringify(value, null, 2);
        } catch (_) {
            return String(value);
        }
    },

    formatDate(value) {
        if (!value) return '-';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        return date.toLocaleString('zh-CN', {hour12: false});
    },

    formatElapsed(value) {
        if (value == null || value === '') return '-';
        const number = Number(value);
        return Number.isFinite(number) ? `${number.toFixed(3)}s` : '-';
    },

    formatBytes(value) {
        const bytes = Number(value) || 0;
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    },

    showError(message) {
        this.showToast(message || '操作失败', true);
    },

    showToast(message, isError = false) {
        const toast = document.getElementById('tlv-toast');
        toast.textContent = message;
        toast.className = `tlv-toast show${isError ? ' error' : ''}`;
        clearTimeout(this.toastTimer);
        this.toastTimer = setTimeout(() => { toast.className = 'tlv-toast'; }, 3500);
    },
};

function applyTheme(theme) {
    document.body.className = `theme-${theme || 'light'}`;
}

window.applyTheme = applyTheme;
window.addEventListener('pywebviewready', () => translationLogViewer.init());
