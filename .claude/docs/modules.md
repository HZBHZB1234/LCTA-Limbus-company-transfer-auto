# LCTA Module Map

<!-- Last updated: 2026-08-11 -->

## Directory Overview

| Directory | Role | Key Files |
|-----------|------|-----------|
| `webui/` | Frontend application (pywebview + HTML/CSS/JS) | 5 standalone pages + sections |
| `webutils/` | Business logic layer (feature modules + beautification engines) | 70 Python files |
| `webFunc/` | Infrastructure (network, downloads) | 4 |
| `translateFunc/` | Translation engine (LLM pipeline) | 13+ |
| `globalManagers/` | Cross-cutting singletons | 2 |
| `launcher/` | Standalone game launcher (GPL-3.0) | 11 |
| `resource_updater/` | Official localize/Bundle updater and Launcher fingerprint gate | 4 |
| `tools/cfst/` | CloudflareSpeedTest binary + IP lists（构建时由 InitCode 下载，运行时懒加载兜底） | 3 |
| `hooks/` | C source for native DLLs | `rawinput_hook.c` (input bypass), compiled to `rawinput_hook.dll` by build.ps1 / CI; 作弊工具箱的 hook DLL 源码已迁往私有仓库 LCTA_CheatingCore（`hooks/*.c` 扫描编译，见 `cheat_core/`） |
| `vendor/minhook/` | 空（MinHook 已随作弊工具箱功能迁往私有仓库） | — |
| `scripts/` | 单文件脚本 | `cheat_encrypt.py` — CheatCore 加密器（私有仓库功能文件 → `cheat_core.bin`，格式见私有仓库 README） |
| `cheat_core/` | 运行期加密数据（构建产物，不入库） | `cheat_core.bin` — 加密的作弊工具箱功能包，由 webutils/cheat_core.py 在用户输入密钥后解密加载 |
| `fancy/` | User rule sets (one JSON file per ruleset) | auto-created |
| `metadata_recovery/` | Metadata 恢复流水线运行产物（每运行一个 `run_<时间戳>/` 子目录：candidate_profile、各阶段 report.json/md、section-map、重建标准文件、正式 profile） | auto-created |
| `tests/` | Pytest test suite | 27 Python files |
| `.githooks/` | Repository-local Git hooks | `pre-commit` |
| `.github/workflows/` | CI/CD and repository consistency checks | `release.yml`, `check.yml`, `check-sync.yml` |

## Repository Guidance & Automation

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Source project instructions and AI-first knowledge-base index |
| `AGENTS.md` | Cross-tool copy of `CLAUDE.md`; kept byte-for-byte synchronized for other coding agents |
| `.githooks/pre-commit` | Optional local hook (`git config core.hooksPath .githooks`) that copies `CLAUDE.md` to `AGENTS.md` and stages the synchronized file before commit |
| `.github/InitCode.py` | Release preparation script. Localizes shared HTML resources across the main shell and standalone pages; recursively downloads esm.sh module graphs and rewrites their imports to local files so CodeMirror works offline |
| `.github/workflows/check-sync.yml` | Pull-request/manual CI guard that fails when `CLAUDE.md` and `AGENTS.md` differ |

## webui/ — Frontend Application

