# LCTA Module Map

<!-- Last updated: 2026-08-06 -->

## Directory Overview

| Directory | Role | Key Files |
|-----------|------|-----------|
| `webui/` | Frontend application (pywebview + HTML/CSS/JS) | 15 + sections |
| `webutils/` | Business logic layer (feature modules + beautification engines) | 62 Python files |
| `webFunc/` | Infrastructure (network, downloads) | 4 |
| `translateFunc/` | Translation engine (LLM pipeline) | 13+ |
| `globalManagers/` | Cross-cutting singletons | 2 |
| `launcher/` | Standalone game launcher (GPL-3.0) | 11 |
| `resource_updater/` | Official localize/Bundle updater and Launcher fingerprint gate | 4 |
| `CFST/` | CloudflareSpeedTest binary + IP lists | 3 |
| `fancy/` | User rule sets (one JSON file per ruleset) | auto-created |
| `tests/` | Pytest test suite | 23 Python files |
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
| `app.py` | **Core** pywebview bridge. Includes the main `LCTA_API`, owns the shared `ResourceUpdaterAPI` used by the in-app resource page, plus `RuleEditorAPI`, `QuickEditorAPI`, and read-only `TranslationLogViewerAPI`; exposes bus-rule multi-file import, spawns editor/viewer windows, and synchronizes light/dark/purple themes |
| `index.html` | Single-page HTML shell (~200 lines), section placeholders loaded dynamically from `sections/`; the 游戏资源更新 sidebar item is an ordinary SPA route |
| `rule-editor.html` | Standalone pywebview page for the 美化规则编辑器. Sidebar search input filters filenames/categories while typing and runs full-content search on Enter or the search button. File-edit tab: VSCode-style CodeMirror 6 editor with find/replace (Ctrl+F/H), match highlighting, dirty state indicator, status bar, change tracking, and smart ruleset generation. Ruleset-edit tab: simple form + advanced JSON editors for ruleset CRUD. Theme syncs with main app window (light/dark/purple) |
| `quick-editor.html` | Standalone pywebview page for the 简易翻译编辑器. Simpler than rule-editor: sidebar file browser (categorized, searchable) + CodeMirror 6 JSON editor + bottom change list panel. Changes recorded as `{file, path, old, new}`, saved with derived bus `set` rules to fixed `fancy/_quick_edits.json`, and shown read-only in the main Fancy list |
| `translation-log-viewer.html` | Standalone read-only translation diagnostic viewer. Opens one user-selected current `schema_version: 2` JSONL dump and provides structured filters, pagination, lazy full-record details, copy, refresh, and filtered export |
| `css/base.css` | Base styling with 3 theme definitions (light/dark/purple) and CSS custom properties |
| `css/components.css` | Component-specific styles: cards, buttons, forms, progress bars, modals |
| `css/layout-extras.css` | Layout utilities, modals, drawers, scrollbars, responsive breakpoints, and the two-column responsive layout for the resource updater page. Also loaded by rule-editor.html |
| `css/rule-editor.css` | Rule editor styles: sidebar+main+bottom panel layout, VSCode-style find bar, bounded pointer-drag search panel with touch handling, data cards, smart-gen dialog (V1/V2/V3 with merge connectors), tiered scope options, editor status bar, match highlights, toasts, per-theme colors |
| `css/quick-editor.css` | Quick editor styles: 3-panel flex layout (sidebar+main+changes), category groups with collapsible headers, file item active/hover states, toolbar buttons, change list cards with old→new diff display, resize handles, batch replace dialog, per-theme color variables |
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
| `js/speed.js` | Game speed control page logic |
| `js/list-managers.js` | List/tab view management; constructors tolerate missing containers (lazy load compatible); container refs updated by `onSectionLoaded` |
| `js/rule-editor.js` | Rule editor frontend logic: two main mode tabs (file-edit / ruleset-edit). Sidebar typing performs local filename/category filtering; explicit search performs asynchronous full-content search with request IDs so stale results cannot overwrite newer searches. CodeMirror find panels use pointer capture, animation-frame transforms, boundary clamping, and cross-tab position restoration. File editing, JSON diff tracking, batch replace, ruleset CRUD, templates, validation, and V1/V2/V3 smart generation remain in this module |
| `js/quick-editor.js` | Quick editor frontend logic (~800 lines): file browser with category grouping, CodeMirror 6 JSON editing, `diff_json`-based change tracking (`recordChanges()`), edit list rendering with per-item delete, search across files by keyword with drill-down, batch replace dialog, resize handle drag, theme sync with main window, Ctrl+S to record changes |
| `js/translation-log-viewer.js` | Translation dump viewer frontend: native file selection, manual reread, structured filters, pagination, lazy detail rendering, clipboard copy, and filtered JSONL export; no directory scan or content search |
| `sections/preload.js` | Lazy section loader: preloads only dashboard at startup, fetches others on first navigation via `loadSection()`; `onSectionLoaded()` initializes the embedded resource updater and other per-section controllers |
| `sections/*.html` | 19 individual section HTML fragments, including `resource-updater.html` with read-only shared game path (set in 设置 page), update scope, download strategy, progress, actions, logs, and a Launcher integration intro card (switch + detailed settings on launcher-config page) |
| `guide/*.md` | 19 in-app user guide pages (one per feature tab, including the embedded resource updater) |
| `assets/update.md` | Release changelog (v5.0.0+) |
| `assets/LCTA-AU.md` | Auto-update system documentation |
| `assets/firstUse.md` | Short first-use welcome with direct entry to the three-step quick-start flow |

