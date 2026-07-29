# LCTA Module Map

<!-- Last updated: 2026-07-29 -->

## Directory Overview

| Directory | Role | Key Files |
|-----------|------|-----------|
| `webui/` | Frontend application (pywebview + HTML/CSS/JS) | 15 + sections |
| `webutils/` | Business logic layer (feature modules + beautification engine) | 32 Python files |
| `webFunc/` | Infrastructure (network, downloads) | 4 |
| `translateFunc/` | Thin Rust engine/config bridge | 5 Python files |
| `native/lcta_translation_engine/` | PyO3 native translation engine | Rust crate |
| `globalManagers/` | Cross-cutting singletons | 2 |
| `launcher/` | Standalone game launcher (GPL-3.0) | 11 |
| `CFST/` | CloudflareSpeedTest binary + IP lists | 3 |
| `fancy/` | User rule sets (one JSON file per ruleset) | auto-created |
| `tests/` | Pytest test suite | 7 Python files |
| `.githooks/` | Repository-local Git hooks | `pre-commit` |
| `.github/workflows/` | CI/CD and repository consistency checks | `release.yml`, `check.yml`, `check-sync.yml` |

## Repository Guidance & Automation

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Source project instructions and AI-first knowledge-base index |
| `AGENTS.md` | Cross-tool copy of `CLAUDE.md`; kept byte-for-byte synchronized for other coding agents |
| `.githooks/pre-commit` | Optional local hook (`git config core.hooksPath .githooks`) that copies `CLAUDE.md` to `AGENTS.md` and stages the synchronized file before commit |
| `.github/workflows/check-sync.yml` | Pull-request/manual CI guard that fails when `CLAUDE.md` and `AGENTS.md` differ |

## webui/ — Frontend Application

