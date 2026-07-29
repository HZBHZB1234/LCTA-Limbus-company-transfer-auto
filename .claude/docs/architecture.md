# LCTA Architecture Overview

<!-- Last updated: 2026-07-29 -->

## Project Purpose

LCTA (Limbus Company Transfer Auto / 边狱公司工具箱) is a comprehensive desktop toolkit for the game *Limbus Company*. Core feature: **Chinese localization/translation management** with automatic LLM-based translation updates. Also provides CDN optimization (with cache TTL to avoid redundant speed tests), an integrated game launcher with mod support, bubble language pack download, manual update from local zip, and various game optimization tools. Version 5.0.0, MIT-licensed (launcher/ is GPL-3.0).

## Tech Stack

| Language | Layer | Notes |
|----------|-------|-------|
| Python 3.9.6+ | Backend bridge | WebUI, configuration, events, packaging, and static provider metadata |
| Rust | Native translation engine | PyO3 job/provider-test APIs, Tokio/Reqwest networking, concurrent JSON/file I/O, immutable rule snapshots, and deterministic validation |
| C (MinGW-w64) | Native launcher | `launcher.c` → compiled to .exe as PE entry point for packaged releases |
| JavaScript | Frontend | SPA modules plus standalone editor and translation-log viewer scripts, bridged to Python via `pywebview.api` |
| HTML/CSS | Frontend | SPA in `webui/index.html` with lazy section fragments plus standalone rule editor, quick editor, and translation diagnostic viewer windows with theme sync |
| PowerShell | Build system | `build.ps1` (617 lines), 6-step build pipeline |
| YAML | CI/CD | GitHub Actions: `release.yml`, `check.yml`, `check-sync.yml` |

## Layered Architecture

```
┌─────────────────────────────────────────────────────┐
│                   PRESENTATION                       │
│  start_webui.py          dispatcher (WebUI/Launcher) │
│  webui/app.py            LCTA_API class (pywebview)  │
│  webui/index.html + js/  frontend SPA                │
│  launcher/main.py        CLI launcher entry point    │
├─────────────────────────────────────────────────────┤
│                  BUSINESS LOGIC                      │
│  webutils/__init__.py    public API aggregation      │
│  webutils/function_*.py  feature modules             │
│  webutils/update.py      self-update via GitHub API  │
│  webutils/load.py        config loading/validation   │
├─────────────────────────────────────────────────────┤
│                DOMAIN ENGINES                        │
│  native/lcta_translation_engine/                     │
│    engine.rs              async translation pipeline │
│    matcher.rs             immutable AC snapshots     │
│    rules.rs               terminology + validation   │
│    provider.rs            pooled HTTP provider       │
│    response.rs            JSON extraction + repair   │
│    diagnostics.rs         async schema-v2 JSONL      │
│  translateFunc/           thin PyO3/config bridge    │
│  webutils/fancy_engine.py compiled v2 rule engine    │
│  webutils/function_fancy.py file orchestration/stats │
├─────────────────────────────────────────────────────┤
│                INFRASTRUCTURE                        │
│  webFunc/                 GitHub API, file upload,   │
│                           Lanzou downloads, web notes│
│  globalManagers/          ConfigManager, LogManager  │
│  CFST/                    CloudflareSpeedTest binary │
├─────────────────────────────────────────────────────┤
│               EXTERNAL TOOLS                         │
│  openspeedy  UnityPy  pywebview  etcpak              │
└─────────────────────────────────────────────────────┘
```

## The 6 Source Directories

| Directory | Role |
|-----------|------|
| `webui/` | Frontend: pywebview desktop window + HTML/CSS/JS SPA |
| `webutils/` | Business logic: one `function_*.py` per feature, all exported via `__init__.py` |
| `webFunc/` | Infrastructure: GitHub downloads, file transfer, Lanzou parsing, web notes |
| `translateFunc/` | Thin Python bridge: native provider schema, immutable run config conversion, events, and summary types |
| `native/lcta_translation_engine/` | Rust translation engine: priority barriers, JSON transformation, async provider/file I/O, rule snapshots, validation, schema-v2 diagnostics, and atomic output |
| `globalManagers/` | Cross-cutting singletons: `ConfigManager.py`, `LogManager.py` |
| `launcher/` | Standalone game launcher (GPL-3.0): mod patching, updates, CDN, speed hotkey, optional WinForms GUI progress window |

## Design Patterns

