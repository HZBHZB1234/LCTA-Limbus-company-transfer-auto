# LCTA Architecture Overview

<!-- Last updated: 2026-08-06 -->

## Project Purpose

LCTA (Limbus Company Transfer Auto / 边狱公司工具箱) is a comprehensive desktop toolkit for the game *Limbus Company*. Core feature: **Chinese localization/translation management** with automatic LLM-based translation updates. Also provides CDN optimization (with cache TTL to avoid redundant speed tests), an integrated game launcher with mod support, official localize/AssetBundle pre-download, 调爪 text modification package download/import, manual update from local zip, and various game optimization tools. Version 5.0.0, MIT-licensed (launcher/ is GPL-3.0).

## Tech Stack

| Language | Layer | Notes |
|----------|-------|-------|
| Python 3.9.6+ | Backend (primary) | Business logic, translation engine, webview bridge |
| C (MinGW-w64) | Native launcher | `launcher.c` → compiled to .exe as PE entry point for packaged releases |
| TypeScript / Vue 3 | Modern frontend | Vite multi-page build with Pinia stores for the main product shell and Launcher WebView |
| JavaScript | Legacy frontend | Existing SPA modules plus standalone editor and translation-log viewer scripts, bridged to Python via `pywebview.api` |
| HTML/CSS | Frontend | Modern build output in `webui/product/`; legacy SPA and standalone tools remain available during migration |
| PowerShell | Build system | `build.ps1` runs the Vite build before the existing release pipeline |
| YAML | CI/CD | GitHub Actions: `release.yml`, `check.yml`, `check-sync.yml` |

## Layered Architecture

```
┌─────────────────────────────────────────────────────┐
│                   PRESENTATION                       │
│  start_webui.py          dispatcher (WebUI/Launcher) │
│  webui/app.py            LCTA_API 组装壳 + main (pywebview)  │
│  webui/app_api/*.py      LCTA_API 功能域 mixin（core/config/  │
│                          packages/download/fancy/windows/    │
│                          cdn/speed/update/drops/resources/    │
│                          product）                            │
│  frontend/               Vue/Vite source, dual HTML entries  │
│  webui/product/          generated dual WebView assets       │
│  webui/index.html + js/  legacy frontend SPA fallback        │
│  launcher/webview_window.py modern Launcher window/API       │
│  launcher/main.py        Launcher dispatcher + worker flow   │
├─────────────────────────────────────────────────────┤
│                  PRODUCT SERVICES                    │
│  product/workspace.py   WorkspaceSnapshot           │
│  product/actions.py     versioned ActionPlan flow   │
│  product/tasks.py       unified in-process tasks     │
│  product/launcher_session.py persistent session      │
├─────────────────────────────────────────────────────┤
│                  BUSINESS LOGIC                      │
│  webutils/__init__.py    public API aggregation      │
│  webutils/function_*.py  feature modules             │
│  webutils/update.py      self-update via GitHub API  │
│  webutils/load.py        config loading/validation   │
├─────────────────────────────────────────────────────┤
│                DOMAIN ENGINES                        │
│  translateFunc/           LLM translation pipeline   │
│    pipeline.py            orchestration              │
│    processor.py           per-file logic             │
│    validator.py           rule-based post-processing │
│    workers.py             concurrency                │
│    builder/               prompt & request building  │
│    matcher/               proper noun AC matching    │
│  webutils/fancy/engine.py compiled v2 rule engine    │
│  webutils/fancy/bus.py     bus/import rule engine     │
│  webutils/llm_fancy/       LLM text-beautification    │
│  webutils/function_fancy.py file orchestration/stats │
│  resource_updater/         official resource updater  │
├─────────────────────────────────────────────────────┤
│                INFRASTRUCTURE                        │
│  webFunc/                 GitHub API, file upload,   │
│                           Lanzou downloads, web notes│
│  globalManagers/          ConfigManager, LogManager  │
│  CFST/                    CloudflareSpeedTest binary │
├─────────────────────────────────────────────────────┤
│               EXTERNAL TOOLS                         │
│  translatekit  openspeedy  UnityPy  pywebview  etcpak│
└─────────────────────────────────────────────────────┘
```

## Source Directories

| Directory | Role |
|-----------|------|
| `frontend/` | Vue 3 + TypeScript + Vite source for main and Launcher WebViews |
| `product/` | Product-facing snapshots, action plans, task state, and Launcher sessions |
| `webui/` | pywebview host, generated modern assets, legacy SPA, and standalone tools |
| `webutils/` | Business logic: one `function_*.py` per feature, all exported via `__init__.py` |
| `webFunc/` | Infrastructure: GitHub downloads, file transfer, Lanzou parsing, web notes |
| `translateFunc/` | Translation engine: multi-stage LLM pipeline with proper noun matching |
| `globalManagers/` | Cross-cutting singletons: `ConfigManager.py`, `LogManager.py` |
| `launcher/` | Standalone game launcher (GPL-3.0): mod patching, updates, CDN, speed hotkey, optional WinForms GUI progress window |
| `resource_updater/` | Official game resource updater: CDN token extraction, localize ZIP deployment, Unity Bundle cache population, aria2 RPC, Launcher fingerprint state, and the main-window page API |