| File | Purpose |
|------|---------|
| `app.py` | **Core** pywebview bridge. Includes the main `LCTA_API` plus `RuleEditorAPI`, `QuickEditorAPI`, and read-only `TranslationLogViewerAPI`; spawns secondary windows and synchronizes light/dark/purple themes |
| `index.html` | Single-page HTML shell (~200 lines), section placeholders loaded dynamically from `sections/` |
| `rule-editor.html` | Standalone pywebview page for the 美化规则编辑器. Sidebar search input filters filenames/categories while typing and runs full-content search on Enter or the search button. File-edit tab: VSCode-style CodeMirror 6 editor with find/replace (Ctrl+F/H), match highlighting, dirty state indicator, status bar, change tracking, and smart ruleset generation. Ruleset-edit tab: simple form + advanced JSON editors for ruleset CRUD. Theme syncs with main app window (light/dark/purple) |
| `quick-editor.html` | Standalone pywebview page for the 简易翻译编辑器. Simpler than rule-editor: sidebar file browser (categorized, searchable) + CodeMirror 6 JSON editor + bottom change list panel. Changes recorded as `{file, path, old, new}` path-patch format, saved to fixed `fancy/_quick_edits.json`. No ruleset management or regex patterns — designed for lightweight users who just want to edit translations directly |
| `translation-log-viewer.html` | Standalone read-only translation diagnostic viewer. Opens one user-selected current `schema_version: 2` JSONL dump and provides structured filters, pagination, lazy full-record details, copy, refresh, and filtered export |
| `css/base.css` | Base styling with 3 theme definitions (light/dark/purple) and CSS custom properties |
| `css/components.css` | Component-specific styles: cards, buttons, forms, progress bars, modals |
| `css/layout-extras.css` | Layout utilities, modals, drawers, scrollbars, responsive breakpoints. Now also loaded by rule-editor.html |
| `css/rule-editor.css` | Rule editor styles: sidebar+main+bottom panel layout, VSCode-style find bar, bounded pointer-drag search panel with touch handling, data cards, smart-gen dialog (V1/V2/V3 with merge connectors), tiered scope options, editor status bar, match highlights, toasts, per-theme colors |
| `css/quick-editor.css` | Quick editor styles: 3-panel flex layout (sidebar+main+changes), category groups with collapsible headers, file item active/hover states, toolbar buttons, change list cards with old→new diff display, resize handles, batch replace dialog, per-theme color variables |
| `css/translation-log-viewer.css` | Three-column diagnostic viewer layout, filters, record table, collapsible detail cards, responsive detail panel, and theme-aware status styling |
| `js/core.js` | Core framework: API binding, event system, navigation |
| `js/features.js` | Feature-specific UI logic, drag-drop manager, manual update from local zip, FancyManager (saveAll now persists to `fancy/` folder via `pywebview.api.save_ruleset()`), `openRuleEditor()` global function |
| `js/init.js` | Initialization and bootstrap: uses single `get_startup_data()` call; welcome content deferred via `_pendingWelcomeContent` for lazy section loading compatibility |
| `js/utils.js` | Navigation, encryption, sidebar search; `initNavigation` async handler with `await loadSection()`, `goAndShow` async for lazy section loading |
| `js/modals.js` | Modal dialog management, markdown content loader with `_loadedMarkdowns` cache, toggle functions (all null-guarded for lazy section loading safety) |
| `js/api-config.js` | API configuration page logic; container-not-found logs suppressed for lazy loading compatibility |
| `js/cdn.js` | CDN optimization page logic |
| `js/speed.js` | Game speed control page logic |
| `js/list-managers.js` | List/tab view management; constructors tolerate missing containers (lazy load compatible); container refs updated by `onSectionLoaded` |
| `js/rule-editor.js` | Rule editor frontend logic: two main mode tabs (file-edit / ruleset-edit). Sidebar typing performs local filename/category filtering; explicit search performs asynchronous full-content search with request IDs so stale results cannot overwrite newer searches. CodeMirror find panels use pointer capture, animation-frame transforms, boundary clamping, and cross-tab position restoration. File editing, JSON diff tracking, batch replace, ruleset CRUD, templates, validation, and V1/V2/V3 smart generation remain in this module |
| `js/quick-editor.js` | Quick editor frontend logic (~800 lines): file browser with category grouping, CodeMirror 6 JSON editing, `diff_json`-based change tracking (`recordChanges()`), edit list rendering with per-item delete, search across files by keyword with drill-down, batch replace dialog, resize handle drag, theme sync with main window, Ctrl+S to record changes |
| `js/translation-log-viewer.js` | Translation dump viewer frontend: native file selection, manual reread, structured filters, pagination, lazy detail rendering, clipboard copy, and filtered JSONL export; no directory scan or content search |
| `sections/preload.js` | Lazy section loader: preloads only dashboard at startup, fetches others on first navigation via `loadSection()`; `onSectionLoaded()` callback re-runs per-section init (toggle funcs, list manager refs, select box values, DOM ref rebuilds) |
| `sections/*.html` | 18 individual section HTML fragments (dashboard, translate, install, etc.) |
| `guide/*.md` | 16 in-app user guide pages (one per feature tab) |
| `elder/*.md` | 14 setup wizard pages |
| `assets/update.md` | Release changelog (v5.0.0+) |
| `assets/LCTA-AU.md` | Auto-update system documentation |
| `assets/firstUse.md` | First-time user welcome guide |

## webutils/ — Business Logic Layer

Public API aggregated in `__init__.py`. Each `function_*.py` handles one feature domain.

