# Task 7 Report: WebUI「音频工具」页面 + BankMixin

**Status:** DONE_WITH_CONCERNS
**Commit:** `7609e2e` feat: WebUI 音频工具页（解包/重打包/.rebank 导出转换）

## What I implemented

### New files
- `webui/app_api/bank.py` — `BankMixin`（verbatim from brief）：10 个 `bank_*` 桥接方法，逐条转发 `webutils.function_bank`。
- `webui/sections/bank.html` — 六卡页面（FMOD DLL 状态 / 解包 / 重打包 / 导出 .rebank / 转换整包 / 补丁预览），全部采用 brief 规定的元素 ID，视觉与 `manage.html`/`cg.html` 一致（setting-card / form-group / file-input-group / action-btn / checkbox-container / list-container）。额外补充：卡片 2 隐藏输入 `bank-extract-file`（手动选 .bank 回填用）、卡片 3 输出目录浏览按钮、卡片 6 目标 bank/输出目录浏览按钮、各卡「浏览」按钮齐全。
- `webui/js/bank.js` — 全局函数控制器（非类）：
  - `initBankSection()`（preload.js 首次加载调用）= `refreshBankDllStatus` + `refreshBankGameBanks` + `refreshBankConvertList` + `loadBankConfig`
  - 卡片 1：`refreshBankDllStatus`（绿「正常（目录）」/红「缺少: …」，检测目录仅在输入框为空时回填，保存值优先）、`saveBankDllDir`、`clearBankDllDir`、`browseBankDllDir`
  - 卡片 2：`refreshBankGameBanks`（下拉含 fsb 数/加密标记 + 「（选择其他文件...）」项，`bankSelectedFile` 记忆手动路径）、`browseBankExtractFile`（经隐藏输入走 `browse_file`）、`browseBankExtractDir`（浏览后手动派发 change 以纳入 bindConfigAutoSave 自动保存）、`runBankExtract`（输出目录留空先弹目录选择，成功 showMessage 说明子目录对应 FSB 组）
  - 卡片 3：`browseBankRebuildBank/Wav/Out`、`runBankRebuild`（backend 默认 vorbis/quality=92）
  - 卡片 4：`browseBankExportOriginal/Modded`、`runBankExport`（out_path 默认 = 模组版 bank 同目录 `.rebank`；勾选「导出到模组目录」时后端再复制一份，成功提示「已放入模组目录，下次启动生效」+ 刷新转换列表）
  - 卡片 5：`refreshBankConvertList`（`find_installed_mod().able` 过滤 `.bank` 渲染 checkbox 行）、`runBankConvert`（逐个 `bank_convert_mod(name, keep)` 汇总成败）
  - 卡片 6：`browseBankPatchRebank/Bank/Out`、`runBankPatchFull`（目标 bank 留空时 `_bankResolvePatchTarget` 读 `bank_rebank_info` 的 `config.base_bank` 在游戏 bank 列表匹配，命中 showConfirm 确认后自动填写）、`showBankRebankInfo`（config 摘要 + 逐行文件清单）
  - 互斥 busy guard：`bankBusy` + `_bankWithBusy`，运行期间禁用 `#bank-section` 全部 action 按钮，防止并发桥接调用
  - 未调用 `bank_get_game_path`（不存在）

### Registration edits
- `webui/index.html` — nav 按钮 `bank-btn`（cg-btn 之后）、`#bank-section` div（cg-section 之后）、`<script src="js/bank.js">`（cg.js 之后）
- `webui/sections/preload.js` — `onSectionLoaded` 增加 `case 'bank':`（typeof 守卫）
- `webui/js/core.js` — configKeyMap 增加 `'bank-dll-dir': 'ui_default.bank.dll_dir'`、`'bank-extract-dir': 'ui_default.bank.extract_dir'`
- `.github/InitCode.py` — js_files 在 `'js/cg.js'` 后追加 `'js/bank.js'`（与 index.html script 顺序一致）
- `webui/app.py` — import BankMixin + LCTA_API 基类列表追加

### 顺带修复（超出 brief 文件清单，见 Concerns）
- `webutils/function_bank.py` — `bank_export_rebank` 在 `into_mod_folder=True` 且 out_path 已在模组目录（模组版 bank 取自模组目录的常见流程）时 `shutil.copy2` 对同一文件抛 `SameFileError`。已加路径相等守卫（相等则视为已入模组目录）。
- `tests/test_function_bank.py` — 新增 `test_bank_export_rebank_into_mod_same_path` 覆盖上述修复。