## Design Patterns

| Pattern | Where | Concrete Example |
|---------|-------|-----------------|
| **Singleton** | `globalManagers/` | `ConfigManager` — thread-safe, lazy-init, dotted-path access. `LogManager` — async UI callbacks via thread pool |
| **Bridge** | `webui/app.py` + `webui/app_api/` ↔ JS | `LCTA_API` class exposes Python methods to JS via `pywebview.api` (pywebview enumerates `dir()` so inherited mixin methods are exposed transparently); JS calls like `pywebview.api.install_llc()` |
| **Pipeline** | `translateFunc/pipeline.py` | `TranslationPipeline` orchestrates: fetch proper nouns → build matcher → priority files → WorkerPool → aggregate |
| **Compile/Apply** | `webutils/fancy/engine.py` | Text beautification validates and compiles v2 rules once, selects rules per file, then applies structured-path conditions/actions without repeatedly reparsing paths or regexes |
| **Bus Compile/Apply** | `webutils/fancy/bus.py` | Validates `format: lcta-bus`, compiles glob/regex/exact file matchers into per-file indexes, caches selector lookups by list path/field, preserves ordered literal/regex/end/safe/set operations, and mechanically converts 调爪、LCJE、FL and quick-editor edits |
| **Scan-Exclude-LLM** | `webutils/llm_fancy/` | Bus-syntax selection scan → user-chosen bus rulesets simulated on a data copy to exclude already-handled paths → size-batched LLM rewriting (default 20k chars) → validated `lcta-bus` ruleset built, saved to `fancy/`, and auto-enabled |
| **Factory** | `launcher/updates.py` | Update objects for LLC, OurPlay, Machine translation — each implements a common interface |
| **Observer/Callback** | `globalManagers/LogManager.py` → `webui/app.py` → JS | Real-time log/progress/status via callback chains through modal windows |
| **Pipeline** | `launcher/pipeline.py` | `LaunchPipeline` — phase-based event-driven pipeline (init→check_update→resource_update→cdn→prepare_mod→launch→running→exit). Modules register callbacks per phase via `on(phase, callback)`; `cancel_event` supports GUI-initiated shutdown.
| **Fingerprint Gate** | `resource_updater/service.py` | Local SHA-256 of `LimbusCompany.exe` gates Launcher pre-download without an online version check; successful resource scopes are persisted and merged so partial manual runs do not suppress missing work. `record_update_result()` marks only fully completed scopes — failed scopes stay unmarked and re-run on the next launch — and persists the last result (counts + failed item names/reasons) for the manual page |
| **Registry + Interface** | `webutils/drop/` | `DropFileHandler` 接口（检测 + 执行 + 显示名收敛于单类）; `DropFileHandlerRegistry` 按容器类型（zip/folder/json/path）有序检测、按类型分派执行，兜底 `invalid` |

## Key Interfaces

