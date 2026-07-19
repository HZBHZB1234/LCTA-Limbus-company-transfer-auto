# LCTA Architecture Overview

<!-- Last updated: 2026-07-19 -->

## Project Purpose

LCTA (Limbus Company Transfer Auto / 边狱公司工具箱) is a comprehensive desktop toolkit for the game *Limbus Company*. Core feature: **Chinese localization/translation management** with automatic LLM-based translation updates. Also provides CDN optimization (with cache TTL to avoid redundant speed tests), an integrated game launcher with mod support, bubble language pack download, manual update from local zip, and various game optimization tools. Version 5.0.0, MIT-licensed (launcher/ is GPL-3.0).

## Tech Stack

| Language | Layer | Notes |
|----------|-------|-------|
| Python 3.9.6+ | Backend (primary) | Business logic, translation engine, webview bridge |
| C (MinGW-w64) | Native launcher | `launcher.c` → compiled to .exe as PE entry point for packaged releases |
| TypeScript (Vue 3) | Frontend | 48 SFC components in `webui/src/`, Pinia stores, bridges to Python via `pywebview.api` (typed) + CustomEvent |
| CSS (Scoped) | Frontend | Vue `<style scoped>` per component, CSS custom properties for 3 themes |
| PowerShell | Build system | `build.ps1`, 7-step build pipeline (added Vite build step) |
| YAML | CI/CD | GitHub Actions: `release.yml`, `check.yml` |

## Layered Architecture

```
┌─────────────────────────────────────────────────────┐
│                   PRESENTATION                       │
│  start_webui.py          dispatcher (WebUI/Launcher) │
│  webui/app.py            LCTA_API class (pywebview)  │
│  webui/src/              Vue 3 SPA (Vite-built)      │
│  launcher/main.py        CLI launcher entry point    │
├─────────────────────────────────────────────────────┤
│                  BUSINESS LOGIC                      │
│  webutils/__init__.py    public API aggregation      │
│  webutils/function_*.py  feature modules (24 files)  │
│  webutils/update.py      self-update via GitHub API  │
│  webutils/load.py        config loading/validation   │
├─────────────────────────────────────────────────────┤
│                DOMAIN ENGINES                        │
│  translateFunc/           LLM translation pipeline   │
│    pipeline.py            orchestration              │
│    processor.py           per-file logic             │
│    workers.py             concurrency                │
│    builder/               prompt & request building  │
│    matcher/               proper noun AC matching    │
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

## The 6 Source Directories

| Directory | Role |
|-----------|------|
| `webui/` | Frontend: Vue 3 + TypeScript + Vite SPA, Pinia stores, scoped CSS |
| `webutils/` | Business logic: one `function_*.py` per feature, all exported via `__init__.py` |
| `webFunc/` | Infrastructure: GitHub downloads, file transfer, Lanzou parsing, web notes |
| `translateFunc/` | Translation engine: multi-stage LLM pipeline with proper noun matching |
| `globalManagers/` | Cross-cutting singletons: `ConfigManager.py`, `LogManager.py` |
| `launcher/` | Standalone game launcher (GPL-3.0): mod patching, updates, CDN, speed hotkey, optional WinForms GUI progress window |

## Design Patterns

| Pattern | Where | Concrete Example |
|---------|-------|-----------------|
| **Singleton** | `globalManagers/` | `ConfigManager` — thread-safe, lazy-init, dotted-path access. `LogManager` — async UI callbacks via thread pool |
| **Bridge** | `webui/app.py` ↔ Vue | `LCTA_API` class exposes Python methods to JS via `pywebview.api`; JS calls via typed `getApi().xxx()`. Python pushes to Vue via `self._emit('lcta:*')` → `CustomEvent` → Pinia stores |
| **Pipeline** | `translateFunc/pipeline.py` | `TranslationPipeline` orchestrates: fetch proper nouns → build matcher → priority files → WorkerPool → aggregate |
| **Factory** | `launcher/updates.py` | Update objects for LLC, OurPlay, Machine translation — each implements a common interface |
| **Observer/Callback** | `globalManagers/LogManager.py` → `webui/app.py` → Vue | Real-time log/progress/status via Event Bridge through Pinia modalStore |

## Key Interfaces

| Interface | File | Role |
|-----------|------|------|
| `LCTA_API` | `webui/app.py` | Central hub: ~1490 lines, bridges all backend features to Vue frontend via `pywebview.api` + `_emit()` Event Bridge. Includes `get_startup_data()` for consolidated frontend init, auto-detects dev environment (dist/ exists → production; missing → Vite dev server) |
| `ConfigManager` | `globalManagers/ConfigManager.py` | Singleton config with dotted-path access, validation, auto-save |
| `TranslationPipeline` | `translateFunc/pipeline.py` | Orchestrates the 6-stage LLM translation pipeline |
| `LogManager` | `globalManagers/LogManager.py` | Singleton logger: file rotation, console, webview modal callbacks |

## Polyglot Boundaries

- **Python ↔ Vue**: `pywebview` exposes `LCTA_API` instance as `window.pywebview.api`. Vue calls Python via typed `getApi()` (from `src/utils/api.ts`). Python pushes to Vue via `self._emit('lcta:event', {detail})` → `window.dispatchEvent(CustomEvent)` → Pinia stores react.
- **Vue SPA**: `src/main.ts` bootstraps: await `initApi()` → `get_startup_data()` → `configStore.init()` → `createApp(App).use(pinia).use(router).mount('#app')`. Vue Router with hash mode, all 18 routes lazy-loaded via `import()`.
- **C → Python**: Native `launcher.c` compiled with `-mwindows` (no console). Embeds Python interpreter path, verifies hash, runs Python script. Avoids console window on double-click.
- **Python → C binaries**: Subprocess calls to `CFST/cfst.exe` (CloudflareSpeedTest) and `7z.exe` (7-Zip)

## External Binaries

| Binary | Source | Purpose |
|--------|--------|---------|
| `cfst.exe` v2.3.5 | Bundled in `CFST/` | Cloudflare CDN speed testing |
| `7z.exe` | Downloaded at runtime | Archive extraction |
| Embedded Python 3.9.6 | Downloaded during build | Bundled into release packages |
| `openspeedy` DLL | pip package | DLL injection for game speed acceleration |