| File | Purpose |
|------|---------|
| `app.py` | **Core** pywebview bridge — thin shell (~100 lines). Assembles `LCTA_API` from the feature-domain mixins in `webui/app_api/`, re-exports the 4 window bridge classes (`RuleEditorAPI`/`QuickEditorAPI`/`LLMFancyAPI`/`TranslationLogViewerAPI` from their own files) and `CancelRunning`, and defines `main()` (window creation + modal callback wiring). Owns the shared `ResourceUpdaterAPI` used by the in-app resource page |
| `app_api/` | `LCTA_API` 按功能域拆分的 mixin 模块包（详见下方小节）。`webui/app.py` 的 `LCTA_API` 依次继承这些 mixin；pywebview 通过 `dir()` 枚举 JS API，继承方法对前端透明，无需改动 JS |
| `rule_editor_api.py` | `RuleEditorAPI` 窗口桥接：美化规则编辑器（文件浏览、规则 CRUD、校验、智能分析、模板） |
| `quick_editor_api.py` | `QuickEditorAPI` 窗口桥接：简易翻译编辑器（diff/批量编辑） |
| `llm_fancy_api.py` | `LLMFancyAPI` 窗口桥接：LLM 文本美化（扫描预览/批处理/取消/配置持久化，后台线程 + 事件推送） |
| `aria2_downloader_api.py` | `Aria2DownloaderAPI` 窗口桥接：泛用高速下载器（aria2c 服务启停、URL/磁力/torrent 提交、暂停/继续/删除、目录选择、配置持久化，快照经 `__aria2DlDispatch` 事件推送）。默认保存目录经 `webutils/utils/shell.py get_downloads_dir()` 解析系统真实「下载」已知文件夹（支持迁移重定向），`get_state` 返回 `save_dir_exists` 供前端提示 |
| `translation_log_api.py` | `TranslationLogViewerAPI` 只读桥接：翻译诊断日志查看器（选择 dump、分页查询、过滤导出） |
| `index.html` | Single-page HTML shell (~200 lines), section placeholders loaded dynamically from `sections/`; the 游戏资源更新 sidebar item is an ordinary SPA route |
| `rule-editor.html` | Standalone pywebview page for the 美化规则编辑器. Sidebar search input filters filenames/categories while typing and runs full-content search on Enter or the search button. File-edit tab: VSCode-style CodeMirror 6 editor with find/replace (Ctrl+F/H), match highlighting, dirty state indicator, status bar, change tracking, and smart ruleset generation. Ruleset-edit tab: simple form + advanced JSON editors for ruleset CRUD. Theme syncs with main app window (light/dark/purple) |
| `llm-fancy.html` | Standalone pywebview page for the LLM 文本美化 window (opened from the fancy page). Bus-syntax selection rules JSON editor, fancy/ bus-ruleset exclusion checkboxes, custom prompt toggle + textarea, batch size / concurrency inputs, scan preview and run buttons with streamed progress/log and result summary. Theme syncs with main app window |
| `aria2-downloader.html` | Standalone pywebview page for the 泛用高速下载器 (opened from the 游戏资源更新 page). URL/magnet textarea + save dir + .torrent picker, jobs/connection/seed-time settings, task list with progress/speed/status badges and per-task pause/resume/delete, global pause-all/resume-all/purge. Backed by `Aria2DownloaderAPI` + `webutils/function_aria2_downloader.py`; theme syncs with main app window |
| `quick-editor.html` | Standalone pywebview page for the 简易翻译编辑器. Simpler than rule-editor: sidebar file browser (categorized, searchable) + CodeMirror 6 JSON editor + bottom change list panel; in-editor find/replace search bar shared with rule-editor via `css/editor-search-panel.css` + `js/editor-search-panel.js`. Changes recorded as `{file, path, old, new}`, saved with derived bus `set` rules to fixed `fancy/_quick_edits.json`, and shown read-only in the main Fancy list |
| `translation-log-viewer.html` | Standalone read-only translation diagnostic viewer. Opens one user-selected current `schema_version: 2` JSONL dump and provides structured filters, pagination, lazy full-record details, copy, refresh, and filtered export |
| `css/base.css` | Base styling with 3 theme definitions (light/dark/purple) and CSS custom properties |
| `css/components.css` | Component-specific styles: cards, buttons, forms, progress bars, modals |
| `css/layout-extras.css` | Layout utilities, modals, drawers, scrollbars, responsive breakpoints, and the two-column responsive layout for the resource updater page. Also loaded by rule-editor.html |
| `css/editor-search-panel.css` | **Shared** CM6 in-editor search panel styles (VSCode floating `.cm-panels`, draggable `.cm-search` card, textfield/button/label/dark-theme). Loaded by both `rule-editor.html` and `quick-editor.html` so both editors share one look |
| `css/rule-editor.css` | Rule editor styles: sidebar+main+bottom panel layout, data cards, smart-gen dialog, tiered scope options, editor status bar, match highlights, toasts, per-theme colors. (Search panel styles now live in the shared `editor-search-panel.css`) |
| `css/quick-editor.css` | Quick editor styles: 3-panel layout (sidebar+main+changes), category groups with collapsible headers, file item active/hover states, toolbar/change-list/resize-handle styling, per-theme color variables. In-editor search panel comes from shared `editor-search-panel.css` |
| `css/llm-fancy.css` | LLM text-beautification window styles: card layout, bus selection JSON editor, exclusion checkbox list, prompt textarea, action buttons, progress bar + log panel, result card; theme-aware via CSS variables |
| `css/aria2-downloader.css` | 高速下载器窗口样式：状态 chip、任务卡、进度条/速度行、状态徽标、统计行、toast；主题变量映射同 llm-fancy |
| `css/translation-log-viewer.css` | Three-column diagnostic viewer layout, filters, record table, collapsible detail cards, responsive detail panel, and theme-aware status styling |
| `js/core.js` | Core framework: API binding, event system, navigation; `applyConfigToSection(容器)` 限定容器回填已渲染表单（跳过 pendingUpdates 待保存键），供懒加载 section 回填配置用 |
| `js/resource-updater.js` | In-app resource updater page controller: refreshes persisted state on navigation, shows the shared game directory (read-only, linked to the main program's `game_path` setting), probes the game directory, starts/cancels work, and renders channel progress/log events from `ResourceUpdaterAPI`. The Launcher auto-download switch (`launcher.resource_update.enabled`) lives only on the Launcher config page and is read here from the config cache (source page shows integration intro + jump button) |
| `js/features.js` | Feature-specific UI logic, drag-drop manager, manual update from local zip, FancyManager (saveAll now persists to `fancy/` folder via `pywebview.api.save_ruleset()`), `openRuleEditor()` global function |
| `js/init.js` | Initialization and bootstrap: uses single `get_startup_data()` call; welcome content deferred via `_pendingWelcomeContent` for lazy section loading compatibility |
| `js/utils.js` | Navigation, encryption, and sidebar search; all ordinary tools, including 游戏资源更新, use lazy SPA sections through `await loadSection()` |
| `js/modals.js` | Modal dialog management, markdown content loader with `_loadedMarkdowns` cache, and toggle functions (all null-guarded for lazy section loading safety)。`ProgressModal.complete()` 末尾自动 `del_modal_list`（仅 Promise 落定后调用，无竞态）；`updateProgress` 对 percent 钳制 [0,100] 且主进度条耦合元素判空；取消统一约定：后端返回 `message: '已取消'` 时前端 `modal.cancel()` |
| `js/quick-start.js` | Three-step first-use flow: choose one of four goals, check only goal-specific settings, save ordinary config where needed, then jump directly to the target feature page; no wizard progress/config schema |
| `js/api-config.js` | API configuration page logic; container-not-found logs suppressed for lazy loading compatibility |
| `js/cdn.js` | CDN optimization page logic |
| `js/speed.js` | Game speed control page logic; delegates the first-time risk-notice gate to the shared `RiskGate` module |
| `js/risk-gate.js` | **Shared** risk-service gate module (`RISK_SERVICES` registry + global `RiskGate`): normalized disclaimer text (common bullets + per-service line + optional per-service `agreementSections`, single source of truth), consent persistence via `{service}.disclaimer_accepted` config keys, first-entry overlay gating for risk pages (`gatePage`), in-place consent modal for Launcher-config checkboxes (`gateLauncherSection` + `showConsentModal`), a view-only re-read modal (`showNoticeModal`), and `refreshLauncherVisibility()` — services flagged `hideUntilConsent` (currently `cheat`) stay hidden on the Launcher-config page until consent is given on the source page (re-checked on each navigation into the page and after `acceptConsent`). `cheat` additionally carries an `agreementSections` array (作者承诺 / 使用者义务 / 服务可用性说明) rendered after the common disclaimer, plus its own `consentLabel` (resolved via `_consentLabel(service)`, falls back to the shared label for other services). The toolbox's Launcher items are no longer static: `cheat` has no `launcherCheckboxId`; `cheat-shell.js` renders them dynamically into `#cheat-plugin-launcher` from the plugin registry (each rendered group carries `data-risk-service="cheat"` so visibility/consent still apply). Adding a new risk service = one registry entry + `data-risk-overlay` container on the source page + `data-risk-service` attribute on the Launcher-config checkbox |
| `js/input-bypass.js` | Input anti-detection page logic; gated by the shared `RiskGate` risk-notice overlay before the page content unlocks |
| `js/cheat-shell.js` | 作弊工具箱**密钥门壳**（bundle 内置）：进入时先经 `RiskGate.gatePage('cheat')` 风险门（未同意显示覆盖层并隐藏 `#cheat-main-content`，同意后 `_showMainContent` 恢复可见；覆盖层缺失兜底直接显示，避免整页空白），再查询解锁状态（`cheat_core_status`）→ 未解锁 `_showGate` 显示密钥输入门；已解锁/自动解锁后经 `cheat_plugins_list()` 遍历插件，逐个 `cheat_core_get_section_html/script_js` 拉取解密的功能页 HTML/JS，`new Function` 注入并调用解密 JS 导出的 `initCheatPage()`。另提供 `renderLauncherPlugins()` 按插件注册表把 Launcher 集成开关动态渲染进 `#cheat-plugin-launcher`（未同意风险就地弹窗、值直写 config）。对外保持 `cheatPage` 全局名（init/stop）兼容 utils.js 导航生命周期，另暴露 `cheatCoreLockAndReload()` 供「锁定」按钮使用。功能实现 JS 位于私有仓库 |
| `js/metadata-recovery.js` | Metadata 恢复页控制器：`MetadataRecoveryPage`（init 绑定事件 + 刷新插件/输出目录状态，导航每次进入重刷；安装插件/浏览目录/开始运行）。**结构化流程**：`loadExport()`（步骤 3：路径 + 候选 rank → `metadata_recovery_load_export` → `renderExport` 填充候选下拉（`#rank name (score)`，无文本的标记「无反编译文本」）+ 信息区（verdict 徽标/hex/文本就绪状态）+ 自动回填 textarea/hex/反编译文件输入）。运行经 `ProgressModal` + `metadata_recovery_run(config, modal.id)`，结果渲染各阶段 verdict 徽标（PASS/PASS_WITH_REVIEW/FAIL/SKIP）+ 输出文件列表；输入校验（必填 metadata、反编译文本或既有 profile、table hex/SHA 格式） |
| `js/list-managers.js` | List/tab view management; constructors tolerate missing containers (lazy load compatible); container refs updated by `onSectionLoaded` |
| `js/editor-search-panel.js` | **Shared** CM6 search panel module (`window.EditorSearchPanel`): `attach(container, bridge)` observes dynamically-added `.cm-search` nodes and applies `localizeSearchPanel` (CN translation) + `attachDrag` (pointer-capture drag, rAF transform, 3px dead-zone) + `setSearchPanelPosition` (boundary clamp). The `bridge` object holds per-page state (`isOpen`/`panelLeft`/`panelTop`/`panelRight`/`onPanelClose`). Used by both rule- and quick-editor |
| `js/rule-editor.js` | Rule editor frontend logic: two main mode tabs (file-edit / ruleset-edit). Sidebar typing performs local filename/category filtering; explicit search performs asynchronous full-content search with request IDs so stale results cannot overwrite newer searches. In-editor CodeMirror find/replace panel (Ctrl+F) is powered by the shared `EditorSearchPanel`; cross-tab search query/position save-restore lives here (`_searchBridge`/`_captureSearchState`/`_restoreSearchState`). File editing, JSON diff tracking, batch replace, ruleset CRUD, templates, validation, and V1/V2/V3 smart generation remain in this module |
| `js/quick-editor.js` | Quick editor frontend logic (~900 lines): file browser with category grouping, CodeMirror 6 JSON editing, `diff_json`-based change tracking (`recordChanges()`), edit list rendering with per-item delete, search across files by keyword with drill-down, batch replace dialog, resize handle drag, theme sync with main window, Ctrl+S to record changes. Shares the in-editor search panel with the rule editor via the shared `EditorSearchPanel` (Ctrl+F opens the localized/draggable panel; Ctrl+Shift+F focuses the sidebar search) |
| `js/llm-fancy.js` | LLM text-beautification window frontend: `get_initial_state()` bootstrap (rulesets, api_config snapshot, persisted config), WebCrypto `decryptText` for `api_crypto` compatibility, bus selection JSON editor + validation + example, exclusion checkbox list, scan preview / run with `__llmFancyDispatch` event streaming (log/progress/scan_done/run_done), cancel, config save, theme sync |
| `js/aria2-downloader.js` | 高速下载器窗口前端：`get_state()` 引导（aria2c 可用性/服务状态/持久化配置）→ 自动 `start_server()`；`__aria2DlDispatch` 快照事件渲染任务列表（进度/速度/状态徽标/单任务暂停继续删除）；URL 批量提交、torrent 选择、全局暂停/继续/清除、设置保存、保存目录缺失常驻警告（`save_dir_exists=false` 显示 `#adl-dir-warning`，浏览成功即隐藏）、`applyTheme` 主题同步 |
| `js/translation-log-viewer.js` | Translation dump viewer frontend: native file selection, manual reread, structured filters, pagination, lazy detail rendering, clipboard copy, and filtered JSONL export; no directory scan or content search |
| `sections/preload.js` | Lazy section loader: preloads only dashboard at startup, fetches others on first navigation via `loadSection()`; `onSectionLoaded()` initializes the embedded resource updater and other per-section controllers, and binds `RiskGate.gateLauncherSection()` on the Launcher config page (per-navigation visibility refresh for consent-gated options lives in `js/utils.js` `initNavigation`)。`onSectionLoaded` 为 async：先 `applyConfigToSection(容器)` 回填本 section 已保存配置，再执行依赖回填值的显隐 toggle；`loadSection` 对进行中的加载去重（`loadingSections` Map 复用同一 Promise，失败返回 false 且导航回滚激活态） |
| `sections/*.html` | 21 individual section HTML fragments (log section removed), including `resource-updater.html` with read-only shared game path (set in 设置 page), update scope, download strategy, progress, actions, logs, and a Launcher integration intro card (switch + detailed settings on launcher-config page). Risk-service sections (`speed.html`, `input-bypass.html`, `cheat.html`) carry a `data-risk-overlay` container filled by `RiskGate`, plus a 查看风险须知 re-read link; `cheat.html` 为**密钥门版本**（密钥输入 + 解锁按钮 + 数据缺失提示），完整功能 UI 在解锁后由解密内容动态替换。`metadata-recovery.html`（Metadata 恢复，六步骤结构化流程）：步骤 1-2 IDA 定位器插件安装卡（自动探测/手动目录）+ 步骤 3 导入定位器导出卡（`locate_candidates.json` 或导出目录选择、候选下拉 rank1-5、载入按钮、载入信息区）+ 步骤 4 输入文件卡（metadata/dll 游戏目录自动推导提示、参考标准文件手动）+ 步骤 5 反编译文本/高级参数卡（导出载入后自动填充 textarea + hex，可手改）+ 步骤 6 运行流水线卡（单按钮执行 extract→verify→solve→apply，verdict 徽标 + 产物列表）+ 完整教程卡（Il2CppDumper 修复版外链）。`launcher-config.html` risk checkboxes carry `data-risk-service` attributes（作弊工具箱的集成项由 `cheat-shell.js` 动态渲染进 `#cheat-plugin-launcher` 占位容器，未同意前由 `RiskGate.refreshLauncherVisibility()` 整组隐藏）。`launcher-config.html` 已取消独立的汉化包下载配置（零协/OurPlay/LCTA-AU 三卡），原「汉化包下载配置」跳转卡已改为「调爪替换文本包」卡；**汉化包下载页与 Launcher 页拥有相同的 5 个勾选项**（下载页 `dl-tiaozhua-replace-*` / Launcher 页 `lc-tiaozhua-replace-*`，两套 id 映射同一 `ui_default.tiaozhua.replace_*` 配置键）。三种气泡（3/4/8）为互斥选项——`bindTiaozhuaReplaceSync()`（core.js）在任一页勾选时**同步另一页对应复选框视觉状态**并取消其余两个气泡（两页全量），进入任一侧时 `syncTiaozhuaReplaceFromConfig()`（utils.js initNavigation）按配置兜底刷新；后端 `_select_replace_packages` 兜底仅应用编号最小者；下载细节与「汉化包下载」页共用 `ui_default.{zero,ourplay,machine}` 一套配置 |
| `guide/*.md` | 20 in-app user guide pages (one per feature tab, including the embedded resource updater; `metadata-recovery.md` 为完整五阶段教程：背景原理/IDA 定位器/参数提取/验证/求解/提升/结果判读/FAQ/Il2CppDumper 链接) |
| `assets/update.md` | Release changelog (v5.0.2+) |

### webui/app_api/ — LCTA_API 功能域 mixin

| File | Mixin | Methods |
|------|-------|---------|
| `core.py` | `CoreMixin` | 核心管道：`__init__`/`config` 属性/`set_function`/`init_*`/`set_window`/`run_func`/`get_attr`/`set_attr`、日志（`log`/`log_error`/`log_ui`）、进度、模态窗口管理全套（`add_modal_id`/`check_modal_running`/`set_modal_running`/`del_modal_list`/`set_modal_status`/`add_modal_log`/`update_modal_progress`/`_make_cdn_callbacks`）、`browse_file`/`browse_folder`、`check_show`、`get_startup_data`。注意 `check_show` 用 `Path(__file__).resolve().parent.parent` 定位 `webui/assets/update.md`。模态取消语义：`_wait_continue` 暂停期间收到 cancel 立即抛 `CancelRunning`（不再吞掉）；`update_modal_progress` 将 percent 钳制为 [0,100] 整数；`_check_modal_running` 对不存在的 modal_id 返回 "running"（modal_list 条目的生命周期由前端 `complete()` 与后端 `except CancelRunning` 分支负责删除）。配置持久化走前端懒同步：控件 change → `bindConfigAutoSave`（core.js）→ `updateConfigValue` 防抖 500ms → `flushPendingUpdates` → `update_config_batch` → `set_batch(auto_save=True)` 写盘；已移除关闭时 JS 同步（`save_setting_from`/`events.closing` 钩子，历史死锁源头） |
| `config.py` | `ConfigMixin` | 配置读写：`update_config_value`/`update_config_batch`/`get_config_value`/`get_config_batch`/`save_settings`/`use_default_config`/`reset_config`/`save_config_to_file` |
| `translation.py` | `TranslatorMixin` | `start_translation`（消费 `translate_main` 返回值：打包失败返回 `success:False`）/`format_api_settings`/`test_api`（已接 modal_id，3 次串行翻译前 `check_modal_running`，取消返回 `已取消`）/`fetch_proper_nouns`（取消返回 `已取消` + `del_modal_list`） |
| `packages.py` | `PackagesMixin` | 汉化包安装/删除/切换/字体、Mod 管理、软链接、`move_folders`、`clean_cache`、`get_system_fonts`、`upload_cache_font`（上传本地字体替换缓存默认字体） |
| `download.py` | `DownloadMixin` | OurPlay / 零协 / LCTA 自动 / 调爪 下载 |
| `fancy.py` | `FancyMixin` | `get_fancy_rulesets`/`save_ruleset`/`import_bus_rules`/`fancy_main`/`check_fancy_marker`、规则编辑器窗口 `open_rule_editor`/`sync_theme_to_rule_editor`。`fancy_main` 返回 `{"success": bool, "message": str}`，取消返回 `已取消` + `del_modal_list` |
| `windows.py` | `WindowMixin` | 辅助窗口：`open_quick_editor`/`open_llm_fancy`/`open_translation_log_viewer`/`open_aria2_downloader`（泛用高速下载器，窗口关闭时 `aria2_manager.stop()` 释放 aria2c 进程）+ 其余 `sync_theme_to_*`、Nexus 测试窗口 `startTest`/`eval_skip`/`sign_eval_js` |
| `cdn.py` | `CdnMixin` | `cdn_*` 全部（Cloudflare/CloudFront 优选、hosts 写入/移除） |
| `speed.py` | `SpeedMixin` | `speed_*` 全部（DLL 注入/弹出/倍率） |
| `update.py` | `UpdateMixin` | `auto_check_update`/`manual_check_update`/`perform_update_in_modal`/`perform_update_from_file`。两个 perform_* 均已接线 modal_id（**下载阶段可取消**；安装/替换文件阶段不可取消为预期设计）、取消返回 `已取消` + `del_modal_list`；`perform_update_in_modal` 返回 `{"success": bool, "message": str}` |
| `input_bypass.py` | `InputBypassMixin` | `input_bypass_*` 全部（get_status/apply/inject/eject，转发到 `webutils.function_input_bypass.InputBypassManager`） |
| `cheat_core.py` | `CheatCoreMixin` | `cheat_core_*` 全部（status/unlock/lock/get_section_html/get_script_js）+ 插件通用分发 `cheat_plugins_list`/`cheat_plugin_invoke(action,args)`，转发到 `webutils.cheat_core` / `webutils.cheat_plugins`（密钥门前端入口；具体工具 API 不再有硬编码 mixin） |
| `drops.py` | `DropMixin` | `handle_dropped_files`/`on_drop`/`eval_dropped_files` |
| `metadata_recovery.py` | `MetadataRecoveryMixin` | `metadata_recovery_status`（输出目录/IDA 插件探测/游戏文件自动推导 `derive_game_files(game_path)`）/`metadata_recovery_install_ida_plugin`（自动安装定位器插件，可传手动目录）/`metadata_recovery_load_export(path, rank)`（载入 IDA 插件导出，log_ui 摘要）/`metadata_recovery_run`（后台线程 + modal 进度执行 `run_recovery`，支持取消；modal_id 仅由前端 ProgressModal 注册，取消返回 `已取消` + `del_modal_list`） |
| `resources.py` | `ResourceMixin` | `resource_updater_*` 转发到 `self.resource_updater_api` |
| `exceptions.py` | — | `CancelRunning` re-export（实现在 `globalManagers/exceptions.py`，业务层 webutils/translateFunc/launcher 直接导入共享层，避免反向依赖 webui；`webui/app.py` 亦 re-export） |
| `assets/LCTA-AU.md` | Auto-update system documentation |
| `assets/firstUse.md` | Short first-use welcome with direct entry to the three-step quick-start flow |

## webutils/ — Business Logic Layer

Public API aggregated in `__init__.py`. Each `function_*.py` handles one feature domain.

| File | Feature | Key Points |
|------|---------|------------|
| `__init__.py` | Public API surface | Re-exports all feature functions consumed by `webui/app.py` |
| `clr_bootstrap.py` | pythonnet/clr_loader 引导 | `ensure_clr()` 强制 netfx 并导入 clr:预检 `Python.Runtime.dll` 存在性、clr_loader 版本(<0.2.8 警告)、.NET Framework >=4.7.2;失败时用 PowerShell 反射探针暴露 clr_loader 吞掉的真实异常并给出修复指引,不再自动回退 coreclr/mono。被 `start_webui.py`、`launcher/gui_progress.py`、`launcher/speed_hotkey.py` 共用 |
| `utils/` | Shared utility package | `io.py` zip/unzip, hashing, 7z integration（环境无 7z 时自动从官网下载 7zr.exe 到 `tools/7z/`）; `net.py` downloads（`download_with`/`download_with_github` 透传 `CancelRunning`，不再吞成失败）；`shell.py` Windows Shell API（`_move_folders` 移动、`get_downloads_dir` 经 SHGetKnownFolderPath 解析真实「下载」已知文件夹，支持用户迁移重定向，失败回退 `Path.home()/Downloads`）; `font.py` font caching（`get_cache_font` 缓存优先回退链 + `save_cache_font` 上传/拖入本地字体替换 `cache_path/ChineseFont.ttf`）; `misc.py` steam command/icon; facade re-exported via `utils/__init__.py`。`zip_folder` 支持可选 `modal_id`（打包循环内逐文件 `check_running`，取消透传） |
| `load.py` | Config & game detection | Config loading/validation, Steam registry game path detection |
| `update.py` | Self-updater | GitHub Releases-based auto-update. `install_requirements` 按**包名**比对 requirements（去行内注释/空行/选项行，PEP 503 归一化）：涉及依赖移除或版本变动时，将整个依赖修改写入 pending 文件（`%LOCALAPPDATA%/LCTA/pending_pip_ops.json`），延迟到下次启动、加载任何扩展包 DLL 之前由 `apply_pending_pip_ops()` 统一执行（先卸载后安装）——规避 pythonnet/clr_loader 等已加载 DLL 包在更新会话中无法卸载/替换的问题；仅全新依赖立即安装，失败跳过继续。`check_and_update` 缓存下载/解压置于 `tempfile.mkdtemp` 临时目录（不再用应用目录内 `updateCache`，否则 update_files 清空应用目录时销毁解压源导致复制必然失败），finally 清理（仅清理本函数自建的临时目录，调用方传入的缓存目录保留）；`update_files` 失败时还原 `install_requirements` 写入的 pending 操作记录（避免下次启动按新版本依赖卸载旧代码） |
| `translator_constants.py` | API provider configs | TranslateKit provider definitions (Baidu, Google, DeepL, etc.) |
| `function_llc.py` | LLC/零协会 install | Download & install Zero Association translation packs |
| `function_ourplay_pc.py` | OurPlay PC install | Download OurPlay PC translation packs |
| `function_ourplay_android.py` | OurPlay Android install | Download OurPlay Android-origin translation packs |
| `function_LCTA_auto.py` | Auto-translate download | Download from LCTA_auto_update repo |
| `function_lanzou_tiaozhua.py` | 调爪 text package | One-click 调爪 text modification package download via qaiu API (getFileList + parser) and import as bus rulesets。另有调爪「替换」文本包（3彩色气泡/4无色气泡/5随机加载文本/7事件美化/8旧翻译版气泡，包 6 与文本美化重复永不集成）：`function_lanzou_tiaozhua_replace_main` 按 `ui_default.tiaozhua.replace_*` 勾选下载（`_select_replace_packages` 强制 3/4/8 气泡互斥仅留编号最小者），`install_replace_package` 用 zipfile **选择性拷贝** `文件/*.json` 到 `resolve_replace_target_dir`（`get_active_lang_path`+config.json 的 lang 值），跳过包内冗余 `python/` 解释器，成员名经 `_sanitize_zip_member_name` 校验；各包独立版本缓存 `tiaozhua_replace_<n>_version.txt` |
| `packages/install.py` | Local package install | Install/delete/font-change for local translation packages。`install_translation_package` 含取消检查点（rmtree 旧包前/逐文件复制/写配置前）；zip 压缩包安装前对全部成员名做 `_sanitize_zip_member_name` 路径穿越校验（拒绝空/`.`/`..`/盘符/绝对路径，空包报错），安装目标为当前启用汉化目录（`get_active_lang_path`，禁用态 `_lang`，不重建 lang 造成双目录）；`change_font_for_package` 保留既有检查点并覆盖文件夹分支（文件夹分支在临时目录副本替换字体后产出 `{name}_fonted.zip`）；zip 打包经 `io.zip_folder(modal_id=...)` 可取消 |
| `packages/manage.py` | Package management | Installed packages, mod management, symlink operations; `get_active_lang_path()` 返回当前启用汉化目录（禁用态 `_lang`）；`toggle_install_package` 移动前先删除已存在的旧目标避免嵌套移动；`remove_symlink_for` 返回 bool 并记录错误 |
| `packages/clean.py` | Cache cleaner | Clean game cache files（循环头 `check_running` 检查点，置于 try/except 之外避免被吞） |
| `function_fetch.py` | Proper noun scrape | Fetch proper nouns from remote sources（每页请求前 `check_running`，可取消） |
| `function_fancy.py` | Text effects orchestration | Selects enabled v2/bus rulesets, fixed bus-first execution order (bus 文本替换先于 v2 文本美化, stable within each engine), prepares skill-color resources only when required, scans UTF-8-SIG language JSON, atomically rewrites final changes, writes a `.lcta_fancy_applied` marker into the beautified language-pack directory (with `has_fancy_marker` for second-run UI confirmation), and returns `FancyRunStats`. 文件循环头带 `check_running` 取消检查点。Also owns validated `fancy/` load/save/delete and shared bus/调爪/LCJE/FL import helpers |
| `fancy/` | Rule engine family | `engine.py` (compiled v2 beautification engine: validates/compiles file globs, structured JSON paths, AND conditions and typed actions, filters rules per file, returns exact changed paths via `ApplyResult`; `faust`/`skillColorHandler` imports hoisted out of the per-value loop with lazy caching), `bus.py` (bus replacement engine + converters: `format: lcta-bus`/`version: 1`, compile-time exact/dynamic file indexes with deduplicated shared glob/regex matchers, precomputed case-insensitive dir exclusions, optional prematched-rules argument on `apply_bus` to avoid double file matching, cached selector indexes by list path/field with mutation invalidation, regex-accelerated safe replacements, wildcard/index/selector paths, ordered literal/regex/end/safe/set operations, 调爪/LCJE/FL补丁 & quick-edit conversion; LCJE accepts both path-map patches and the reference editor's `{mods:[{file,path,old,new}]}` format), `builtin_data.py` (built-in rule data: `fancy`, `TEXT_REPLACEMENTS`, `EGO_WARNING_ACTIONS`, `EGO_NORMAL_ACTIONS`, `SKILL_COLOR_ACTIONS`), `builtin_func.py` (`SkillColorHandler` lazily extracts skill attributes from Unity resources, fingerprints top-level account folder names, caches color mappings in `tmp/fancy/skill-colors.json`, records cache hits, suppresses retries after init failure), `faust.py` (Faust character-specific fancy text rules; gradient processing rewritten as a single pass with a module-level hex lookup table and inlined interpolation, output identical to the previous per-character implementation). Facade re-exports all public symbols |
| `llm_fancy/` | LLM text-beautification window backend, fully decoupled from `translateFunc/` (imports only `translatekit`, `webutils/fancy/bus.py`, `webutils/function_fancy.py`, `globalManagers/`). `config.py` (`LLMFancyConfig` + ConfigManager persistence under `ui_default.llm_fancy`, incl. `dedup_enabled`), `scanner.py` (bus-syntax selection rules: file matchers + `parse_bus_path` tokens, independent path-resolution walker, `Candidate` collection with `set`-ready `bus_path` serialization, skips empty/`-` placeholders, `dedup_candidates` exact-text dedup returning representative candidates + groups), `exclude.py` (user-selected fancy/ bus rulesets simulated via `apply_bus` on a data copy; changed paths excluded from LLM candidates), `splitter.py` (greedy batch splitting by estimated size, default 20000 chars; 超长条目按 JSON 渲染长度二分 + 自然边界回退切分为子条目独立成批（`split_text`/`split_items(splitter=...)`），批次外层包装开销 `_BATCH_WRAPPER_OVERHEAD` 计入分批判断), `llm.py` (`LLMGeneralTranslator` wrapper mirroring `format_api_settings` normalization, default parse-guarantee system prompt + optional user custom prompt, code-fence-stripping JSON array response parser with per-item `None` fallback), `builder.py` (results → validated `lcta-bus` ruleset with exact-file `set` rules, saved via `save_ruleset_to_folder` and auto-enabled in `fancy_allow`), `runner.py` (scan → exclusion → optional dedup → split → `ThreadPoolExecutor` LLM batches → expanded per-path results → ruleset; `scan_preview`/`run_beautify` with log/progress callbacks and cancel event; 超长候选分割后按子条目结果拼接还原；批次回调在 cancel 时抛 `LLMFancyCancelled`; `resolve_lang_dir` reads `Lang/config.json`). Facade re-exports all public API |
| `function_translate.py` | Translation orchestration | Connects webui to translateFunc pipeline。`translate_main` 返回打包是否成功（bool）：zip 失败不再推 100%、不再弹资源管理器 + sleep(60)；打包阶段经 `zip_folder(modal_id=...)` 可取消 |
| `function_translation_logs.py` | Translation diagnostics viewer backend | Reads only the user-selected `.jsonl` within its selected parent directory; v2-only indexing, cached summaries/byte offsets, filtering, pagination, lazy record reads, and filtered JSONL export |
| `drop/` | Drag-and-drop | Former `function_drop.py` split into a package: `handler.py` (`DropFileHandler` 接口 ABC + `DropFileHandlerRegistry` 注册表 + `remove_existing`/进度辅助), `context.py` (`FileExecutionContext`), `inspect.py` (zip/folder/json 只读快照，供各处理器复用), `handlers/` (每个 NAMEREFER 类别一个处理器类：`translation.py` full/nofont 汉化包、`archive_mod.py` FLmod/jsononly 压缩模组包、`copy_mod.py` carra/bank/textFile/LCTAchange/FLchange 单文件复制、`font.py` 缓存字体替换（.ttf/.otf → `cache_path/ChineseFont.ttf`）、`bus_import.py`、`update.py`、`invalid.py`；`__init__.py` 按容器类型分组的有序检测注册表), `detect.py` (`evalZip`/`evalFolder`/`eval7zip`/`evalJson`/`evalFile` 门面；`evalZip` 解包/检测异常返回 `invalid` 不崩溃), `message.py` (`makeMessage`，显示名来自注册表), `eval_files.py` (`evalFiles` 主流程，按类型查注册表执行，结果含 `fonts` 计数; handler 抛 `CancelRunning` 立即上抛中止；存在错误时不推 100%)；zip/7z extraction, mod installation, update package handling via Updater, plus bus/调爪/LCJE/FL JSON recognition and shared import into `fancy/` |
| `metadata_recovery/` | **Metadata 恢复**（移植自私有仓库 LimbusMetadataRecovery）：`report.py`（门/review/裁决框架）、`locator.py`（IDA 定位器：xorshift 指令扫描 + 反编译特征评分，`INSIDE_IDA` 守卫三态兼容——包内导入/独立脚本/MCP py_exec_file）、`extractor.py`（反编译文本 → header/seed/表/7 节段参数 + 证据行）、`verify.py`（布局判定 + 结构门验证闭环）、`solver.py`（31 段映射：C1 记录大小 + C5 内容指纹 + C3 链装配 + 重建）、`profile.py`（正式 profile 提升 + 自检 SHA）、`pipeline.py`（离线四阶段编排 `run_recovery()`：表 hex 解析（手工/`read_rva_data` 从 GameAssembly.dll 按 VA 读取）/提取/验证/求解/提升，阶段边界取消点、每阶段 report 落盘 `metadata_recovery/run_<时间戳>/`）、`__init__.py` 门面（+`install_ida_plugin`/`find_ida_plugins_dir` 自动探测注册表与常见路径写入 `metadata_locator_plugin.py` + `metadata_recovery_tools/`，热键 Ctrl-Alt-Shift-M；+`derive_game_files` 从游戏根目录推导 `LimbusCompany_Data/il2cpp_data/Metadata/global-metadata.dat` 与 `GameAssembly.dll`；+`load_locator_export(path, rank)` 载入 IDA 插件导出——兼容目录或 `locate_candidates.json` 文件，解析 verdict + 全候选（探测 `decompile_rank{n}_{name}.c` 存在性），按 rank 取替换表 hex 与反编译文本，错误明细入 `errors[]`） |
| `cdn/` | CDN optimization | Former `function_cdn.py` split into a package: `constants.py` (常量定义，对应 LLC_BABEL CdnTarget.cs), `classify.py` (CloudFront 探测失败分类), `cfst.py` (CloudflareSpeedTest 子进程 + CSV 解析), `cloudfront.py` (CloudFront DNS 候选发现与 HTTPS 端点探测), `selector.py` (CloudFront 两阶段 IP 选择), `hosts.py` (hosts 文件管理：编码/BOM 保留、受管标记块写入、原子替换前清除只读属性、`raise_on_permission_error` 权限错误重抛供提权判断、`elevated` 失败文案区分；权限/占用类替换失败按 `REPLACE_MAX_ATTEMPTS` 次短间隔重试，全部失败后经 Restart Manager API 分析占用进程 PID 与路径并附加到错误文案), `elevate.py` (管理员提权写入/移除 hosts 与提权子进程入口；策略：非管理员先真实尝试直写，仅权限类失败才触发 UAC 提权重试——无"新建文件"探针，避免假阳性短路提权路径), `optimize.py` (完整优选流程编排，含缓存 TTL 避免重复测速); facade re-exports all public API |
| `function_speed.py` | Game speed | Game speed acceleration via openspeedy DLL injection; `is_injected()` checks self-tracked injection state |
| `function_input_bypass.py` | 输入反检测 (CommonLib import anti-detection) | Injects `hooks/rawinput_hook.dll` into `LimbusCompany.exe` and controls synthesized/real input counts via a named shared-memory map (`Local\LCTA_RawInputHook_Config`, 80-byte `RHConfig` matching the C struct). `auto` mode zeroes synthesized counts/ratios; `manual` mode overrides the 4 counts (real/synth × mouse/key) from `launcher.work.input_bypass_*` config, auto-calculates the synth ratio as `synth/(real+synth)` (clamped `< 0.9`), and supports a `volatility` percentage (0-50) that makes the C hook jitter counts within a time window so reported values aren't constant. Manager API: `apply()` (write config), `inject(pid)`/`eject()`, `get_status()`, `close()`; pure helpers `parse_count`/`parse_percent`/`parse_ratio`/`auto_ratio`/`build_config` clamp values (ratios to `[0, 0.9)` to avoid the game's reset-window logic). Explicit `restype`/`argtypes` declarations for kernel32 calls so 64-bit handles/pointers are not truncated；注入后经 psapi `EnumProcessModules`/`GetModuleBaseNameW` 按 DLL 文件名取真实 64 位 HMODULE（失败回退远程线程退出码）；C 端 `detach_hook` 卸载前恢复残留 detour 防悬空 |
| `function_aria2_downloader.py` | 泛用高速下载器 | `Aria2DlClient`（aria2c JSON-RPC 封装：仅本机 loopback + secret 认证、`--seed-time` 可配做种、`--content-disposition-default-utf8=true`、addUri/addTorrent(base64)/pause/forcePause/unpause/remove/forceRemove/removeDownloadResult/pauseAll/unpauseAll/purgeDownloadResult）+ `Aria2DownloaderManager` 模块级单例 `aria2_manager`（幂等 start_server 按 `ui_default.aria2_dl` 配置并发/连接数/做种时间启动子进程 + 后台 1s 轮询快照回调；add_urls 校验 http/https/ftp/magnet 前缀与去重，**不强制 out**——落盘名由 aria2 按 Content-Disposition 优先解析（哈希段 URL 不再落成长 hex 文件名），**保存目录必须已存在，不自动创建**，缺失时返回错误不创建任务；add_torrent 校验 .torrent 扩展名；暂停 remove 失败逐级兜底 forcePause/forceRemove/removeDownloadResult；快照聚合状态计数/总速度/百分比，显示名链 `bittorrent.info.name` → `files[0].path` 基名（全类型）→ `derive_display_name(url)`（仅显示回退），并**收养磁力派生任务**——元数据取回后 aria2 以新 gid 派生文件下载，按 dir 匹配收养进原任务记录）。`resolve_aria2_binary` 复用 `resource_updater.core`（单一来源）。配置键 `ui_default.aria2_dl.{save_dir,jobs,connection_limit,seed_time}` |
| `function_steam_launcher.py` | Steam 启动器设置 | 通过 vdf 库一键把《Limbus Company》(appid 1973530) 的 LaunchOptions 写入 `userdata/<账号>/config/localconfig.vdf`（键名用 Steam 实际的小写 `apps`）。路径自动生成：`get_steam_path()` 读注册表 `HKCU\SOFTWARE\Valve\Steam\SteamPath` 并归一化分隔符；`resolve_localconfig_path()` 主用 `config/loginusers.vdf` 的 `MostRecent==1` 账号，缺失时回退扫描 `userdata\*`（含 appid 条目优先、账号 ID 降序）。`is_lcta_launch_options()` 以 `' -launcher %command%'` 判定是否 LCTA 型启动项；`get_current_launch_command()` 生成当前 LCTA 命令（异常返回 None）；`get_steam_launcher_status()` 返回 `state`（missing/unconfigured/lcta_current/lcta_stale/lcta/other，`lcta_current`=与当前命令精确相等、`lcta_stale`=旧版 LCTA 命令、`lcta`=当前命令不可比较）+ `is_current_lcta`（True/False/None）+ steam.exe 运行态供前端展示（前端只显示状态文本，不展示原始路径与值）；`set_steam_launch_options()` / `clear_steam_launch_options()` 先备份 `localconfig.vdf.lcta.bak`，`vdf.load` 后写入/移除 LaunchOptions（保留该游戏其他字段），按原 BOM 状态 `vdf.dump` 写回。VDF 解析/写回用 `escaped=False` 并还原/转义引号（`_restore_vdf_quotes`/`_escape_vdf_quotes`），反斜杠路径（`D:\LCTA\temp` 类）原样保留，不会被误解码为 TAB/换行。写入内容来自 `webutils/utils/misc.py get_steam_command()`。入口：Launcher配置页 steam命令旁「写入Steam启动选项」/「清除启动项」按钮 |
| `cheat_plugins.py` | 作弊工具箱**插件宿主**（公共仓库） | 解锁后读私有仓库 `cheatcore/registry.py` 的插件描述符自动注册：`reload()`（读 `get_plugins()` + 播种配置默认值到 ConfigManager）、`list()`（插件摘要）、`invoke(action,args)`（按注册表 api 白名单分发到**声明该 action** 的插件管理器类）、`run_launcher_phase(phase)`（查 enabled_key + consent 后调 on_start/on_stop）、`close_all()`（atexit 兜底）。未解锁时 `_plugins` 为空，安全短路。替代旧 `DamageHookManager` 门面——主仓库不感知具体工具 |
| `cheat_core.py` | CheatCore 解密加载器 | 密钥门核心：`blob_path()`（`<path_>/cheat_core/cheat_core.bin` + 仓库相对路径兜底）、`dev_src_dir()`（`LCTA_CHEAT_DEV_SRC` 环境变量 > 仓库根 `LCTA_CheatingCore/` 克隆，开发模式免密钥直连）、`runtime_dir()`（`%LOCALAPPDATA%/LCTA/cheat-core`）、`unlock(key)`（校验解密 → 逐文件 SHA-256 校验 → dest 路径净化（拒绝 `..` 段/盘符/绝对路径，防写穿运行时目录）→ 释放文件 → sys.path 动态导入 `cheatcore` 包 → `_reload_plugins()` 触发插件注册）、`ensure_unlocked()`（dev > 已解锁 > 持久化密钥自动解锁 > blob_missing/blob_corrupt/need_key）、`lock()`（清配置密钥/内存态/插件注册/sys.path/运行时目录）、`get_package()`/`section_html()`/`script_js()`（未解锁抛 RuntimeError）。格式说明见私有仓库 README。密钥持久化于 `cheat_core.unlock_key`。blob 结构/校验失败与密钥错误区分（`BlobCorruptError` → reason `blob_corrupt`，保留已持久化密钥不清除；密钥错误 → `invalid_key`）。功能实现（偏移 API 缓存锚定、共享内存 DHConfig、伤害日志环形缓冲）在私有仓库 `cheatcore/cheat_damage_hook.py` |
| `function_resource.py` | Unity resource reader | Locates Limbus resource files and extracts text assets in batches through UnityPy; sets fallback Unity version `6000.3.12f1` for resources without usable version metadata; skips objects whose container is missing/None (UnityPy returns `None` for objects outside the container map) instead of crashing |
| `rule_editor/` | Rule editor backend | `browser.py` (file browser: `_get_lang_dir`（不再缓存、随配置实时解析）, `get_lang_files`, `get_category`, `get_file_content`, `search_files` — raw text occurrence counts with `utf-8-sig`, so BOM and temporarily invalid JSON files remain searchable — and JSON-validated `save_file_content` with backup + 临时文件 `os.replace` 原子写，失败清理残留), `rules.py` (ruleset CRUD: `get_ruleset_list`, `get_ruleset`, `save_ruleset`, `create_ruleset`, `delete_ruleset`, `apply_ruleset_to_content` + form helpers `build_rule_from_form`, `validate_rule`), `generate.py` (V1/V2/V3 smart analysis, change clustering, 5-dimension scoring, merge-candidate detection — V3 合并候选为语义验证：`_rule_covers_items` 用一组的规则推广覆盖另一组原始变更 `_raw_changes`，结果一致才可合并;实际合并 `_mergeTwoGroups`/`_autoMergeCandidates` 在前端 `rule-editor.js`), `quick.py` (quick editor backend: deep JSON diffs `{file, path, old, new}`, persistence of edits plus derived bus `set` rules to `fancy/_quick_edits.json`, legacy migration, per-edit path failures and atomic writes), `constants.py` (single-source-of-truth `FILE_PREFIX_RULES`, `CATEGORY_FILE_PATTERNS`, `COMMON_REPLACEMENTS`, `TEMPLATES`; JS fetches via `get_editor_constants()` API with hardcoded fallback). Facade re-exports all public API |
| `debug_environ_test.py` | Environment diag | Environment diagnostics on startup failure |

## webFunc/ — Infrastructure Layer

| File | Purpose |
|------|---------|
| `GithubDownload.py` | GitHub Release API client: proxy support, rate limiting, concurrent downloads |
| `FileTransfer.py` | File upload client (UpFileClient) |
| `LanzouFolder.py` | Lanzou cloud drive folder downloader (modified from 52pojie) |
| `Webnote.py` | Webnote/note.chat API client for remote config/data |

## translateFunc/ — Translation Engine

Standalone library with own `__init__.py` public API.

**Root files:**

| File | Purpose |
|------|---------|
| `__init__.py` | Public API |
| `pipeline.py` | `TranslationPipeline` — end-to-end orchestration |
| `config.py` | `TranslateConfig` dataclass, `PipelineSummary`, `ProcessOutcome` |
| `enums.py` | `ProcessResult`, `FileType`, `MatchConfidence` enums |
| `processor.py` | `FileProcessor` — per-file translation logic; Stage 2 self-check on the combined translation result. KR 缺失/解析失败返回 `JSON_DECODE_ERROR`；EN/JP/LLC 参考文件缺失或损坏时按缺失回退（不中断流程） |
| `workers.py` | `WorkerPool` — concurrent translation execution |
| `translate_request.py` | LLM API request construction and response parsing |
| `translate_doc.py` | Translation documentation/help |
| `get_proper.py` | Proper noun fetching from remote sources |
| `log_bridge.py` | Bridge between translateFunc logging and global LogManager |
| `profiler.py` | `TimingProfiler` — performance profiling |
| `recorder.py` | `TranslationRecorder` — per-translation dump record writing (JSONL) |
| `validator.py` | `RuleBasedValidator` — deterministic post-processing checks between Stage 1 and Stage 2. Detects/auto-fixes: `[ID]` bracket spacing errors, missing effect references. Skill files only, controlled by `enable_rule_validation` config |

**Subdirectories:**

| Path | Purpose |
|------|---------|
| `builder/prompt.py` | LLM prompt construction: `PromptFactory` with XML/JSON format-aware escape rules, response parsing with repair fallbacks. v1 prompt_version removed; only v2 (priority-tagged rules, reasoning-first) remains. Supports file-type-conditional rules via `_FILETYPE_RULES` (SKILL/STORY/UI) |
| `builder/request.py` | API request building with format-aware input limits, equal-partition splitting, and per-part reference trimming |
| `builder/stages.py` | Pipeline stage definitions |
| `builder/examples.py` | Example translations for few-shot prompting |
| `matcher/engine.py` | `MatcherEngine` — proper noun/effect matching orchestration; Korean effect-name hits are cross-checked against JP/EN BattleKeywords names when references are available |
| `matcher/ac_automaton.py` | Aho-Corasick automaton for fast multi-pattern matching |
| `matcher/proper.py` | `ProperAnalyzer` — proper noun analysis |
| `proper/analyze.py` | Proper noun analysis utilities |
| `proper/flat.py` | Proper noun flattening/normalization |

## globalManagers/ — Cross-Cutting Singletons

| File | Purpose |
|------|---------|
| `ConfigManager.py` | Singleton config: dotted-path access (`ui_default.translator.enable_proper`), JSON validation via `config_check.json`, auto-save on mutation, thread-safe。`get()` 对 dict/list 返回内部活引用（调用方不应在锁外修改/跨线程共享）；`raw` 属性返回深拷贝；`save()`/`reset()` 带 `_generation` 守卫，旧实例（如 reset 后残留引用）不得再写盘 |
| `LogManager.py` | Singleton logger: file rotation, console output, webview modal callbacks via thread pool for async UI updates; also configures `fancy`/`rule_editor` child loggers with the same handlers so their INFO/DEBUG output lands in `app.log` |

## launcher/ — Standalone Launcher (GPL-3.0)

| File | Purpose |
|------|---------|
| `main.py` | Entry point: pipeline orchestration — creates `LaunchPipeline`, registers handlers for resource-update/mod/speed-hotkey, optionally creates the WinForms launch center, then emits pipeline phases in order. Connects LogManager modal status/progress, resource download progress, CDN percentages, stepped mod preparation, and launch-process milestones to the GUI. Uses `subprocess.Popen` (not `subprocess.call`) for game launch to support cancel-flow from GUI |
| `game_launch.py` | Game launch phases: `prepare_mod(steam_argv, progress_callback, cancel_event)` (mod patching pre-game; 各步骤间 `check_cancel()`，cancel_event 触发即中止), `cleanup_mod_assets()` (post-game restore), `start_speed_hotkey()` / `stop_speed_hotkey()` (lifecycle wrappers), `start_input_bypass()` / `start_cheat_plugins()` / `stop_cheat_plugins()`（`start_cheat_plugins` 先 `cheat_core.ensure_unlocked()`，通过后 `CheatPluginHost.run_launcher_phase('start')` 通用分发到插件 on_start，注入逻辑在私有仓库 `start_launcher()`）。Game process launch moved to `main.py` pipeline |
| `updates.py` | Translation pack update system (Factory pattern for LLC/OurPlay/Machine). 汉化包下载参数改读 `ConfigManager().get('ui_default')` 的 `zero`/`machine`/`ourplay` 段（与「汉化包下载」页共用一套配置，不再读 `launcher.{zero,machine,ourplay}`；`launcher.work.*` 更新模式/集成开关仍读 `launcher` 段）。Optional post-update beautification passes all built-in/user rules plus the enable map to `fancy_main()`, allowing disabled skill-color rules to avoid resource preparation |
| `cdn.py` | CDN optimization for launcher mode with cache TTL to avoid redundant speed tests |
| `patch.py` | Unity asset patching for mods |
| `modfolder.py` | Mod folder management and detection |
| `sound.py` | Sound file replacement for mods |
| `changes.py` | Text data patch application |
| `compress.py` | Compression utilities |
| `speed_hotkey.py` | Game speed hotkey (Ctrl+Shift+S) with comprehensive lifecycle logging, foreground process check, .NET STA threading for UI; 倍率窗口用 `_slider_lock` 防重复弹出，后台 STA 线程不再阻塞热键线程 |
| `gui_progress.py` | WinForms launch center for GUI mode: dark card layout with header/status badge, configuration summary (game path/update mode/enabled integrations/launch source), vertical dynamic phase rail, separate overall and stage progress bars, detailed task text, expandable real-time log panel, explicit cancel/exit action, and running/exited views with PID, uptime, hotkey hints, runtime, and exit code. `register_to_pipeline()` wires GUI to `LaunchPipeline`; dedicated modal/resource/CDN progress adapters accept real backend progress; `FormClosing` retains the cancel/launcher-only/game-termination confirmation flow |
| `pipeline.py` | `LaunchPipeline` — phase-based event-driven pipeline: `on(phase, callback)` for module registration, `emit(phase, **kwargs)` to trigger all callbacks. Defines 8 phases (`PHASE_INIT` through `PHASE_EXIT`, including `PHASE_RESOURCE_UPDATE` between check_update and cdn). `cancel_event` (threading.Event) supports GUI-initiated abort. `context` dict shares state (steam_argv, game_process, game_pid) across phases |

## resource_updater/ — Official Game Resource Updater

| File | Purpose |
|------|---------|
| `core.py` | Core updater: validates game files, extracts S/L CDN tokens and the real remote catalog URL, uses the game-compatible Unity request headers, hashes `LimbusCompany.exe`, parses Bundle names/cache keys, downloads token-scoped localize ZIPs, safely deploys localize files, populates Unity cache entries, removes failed Bundle entry directories, logs through `LogManager`, and manages bundled aria2c JSON-RPC with urllib fallback. Download failures are reported at WARNING level with file name + error code and collected into `failed_items` in the run result; aria2 polling progress logs are throttled to count changes (progress callbacks still fire each poll). Transient failures (aria2 error state, builtin downloader exceptions, remote catalog fetch) are automatically retried with a configurable `retry_max`/`retry_delay` backoff (0 = disabled, keeps legacy behavior); exhausted retries run a Range probe (`_probe_failure`) that captures status code + diagnostic response headers into `failed_items[].diagnostics`, and the run result aggregates a `retried` counter |
| `service.py` | Shared configuration/state service. Stores Launcher state under `%LOCALAPPDATA%/LCTA/resource-updater/launcher-state.json`, compares the local `LimbusCompany.exe` SHA-256 fingerprint, checks whether prior partial runs cover current configured scopes, and records update results (success or failure) via `record_update_result` — only fully completed scopes are marked so failed scopes are retried on the next launch. Also persists the last result (success/failed/retried counts + failed item names/reasons) under `last_result` and exposes retry defaults (`retry_max=2`, `retry_delay=30`, `connection_limit=8`) from config |
| `web_api.py` | Main-window resource updater controller. `LCTA_API` delegates prefixed bridge methods to it; it probes the shared game directory (read from main config `game_path`), persists updater options (including retry settings), runs/cancels the worker, records results, exposes the last update result to the page, and logs lifecycle/errors through `LogManager` |
| `__init__.py` | Public resource updater exports used by Launcher and tests |

## Import Dependency Graph

```
webui/app.py                       (thin shell: 组装 LCTA_API + main + re-export)
  → webui/app_api/core.py          CoreMixin: ConfigManager/LogManager/ResourceUpdaterAPI,
                                   webview, webutils.load, GithubDownload, translator_constants
  → webui/app_api/{config,translation,packages,download,fancy,windows,cdn,speed,update,
                    drops,resources}.py  各功能域 mixin → webutils/ (feature functions)
  → webui/app_api/metadata_recovery.py   MetadataRecoveryMixin → webutils.metadata_recovery/
      （run_recovery 编排 extractor/verify/solver/profile；install_ida_plugin 纯 stdlib）
  → webui/rule_editor_api.py       RuleEditorAPI → webutils/rule_editor/, function_fancy
  → webui/quick_editor_api.py      QuickEditorAPI → webutils/rule_editor/
  → webui/llm_fancy_api.py         LLMFancyAPI → webutils/llm_fancy/
  → webui/translation_log_api.py   TranslationLogViewerAPI → webutils/function_translation_logs
  → webutils/ (all feature functions via __init__.py)
    → translateFunc/ (translation pipeline)
    → webFunc/ (GitHub downloads, file transfer)
  → globalManagers/ (ConfigManager, LogManager)
  → webutils/rule_editor/ (file browser, rules CRUD)
  → webutils/function_fancy.py (load_fancy_folder_rules, fancy_main)
  → webutils/llm_fancy/ (LLMFancyAPI: scan/exclude/split/LLM/ruleset build; imports translatekit only, no translateFunc/)

webutils/rule_editor/
  → webutils/function_fancy.py (load_fancy_folder_rules, save_ruleset_to_folder, etc.)
  → webutils/fancy/engine.py (shared v2 validation)
  → webutils/fancy/bus.py (compile_bus_ruleset, is_bus_ruleset)
  → globalManagers/ConfigManager.py (browser._get_lang_dir)

webutils/function_fancy.py
  → webutils/fancy/engine.py (compile_rulesets, apply_rules)
  → webutils/fancy/bus.py (compile_bus_ruleset, apply_bus, import conversion)
  → webutils/fancy/builtin_func.py (lazy skill-color preparation when required)
    → webutils/function_resource.py (Unity text asset extraction)

launcher/updates.py
  → webutils/function_fancy.py (loads folder rules and executes only rulesets enabled by fancy_allow)

launcher/main.py
  → launcher/gui_progress.py (if gui_mode enabled: WinForms progress window)
  → launcher/updates.py (reuses shared webutils/webFunc install, download and beautification helpers)
  → launcher/game_launch.py
  → launcher/cdn.py
  → resource_updater/service.py (fingerprint-gated official localize/Bundle pre-download)

resource_updater/web_api.py
  → resource_updater/core.py (manual update worker with retry)
  → resource_updater/service.py (config, retry defaults, and last-result state)
  → globalManagers/ConfigManager.py

Note: `launcher/` is separately GPL-3.0-licensed, but the current Python implementation is not import-isolated: launcher modules directly reuse `webutils/`, `webFunc/`, and `globalManagers/`.
```

## Key External Libraries

| Package | Used In | Purpose |
|---------|---------|---------|
| `pywebview` | `webui/app.py` | Native desktop webview window |
| `translatekit` | `webutils/`, `translateFunc/` | Multi-provider translation API (Baidu, Google, DeepL, LLM) |
| `UnityPy` | `launcher/patch.py`, `webutils/function_resource.py` | Unity asset patching plus batched text-asset extraction for skill-color beautification |
| `openspeedy` | `webutils/function_speed.py`, `launcher/speed_hotkey.py` | DLL injection for game speed |
| `keyboard` | `launcher/speed_hotkey.py` | Global hotkey registration |
| `requests` | `webFunc/GithubDownload.py` | HTTP client with proxy support |
| `Brotli` / `lz4` / `etcpak` | `webutils/`, translate pipeline | Compression/decompression |
| `pillow` / `texture2ddecoder` | `webutils/` | Image and texture processing |
