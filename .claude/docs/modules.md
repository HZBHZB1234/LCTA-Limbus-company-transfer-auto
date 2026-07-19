# LCTA Module Map

<!-- Last updated: 2026-07-19 -->

## Directory Overview

| Directory | Role | Key Files |
|-----------|------|-----------|
| `webui/` | Frontend application (Vue 3 + TypeScript + Vite) | 48 SFC, 5 stores, 3 utils |
| `webutils/` | Business logic layer (one file per feature) | 24 |
| `webFunc/` | Infrastructure (network, downloads) | 4 |
| `translateFunc/` | Translation engine (LLM pipeline) | 12+ |
| `globalManagers/` | Cross-cutting singletons | 2 |
| `launcher/` | Standalone game launcher (GPL-3.0) | 11 |
| `CFST/` | CloudflareSpeedTest binary + IP lists | 3 |
| `tests/` | Pytest test suite | ~6 |

## webui/ — Frontend Application (Vue 3 + TypeScript + Vite)

| File | Purpose |
|------|---------|
| `app.py` | **Core**: `LCTA_API` class, bridges all backend features to Vue via `pywebview.api` + `_emit()` Event Bridge (CustomEvent → Pinia stores). Auto-detects dev/prod environment |
| `package.json` | npm dependencies: Vue 3, Vue Router, Pinia, marked, Font Awesome; dev: TypeScript, Vite, Vitest, ESLint |
| `vite.config.ts` | Vite build config: `base: './'`, `strictPort: 5173`, Vue plugin, `@/` path alias |
| `tsconfig.json` | TypeScript `strict: true`, path aliases, Vue SFC support |
| `eslint.config.js` | ESLint flat config: `@typescript-eslint` + `eslint-plugin-vue` |
| `vitest.config.ts` | Vitest config: happy-dom environment, 60% coverage threshold |
| `index.html` | Vite entry point: `<div id="app">` + `<script type="module" src="/src/main.ts">` |
| `dist/` | Vite build output (production). Excluded from git, included in release packages |

### `src/` — Vue Source

| Path | Purpose |
|------|---------|
| `main.ts` | Bootstrap: `await initApi()` → `get_startup_data()` → `configStore.init()` → `createApp(App).use(pinia).use(router).mount('#app')` |
| `App.vue` | Root layout: AppSidebar + `<router-view>` + ModalContainer + HelpDrawer + DragOverlay. Global CSS reset + theme variables |
| `router.ts` | Vue Router hash mode, 18 lazy routes via `() => import('./views/Xxx.vue')` |
| `env.d.ts` | Vue SFC type shim (`declare module '*.vue'`) |
| `types/api.d.ts` | `PyWebViewApi` interface — ~80 typed method signatures for all `pywebview.api` calls |
| `types/config.d.ts` | `StartupData`, `PackageInfo`, `CdnStatus`, `SpeedStatus`, `UpdateInfo`, etc. |
| `types/events.d.ts` | `LctaEventMap` — typed CustomEvent payloads (`lcta:log`, `lcta:modal-progress`, etc.) |
| `utils/api.ts` | `initApi()` — awaits `pywebviewready`, returns typed `PyWebViewApi`; `getApi()` — returns singleton |
| `utils/events.ts` | `listenEvent(name, handler)` — typed CustomEvent listener with cleanup return |
| `utils/crypto.ts` | AES-256-GCM + PBKDF2 encryption (migrated from `js/utils.js`) |
| `stores/config.ts` | Pinia configStore: `get(path)`, `set(path, value)`, `save()`, `reload()`. Single source of truth, replaces old ConfigManager.configCache |
| `stores/modal.ts` | Pinia modalStore: `create()`, `remove()`, `updateProgress()`, `addLog()`, `setStatus()`, `minimize()`, `restore()`. Registers Event listeners for Python → Vue push |
| `stores/log.ts` | Pinia logStore: `add(message, level)`, `clear()`. Max 500 entries |
| `stores/theme.ts` | Pinia themeStore: `switchTheme('light'|'dark'|'purple')`, persists to localStorage |
| `stores/update.ts` | Pinia updateStore: `check()`, `perform(modalId)` |

### `src/components/` — Shared Components

| File | Purpose |
|------|---------|
| `AppSidebar.vue` | Navigation sidebar: 3 nav groups (常用工具/管理配置/系统), ThemeToggle, minimized modals |
| `ThemeToggle.vue` | 3-theme button group (light/dark/purple) |
| `ModalContainer.vue` | Teleports to body, renders `v-for="modalStore.activeModals"` |
| `ModalWindow.vue` | Modal with ProgressBar, LogPanel, cancel/pause/resume/confirm actions |
| `ProgressBar.vue` | Animated progress bar (percent + text) |
| `HelpDrawer.vue` | Side drawer with 3 tabs (页面帮助/使用指南/常见问题), renders markdown via `marked` |
| `DragOverlay.vue` | Glass-morph drag-and-drop overlay |

### `src/views/` — 18 Route Pages

| View | Route | Feature |
|------|-------|---------|
| `Dashboard.vue` | `/` | 4 status cards (汉化包/启动器/更新/API) + quick actions |
| `Translate.vue` | `/translate` | LLM translation config + start |
| `Download.vue` | `/download` | OurPlay/零协会/LCTA/Bubble download cards |
| `Install.vue` | `/install` | Package directory picker + package list + install/delete |
| `Fancy.vue` | `/fancy` | Text beautification ruleset toggle + apply |
| `Cdn.vue` | `/cdn` | Cloudflare/CloudFront CDN optimization |
| `Speed.vue` | `/speed` | Game speed disclaimer gate + inject/eject + slider |
| `Manage.vue` | `/manage` | Installed packages + mods toggle/delete |
| `LauncherConfig.vue` | `/launcher` | Launcher mode settings (update, CDN, mods, steam) |
| `ApiConfig.vue` | `/config` | API service selector + dynamic settings form + test |
| `Proper.vue` | `/proper` | Proper noun fetch config + start |
| `Log.vue` | `/log` | Scrollable log viewer from logStore |
| `Settings.vue` | `/settings` | Global config: game path, debug, update, cache, storage |
| `About.vue` | `/about` | README + update notes + help markdown |
| `Welcome.vue` | `/welcome` | First-use welcome page + entry buttons |
| `Elder.vue` | `/elder` | Setup wizard navigation |
| `Test.vue` | `/test` | Debug page (placeholder) |
| `Clean.vue` | `/clean` | Cache cleanup options + execute |

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