| Pattern | Where | Concrete Example |
|---------|-------|-----------------|
| **Singleton** | `globalManagers/` | `ConfigManager` — thread-safe, lazy-init, dotted-path access. `LogManager` — async UI callbacks via thread pool |
| **Bridge** | `webui/app.py` ↔ JS | `LCTA_API` class exposes Python methods to JS via `pywebview.api`; JS calls like `pywebview.api.install_llc()` |
| **Pipeline** | `native/lcta_translation_engine/src/engine.rs` | Native pipeline orchestrates: scan → async proper terms → priority rule files → freeze snapshot → concurrent files/requests → supplemental translation → optional self-check → atomic output |
| **Immutable Snapshot** | `native/lcta_translation_engine/src/matcher.rs`, `rules.rs` | Proper noun, role, and effect Aho-Corasick matchers are rebuilt only at priority barriers, then shared read-only by file tasks |
| **Single Writer** | `native/lcta_translation_engine/src/diagnostics.rs` | File tasks aggregate diagnostics locally; one Tokio task serializes schema-v2 JSONL records to `processing_log.jsonl` and the optional persistent dump without cross-task file locks |
| **Compile/Apply** | `webutils/fancy_engine.py` | Text beautification validates and compiles v2 rules once, selects rules per file, then applies structured-path conditions/actions without repeatedly reparsing paths or regexes |
| **Factory** | `launcher/updates.py` | Update objects for LLC, OurPlay, Machine translation — each implements a common interface |
| **Observer/Callback** | `globalManagers/LogManager.py` → `webui/app.py` → JS | Real-time log/progress/status via callback chains through modal windows |
| **Pipeline** | `launcher/pipeline.py` | `LaunchPipeline` — phase-based event-driven pipeline (init→check_update→cdn→prepare_mod→launch→running→exit). Modules register callbacks per phase via `on(phase, callback)`; `cancel_event` supports GUI-initiated shutdown.

## Key Interfaces

| Interface | File | Role |
|-----------|------|------|
| `LCTA_API` | `webui/app.py` | Central hub: ~1570 lines, bridges all backend features to JS frontend. Includes `get_startup_data()` for consolidated frontend init, `open_rule_editor()` / `open_quick_editor()` to spawn editor windows with theme injection, `sync_theme_to_rule_editor()` for live cross-window theme sync, and redesigned drag-drop file handling |
| `RuleEditorAPI` | `webui/app.py` | Secondary pywebview bridge for the rule editor window: wraps `webutils/function_rule_editor.py` methods (file browser, rules CRUD, rule building, validation, smart analysis), plus `get_config_value()` for cross-window config queries (e.g. theme). Instantiated as `js_api=RuleEditorAPI()` in a separate `webview.create_window()` call |
| `QuickEditorAPI` | `webui/app.py` | Pywebview bridge for the quick editor window: wraps `webutils/function_quick_editor.py` methods (diff_json, load/save/apply_quick_edits) plus shared methods from `function_rule_editor.py` (file browser, search). Instantiated as `js_api=QuickEditorAPI()` in `open_quick_editor()` |
| `ConfigManager` | `globalManagers/ConfigManager.py` | Singleton config with dotted-path access, validation, auto-save |
| `NativeTranslationPipeline` | `translateFunc/native_pipeline.py` | Converts Python configuration to one immutable native run config and polls the bounded Rust event queue |
| `TranslationJob` / `test_provider` | `native/lcta_translation_engine/src/lib.rs` | PyO3 background job lifecycle plus direct OpenAI-compatible/Null provider validation for WebUI API tests |
| `CompiledRules` / `ApplyResult` | `webutils/fancy_engine.py` | Immutable compiled beautification rules plus per-file changed-path results; exposes `requires_skill_color` so resource extraction is prepared only when an enabled rule needs it |
| `FancyRunStats` | `webutils/function_fancy.py` | Reports scanned, matched and changed files/values, elapsed time, and skill-color resource cache hits; files are rewritten atomically only when content changes |
| `LogManager` | `globalManagers/LogManager.py` | Singleton logger: file rotation, console, webview modal callbacks |

## Polyglot Boundaries

- **Python ↔ JS**: `pywebview` exposes `LCTA_API` instance as `window.pywebview.api` in JS. JS calls Python methods, Python calls JS via `webview.windows[0].evaluate_js()`
- **HTML <> JS**: Section HTML fragments in `webui/sections/*.html` are lazy-loaded by `preload.js` via `loadSection()` on first navigation; `onSectionLoaded()` callback re-runs per-section initialization (config, tooltips, toggle funcs, list manager DOM refs, select box values). Markdown assets loaded on-demand with fetch-caching via `_loadedMarkdowns`; welcome content deferred via `_pendingWelcomeContent`
- **Translation settings → Rust config**: `webui/sections/translate.html` exposes independent file, HTTP-request, and file-I/O concurrency. `webui/js/core.js` persists them under `ui_default.translator.*`; `translateFunc/config.py` parses and bounds them before `native_pipeline.py` serializes the immutable native run config. Legacy format/source-language/disambiguation settings are not part of the native path.
- **C → Python**: Native `launcher.c` compiled with `-mwindows` (GUI subsystem, no console). Python process always started with `CREATE_NO_WINDOW`; stdout/stderr captured via pipe. If Python exits with non-zero code, C layer allocates an error console to display captured output. Console management (AllocConsole for legacy mode, GUI window for gui_mode) handled by `start_webui.py` before importing launcher modules.
- **Python → C binaries**: Subprocess calls to `CFST/cfst.exe` (CloudflareSpeedTest) and `7z.exe` (7-Zip)

## External Binaries

| Binary | Source | Purpose |
|--------|--------|---------|
| `cfst.exe` v2.3.5 | Bundled in `CFST/` | Cloudflare CDN speed testing |
| `7z.exe` | Downloaded at runtime | Archive extraction |
| Embedded Python 3.9.6 | Downloaded during build | Bundled into release packages |
| `openspeedy` DLL | pip package | DLL injection for game speed acceleration |