## webutils/ — Business Logic Layer

Public API aggregated in `__init__.py`. Each `function_*.py` handles one feature domain.

| File | Feature | Key Points |
|------|---------|------------|
| `__init__.py` | Public API surface | Re-exports all feature functions consumed by `webui/app.py` |
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
| `function_translate.py` | Translation orchestration | Connects webui to translateFunc pipeline |
| `function_translation_logs.py` | Translation diagnostics viewer backend | Reads only the user-selected `.jsonl` within its selected parent directory; v2-only indexing, cached summaries/byte offsets, filtering, pagination, lazy record reads, and filtered JSONL export |
| `drop/` | Drag-and-drop | Former `function_drop.py` split into a package: `handler.py` (`DropFileHandler` 接口 ABC + `DropFileHandlerRegistry` 注册表 + `remove_existing`/进度辅助), `context.py` (`FileExecutionContext`), `inspect.py` (zip/folder/json 只读快照，供各处理器复用), `handlers/` (每个 NAMEREFER 类别一个处理器类：`translation.py` full/nofont 汉化包、`archive_mod.py` FLmod/jsononly 压缩模组包、`copy_mod.py` carra/bank/textFile/LCTAchange/FLchange 单文件复制、`bus_import.py`、`update.py`、`invalid.py`；`__init__.py` 按容器类型分组的有序检测注册表), `detect.py` (`evalZip`/`evalFolder`/`eval7zip`/`evalJson`/`evalFile` 门面), `message.py` (`makeMessage`，显示名来自注册表), `eval_files.py` (`evalFiles` 主流程，按类型查注册表执行); zip/7z extraction, mod installation, update package handling via Updater, plus bus/调爪/LCJE/FL JSON recognition and shared import into `fancy/` |
| `cdn/` | CDN optimization | Former `function_cdn.py` split into a package: `constants.py` (常量定义，对应 LLC_BABEL CdnTarget.cs), `classify.py` (CloudFront 探测失败分类), `cfst.py` (CloudflareSpeedTest 子进程 + CSV 解析), `cloudfront.py` (CloudFront DNS 候选发现与 HTTPS 端点探测), `selector.py` (CloudFront 两阶段 IP 选择), `hosts.py` (hosts 文件管理), `elevate.py` (管理员提权写入/移除 hosts 与提权子进程入口), `optimize.py` (完整优选流程编排，含缓存 TTL 避免重复测速); facade re-exports all public API |
| `function_speed.py` | Game speed | Game speed acceleration via openspeedy DLL injection; `is_injected()` checks self-tracked injection state |
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
| `main.py` | Entry point: pipeline orchestration — creates `LaunchPipeline`, registers handlers for resource-update/mod/speed-hotkey, optionally creates GUI window, then emits pipeline phases in order. Uses `subprocess.Popen` (not `subprocess.call`) for game launch to support cancel-flow from GUI |
| `game_launch.py` | Game launch phases: `prepare_mod()` (mod patching pre-game), `cleanup_mod_assets()` (post-game restore), `start_speed_hotkey()` / `stop_speed_hotkey()` (lifecycle wrappers). Game process launch moved to `main.py` pipeline |
| `updates.py` | Translation pack update system (Factory pattern for LLC/OurPlay/Machine). Optional post-update beautification passes all built-in/user rules plus the enable map to `fancy_main()`, allowing disabled skill-color rules to avoid resource preparation |
| `cdn.py` | CDN optimization for launcher mode with cache TTL to avoid redundant speed tests |
| `patch.py` | Unity asset patching for mods |
| `modfolder.py` | Mod folder management and detection |
| `sound.py` | Sound file replacement for mods |
| `changes.py` | Text data patch application |
| `compress.py` | Compression utilities |
| `speed_hotkey.py` | Game speed hotkey (Ctrl+Shift+S) with comprehensive lifecycle logging, foreground process check, .NET STA threading for UI |
| `gui_progress.py` | WinForms companion window for GUI launcher mode: phase indicator (init→update→resource_update→cdn→mod→launch→running), status label, progress bar, collapsible log area, game-running info display (PID + uptime + hotkey hints). `register_to_pipeline()` wires GUI to `LaunchPipeline` phases; `FormClosing` handler shows confirmation dialog and sets `cancel_event` on confirm |
| `pipeline.py` | `LaunchPipeline` — phase-based event-driven pipeline: `on(phase, callback)` for module registration, `emit(phase, **kwargs)` to trigger all callbacks. Defines 8 phases (`PHASE_INIT` through `PHASE_EXIT`, including `PHASE_RESOURCE_UPDATE` between check_update and cdn). `cancel_event` (threading.Event) supports GUI-initiated abort. `context` dict shares state (steam_argv, game_process, game_pid) across phases |