| Interface | File | Role |
|-----------|------|------|
| `LCTA_API` | `webui/app.py`（组装壳）+ `webui/app_api/*.py`（mixin） | Central hub: assembles the feature-domain mixins (`CoreMixin`/`ConfigMixin`/`TranslatorMixin`/`PackagesMixin`/`DownloadMixin`/`FancyMixin`/`WindowMixin`/`CdnMixin`/`SpeedMixin`/`UpdateMixin`/`DropMixin`/`ResourceMixin`), bridges backend features to the SPA, owns the main-window `ResourceUpdaterAPI`, includes `get_startup_data()` for consolidated frontend init, opens editor windows with theme injection, and handles redesigned drag-drop file flows |
| `RuleEditorAPI` | `webui/rule_editor_api.py` | Secondary pywebview bridge for the rule editor window: wraps `webutils/rule_editor/` methods (file browser, rules CRUD, rule building, validation, smart analysis), plus `get_config_value()` for cross-window config queries (e.g. theme). Instantiated as `js_api=RuleEditorAPI()` in a separate `webview.create_window()` call |
| `QuickEditorAPI` | `webui/quick_editor_api.py` | Pywebview bridge for the quick editor window: wraps `webutils/rule_editor/quick.py` methods (diff_json, load/save/apply_quick_edits) plus shared methods from `webutils/rule_editor/browser.py` (file browser, search). Instantiated as `js_api=QuickEditorAPI()` in `open_quick_editor()` |
| `LLMFancyAPI` | `webui/llm_fancy_api.py` | Pywebview bridge for the LLM 文本美化 window: wraps `webutils/llm_fancy/` (selection scan preview, exclusion-ruleset simulation, batched LLM beautification with progress/log callbacks and cancel, ruleset build/save/auto-enable) plus config persistence (`ui_default.llm_fancy`). Instantiated as `js_api=LLMFancyAPI()` in `LCTA_API.open_llm_fancy()` |
| `ResourceUpdaterAPI` | `resource_updater/web_api.py` | Resource-update controller owned by `LCTA_API`. Probes game files, persists updater options (incl. retry settings), runs/cancels the worker thread, records results, exposes the last update result (failure list for the manual retry button), and emits per-channel progress into the main SPA's `resource-updater.js` controller |
| `ResourceUpdater` | `resource_updater/core.py` | Extracts S/L CDN tokens, downloads token-scoped localize ZIPs, parses remote/fallback catalog data, populates Unity cache entries, and selects bundled aria2c or the built-in downloader. Transient download failures auto-retry with `retry_max`/`retry_delay` backoff; exhausted retries emit a Range probe with diagnostic headers; aria2 uses a per-file connection limit |
| `ConfigManager` | `globalManagers/ConfigManager.py` | Singleton config with dotted-path access, validation, auto-save |
| `TranslationPipeline` | `translateFunc/pipeline.py` | Orchestrates the 6-stage LLM translation pipeline |
| `CompiledRules` / `ApplyResult` | `webutils/fancy/engine.py` | Immutable compiled beautification rules plus per-file changed-path results; exposes `requires_skill_color` so resource extraction is prepared only when an enabled rule needs it |
| `CompiledBus` / `BusApplyResult` | `webutils/fancy/bus.py` | Immutable bus rules with precomputed exact/dynamic file indexes, deduplicated shared matchers, per-ruleset directory exclusions, selector indexes, ordered path execution, exact quick-edit success/failure counts, and changed-path reporting |
| `FancyRunStats` | `webutils/function_fancy.py` | Reports scanned, matched and changed files/values, elapsed time, and skill-color resource cache hits; files are rewritten atomically only when content changes |
| `DropFileHandler` / `DropFileHandlerRegistry` | `webutils/drop/handler.py` | 接口：每个分支类实现 `detect()`（快照/路径 → 类型字符串）与 `execute()`（上下文 → 结果键），声明 `file_type`/`label`; 注册表维护各容器类型的检测顺序（如 zip: full → nofont → FLmod → update → jsononly），并按类型查处理器执行，无需改动 `evalFile()` / `evalFiles()` 即可扩展新分支 |
| `LogManager` | `globalManagers/LogManager.py` | Singleton logger: file rotation, console, webview modal callbacks |

## Polyglot Boundaries

- **Python ↔ JS**: `pywebview` exposes `LCTA_API` instance as `window.pywebview.api` in JS. JS calls Python methods, Python calls JS via `webview.windows[0].evaluate_js()`
- **HTML <> JS**: Section HTML fragments in `webui/sections/*.html` are lazy-loaded by `preload.js` via `loadSection()` on first navigation; `onSectionLoaded()` callback re-runs per-section initialization (config, tooltips, toggle funcs, list manager DOM refs, select box values). Markdown assets loaded on-demand with fetch-caching via `_loadedMarkdowns`; welcome content deferred via `_pendingWelcomeContent`
- **C → Python**: Native `launcher.c` compiled with `-mwindows` (GUI subsystem, no console). Python process always started with `CREATE_NO_WINDOW`; stdout/stderr captured via pipe. If Python exits with non-zero code, C layer allocates an error console to display captured output. Console management (AllocConsole for legacy mode, GUI window for gui_mode) handled by `start_webui.py` before importing launcher modules.
- **Python → C binaries**: Subprocess calls to `CFST/cfst.exe` (CloudflareSpeedTest), `tools/aria2/aria2c.exe` (official resource downloads), and `7z.exe` (7-Zip)

## External Binaries

| Binary | Source | Purpose |
|--------|--------|---------|
| `cfst.exe` v2.3.5 | Bundled in `CFST/` | Cloudflare CDN speed testing |
| `aria2c.exe` v1.37.0 | Downloaded during build into `tools/aria2/` | Multi-connection localize and AssetBundle downloads through localhost JSON-RPC; built-in urllib fallback remains available |
| `7z.exe` | Downloaded at runtime | Archive extraction |
| Embedded Python 3.9.6 | Downloaded during build | Bundled into release packages |
| `openspeedy` DLL | pip package | DLL injection for game speed acceleration |