| File | Feature | Key Points |
|------|---------|------------|
| `__init__.py` | Public API surface | Re-exports all feature functions consumed by `webui/app.py` |
| `functions.py` | Shared utilities | zip/unzip, hashing, downloads, 7z integration, symlinks, font handling |
| `load.py` | Config & game detection | Config loading/validation, Steam registry game path detection |
| `update.py` | Self-updater | GitHub Releases-based auto-update |
| `const_apiConfig.py` | API provider config compatibility export | Re-exports the project-specific Rust-native OpenAI-compatible/Null provider catalog used by the WebUI |
| `function_llc.py` | LLC/零协会 install | Download & install Zero Association translation packs |
| `function_ourplay.py` | OurPlay PC install | Download OurPlay PC translation packs |
| `function_ourplay_new.py` | OurPlay Android install | Download OurPlay Android-origin translation packs |
| `function_LCTA_auto.py` | Auto-translate download | Download from LCTA_auto_update repo |
| `function_bubble.py` | Bubble language pack | One-click bubble text language pack download |
| `function_install.py` | Local package install | Install/delete/font-change for local translation packages |
| `function_manage.py` | Package management | Installed packages, mod management, symlink operations |
| `function_clean.py` | Cache cleaner | Clean game cache files |
| `function_fetch.py` | Proper noun scrape | Fetch proper nouns from remote sources |
| `function_fancy.py` | Text effects orchestration | Selects enabled built-in/user v2 rulesets before compilation, prepares skill-color resources only when required, scans matching language JSON files with UTF-8 BOM support, applies compiled rules, atomically rewrites changed files only, and returns `FancyRunStats`. Also owns validated `fancy/` ruleset load/save/delete helpers |
| `fancy_engine.py` | Compiled v2 beautification engine | Validates and compiles file globs, structured JSON paths, AND conditions (`equals`, `in`, `contains`, `regex`) and typed actions (`replace`, `wrap`, `gradient`, `skill_color`); filters rules per file and returns exact changed paths through `ApplyResult` |
| `function_translate.py` | Translation orchestration | Connects webui to translateFunc pipeline |
| `function_translation_logs.py` | Translation diagnostics viewer backend | Reads only the user-selected `.jsonl` within its selected parent directory; v2-only indexing, cached summaries/byte offsets, filtering, pagination, lazy record reads, and filtered JSONL export |
| `function_drop.py` | Drag-and-drop | Drag-and-drop file installation with zip/7z extraction, mod installation, update package handling via Updater |
| `function_cdn.py` | CDN optimization | Cloudflare + CloudFront CDN speed testing and optimization |
| `function_speed.py` | Game speed | Game speed acceleration via openspeedy DLL injection; `is_injected()` checks self-tracked injection state |
| `builtinFancy.py` | Built-in text rules | Built-in text beautification rules |
| `builtinFancyFunc.py` | Fancy skill-color resources | `SkillColorHandler` lazily extracts skill attributes from Unity resources, fingerprints source files, caches color mappings in `tmp/fancy/skill-colors.json`, records cache hits, and suppresses repeated retries after an initialization failure |
| `function_resource.py` | Unity resource reader | Locates Limbus resource files and extracts text assets in batches through UnityPy; sets fallback Unity version `6000.3.12f1` for resources without usable version metadata |
| `eiderConst.py` | Elder-mode bindings/constants | Update lists, dependency chains, and the reduced native translation-setting bindings |
| `FL2LCTA.py` | Rule converter | Fancy Language → LCTA rule format converter |
| `Faust_fancy.py` | Faust rules | Faust character-specific fancy text rules |
| `function_rule_editor.py` | Rule editor backend | File browser (`get_lang_files`, `get_file_content`, `search_files`); content search counts raw text occurrences with `utf-8-sig`, so BOM and temporarily invalid JSON files remain searchable. Also provides ruleset CRUD, v2 rule validation/building, V1/V2/V3 smart analysis, 5-dimension scoring, and JSON-validated file saving with backup |
| `rule_editor_constants.py` | Rule editor shared data | Single-source-of-truth for `FILE_PREFIX_RULES`, `CATEGORY_FILE_PATTERNS`, `COMMON_REPLACEMENTS`, `TEMPLATES`. Imported by `function_rule_editor.py` and `app.py` (RuleEditorAPI). JS fetches via `get_editor_constants()` API with hardcoded fallback. |
| `function_quick_editor.py` | Quick editor backend | Path-patch edit tracking and application. `diff_json()` (deep JSON diff → `{path, old, new}` list), `_set_value_by_path()` (dot-separated JSON path navigation), `load/save/apply_quick_edits()` (persist to `fancy/_quick_edits.json`, apply edits to game files without .bak). Reuses `_get_lang_dir`, `get_lang_files`, `search_files`, etc. from `function_rule_editor.py` |
| `test.py` | Debug utilities | Internal testing/debug helpers |
| `debug_environ_test.py` | Environment diag | Environment diagnostics on startup failure |

## webFunc/ — Infrastructure Layer

| File | Purpose |
|------|---------|
| `GithubDownload.py` | GitHub Release API client: proxy support, rate limiting, concurrent downloads |
| `FileTransfer.py` | File upload client (UpFileClient) |
| `LanzouFolder.py` | Lanzou cloud drive folder downloader (modified from 52pojie) |
| `Webnote.py` | Webnote/note.chat API client for remote config/data |

## translateFunc/ — Native Translation Bridge

Python-facing translation API. Translation execution, matching, response repair, diagnostics, file I/O, and validation are implemented by the required Rust engine; Python only normalizes configuration, drives the PyO3 job, reports events, and packages output.

**Root files:**

| File | Purpose |
|------|---------|
| `__init__.py` | Native translation public API and result/config exports |
| `native_pipeline.py` | PyO3 `TranslationJob` adapter, event dispatch, native provider/config/diagnostic-path conversion, and summary conversion |
| `provider_config.py` | Static project-specific provider metadata/defaults and API-setting normalization; active services are OpenAI-compatible LLM and Null |
| `config.py` | `TranslateConfig`, including bounded file/request/file-I/O concurrency normalization, plus summaries/outcomes |
| `enums.py` | `ProcessResult` summary compatibility enum |

## native/lcta_translation_engine/ — Rust Translation Engine

| Path | Purpose |
|------|---------|
| `src/lib.rs` | PyO3 module, background `TranslationJob` lifecycle, and synchronous `test_provider()` bridge |
| `src/engine.rs` | Priority-file barrier, concurrent file pipeline, per-request rule trimming, supplemental translation, optional self-check, per-file diagnostic aggregation, merging, fallback, and atomic output |
| `src/provider.rs` | Shared Reqwest client, request semaphore, retries, OpenAI-compatible request execution, queue-wait timing, and redacted HTTP-attempt traces |
| `src/diagnostics.rs` | Schema-v2 file/call/HTTP diagnostic model, validation/failure classification, sensitive-text redaction, timestamps, and one Tokio JSONL writer for processing and dump logs |
| `src/response.rs` | Project-specific JSON response parser: strict envelope/array decoding, fenced or explanatory-text extraction, common malformed JSON repair, and repair metadata for diagnostics |
| `src/document.rs` | BOM-aware JSON parsing, ID/position indexes, string flattening, and path-based updates |
| `src/matcher.rs` | Project-local immutable Unicode Aho-Corasick implementation used by rule snapshots |
| `src/rules.rs` | Async/local proper-term loading, role/effect snapshot construction, JP/EN-assisted matching, bracket/tag/placeholder/number validation |
| `src/config.rs` | Immutable native run/provider/rule/pipeline/diagnostic configuration and independent file/request/file-I/O concurrency |

## globalManagers/ — Cross-Cutting Singletons

| File | Purpose |
|------|---------|
| `ConfigManager.py` | Singleton config: dotted-path access (`ui_default.translator.enable_proper`), JSON validation via `config_check.json`, auto-save on mutation, thread-safe |
| `LogManager.py` | Singleton logger: file rotation, console output, webview modal callbacks via thread pool for async UI updates |

## launcher/ — Standalone Launcher (GPL-3.0)

