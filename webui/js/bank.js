// bank.js - 音频工具页控制器
// FMOD DLL 状态/解包/重打包/.rebank 导出与转换/补丁预览

// ---- 页面状态 ----
let bankBusy = false;          // 任一运行中操作占位（互斥，防并发桥接调用）
let bankGameBanks = [];        // bank_get_game_banks 的 banks 列表（含 path/fsb_count/encrypted）
let bankSelectedFile = '';     // 「选择其他文件...」手动选择的 .bank 路径

// ---- 通用辅助 ----

function _bankEl(id) {
    return document.getElementById(id);
}

function _bankSetBusy(busy) {
    bankBusy = busy;
    document.querySelectorAll('#bank-section .action-btn, #bank-section .primary-btn').forEach(function (btn) {
        btn.disabled = busy;
    });
}

async function _bankWithBusy(fn) {
    if (bankBusy) return;
    _bankSetBusy(true);
    try {
        await fn();
    } finally {
        _bankSetBusy(false);
    }
}

function _bankPathInput(id) {
    const el = _bankEl(id);
    return el ? el.value.trim() : '';
}

// ---- 页面初始化（preload.js onSectionLoaded 调用，仅首次加载） ----

async function initBankSection() {
    refreshBankDllStatus();
    refreshBankGameBanks();
    refreshBankConvertList();
    loadBankConfig();
}

// ---- 卡片 1: DLL 下载 ----
async function downloadBankDlls() {
    if (!pywebview || !pywebview.api || !pywebview.api.bank_download_dlls) return;
    const btn = _bankEl('bank-download-dlls');
    if (!btn) return;
    btn.disabled = true;
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 下载中...';
    try {
        const result = await pywebview.api.bank_download_dlls(false);
        showMessage(result.success ? '下载完成' : '下载失败', result.message || '');
        await refreshBankDllStatus();
    } catch (error) {
        addLogMessage(error);
        showMessage('下载失败', String(error));
    } finally {
        btn.disabled = false;
        btn.innerHTML = orig;
    }
}

async function requireBankDlls() {
    // 操作前检查：DLL 缺失时提示去下载，返回 false
    if (!pywebview || !pywebview.api || !pywebview.api.bank_dll_status) return true;
    const result = await pywebview.api.bank_dll_status();
    if (result && result.success && result.ok) return true;
    showMessage('缺少 FMOD 工具 DLL', '请先在「FMOD 工具 DLL」卡片点击「一键下载 FMOD DLL」自动获取，或手动选择包含 fmod64.dll / fsbank64.dll / libfsbvorbis64.dll 的目录。');
    return false;
}

// ---- 卡片 1: FMOD DLL 状态 ----

async function refreshBankDllStatus() {
    if (!pywebview || !pywebview.api || !pywebview.api.bank_dll_status) return;
    const statusEl = _bankEl('bank-dll-status');
    const dirInput = _bankEl('bank-dll-dir');
    try {
        const result = await pywebview.api.bank_dll_status();
        if (!result || !result.success) {
            if (statusEl) {
                statusEl.innerHTML = '<span style="color:#e74c3c;"><i class="fas fa-times"></i> '
                    + escapeHtml(result ? result.message : '检测失败') + '</span>';
            }
            return;
        }
        if (result.ok) {
            if (statusEl) {
                statusEl.innerHTML = '<i class="fas fa-check" style="color:#27ae60;"></i> '
                    + '正常（' + escapeHtml(result.dir || '未知目录') + '）';
            }
        } else {
            const missing = (result.missing || []).join(', ');
            if (statusEl) {
                statusEl.innerHTML = '<span style="color:#e74c3c;"><i class="fas fa-times"></i> '
                    + '缺少: ' + escapeHtml(missing) + '（可点击下方按钮一键下载）</span>';
            }
        }
        // 回填检测/配置的目录（已有保存值时不覆盖，保存值优先）
        if (dirInput && !dirInput.value && result.dir) {
            dirInput.value = result.dir;
        }
    } catch (e) {
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#e74c3c;">检测失败: ' + escapeHtml(String(e)) + '</span>';
        }
    }
}

async function saveBankDllDir() {
    const dir = _bankPathInput('bank-dll-dir');
    await _bankWithBusy(async () => {
        if (!pywebview || !pywebview.api || !pywebview.api.bank_set_dll_dir) return;
        try {
            const result = await pywebview.api.bank_set_dll_dir(dir);
            if (result && result.success) {
                showMessage('已保存', result.message || 'DLL 目录已设置');
                refreshBankDllStatus();
            } else {
                showMessage('保存失败', result ? result.message : '未知错误');
                refreshBankDllStatus();
            }
        } catch (e) {
            showMessage('保存失败', String(e));
        }
    });
}