## resource_updater/ — Official Game Resource Updater

| File | Purpose |
|------|---------|
| `core.py` | Core updater: validates game files, extracts S/L CDN tokens and the real remote catalog URL, uses the game-compatible Unity request headers, hashes `LimbusCompany.exe`, parses Bundle names/cache keys, downloads token-scoped localize ZIPs, safely deploys localize files, populates Unity cache entries, removes failed Bundle entry directories, logs through `LogManager`, and manages bundled aria2c JSON-RPC with urllib fallback. Download failures are reported at WARNING level with file name + error code and collected into `failed_items` in the run result; aria2 polling progress logs are throttled to count changes (progress callbacks still fire each poll) |
| `service.py` | Shared configuration/state service. Stores Launcher state under `%LOCALAPPDATA%/LCTA/resource-updater/launcher-state.json`, compares the local `LimbusCompany.exe` SHA-256 fingerprint, checks whether prior partial runs cover current configured scopes, and records successful manual/Launcher work |
| `web_api.py` | Main-window resource updater controller. `LCTA_API` delegates prefixed bridge methods to it; it probes the shared game directory (read from main config `game_path`), persists updater options, runs/cancels the worker, records success state, and logs lifecycle/errors through `LogManager` |
| `__init__.py` | Public resource updater exports used by Launcher and tests |

## Import Dependency Graph

```
webui/app.py
  → webutils/ (all feature functions via __init__.py)
    → translateFunc/ (translation pipeline)
    → webFunc/ (GitHub downloads, file transfer)
  → globalManagers/ (ConfigManager, LogManager)
  → webutils/rule_editor/ (RuleEditorAPI: file browser, rules CRUD; QuickEditorAPI)
  → webutils/function_fancy.py (load_fancy_folder_rules, fancy_main)

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
  → resource_updater/core.py (manual update worker)
  → resource_updater/service.py (config and successful-scope state)
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