### Docs / 更新日志（未提交，与工作区既有 v5.0.3 改动同批）
- `webui/assets/update.md` — v5.0.3 章节追加音频工具条目
- `.claude/docs/modules.md` — 新增 `js/bank.js`、`sections/bank.html`（含 22→23 计数）、`app_api/bank.py`、`webutils/function_bank.py`、`webutils/bank/` 文档行

## Verification

```
python -m py_compile webui/app_api/bank.py webutils/function_bank.py   → 通过（无输出）
python -m py_compile webui/app.py                                        → 通过
python -c "import webui.app"                                             → APP_IMPORT_OK
python -m pytest tests/test_function_bank.py -q                          → 8 passed (原 7 + 新增 1)
node --check webui/js/bank.js                                            → 通过（node v24.14.0）
python -c "from webutils import bank_*"                                  → IMPORTS_OK
```

## Files changed（提交 7609e2e，10 个文件）
```
M .github/InitCode.py
M tests/test_function_bank.py
M webui/app.py
A webui/app_api/bank.py
M webui/index.html      （仅我的 3 个 hunk；既有 v5.0.3 版本号 hunk 未暂存）
A webui/js/bank.js
M webui/js/core.js
A webui/sections/bank.html
M webui/sections/preload.js
M webutils/function_bank.py
```

## Self-review findings（已修复）
1. `showBankRebankInfo` 文件清单：`escapeHtml(files.join('<br>'))` 会把 `<br>` 一并转义 → 改为逐条 escape 后 join。
2. 解包成功文案 `<bank>[序号]` 会被 HTML 解析吞掉标签字面量 → 改为 `bank[序号]`。
3. `runBankConvert` 中 showMessage onCloseCallback 与显式刷新重复 → 去掉回调。
4. `let outPath` 从不重赋值 → 改 `const`。
5. 文件名校名分割 `split('/')` 对反斜杠路径不健壮 → `split(/[\\/]/)`。
6. DLL 目录回填与 `applyConfigToSection` 的回填竞争 → 仅在输入框为空时写入，保证「已保存值优先」且确定性。

## Concerns
1. **`webutils/function_bank.py` 与 `tests/test_function_bank.py` 不在任务指定的 git add 清单内**，但 `bank_export_rebank` 的 SameFileError 会在最常见流程（模组版 bank 就在模组目录 + 勾选导出到模组目录）直接失败，故做了 4 行守卫修复并一起提交。如不认可可 `git revert` 这两文件单独 commit。
2. 无法可视化测试：`python start_webui.py` 需真实游戏环境，页面布局/交互未经运行验证（语法、桥接签名、结果字段均已对照后端核对）。
3. `initBankSection` 仅随 section 首次加载运行（preload.js 一次）；运行中改游戏路径/DLL 目录后重进页面不会自动重刷（与任务注册清单一致，utils.js 未纳入本次修改范围；卡片 5 有「刷新」按钮，DLL 状态可在保存操作后重刷）。
4. 长耗时操作（解包/重打包/生成）为「按钮禁用 + 前后 addLogMessage + 结果弹窗」，未用 ProgressModal——后端 `bank_*` 函数不接受 modal_id，无法流式进度，禁用态是任务允许的最简方案。
5. `update.md` 与 `.claude/docs/modules.md` 的条目因文件本身已有未提交的 v5.0.3 改动，未随本次 commit 提交（避免混入无关内容），会与用户的发布准备改动一起落库。

## Review fix: ��������ͣ��ʾ��commit 63a07fa��
�޸� review ���֣�ank-dll-dir / ank-extract-dir ȱ�� hover tooltip��
- webui/js/utils.js TOOLTIP_DATA ���� // ===== ��Ƶ���� ===== ��������
  - ank-dll-dir��FMOD ���� DLL Ŀ¼��fmod64.dll / fsbank64.dll / libfsbvorbis64.dll���������Զ���⣨LCTA_FMOD_DLL_DIR �������� / ����Ŀ¼����Ҳ�ɽ�������.zip��ֱ�����봰��һ�����롣
  - ank-extract-dir��bank ������Ŀ¼������������� ģ��Ŀ¼/BankExtract��
- bank.html ���������루rebuild/export/patch �ȣ���δ�Ǽ� configKeyMap���� tooltip.md ���� 3 ���� tooltip��
- ��֤��
ode --check webui/js/utils.js ͨ����python -m py_compile webui/app_api/bank.py ͨ�������ύ utils.js��4 ����������
