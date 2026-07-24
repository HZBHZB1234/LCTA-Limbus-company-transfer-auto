# LCTA Module Map

<!-- Last updated: 2026-07-24 -->

## Directory Overview

| Directory | Role | Key Files |
|-----------|------|-----------|
| `webui/` | Frontend application (pywebview + HTML/CSS/JS) | 15 + sections |
| `webutils/` | Business logic layer (one file per feature) | 25 |
| `webFunc/` | Infrastructure (network, downloads) | 4 |
| `translateFunc/` | Translation engine (LLM pipeline) | 13+ |
| `globalManagers/` | Cross-cutting singletons | 2 |
| `launcher/` | Standalone game launcher (GPL-3.0) | 11 |
| `CFST/` | CloudflareSpeedTest binary + IP lists | 3 |
| `fancy/` | User rule sets (one JSON file per ruleset) | auto-created |
| `tests/` | Pytest test suite | ~7 |

## webui/ — Frontend Application

| File | Purpose |
|------|---------|
| `app.py` | **Core**: `LCTA_API` class (~1570 lines), bridges all backend features to JS via pywebview. Includes `RuleEditorAPI` class (the rule editor window's bridge with `get_config_value` for cross-window config queries), `open_rule_editor()` to spawn a second pywebview window with theme injection, `sync_theme_to_rule_editor()` for live theme push. `get_fancy_rulesets()` now loads user rules from `fancy/` folder via `load_fancy_folder_rules()`. Auto-migrates old `user_fancy` config on startup |
| `index.html` | Single-page HTML shell (~200 lines), section placeholders loaded dynamically from `sections/` |
| `rule-editor.html` | Standalone pywebview page for the 美化规则编辑器. Sidebar file browser + two main mode tabs (file-edit / ruleset-edit). File-edit tab: VSCode-style CodeMirror 6 editor with find/replace (Ctrl+F/H), match highlighting, dirty state indicator, status bar, change tracking, smart ruleset generation (V3: auto-merge + instant analysis, replaces 保守/进取 mode selection). Ruleset-edit tab: simple form + advanced JSON editors for ruleset CRUD. Theme syncs with main app window (light/dark/purple) |
| `css/base.css` | Base styling with 3 theme definitions (light/dark/purple) and CSS custom properties |
| `css/components.css` | Component-specific styles: cards, buttons, forms, progress bars, modals |
| `css/layout-extras.css` | Layout utilities, modals, drawers, scrollbars, responsive breakpoints. Now also loaded by rule-editor.html |
| `css/rule-editor.css` | Rule editor styles: sidebar+main+bottom panel layout, VSCode-style find bar, data cards, smart-gen dialog (V1/V2/V3 with merge connectors), tiered scope options, editor status bar, match highlight decorations, toast notifications, per-theme editor colors |
| `js/core.js` | Core framework: API binding, event system, navigation |
| `js/features.js` | Feature-specific UI logic, drag-drop manager, manual update from local zip, FancyManager (saveAll now persists to `fancy/` folder via `pywebview.api.save_ruleset()`), `openRuleEditor()` global function |
| `js/init.js` | Initialization and bootstrap: uses single `get_startup_data()` call; welcome content deferred via `_pendingWelcomeContent` for lazy section loading compatibility |
| `js/utils.js` | Navigation, encryption, sidebar search; `initNavigation` async handler with `await loadSection()`, `goAndShow` async for lazy section loading |
| `js/modals.js` | Modal dialog management, markdown content loader with `_loadedMarkdowns` cache, toggle functions (all null-guarded for lazy section loading safety) |
| `js/api-config.js` | API configuration page logic; container-not-found logs suppressed for lazy loading compatibility |
| `js/cdn.js` | CDN optimization page logic |
| `js/speed.js` | Game speed control page logic |
| `js/list-managers.js` | List/tab view management; constructors tolerate missing containers (lazy load compatible); container refs updated by `onSectionLoaded` |
| `js/rule-editor.js` | Rule editor frontend logic: two main mode tabs (file-edit / ruleset-edit). File-edit: editable CodeMirror, JSON diff tracking, change list panel, batch replace, smart gen from file edits. Ruleset-edit: file browser (grouped by category, search with full-text), file content preview (structured data cards / read-only CodeMirror), simple mode form-driven rule builder, advanced mode editable CodeMirror with template loading and validation, smart generation dialog with L1-L4 tiered scope options |
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
| `const_apiConfig.py` | API provider configs | TranslateKit provider definitions (Baidu, Google, DeepL, etc.) |
| `function_llc.py` | LLC/零协会 install | Download & install Zero Association translation packs |
| `function_ourplay.py` | OurPlay PC install | Download OurPlay PC translation packs |
| `function_ourplay_new.py` | OurPlay Android install | Download OurPlay Android-origin translation packs |
| `function_LCTA_auto.py` | Auto-translate download | Download from LCTA_auto_update repo |
| `function_bubble.py` | Bubble language pack | One-click bubble text language pack download |
| `function_install.py` | Local package install | Install/delete/font-change for local translation packages |
| `function_manage.py` | Package management | Installed packages, mod management, symlink operations |
| `function_clean.py` | Cache cleaner | Clean game cache files |
| `function_fetch.py` | Proper noun scrape | Fetch proper nouns from remote sources |
| `function_fancy.py` | Text effects | FL-Like visual text enhancements. Supports `conditions` array (multi-condition AND) with backward-compatible `trigger`/`aim` normalization via `_normalize_rule()`. User rulesets now loaded from `fancy/` folder via `load_fancy_folder_rules()`; legacy `ConfigManager.user_fancy` auto-migrated by `migrate_user_fancy_to_folder()` |
| `function_translate.py` | Translation orchestration | Connects webui to translateFunc pipeline |
| `function_drop.py` | Drag-and-drop | Drag-and-drop file installation with zip/7z extraction, mod installation, update package handling via Updater |
| `function_cdn.py` | CDN optimization | Cloudflare + CloudFront CDN speed testing and optimization |
| `function_speed.py` | Game speed | Game speed acceleration via openspeedy DLL injection; `is_injected()` checks self-tracked injection state |
| `builtinFancy.py` | Built-in text rules | Built-in text beautification rules |
| `builtinFancyFunc.py` | Fancy rule functions | Fancy rule processing functions |
| `eiderConst.py` | Update constants | Translation pack update lists, dependency chains |
| `FL2LCTA.py` | Rule converter | Fancy Language → LCTA rule format converter |
| `Faust_fancy.py` | Faust rules | Faust character-specific fancy text rules |
| `function_rule_editor.py` | Rule editor backend | File browser (`get_lang_files`, `get_file_content`, `search_files`), ruleset CRUD (`get_ruleset_list`, `save_ruleset`, `create_ruleset`, `delete_ruleset`), rule building (`build_rule_from_form`, `validate_rule`), smart change analysis V1/V2/V3 (`analyze_changes`, `analyze_changes_v2`, `analyze_changes_v3` — V3 adds auto-merge by (old_val,new_val,field_path) key + merge candidate detection), 5-dimension scoring (`_score_group`), file saving (`save_file_content` with JSON validation + backup) |
| `rule_editor_constants.py` | Rule editor shared data | Single-source-of-truth for `FILE_PREFIX_RULES`, `CATEGORY_FILE_PATTERNS`, `COMMON_REPLACEMENTS`, `TEMPLATES`. Imported by `function_rule_editor.py` and `app.py` (RuleEditorAPI). JS fetches via `get_editor_constants()` API with hardcoded fallback. |
| `test.py` | Debug utilities | Internal testing/debug helpers |
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
| `processor.py` | `FileProcessor` — per-file translation logic |
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
| `builder/request.py` | API request building |
| `builder/stages.py` | Pipeline stage definitions |
| `builder/examples.py` | Example translations for few-shot prompting |
| `matcher/engine.py` | `MatcherEngine` — proper noun matching orchestration |
| `matcher/ac_automaton.py` | Aho-Corasick automaton for fast multi-pattern matching |
| `matcher/proper.py` | `ProperAnalyzer` — proper noun analysis |
| `proper/analyze.py` | Proper noun analysis utilities |
| `proper/flat.py` | Proper noun flattening/normalization |

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
| `updates.py` | Translation pack update system (Factory pattern for LLC/OurPlay/Machine) |
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
    → translateFunc/ (translation pipeline)
    → webFunc/ (GitHub downloads, file transfer)
  → globalManagers/ (ConfigManager, LogManager)
  → webutils/function_rule_editor.py (RuleEditorAPI: file browser, rules CRUD)
  → webutils/function_fancy.py (load_fancy_folder_rules, fancy_main)

webutils/function_rule_editor.py
  → webutils/function_fancy.py (load_fancy_folder_rules, save_ruleset_to_folder, etc.)
  → globalManagers/ConfigManager.py (_get_lang_dir)

launcher/updates.py
  → webutils/function_fancy.py (load_fancy_folder_rules) — now reads user rules from fancy/ folder

launcher/main.py
  → launcher/gui_progress.py (if gui_mode enabled: WinForms progress window)
  → launcher/updates.py (standalone, no import from webutils/)
  → launcher/game_launch.py
  → launcher/cdn.py

Note: launcher/ and main app are IMPORT-ISOLATED (GPL boundary).
They share only config.json and command-line invocation.
```

## Key External Libraries

| Package | Used In | Purpose |
|---------|---------|---------|
| `pywebview` | `webui/app.py` | Native desktop webview window |
| `translatekit` | `webutils/`, `translateFunc/` | Multi-provider translation API (Baidu, Google, DeepL, LLM) |
| `UnityPy` | `launcher/patch.py` | Unity asset extraction and patching |
| `openspeedy` | `webutils/function_speed.py`, `launcher/speed_hotkey.py` | DLL injection for game speed |
| `keyboard` | `launcher/speed_hotkey.py` | Global hotkey registration |
| `requests` | `webFunc/GithubDownload.py` | HTTP client with proxy support |
| `Brotli` / `lz4` / `etcpak` | `webutils/`, translate pipeline | Compression/decompression |
| `pillow` / `texture2ddecoder` | `webutils/` | Image and texture processing |