function clearBankDllDir() {
    const el = _bankEl('bank-dll-dir');
    if (el) el.value = '';
    saveBankDllDir();
}

function browseBankDllDir() {
    if (pywebview && pywebview.api && pywebview.api.browse_folder) {
        pywebview.api.browse_folder('bank-dll-dir');
    }
}

// ---- 卡片 2: 游戏 bank 列表 + 解包 ----

async function refreshBankGameBanks() {
    if (!pywebview || !pywebview.api || !pywebview.api.bank_get_game_banks) return;
    const select = _bankEl('bank-extract-select');
    if (!select) return;
    try {
        const result = await pywebview.api.bank_get_game_banks();
        bankGameBanks = (result && result.success && result.banks) || [];
        select.innerHTML = '';
        if (!bankGameBanks.length) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = (result && result.success)
                ? '未检测到游戏 bank（未配置游戏路径？可「选择文件」）'
                : (result ? result.message : '获取失败');
            select.appendChild(opt);
        } else {
            bankGameBanks.forEach(function (b) {
                const opt = document.createElement('option');
                opt.value = b.path;
                opt.textContent = b.name + '（' + b.fsb_count + ' 个音频'
                    + (b.encrypted ? '·加密' : '') + '）';
                select.appendChild(opt);
            });
        }
        const fileOpt = document.createElement('option');
        fileOpt.value = '__file__';
        fileOpt.id = 'bank-extract-file-option';
        fileOpt.textContent = bankSelectedFile ? bankSelectedFile.split(/[\\/]/).pop() : '（选择其他文件...）';
        select.appendChild(fileOpt);
    } catch (e) {
        console.error('[bank] refreshBankGameBanks failed:', e);
    }
}

function browseBankExtractFile() {
    if (!pywebview || !pywebview.api || !pywebview.api.browse_file) return;
    pywebview.api.browse_file('bank-extract-file').then(function (path) {
        if (!path) return;
        bankSelectedFile = path;
        const select = _bankEl('bank-extract-select');
        const fileOpt = _bankEl('bank-extract-file-option');
        if (fileOpt) fileOpt.textContent = path.split(/[\\/]/).pop();
        if (select) select.value = '__file__';
    }).catch(function (e) {
        console.error('[bank] browseBankExtractFile failed:', e);
    });
}

