# LCTA Development Guide

<!-- Last updated: 2026-07-19 -->

## How to Run

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies (first time / after package.json changes)
cd webui && npm install

# Development mode (with Vite HMR)
# Terminal 1: start Vite dev server
cd webui && npm run dev

# Terminal 2: start pywebview (auto-detects dev environment)
python start_webui.py

# Production mode (requires Vite build first)
cd webui && npm run build
python start_webui.py

# Launcher mode (game launcher only)
python start_webui.py -launcher
```

## How to Build

```powershell
.\build.ps1
```

7-step pipeline: InitCode → **Vite build (1.5)** → C compilation (MinGW-w64) → embedded Python → dist assembly → update package clean → ZIP packaging.

Outputs:
- `LCTA-Portable-Full.zip` — normal release
- `LCTA-Portable-Full-Compatible.zip` — compatible release
- `LCTA-update.zip` — source update package

Requirements: PowerShell 5.0+, Node.js 20+, MinGW-w64 (optional, skips if unavailable), Python 3.9.6, network.

## How to Test

```bash
# Run Python backend tests
pytest tests/

# Run specific test file
pytest tests/test_config.py

# Run frontend unit tests (Vitest)
cd webui && npm run test

# Run frontend tests in watch mode
cd webui && npm run test:watch
```

Key test files: `tests/test_config.py`, `tests/test_translate.py`, `tests/test_webui.py`  
Frontend tests: `webui/src/utils/__tests__/`, `webui/src/stores/__tests__/`

## Project Conventions

- **Module naming**: Feature modules in `webutils/` use `function_<feature>.py` pattern
- **Config access**: Always use `ConfigManager.get("dotted.path")`, never read `config.json` directly
- **Logging**: Use `LogManager` singleton, not `print()` or root `logging`
- **Bridge pattern**: New JS-accessible methods go in `webui/app.py` `LCTA_API` class; JS calls via `pywebview.api.<method>()`
- **Public API**: New webutils functions must be exported in `webutils/__init__.py`
- **GPL boundary**: `launcher/` and main app share NO imports — only config.json and CLI invocation

## Common Development Patterns

### Adding a New Feature Module

1. Create `webutils/function_<newfeature>.py` with the feature logic
2. Export public functions in `webutils/__init__.py`
3. Add API methods in `webui/app.py` `LCTA_API` class
4. Create Vue view component `webui/src/views/<NewFeature>.vue`
5. Add route entry in `webui/src/router.ts`: `{ path: '/newfeature', component: () => import('./views/NewFeature.vue') }`
6. Add sidebar nav entry in `webui/src/components/AppSidebar.vue`
7. Create guide page `webui/guide/<newfeature>.md`
8. If it has config items, update `config_default.json` and `config_check.json`

### Python → Vue Communication

Use the Event Bridge pattern:
```python
# Python side (app.py)
self._emit('lcta:event-name', {'key': 'value'})
```
```typescript
// Vue side (Pinia store or component)
import { listenEvent } from '@/utils/events'
listenEvent('lcta:event-name', (detail) => { /* handle */ })
```

### Adding a New Config Item

1. Add default value to `config_default.json`
2. Add type entry to `config_check.json`
3. If it needs a tooltip, follow `prompts/tooltip.md`
4. UI reads via `configStore.get('path.to.key')` (typed)

### Adding a New Modal Operation

Follow existing modal pattern: Vue component calls `modalStore.create()` → registers modalId with Python → Python emits `lcta:modal-progress`/`lcta:modal-log` events → Pinia modalStore reacts → ModalWindow renders.

## Debugging

- **Frontend HMR**: Run `cd webui && npm run dev` → Vite dev server at `localhost:5173`. `python start_webui.py` auto-detects dev environment and loads from Vite.
- **Frontend type check**: `cd webui && npx vue-tsc --noEmit` (also runs in `npm run build`)
- **Frontend lint**: `cd webui && npx eslint src/` (also runs in `npm run build`)
- **Debug flag**: `python start_webui.py --debug` enables verbose logging
- **Console output**: Check terminal for `LogManager` output
- **Log files**: Check `logs/` directory for timestamped log files
- **Frontend errors**: Check pywebview console (right-click → inspect or devtools)
- **Environment diagnostic**: `python webutils/debug_environ_test.py` for startup issues

## CI/CD

| Workflow | File | Trigger |
|----------|------|---------|
| Build & Release | `.github/workflows/release.yml` | Push to `main`, git tag `v*` |
| Scheduled Check | `.github/workflows/check.yml` | Scheduled cron |

Release workflow: windows-latest runner, MSYS2/MinGW-w64 for C compilation, mirrors `build.ps1` logic.

## Key Constraints

- **Python 3.9.6** exactly for embedded Python packaging (build.ps1 downloads this version)
- **Windows only** — uses Win32 API, pywebview, MSYS2
- **`build.ps1` MUST be UTF-8 with BOM** (PowerShell requirement for Chinese text)
- **Build/release sync** — changes to gcc flags or C structure must update BOTH `build.ps1` AND `.github/workflows/release.yml`
- **Node.js 20+** required for frontend build and development
- **etcpak==0.9.8 pinned** — version 0.9.9 crashes
- **GPL-3.0 isolation** — `launcher/` is import-isolated from MIT-licensed main code
