# LCTA Module Map

<!-- Last updated: 2026-07-18 -->

## Directory Overview

| Directory | Role | Key Files |
|-----------|------|-----------|
| `webui/` | Frontend application (pywebview + HTML/CSS/JS) | 12 + sections |
| `webutils/` | Business logic layer (one file per feature) | 24 |
| `webFunc/` | Infrastructure (network, downloads) | 4 |
| `translateFunc/` | Translation engine (LLM pipeline) | 12+ |
| `globalManagers/` | Cross-cutting singletons | 2 |
| `launcher/` | Standalone game launcher (GPL-3.0) | 11 |
| `CFST/` | CloudflareSpeedTest binary + IP lists | 3 |
| `tests/` | Pytest test suite | ~6 |

## webui/ — Frontend Application

| File | Purpose |
|------|---------|
| `app.py` | **Core**: `LCTA_API` class (~1528 lines), bridges all backend features to JS via pywebview. Includes `get_startup_data()` to batch-initialize frontend in a single bridge call, `perform_update_from_file()` for manual local package updates and redesigned drag-drop flow |
| `index.html` | Single-page HTML shell (~200 lines), section placeholders loaded dynamically from `sections/` |
| `css/base.css` | Base styling |
| `css/components.css` | Component-specific styles |
| `css/layout-extras.css` | Layout utilities and extra styles |
| `js/core.js` | Core framework: API binding, event system, navigation |
| `js/features.js` | Feature-specific UI logic, drag-drop manager, manual update from local zip, FancyManager (`updateEditorUI` fully null-guarded for lazy section loading) |
| `js/init.js` | Initialization and bootstrap: uses single `get_startup_data()` call; welcome content deferred via `_pendingWelcomeContent` for lazy section loading compatibility |
| `js/utils.js` | Navigation, encryption, sidebar search; `initNavigation` async handler with `await loadSection()`, `goAndShow` async for lazy section loading |
| `js/modals.js` | Modal dialog management, markdown content loader with `_loadedMarkdowns` cache, toggle functions (all null-guarded for lazy section loading safety) |
| `js/api-config.js` | API configuration page logic; container-not-found logs suppressed for lazy loading compatibility |
| `js/cdn.js` | CDN optimization page logic |
| `js/speed.js` | Game speed control page logic |
| `js/list-managers.js` | List/tab view management; constructors tolerate missing containers (lazy load compatible); container refs updated by `onSectionLoaded` |
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
| `function_fancy.py` | Text effects | FL-Like visual text enhancements |
| `function_translate.py` | Translation orchestration | Connects webui to translateFunc pipeline |
| `function_drop.py` | Drag-and-drop | Drag-and-drop file installation with zip/7z extraction, mod installation, update package handling via Updater |
| `function_cdn.py` | CDN optimization | Cloudflare + CloudFront CDN speed testing and optimization |
| `function_speed.py` | Game speed | Game speed acceleration via openspeedy DLL injection; `is_injected()` trusts self-record when openspeedy throws |
| `builtinFancy.py` | Built-in text rules | Built-in text beautification rules |
| `builtinFancyFunc.py` | Fancy rule functions | Fancy rule processing functions |
| `eiderConst.py` | Update constants | Translation pack update lists, dependency chains |
| `FL2LCTA.py` | Rule converter | Fancy Language → LCTA rule format converter |
| `Faust_fancy.py` | Faust rules | Faust character-specific fancy text rules |
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

**Subdirectories:**

| Path | Purpose |
|------|---------|
| `builder/prompt.py` | LLM prompt construction for translation |
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
| `main.py` | Entry point: update check → CDN optimize → launch game |
| `game_launch.py` | Game launch: mod mode (with patching) or plain mode |
| `updates.py` | Translation pack update system (Factory pattern for LLC/OurPlay/Machine) |
| `cdn.py` | CDN optimization for launcher mode with cache TTL to avoid redundant speed tests |
| `patch.py` | Unity asset patching for mods |
| `modfolder.py` | Mod folder management and detection |
| `sound.py` | Sound file replacement for mods |
| `changes.py` | Text data patch application |
| `compress.py` | Compression utilities |
| `speed_hotkey.py` | Game speed hotkey (Ctrl+Shift+S) with comprehensive lifecycle logging, foreground process check, .NET STA threading for UI |
| `gui_progress.py` | WinForms progress window for GUI launcher mode: status label, progress bar, scrollable log area; thread-safe UI updates via BeginInvoke; custom logging.Handler for log interception |

## Import Dependency Graph

```
webui/app.py
  → webutils/ (all feature functions via __init__.py)
    → translateFunc/ (translation pipeline)
    → webFunc/ (GitHub downloads, file transfer)
  → globalManagers/ (ConfigManager, LogManager)

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