| File | Purpose |
|------|---------|
| `main.py` | Entry point: pipeline orchestration — creates `LaunchPipeline`, registers handlers for mod/speed-hotkey, optionally creates GUI window, then emits pipeline phases in order. Uses `subprocess.Popen` (not `subprocess.call`) for game launch to support cancel-flow from GUI |
| `game_launch.py` | Game launch phases: `prepare_mod()` (mod patching pre-game), `cleanup_mod_assets()` (post-game restore), `start_speed_hotkey()` / `stop_speed_hotkey()` (lifecycle wrappers). Game process launch moved to `main.py` pipeline |
| `updates.py` | Translation pack update system (Factory pattern for LLC/OurPlay/Machine). Optional post-update beautification passes all built-in/user rules plus the enable map to `fancy_main()`, allowing disabled skill-color rules to avoid resource preparation |
| `cdn.py` | CDN optimization for launcher mode with cache TTL to avoid redundant speed tests |
| `patch.py` | Unity asset patching for mods |
| `modfolder.py` | Mod folder management and detection |
| `sound.py` | Sound file replacement for mods |
| `changes.py` | Text data patch application |
| `compress.py` | Compression utilities |
| `speed_hotkey.py` | Game speed hotkey (Ctrl+Shift+S) with comprehensive lifecycle logging, foreground process check, .NET STA threading for UI |
| `gui_progress.py` | WinForms companion window for GUI launcher mode: phase indicator (init→update→cdn→mod→launch→running), status label, progress bar, collapsible log area, game-running info display (PID + uptime + hotkey hints). `register_to_pipeline()` wires GUI to `LaunchPipeline` phases; `FormClosing` handler shows confirmation dialog and sets `cancel_event` on confirm |
| `pipeline.py` | `LaunchPipeline` — phase-based event-driven pipeline: `on(phase, callback)` for module registration, `emit(phase, **kwargs)` to trigger all callbacks. Defines 7 phases (`PHASE_INIT` through `PHASE_EXIT`). `cancel_event` (threading.Event) supports GUI-initiated abort. `context` dict shares state (steam_argv, game_process, game_pid) across phases |

## Import Dependency Graph

```
webui/app.py
  → webutils/ (all feature functions via __init__.py)
    → translateFunc/ (native translation bridge)
    → webFunc/ (GitHub downloads, file transfer)
  → globalManagers/ (ConfigManager, LogManager)
  → webutils/function_rule_editor.py (RuleEditorAPI: file browser, rules CRUD)
  → webutils/function_fancy.py (load_fancy_folder_rules, fancy_main)

webutils/function_rule_editor.py
  → webutils/function_fancy.py (load_fancy_folder_rules, save_ruleset_to_folder, etc.)
  → webutils/fancy_engine.py (shared v2 validation)
  → globalManagers/ConfigManager.py (_get_lang_dir)

webutils/function_fancy.py
  → webutils/fancy_engine.py (compile_rulesets, apply_rules)
  → webutils/builtinFancyFunc.py (lazy skill-color preparation when required)
    → webutils/function_resource.py (Unity text asset extraction)

launcher/updates.py
  → webutils/function_fancy.py (loads folder rules and executes only rulesets enabled by fancy_allow)

launcher/main.py
  → launcher/gui_progress.py (if gui_mode enabled: WinForms progress window)
  → launcher/updates.py (reuses shared webutils/webFunc install, download and beautification helpers)
  → launcher/game_launch.py
  → launcher/cdn.py

Note: `launcher/` is separately GPL-3.0-licensed, but the current Python implementation is not import-isolated: launcher modules directly reuse `webutils/`, `webFunc/`, and `globalManagers/`.
```

## Key External Libraries

| Package | Used In | Purpose |
|---------|---------|---------|
| `pywebview` | `webui/app.py` | Native desktop webview window |
| `UnityPy` | `launcher/patch.py`, `webutils/function_resource.py` | Unity asset patching plus batched text-asset extraction for skill-color beautification |
| `openspeedy` | `webutils/function_speed.py`, `launcher/speed_hotkey.py` | DLL injection for game speed |
| `keyboard` | `launcher/speed_hotkey.py` | Global hotkey registration |
| `requests` | `webFunc/GithubDownload.py` | HTTP client with proxy support |
| `Brotli` / `lz4` / `etcpak` | `webutils/`, translate pipeline | Compression/decompression |
| `pillow` / `texture2ddecoder` | `webutils/` | Image and texture processing |
