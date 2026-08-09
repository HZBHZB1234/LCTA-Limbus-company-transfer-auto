# LCTA Module Map

<!-- Last updated: 2026-08-09 -->

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
| `CFST/` | CloudflareSpeedTest binary + IP lists | 3 |
| `hooks/` | C source for native DLLs | `rawinput_hook.c` (input bypass), compiled to `rawinput_hook.dll` by build.ps1 / CI; 作弊工具箱的 hook DLL 源码已迁往私有仓库 LCTA_CheatingCore（`hooks/*.c` 扫描编译，见 `cheat_core/`） |
| `vendor/minhook/` | 空（MinHook 已随作弊工具箱功能迁往私有仓库） | — |
| `scripts/` | 单文件脚本 | `cheat_encrypt.py` — CheatCore 加密器（私有仓库功能文件 → `cheat_core.bin`，格式见私有仓库 README） |
| `cheat_core/` | 运行期加密数据（构建产物，不入库） | `cheat_core.bin` — 加密的作弊工具箱功能包，由 webutils/cheat_core.py 在用户输入密钥后解密加载 |
| `fancy/` | User rule sets (one JSON file per ruleset) | auto-created |
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
| `translation_log_api.py` | `TranslationLogViewerAPI` 只读桥接：翻译诊断日志查看器（选择 dump、分页查询、过滤导出） |
| `index.html` | Single-page HTML shell (~200 lines), section placeholders loaded dynamically from `sections/`; the 游戏资源更新 sidebar item is an ordinary SPA route |
| `rule-editor.html` | Standalone pywebview page for the 美化规则编辑器. Sidebar search input filters filenames/categories while typing and runs full-content search on Enter or the search button. File-edit tab: VSCode-style CodeMirror 6 editor with find/replace (Ctrl+F/H), match highlighting, dirty state indicator, status bar, change tracking, and smart ruleset generation. Ruleset-edit tab: simple form + advanced JSON editors for ruleset CRUD. Theme syncs with main app window (light/dark/purple) |
| `llm-fancy.html` | Standalone pywebview page for the LLM 文本美化 window (opened from the fancy page). Bus-syntax selection rules JSON editor, fancy/ bus-ruleset exclusion checkboxes, custom prompt toggle + textarea, batch size / concurrency inputs, scan preview and run buttons with streamed progress/log and result summary. Theme syncs with main app window |
| `quick-editor.html` | Standalone pywebview page for the 简易翻译编辑器. Simpler than rule-editor: sidebar file browser (categorized, searchable) + CodeMirror 6 JSON editor + bottom change list panel; in-editor find/replace search bar shared with rule-editor via `css/editor-search-panel.css` + `js/editor-search-panel.js`. Changes recorded as `{file, path, old, new}`, saved with derived bus `set` rules to fixed `fancy/_quick_edits.json`, and shown read-only in the main Fancy list |
| `translation-log-viewer.html` | Standalone read-only translation diagnostic viewer. Opens one user-selected current `schema_version: 2` JSONL dump and provides structured filters, pagination, lazy full-record details, copy, refresh, and filtered export |
| `css/base.css` | Base styling with 3 theme definitions (light/dark/purple) and CSS custom properties |
| `css/components.css` | Component-specific styles: cards, buttons, forms, progress bars, modals |
| `css/layout-extras.css` | Layout utilities, modals, drawers, scrollbars, responsive breakpoints, and the two-column responsive layout for the resource updater page. Also loaded by rule-editor.html |
| `css/editor-search-panel.css` | **Shared** CM6 in-editor search panel styles (VSCode floating `.cm-panels`, draggable `.cm-search` card, textfield/button/label/dark-theme). Loaded by both `rule-editor.html` and `quick-editor.html` so both editors share one look |
| `css/rule-editor.css` | Rule editor styles: sidebar+main+bottom panel layout, data cards, smart-gen dialog, tiered scope options, editor status bar, match highlights, toasts, per-theme colors. (Search panel styles now live in the shared `editor-search-panel.css`) |
| `css/quick-editor.css` | Quick editor styles: 3-panel layout (sidebar+main+changes), category groups with collapsible headers, file item active/hover states, toolbar/change-list/resize-handle styling, per-theme color variables. In-editor search panel comes from shared `editor-search-panel.css` |
| `css/llm-fancy.css` | LLM text-beautification window styles: card layout, bus selection JSON editor, exclusion checkbox list, prompt textarea, action buttons, progress bar + log panel, result card; theme-aware via CSS variables |
| `css/translation-log-viewer.css` | Three-column diagnostic viewer layout, filters, record table, collapsible detail cards, responsive detail panel, and theme-aware status styling |
| `js/core.js` | Core framework: API binding, event system, navigation |
| `js/resource-updater.js` | In-app resource updater page controller: refreshes persisted state on navigation, shows the shared game directory (read-only, linked to the main program's `game_path` setting), probes the game directory, starts/cancels work, and renders channel progress/log events from `ResourceUpdaterAPI`. The Launcher auto-download switch (`launcher.resource_update.enabled`) lives only on the Launcher config page and is read here from the config cache (source page shows integration intro + jump button) |
| `js/features.js` | Feature-specific UI logic, drag-drop manager, manual update from local zip, FancyManager (saveAll now persists to `fancy/` folder via `pywebview.api.save_ruleset()`), `openRuleEditor()` global function |
| `js/init.js` | Initialization and bootstrap: uses single `get_startup_data()` call; welcome content deferred via `_pendingWelcomeContent` for lazy section loading compatibility |
| `js/utils.js` | Navigation, encryption, and sidebar search; all ordinary tools, including 游戏资源更新, use lazy SPA sections through `await loadSection()` |
| `js/modals.js` | Modal dialog management, markdown content loader with `_loadedMarkdowns` cache, and toggle functions (all null-guarded for lazy section loading safety) |
| `js/quick-start.js` | Three-step first-use flow: choose one of four goals, check only goal-specific settings, save ordinary config where needed, then jump directly to the target feature page; no wizard progress/config schema |
| `js/api-config.js` | API configuration page logic; container-not-found logs suppressed for lazy loading compatibility |
| `js/cdn.js` | CDN optimization page logic |
| `js/speed.js` | Game speed control page logic; delegates the first-time risk-notice gate to the shared `RiskGate` module |
| `js/risk-gate.js` | **Shared** risk-service gate module (`RISK_SERVICES` registry + global `RiskGate`): normalized disclaimer text (common bullets + per-service line + optional per-service `agreementSections`, single source of truth), consent persistence via `{service}.disclaimer_accepted` config keys, first-entry overlay gating for risk pages (`gatePage`), in-place consent modal for Launcher-config checkboxes (`gateLauncherSection` + `showConsentModal`), a view-only re-read modal (`showNoticeModal`), and `refreshLauncherVisibility()` — services flagged `hideUntilConsent` (currently `cheat`) stay hidden on the Launcher-config page until consent is given on the source page (re-checked on each navigation into the page and after `acceptConsent`). `cheat` additionally carries an `agreementSections` array (作者承诺 / 使用者义务 / 服务可用性说明) rendered after the common disclaimer, plus its own `consentLabel` (resolved via `_consentLabel(service)`, falls back to the shared label for other services). The toolbox's Launcher items are no longer static: `cheat` has no `launcherCheckboxId`; `cheat-shell.js` renders them dynamically into `#cheat-plugin-launcher` from the plugin registry (each rendered group carries `data-risk-service="cheat"` so visibility/consent still apply). Adding a new risk service = one registry entry + `data-risk-overlay` container on the source page + `data-risk-service` attribute on the Launcher-config checkbox |
| `js/input-bypass.js` | Input anti-detection page logic; gated by the shared `RiskGate` risk-notice overlay before the page content unlocks |
| `js/cheat-shell.js` | 作弊工具箱**密钥门壳**（bundle 内置）：进入时先经 `RiskGate.gatePage('cheat')` 风险门（未同意显示覆盖层并隐藏 `#cheat-main-content`，同意后 `_showMainContent` 恢复可见；覆盖层缺失兜底直接显示，避免整页空白），再查询解锁状态（`cheat_core_status`）→ 未解锁 `_showGate` 显示密钥输入门；已解锁/自动解锁后经 `cheat_plugins_list()` 遍历插件，逐个 `cheat_core_get_section_html/script_js` 拉取解密的功能页 HTML/JS，`new Function` 注入并调用解密 JS 导出的 `initCheatPage()`。另提供 `renderLauncherPlugins()` 按插件注册表把 Launcher 集成开关动态渲染进 `#cheat-plugin-launcher`（未同意风险就地弹窗、值直写 config）。对外保持 `cheatPage` 全局名（init/stop）兼容 utils.js 导航生命周期，另暴露 `cheatCoreLockAndReload()` 供「锁定」按钮使用。功能实现 JS 位于私有仓库 |
| `js/list-managers.js` | List/tab view management; constructors tolerate missing containers (lazy load compatible); container refs updated by `onSectionLoaded` |
| `js/editor-search-panel.js` | **Shared** CM6 search panel module (`window.EditorSearchPanel`): `attach(container, bridge)` observes dynamically-added `.cm-search` nodes and applies `localizeSearchPanel` (CN translation) + `attachDrag` (pointer-capture drag, rAF transform, 3px dead-zone) + `setSearchPanelPosition` (boundary clamp). The `bridge` object holds per-page state (`isOpen`/`panelLeft`/`panelTop`/`panelRight`/`onPanelClose`). Used by both rule- and quick-editor |
| `js/rule-editor.js` | Rule editor frontend logic: two main mode tabs (file-edit / ruleset-edit). Sidebar typing performs local filename/category filtering; explicit search performs asynchronous full-content search with request IDs so stale results cannot overwrite newer searches. In-editor CodeMirror find/replace panel (Ctrl+F) is powered by the shared `EditorSearchPanel`; cross-tab search query/position save-restore lives here (`_searchBridge`/`_captureSearchState`/`_restoreSearchState`). File editing, JSON diff tracking, batch replace, ruleset CRUD, templates, validation, and V1/V2/V3 smart generation remain in this module |
| `js/quick-editor.js` | Quick editor frontend logic (~900 lines): file browser with category grouping, CodeMirror 6 JSON editing, `diff_json`-based change tracking (`recordChanges()`), edit list rendering with per-item delete, search across files by keyword with drill-down, batch replace dialog, resize handle drag, theme sync with main window, Ctrl+S to record changes. Shares the in-editor search panel with the rule editor via the shared `EditorSearchPanel` (Ctrl+F opens the localized/draggable panel; Ctrl+Shift+F focuses the sidebar search) |
| `js/llm-fancy.js` | LLM text-beautification window frontend: `get_initial_state()` bootstrap (rulesets, api_config snapshot, persisted config), WebCrypto `decryptText` for `api_crypto` compatibility, bus selection JSON editor + validation + example, exclusion checkbox list, scan preview / run with `__llmFancyDispatch` event streaming (log/progress/scan_done/run_done), cancel, config save, theme sync |
| `js/translation-log-viewer.js` | Translation dump viewer frontend: native file selection, manual reread, structured filters, pagination, lazy detail rendering, clipboard copy, and filtered JSONL export; no directory scan or content search |
| `sections/preload.js` | Lazy section loader: preloads only dashboard at startup, fetches others on first navigation via `loadSection()`; `onSectionLoaded()` initializes the embedded resource updater and other per-section controllers, and binds `RiskGate.gateLauncherSection()` on the Launcher config page (per-navigation visibility refresh for consent-gated options lives in `js/utils.js` `initNavigation`) |
| `sections/*.html` | 20 individual section HTML fragments, including `resource-updater.html` with read-only shared game path (set in 设置 page), update scope, download strategy, progress, actions, logs, and a Launcher integration intro card (switch + detailed settings on launcher-config page). Risk-service sections (`speed.html`, `input-bypass.html`, `cheat.html`) carry a `data-risk-overlay` container filled by `RiskGate`, plus a 查看风险须知 re-read link; `cheat.html` 为**密钥门版本**（密钥输入 + 解锁按钮 + 数据缺失提示），完整功能 UI 在解锁后由解密内容动态替换。`launcher-config.html` risk checkboxes carry `data-risk-service` attributes（作弊工具箱的集成项由 `cheat-shell.js` 动态渲染进 `#cheat-plugin-launcher` 占位容器，未同意前由 `RiskGate.refreshLauncherVisibility()` 整组隐藏）。`launcher-config.html` 已取消独立的汉化包下载配置（零协/OurPlay/LCTA-AU 三卡），仅保留「工作模式配置」「更新集成」「游戏加速」「CDN优选」「启动增强」五张卡片 + 「汉化包下载配置」跳转卡（`goAndShow('download')`）；下载细节与「汉化包下载」页共用 `ui_default.{zero,ourplay,machine}` 一套配置 |
| `guide/*.md` | 19 in-app user guide pages (one per feature tab, including the embedded resource updater) |
| `assets/update.md` | Release changelog (v5.0.1+) |

### webui/app_api/ — LCTA_API 功能域 mixin

| File | Mixin | Methods |
|------|-------|---------|
| `core.py` | `CoreMixin` | 核心管道：`__init__`/`config` 属性/`set_function`/`init_*`/`set_window`/`run_func`/`get_attr`/`set_attr`、日志（`log`/`log_error`/`log_ui`）、进度、模态窗口管理全套（`add_modal_id`/`check_modal_running`/`set_modal_running`/`del_modal_list`/`set_modal_status`/`add_modal_log`/`update_modal_progress`/`_make_cdn_callbacks`）、`browse_file`/`browse_folder`、`check_show`、`get_startup_data`、`save_setting_from`。注意 `check_show` 用 `Path(__file__).resolve().parent.parent` 定位 `webui/assets/update.md` |
| `config.py` | `ConfigMixin` | 配置读写：`update_config_value`/`update_config_batch`/`get_config_value`/`get_config_batch`/`save_settings`/`use_default_config`/`reset_config`/`save_config_to_file` |
| `translation.py` | `TranslatorMixin` | `start_translation`/`format_api_settings`/`test_api`/`fetch_proper_nouns` |
| `packages.py` | `PackagesMixin` | 汉化包安装/删除/切换/字体、Mod 管理、软链接、`move_folders`、`clean_cache`、`get_system_fonts` |
| `download.py` | `DownloadMixin` | OurPlay / 零协 / LCTA 自动 / 调爪 下载 |
| `fancy.py` | `FancyMixin` | `get_fancy_rulesets`/`save_ruleset`/`import_bus_rules`/`fancy_main`/`check_fancy_marker`、规则编辑器窗口 `open_rule_editor`/`sync_theme_to_rule_editor` |
| `windows.py` | `WindowMixin` | 辅助窗口：`open_quick_editor`/`open_llm_fancy`/`open_translation_log_viewer` + 其余 `sync_theme_to_*`、Nexus 测试窗口 `startTest`/`eval_skip`/`sign_eval_js` |
| `cdn.py` | `CdnMixin` | `cdn_*` 全部（Cloudflare/CloudFront 优选、hosts 写入/移除） |
| `speed.py` | `SpeedMixin` | `speed_*` 全部（DLL 注入/弹出/倍率） |
| `update.py` | `UpdateMixin` | `auto_check_update`/`manual_check_update`/`perform_update_in_modal`/`perform_update_from_file` |
| `input_bypass.py` | `InputBypassMixin` | `input_bypass_*` 全部（get_status/apply/inject/eject，转发到 `webutils.function_input_bypass.InputBypassManager`） |
| `cheat_core.py` | `CheatCoreMixin` | `cheat_core_*` 全部（status/unlock/lock/get_section_html/get_script_js）+ 插件通用分发 `cheat_plugins_list`/`cheat_plugin_invoke(action,args)`，转发到 `webutils.cheat_core` / `webutils.cheat_plugins`（密钥门前端入口；具体工具 API 不再有硬编码 mixin） |
| `drops.py` | `DropMixin` | `handle_dropped_files`/`on_drop`/`eval_dropped_files` |
| `resources.py` | `ResourceMixin` | `resource_updater_*` 转发到 `self.resource_updater_api` |
| `exceptions.py` | — | `CancelRunning`（各 mixin 共用，`webui/app.py` re-export） |
| `assets/LCTA-AU.md` | Auto-update system documentation |
| `assets/firstUse.md` | Short first-use welcome with direct entry to the three-step quick-start flow |

## webutils/ — Business Logic Layer

Public API aggregated in `__init__.py`. Each `function_*.py` handles one feature domain.

| File | Feature | Key Points |
|------|---------|------------|
| `__init__.py` | Public API surface | Re-exports all feature functions consumed by `webui/app.py` |
| `clr_bootstrap.py` | pythonnet/clr_loader 引导 | `ensure_clr()` 强制 netfx 并导入 clr:预检 `Python.Runtime.dll` 存在性、clr_loader 版本(<0.2.8 警告)、.NET Framework >=4.7.2;失败时用 PowerShell 反射探针暴露 clr_loader 吞掉的真实异常并给出修复指引,不再自动回退 coreclr/mono。被 `start_webui.py`、`launcher/gui_progress.py`、`launcher/speed_hotkey.py`、`scripts/test_environment.py` 共用 |
| `utils/` | Shared utility package | `io.py` zip/unzip, hashing, 7z integration; `net.py` downloads; `shell.py` Windows Shell API; `font.py` font caching; `misc.py` steam command/icon; facade re-exported via `utils/__init__.py` |
| `load.py` | Config & game detection | Config loading/validation, Steam registry game path detection |
| `update.py` | Self-updater | GitHub Releases-based auto-update |
| `translator_constants.py` | API provider configs | TranslateKit provider definitions (Baidu, Google, DeepL, etc.) |
| `function_llc.py` | LLC/零协会 install | Download & install Zero Association translation packs |
| `function_ourplay_pc.py` | OurPlay PC install | Download OurPlay PC translation packs |
| `function_ourplay_android.py` | OurPlay Android install | Download OurPlay Android-origin translation packs |
| `function_LCTA_auto.py` | Auto-translate download | Download from LCTA_auto_update repo |
| `function_lanzou_tiaozhua.py` | 调爪 text package | One-click 调爪 text modification package download via qaiu API (getFileList + parser) and import as bus rulesets |
| `packages/install.py` | Local package install | Install/delete/font-change for local translation packages |
| `packages/manage.py` | Package management | Installed packages, mod management, symlink operations |
| `packages/clean.py` | Cache cleaner | Clean game cache files |
| `function_fetch.py` | Proper noun scrape | Fetch proper nouns from remote sources |
| `function_fancy.py` | Text effects orchestration | Selects enabled v2/bus rulesets, preserves ruleset order across both engines, prepares skill-color resources only when required, scans UTF-8-SIG language JSON, atomically rewrites final changes, writes a `.lcta_fancy_applied` marker into the beautified language-pack directory (with `has_fancy_marker` for second-run UI confirmation), and returns `FancyRunStats`. Also owns validated `fancy/` load/save/delete and shared bus/调爪/LCJE/FL import helpers |
| `fancy/` | Rule engine family | `engine.py` (compiled v2 beautification engine: validates/compiles file globs, structured JSON paths, AND conditions and typed actions, filters rules per file, returns exact changed paths via `ApplyResult`; `faust`/`skillColorHandler` imports hoisted out of the per-value loop with lazy caching), `bus.py` (bus replacement engine + converters: `format: lcta-bus`/`version: 1`, compile-time exact/dynamic file indexes with deduplicated shared glob/regex matchers, precomputed case-insensitive dir exclusions, optional prematched-rules argument on `apply_bus` to avoid double file matching, cached selector indexes by list path/field with mutation invalidation, regex-accelerated safe replacements, wildcard/index/selector paths, ordered literal/regex/end/safe/set operations, 调爪/LCJE/FL补丁 & quick-edit conversion; LCJE accepts both path-map patches and the reference editor's `{mods:[{file,path,old,new}]}` format), `builtin_data.py` (built-in rule data: `fancy`, `TEXT_REPLACEMENTS`, `EGO_WARNING_ACTIONS`, `EGO_NORMAL_ACTIONS`, `SKILL_COLOR_ACTIONS`), `builtin_func.py` (`SkillColorHandler` lazily extracts skill attributes from Unity resources, fingerprints top-level account folder names, caches color mappings in `tmp/fancy/skill-colors.json`, records cache hits, suppresses retries after init failure), `faust.py` (Faust character-specific fancy text rules; gradient processing rewritten as a single pass with a module-level hex lookup table and inlined interpolation, output identical to the previous per-character implementation). Facade re-exports all public symbols |
| `llm_fancy/` | LLM text-beautification window backend, fully decoupled from `translateFunc/` (imports only `translatekit`, `webutils/fancy/bus.py`, `webutils/function_fancy.py`, `globalManagers/`). `config.py` (`LLMFancyConfig` + ConfigManager persistence under `ui_default.llm_fancy`, incl. `dedup_enabled`), `scanner.py` (bus-syntax selection rules: file matchers + `parse_bus_path` tokens, independent path-resolution walker, `Candidate` collection with `set`-ready `bus_path` serialization, skips empty/`-` placeholders, `dedup_candidates` exact-text dedup returning representative candidates + groups), `exclude.py` (user-selected fancy/ bus rulesets simulated via `apply_bus` on a data copy; changed paths excluded from LLM candidates), `splitter.py` (greedy batch splitting by estimated size, default 20000 chars), `llm.py` (`LLMGeneralTranslator` wrapper mirroring `format_api_settings` normalization, default parse-guarantee system prompt + optional user custom prompt, code-fence-stripping JSON array response parser with per-item `None` fallback), `builder.py` (results → validated `lcta-bus` ruleset with exact-file `set` rules, saved via `save_ruleset_to_folder` and auto-enabled in `fancy_allow`), `runner.py` (scan → exclusion → optional dedup → split → `ThreadPoolExecutor` LLM batches → expanded per-path results → ruleset; `scan_preview`/`run_beautify` with log/progress callbacks and cancel event; `resolve_lang_dir` reads `Lang/config.json`). Facade re-exports all public API |
| `function_translate.py` | Translation orchestration | Connects webui to translateFunc pipeline |
| `function_translation_logs.py` | Translation diagnostics viewer backend | Reads only the user-selected `.jsonl` within its selected parent directory; v2-only indexing, cached summaries/byte offsets, filtering, pagination, lazy record reads, and filtered JSONL export |
| `drop/` | Drag-and-drop | Former `function_drop.py` split into a package: `handler.py` (`DropFileHandler` 接口 ABC + `DropFileHandlerRegistry` 注册表 + `remove_existing`/进度辅助), `context.py` (`FileExecutionContext`), `inspect.py` (zip/folder/json 只读快照，供各处理器复用), `handlers/` (每个 NAMEREFER 类别一个处理器类：`translation.py` full/nofont 汉化包、`archive_mod.py` FLmod/jsononly 压缩模组包、`copy_mod.py` carra/bank/textFile/LCTAchange/FLchange 单文件复制、`bus_import.py`、`update.py`、`invalid.py`；`__init__.py` 按容器类型分组的有序检测注册表), `detect.py` (`evalZip`/`evalFolder`/`eval7zip`/`evalJson`/`evalFile` 门面), `message.py` (`makeMessage`，显示名来自注册表), `eval_files.py` (`evalFiles` 主流程，按类型查注册表执行); zip/7z extraction, mod installation, update package handling via Updater, plus bus/调爪/LCJE/FL JSON recognition and shared import into `fancy/` |
| `cdn/` | CDN optimization | Former `function_cdn.py` split into a package: `constants.py` (常量定义，对应 LLC_BABEL CdnTarget.cs), `classify.py` (CloudFront 探测失败分类), `cfst.py` (CloudflareSpeedTest 子进程 + CSV 解析), `cloudfront.py` (CloudFront DNS 候选发现与 HTTPS 端点探测), `selector.py` (CloudFront 两阶段 IP 选择), `hosts.py` (hosts 文件管理：编码/BOM 保留、受管标记块写入、原子替换前清除只读属性、`raise_on_permission_error` 权限错误重抛供提权判断、`elevated` 失败文案区分；权限/占用类替换失败按 `REPLACE_MAX_ATTEMPTS` 次短间隔重试，全部失败后经 Restart Manager API 分析占用进程 PID 与路径并附加到错误文案), `elevate.py` (管理员提权写入/移除 hosts 与提权子进程入口；策略：非管理员先真实尝试直写，仅权限类失败才触发 UAC 提权重试——无"新建文件"探针，避免假阳性短路提权路径), `optimize.py` (完整优选流程编排，含缓存 TTL 避免重复测速); facade re-exports all public API |
| `function_speed.py` | Game speed | Game speed acceleration via openspeedy DLL injection; `is_injected()` checks self-tracked injection state |
| `function_input_bypass.py` | 输入反检测 (CommonLib import anti-detection) | Injects `hooks/rawinput_hook.dll` into `LimbusCompany.exe` and controls synthesized/real input counts via a named shared-memory map (`Local\LCTA_RawInputHook_Config`, 80-byte `RHConfig` matching the C struct). `auto` mode zeroes synthesized counts/ratios; `manual` mode overrides the 4 counts (real/synth × mouse/key) from `launcher.work.input_bypass_*` config, auto-calculates the synth ratio as `synth/(real+synth)` (clamped `< 0.9`), and supports a `volatility` percentage (0-50) that makes the C hook jitter counts within a time window so reported values aren't constant. Manager API: `apply()` (write config), `inject(pid)`/`eject()`, `get_status()`, `close()`; pure helpers `parse_count`/`parse_percent`/`parse_ratio`/`auto_ratio`/`build_config` clamp values (ratios to `[0, 0.9)` to avoid the game's reset-window logic). Explicit `restype`/`argtypes` declarations for kernel32 calls so 64-bit handles/pointers are not truncated |
| `function_steam_launcher.py` | Steam 启动器设置 | 通过 vdf 库一键把《Limbus Company》(appid 1973530) 的 LaunchOptions 写入 `userdata/<账号>/config/localconfig.vdf`（键名用 Steam 实际的小写 `apps`）。路径自动生成：`get_steam_path()` 读注册表 `HKCU\SOFTWARE\Valve\Steam\SteamPath` 并归一化分隔符；`resolve_localconfig_path()` 主用 `config/loginusers.vdf` 的 `MostRecent==1` 账号，缺失时回退扫描 `userdata\*`（含 appid 条目优先、账号 ID 降序）。`is_lcta_launch_options()` 以 `' -launcher %command%'` 判定是否 LCTA 型启动项；`get_current_launch_command()` 生成当前 LCTA 命令（异常返回 None）；`get_steam_launcher_status()` 返回 `state`（missing/unconfigured/lcta_current/lcta_stale/lcta/other，`lcta_current`=与当前命令精确相等、`lcta_stale`=旧版 LCTA 命令、`lcta`=当前命令不可比较）+ `is_current_lcta`（True/False/None）+ steam.exe 运行态供前端展示（前端只显示状态文本，不展示原始路径与值）；`set_steam_launch_options()` / `clear_steam_launch_options()` 先备份 `localconfig.vdf.lcta.bak`，`vdf.load` 后写入/移除 LaunchOptions（保留该游戏其他字段），按原 BOM 状态 `vdf.dump` 写回。写入内容来自 `webutils/utils/misc.py get_steam_command()`。入口：Launcher配置页 steam命令旁「写入Steam启动选项」/「清除启动项」按钮 |
| `cheat_plugins.py` | 作弊工具箱**插件宿主**（公共仓库） | 解锁后读私有仓库 `cheatcore/registry.py` 的插件描述符自动注册：`reload()`（读 `get_plugins()` + 播种配置默认值到 ConfigManager）、`list()`（插件摘要）、`invoke(action,args)`（按注册表 api 白名单分发到插件管理器类）、`run_launcher_phase(phase)`（查 enabled_key + consent 后调 on_start/on_stop）、`close_all()`（atexit 兜底）。未解锁时 `_plugins` 为空，安全短路。替代旧 `DamageHookManager` 门面——主仓库不感知具体工具 |
| `cheat_core.py` | CheatCore 解密加载器 | 密钥门核心：`blob_path()`（`<path_>/cheat_core/cheat_core.bin` + 仓库相对路径兜底）、`dev_src_dir()`（`LCTA_CHEAT_DEV_SRC` 环境变量 > 仓库根 `LCTA_CheatingCore/` 克隆，开发模式免密钥直连）、`runtime_dir()`（`%LOCALAPPDATA%/LCTA/cheat-core`）、`unlock(key)`（校验解密 → 逐文件 SHA-256 校验 → 释放文件 → sys.path 动态导入 `cheatcore` 包 → `_reload_plugins()` 触发插件注册）、`ensure_unlocked()`（dev > 已解锁 > 持久化密钥自动解锁 > blob_missing/need_key）、`lock()`（清配置密钥/内存态/插件注册/sys.path/运行时目录）、`get_package()`/`section_html()`/`script_js()`（未解锁抛 RuntimeError）。格式说明见私有仓库 README。密钥持久化于 `cheat_core.unlock_key`。功能实现（偏移 API 缓存锚定、共享内存 DHConfig、伤害日志环形缓冲）在私有仓库 `cheatcore/cheat_damage_hook.py` |
| `function_resource.py` | Unity resource reader | Locates Limbus resource files and extracts text assets in batches through UnityPy; sets fallback Unity version `6000.3.12f1` for resources without usable version metadata; skips objects whose container is missing/None (UnityPy returns `None` for objects outside the container map) instead of crashing |
| `rule_editor/` | Rule editor backend | `browser.py` (file browser: `_get_lang_dir`, `get_lang_files`, `get_category`, `get_file_content`, `search_files` — raw text occurrence counts with `utf-8-sig`, so BOM and temporarily invalid JSON files remain searchable — and JSON-validated `save_file_content` with backup), `rules.py` (ruleset CRUD: `get_ruleset_list`, `get_ruleset`, `save_ruleset`, `create_ruleset`, `delete_ruleset`, `apply_ruleset_to_content` + form helpers `build_rule_from_form`, `validate_rule`), `generate.py` (V1/V2/V3 smart analysis, change clustering, 5-dimension scoring, merge-candidate detection), `quick.py` (quick editor backend: deep JSON diffs `{file, path, old, new}`, persistence of edits plus derived bus `set` rules to `fancy/_quick_edits.json`, legacy migration, per-edit path failures and atomic writes), `constants.py` (single-source-of-truth `FILE_PREFIX_RULES`, `CATEGORY_FILE_PATTERNS`, `COMMON_REPLACEMENTS`, `TEMPLATES`; JS fetches via `get_editor_constants()` API with hardcoded fallback). Facade re-exports all public API |
| `scripts/test_environment.py` | Debug utilities | Internal testing/debug helpers (moved out of webutils) |
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
| `processor.py` | `FileProcessor` — per-file translation logic; Stage 2 self-check on the combined translation result |
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
| `ConfigManager.py` | Singleton config: dotted-path access (`ui_default.translator.enable_proper`), JSON validation via `config_check.json`, auto-save on mutation, thread-safe |
| `LogManager.py` | Singleton logger: file rotation, console output, webview modal callbacks via thread pool for async UI updates; also configures `fancy`/`rule_editor` child loggers with the same handlers so their INFO/DEBUG output lands in `app.log` |

## launcher/ — Standalone Launcher (GPL-3.0)

| File | Purpose |
|------|---------|
| `main.py` | Entry point: pipeline orchestration — creates `LaunchPipeline`, registers handlers for resource-update/mod/speed-hotkey, optionally creates the WinForms launch center, then emits pipeline phases in order. Connects LogManager modal status/progress, resource download progress, CDN percentages, stepped mod preparation, and launch-process milestones to the GUI. Uses `subprocess.Popen` (not `subprocess.call`) for game launch to support cancel-flow from GUI |
| `game_launch.py` | Game launch phases: `prepare_mod()` (mod patching pre-game), `cleanup_mod_assets()` (post-game restore), `start_speed_hotkey()` / `stop_speed_hotkey()` (lifecycle wrappers), `start_input_bypass()` / `start_cheat_plugins()` / `stop_cheat_plugins()`（`start_cheat_plugins` 先 `cheat_core.ensure_unlocked()`，通过后 `CheatPluginHost.run_launcher_phase('start')` 通用分发到插件 on_start，注入逻辑在私有仓库 `start_launcher()`）。Game process launch moved to `main.py` pipeline |
| `updates.py` | Translation pack update system (Factory pattern for LLC/OurPlay/Machine). 汉化包下载参数改读 `ConfigManager().get('ui_default')` 的 `zero`/`machine`/`ourplay` 段（与「汉化包下载」页共用一套配置，不再读 `launcher.{zero,machine,ourplay}`；`launcher.work.*` 更新模式/集成开关仍读 `launcher` 段）。Optional post-update beautification passes all built-in/user rules plus the enable map to `fancy_main()`, allowing disabled skill-color rules to avoid resource preparation |
| `cdn.py` | CDN optimization for launcher mode with cache TTL to avoid redundant speed tests |
| `patch.py` | Unity asset patching for mods |
| `modfolder.py` | Mod folder management and detection |
| `sound.py` | Sound file replacement for mods |
| `changes.py` | Text data patch application |
| `compress.py` | Compression utilities |
| `speed_hotkey.py` | Game speed hotkey (Ctrl+Shift+S) with comprehensive lifecycle logging, foreground process check, .NET STA threading for UI |
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