function browseBankExtractDir() {
    if (!pywebview || !pywebview.api || !pywebview.api.browse_folder) return;
    return pywebview.api.browse_folder('bank-extract-dir').then(function (path) {
        if (path) {
            const el = _bankEl('bank-extract-dir');
            // browse_folder 经 run_js 赋值不触发 change，手动派发以纳入自动保存
            if (el) el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return path;
    });
}

function _bankResolveExtractPath() {
    const select = _bankEl('bank-extract-select');
    if (!select || !select.value) return '';
    if (select.value === '__file__') return bankSelectedFile;
    return select.value;
}

async function runBankExtract() {
    if (!(await requireBankDlls())) return;
    await _bankWithBusy(async () => {
        const bankPath = _bankResolveExtractPath();
        if (!bankPath) {
            showMessage('提示', '请先选择要解包的 bank（下拉选择或「选择文件」）');
            return;
        }
        let outDir = _bankPathInput('bank-extract-dir');
        if (!outDir) {
            outDir = await browseBankExtractDir();
            if (!outDir) {
                showMessage('提示', '请选择输出目录（或手动填写）');
                return;
            }
        }
        const password = _bankPathInput('bank-extract-password');
        if (!pywebview || !pywebview.api || !pywebview.api.bank_extract) return;
        addLogMessage('开始解包: ' + bankPath + ' → ' + outDir);
        try {
            const result = await pywebview.api.bank_extract(bankPath, outDir, password);
            if (result && result.success) {
                const count = result.fsb_count || 0;
                addLogMessage('解包完成: ' + bankPath + ' → ' + outDir
                    + (result.encrypted ? '（加密 bank，已用密码解密）' : ''));
                showMessage('解包完成', '已解包 ' + count + ' 个音频到：\n' + outDir
                    + '\n\n每个子目录 bank[序号] 对应一个 FSB 音频组，可直接替换 wav 后「重打包」。');
            } else {
                addLogMessage('解包失败: ' + bankPath + (result ? '：' + result.message : ''));
                showMessage('解包失败', result ? result.message : '未知错误');
            }
        } catch (e) {
            addLogMessage('解包失败: ' + String(e));
            showMessage('解包失败', String(e));
        }
    });
}

// ---- 卡片 3: 重打包（wav → bank） ----

function browseBankRebuildBank() {
    if (pywebview && pywebview.api && pywebview.api.browse_file) {
        pywebview.api.browse_file('bank-rebuild-bank');
    }
}

function browseBankRebuildWav() {
    if (pywebview && pywebview.api && pywebview.api.browse_folder) {
        pywebview.api.browse_folder('bank-rebuild-wav');
    }
}

function browseBankRebuildOut() {
    if (pywebview && pywebview.api && pywebview.api.browse_folder) {
        pywebview.api.browse_folder('bank-rebuild-out');
    }
}

async function runBankRebuild() {
    if (!(await requireBankDlls())) return;
    await _bankWithBusy(async () => {
        const bankPath = _bankPathInput('bank-rebuild-bank');
        const wavDir = _bankPathInput('bank-rebuild-wav');
        const outDir = _bankPathInput('bank-rebuild-out');
        if (!bankPath || !wavDir || !outDir) {
            showMessage('提示', '请填写原版 bank、wav 目录与输出目录（可点击「浏览」选择）');
            return;
        }
        if (!pywebview || !pywebview.api || !pywebview.api.bank_rebuild) return;
        addLogMessage('开始重打包: ' + bankPath + ' → ' + outDir);
        try {
            const result = await pywebview.api.bank_rebuild(bankPath, wavDir, outDir, '');
            if (result && result.success) {
                addLogMessage('重打包完成: ' + (result.out_bank || outDir));
                showMessage('重打包完成', '已生成完整 bank：\n' + (result.out_bank || outDir)
                    + '\n\n把它放入模组目录即成为整包模组，或到「导出 .rebank」卡片压缩为差分包。');
            } else {
                addLogMessage('重打包失败: ' + bankPath + (result ? '：' + result.message : ''));
                showMessage('重打包失败', result ? result.message : '未知错误');
            }
        } catch (e) {
            addLogMessage('重打包失败: ' + String(e));
            showMessage('重打包失败', String(e));
        }
    });
}

// ---- 卡片 4: 导出 .rebank 补丁模组 ----

function browseBankExportOriginal() {
    if (pywebview && pywebview.api && pywebview.api.browse_file) {
        pywebview.api.browse_file('bank-export-original');
    }
}

function browseBankExportModded() {
    if (pywebview && pywebview.api && pywebview.api.browse_file) {
        pywebview.api.browse_file('bank-export-modded');
    }
}

async function runBankExport() {
    if (!(await requireBankDlls())) return;
    await _bankWithBusy(async () => {
        const originalPath = _bankPathInput('bank-export-original');
        const moddedPath = _bankPathInput('bank-export-modded');
        if (!originalPath || !moddedPath) {
            showMessage('提示', '请选择「原版 bank」与「模组版 bank」');
            return;
        }
        const name = _bankPathInput('bank-export-name');
        const version = _bankPathInput('bank-export-version') || '1.0';
        const author = _bankPathInput('bank-export-author');
        const desc = _bankEl('bank-export-desc') ? _bankEl('bank-export-desc').value.trim() : '';
        const intoMod = !!(_bankEl('bank-export-into-mod') && _bankEl('bank-export-into-mod').checked);
        // 输出 .rebank 默认放到模组版 bank 旁边；勾选「导出到模组目录」时后端会再复制一份到模组目录
        const outPath = moddedPath.replace(/\.bank$/i, '') + '.rebank';
        if (!pywebview || !pywebview.api || !pywebview.api.bank_export_rebank) return;
        addLogMessage('开始导出 .rebank: ' + originalPath + ' ↔ ' + moddedPath);
        try {
            const result = await pywebview.api.bank_export_rebank(
                originalPath, moddedPath, outPath, name, version, author, desc, intoMod);
            if (result && result.success) {
                const finalPath = result.into_mod_folder ? result.out : outPath;
                const count = result.count || 0;
                addLogMessage('导出完成: ' + finalPath + '（改动音频 ' + count + ' 个）');
                showMessage('导出完成',
                    '已导出 ' + count + ' 个改动音频到：\n' + finalPath
                    + (result.into_mod_folder ? '\n\n已放入模组目录，下次启动游戏生效。' : ''));
                refreshBankConvertList();
            } else {
                addLogMessage('导出失败: ' + moddedPath + (result ? '：' + result.message : ''));
                showMessage('导出失败', result ? result.message : '未知错误');
            }
        } catch (e) {
            addLogMessage('导出失败: ' + String(e));
            showMessage('导出失败', String(e));
        }
    });
}

// ---- 卡片 5: 转换整包 bank 模组 → .rebank ----

async function refreshBankConvertList() {
    const container = _bankEl('bank-convert-list');
    if (!container) return;
    if (!pywebview || !pywebview.api || !pywebview.api.find_installed_mod) {
        container.innerHTML = '<div class="list-empty"><p>无法获取模组列表</p></div>';
        return;
    }
    try {
        const result = await pywebview.api.find_installed_mod();
        const able = (result && result.success && result.able) || [];
        const banks = able.filter(function (n) {
            return /\.bank$/i.test(n);
        }).sort();
        if (!banks.length) {
            container.innerHTML = '<div class="list-empty"><i class="fas fa-box-open"></i><p>暂无整包 bank 模组</p></div>';
            return;
        }
        container.innerHTML = '';
        banks.forEach(function (name) {
            const row = document.createElement('label');
            row.className = 'checkbox-container';
            row.style.cssText = 'display:flex; align-items:center; gap:8px; padding:8px 12px;'
                + 'border-bottom:1px solid var(--color-border-light); cursor:pointer;';
            row.innerHTML = '<input type="checkbox" class="bank-convert-check" value="'
                + escapeHtml(name) + '"><span class="checkmark"></span><span>'
                + escapeHtml(name) + '</span>';
            container.appendChild(row);
        });
    } catch (e) {
        container.innerHTML = '<div class="list-empty"><p>加载失败: ' + escapeHtml(String(e)) + '</p></div>';
    }
}

async function runBankConvert() {
    if (!(await requireBankDlls())) return;
    await _bankWithBusy(async () => {
        const checks = document.querySelectorAll('#bank-convert-list .bank-convert-check:checked');
        const names = [];
        checks.forEach(function (c) { names.push(c.value); });
        if (!names.length) {
            showMessage('提示', '请先勾选要转换的 bank 模组');
            return;
        }
        const keep = !!(_bankEl('bank-convert-keep') && _bankEl('bank-convert-keep').checked);
        if (!pywebview || !pywebview.api || !pywebview.api.bank_convert_mod) return;
        const ok = [];
        const failed = [];
        addLogMessage('开始转换 ' + names.length + ' 个整包模组（保留原 .bank=' + keep + '）...');
        for (const name of names) {
            try {
                const result = await pywebview.api.bank_convert_mod(name, keep);
                if (result && result.success) {
                    ok.push(name + '（改动音频 ' + (result.count || 0) + ' 个）');
                } else {
                    failed.push(name + (result ? '：' + result.message : ''));
                }
            } catch (e) {
                failed.push(name + '：' + String(e));
            }
        }
        if (ok.length) {
            addLogMessage('转换完成: ' + ok.join('，'));
        }
        if (failed.length) {
            addLogMessage('转换失败: ' + failed.join('；'));
        }
        showMessage('转换结果',
            '成功 ' + ok.length + ' 个，失败 ' + failed.length + ' 个。\n\n'
            + (ok.length ? '成功：\n' + ok.join('\n') + '\n\n' : '')
            + (failed.length ? '失败：\n' + failed.join('\n') : ''));
        if (ok.length) refreshBankConvertList();
    });
}

// ---- 卡片 6: 补丁预览 / 生成完整 bank ----

function browseBankPatchRebank() {
    if (pywebview && pywebview.api && pywebview.api.browse_file) {
        pywebview.api.browse_file('bank-patch-rebank');
    }
}

function browseBankPatchBank() {
    if (pywebview && pywebview.api && pywebview.api.browse_file) {
        pywebview.api.browse_file('bank-patch-bank');
    }
}

function browseBankPatchOut() {
    if (pywebview && pywebview.api && pywebview.api.browse_folder) {
        pywebview.api.browse_folder('bank-patch-out');
    }
}

async function runBankPatchFull() {
    if (!(await requireBankDlls())) return;
    await _bankWithBusy(async () => {
        const rebankPath = _bankPathInput('bank-patch-rebank');
        if (!rebankPath) {
            showMessage('提示', '请先选择 .rebank 模组文件');
            return;
        }
        const outDir = _bankPathInput('bank-patch-out');
        if (!outDir) {
            showMessage('提示', '请填写输出目录（可点击「浏览」选择）');
            return;
        }
        let bankPath = _bankPathInput('bank-patch-bank');
        if (!bankPath) {
            bankPath = await _bankResolvePatchTarget(rebankPath);
            if (!bankPath) return;
        }
        if (!pywebview || !pywebview.api || !pywebview.api.bank_patch_full) return;
        addLogMessage('开始生成完整 bank: ' + rebankPath + ' → ' + bankPath);
        try {
            const result = await pywebview.api.bank_patch_full(rebankPath, bankPath, outDir, '');
            if (result && result.success) {
                addLogMessage('生成完成: ' + (result.out_bank || outDir));
                showMessage('生成完成',
                    '已替换 ' + result.replaced + ' 个音频'
                    + ((result.skipped_new || result.skipped_bad)
                        ? '（跳过 ' + (result.skipped_new || 0) + ' 个新增 / '
                          + (result.skipped_bad || 0) + ' 个无效文件）' : '')
                    + '，输出：\n' + (result.out_bank || outDir));
            } else {
                addLogMessage('生成失败: ' + rebankPath + (result ? '：' + result.message : ''));
                showMessage('生成失败', result ? result.message : '未知错误');
            }
        } catch (e) {
            addLogMessage('生成失败: ' + String(e));
            showMessage('生成失败', String(e));
        }
    });
}

// 目标 bank 留空时：读 .rebank 的 base_bank，在游戏 bank 列表里匹配原版文件
async function _bankResolvePatchTarget(rebankPath) {
    if (!pywebview || !pywebview.api || !pywebview.api.bank_rebank_info) return '';
    try {
        const info = await pywebview.api.bank_rebank_info(rebankPath);
        const cfg = info && info.success ? info.config : null;
        if (!cfg || !cfg.base_bank) {
            showMessage('提示', '无法从 .rebank 读取 base_bank，请手动选择目标 bank');
            return '';
        }
        if (!bankGameBanks.length) await refreshBankGameBanks();
        const target = bankGameBanks.find(function (b) {
            return b.name.replace(/\.bank$/i, '') === cfg.base_bank;
        });
        if (!target) {
            showMessage('提示', '游戏目录中未找到原版 bank「' + cfg.base_bank
                + '」，请手动选择目标 bank');
            return '';
        }
        let proceed = false;
        await new Promise(function (resolve) {
            showConfirm('确认目标 bank',
                '将把差分包应用到游戏原版 bank：\n' + target.path + '\n\n继续？',
                function () { proceed = true; resolve(); },
                function () { resolve(); });
        });
        return proceed ? target.path : '';
    } catch (e) {
        showMessage('提示', '读取 .rebank 信息失败: ' + String(e));
        return '';
    }
}

async function showBankRebankInfo() {
    const rebankPath = _bankPathInput('bank-patch-rebank');
    if (!rebankPath) {
        showMessage('提示', '请先在「补丁预览」卡片选择 .rebank 模组文件');
        return;
    }
    if (!pywebview || !pywebview.api || !pywebview.api.bank_rebank_info) return;
    try {
        const result = await pywebview.api.bank_rebank_info(rebankPath);
        if (!result || !result.success) {
            showMessage('无法读取', result ? result.message : '未知错误');
            return;
        }
        const cfg = result.config || {};
        const files = result.files || [];
        const html = '<b>' + escapeHtml(cfg.name || '(未命名)') + '</b> v'
            + escapeHtml(cfg.version || '?')
            + (cfg.author ? ' · 作者 ' + escapeHtml(cfg.author) : '')
            + '<br>基础 bank: <code>' + escapeHtml(cfg.base_bank || '?') + '</code>'
            + ' · 改动音频 ' + (cfg.count != null ? cfg.count : files.length) + ' 个'
            + (cfg.description ? '<br>描述: ' + escapeHtml(cfg.description) : '')
            + (files.length
                ? '<br><br>文件清单:<br>' + files.map(function (f) { return escapeHtml(f); }).join('<br>')
                : '');
        showMessage('模组信息', html);
    } catch (e) {
        showMessage('无法读取', String(e));
    }
}

// ---- 配置回填 ----

// 已登记 configKeyMap 的输入（bank-dll-dir / bank-extract-dir）由 preload.js
// applyConfigToSection 自动回填；此处仅兜底处理非绑定控件的缓存值。
function loadBankConfig() {
    if (typeof configManager === 'undefined' || !configManager) return;
    const extractEl = _bankEl('bank-extract-dir');
    if (extractEl && !extractEl.value) {
        const v = configManager.getCachedValue('ui_default.bank.extract_dir');
        if (v) extractEl.value = v;
    }
}
