# LCTA Development Guide

<!-- Last updated: 2026-08-05 -->

## How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# WebUI mode (full desktop app)
python start_webui.py

# Launcher mode (game launcher only)
python start_webui.py -launcher
```

## How to Build

```powershell
.\build.ps1
```

6-step pipeline: InitCode + pinned aria2c acquisition → C compilation (MinGW-w64) → embedded Python → dist assembly → update package clean → ZIP packaging.

Outputs:
- `LCTA-Portable-Full.zip` — normal release
- `LCTA-Portable-Full-Compatible.zip` — compatible release
- `LCTA-update.zip` — source update package

Requirements: PowerShell 5.0+, MinGW-w64 (optional, skips if unavailable), Python 3.9.6, network.

The build downloads aria2 1.37.0 from the official GitHub release, retries and rejects undersized responses, then places `aria2c.exe` (and `COPYING` when present) under `tools/aria2/` in all three artifacts. Runtime `engine=auto` falls back to urllib when aria2c is unavailable in a source checkout.

## How to Test

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_config.py

# Run text-beautification engine coverage
pytest tests/test_fancy_conditions.py tests/test_fancy_v2.py tests/test_fancy_performance.py

# Run official-resource updater coverage
pytest tests/test_resource_updater.py
```

Key test files: `tests/test_config.py`, `tests/test_translate.py`, `tests/test_webui.py`, `tests/test_validator.py`, `tests/test_fancy_conditions.py`, `tests/test_fancy_v2.py`, `tests/test_fancy_performance.py`, `tests/test_resource_updater.py`

## Project Conventions

- **Module naming**: Feature modules in `webutils/` use `function_<feature>.py` pattern
- **Config access**: Always use `ConfigManager.get("dotted.path")`, never read `config.json` directly
- **Logging**: Use `LogManager` singleton, not `print()` or root `logging`
- **Bridge pattern**: New JS-accessible methods go in `webui/app.py` `LCTA_API` class; JS calls via `pywebview.api.<method>()`
- **Public API**: New webutils functions must be exported in `webutils/__init__.py`
- **Launcher license scope**: `launcher/` is GPL-3.0-licensed, but its Python modules currently reuse shared `webutils/`, `webFunc/`, and `globalManagers/` code; do not assume import isolation
- **Official resource state**: Launcher uses the local SHA-256 of `LimbusCompany.exe`; fingerprints and token-scoped download caches live under `%LOCALAPPDATA%/LCTA/resource-updater/`, not the packaged code directory
- **Official resource logging**: Backend resource-update diagnostics must go through the `LogManager` singleton; the updater page shows task status/progress but does not maintain a separate UI log card
- **Official resource UI**: Keep the manual updater inside the main SPA (`sections/resource-updater.html` + `js/resource-updater.js`); `LCTA_API` delegates prefixed bridge calls to the shared `ResourceUpdaterAPI`
- **Knowledge-base maintenance**: Significant features, files, entry points, dependencies, or structural changes must update the relevant `.claude/docs/*.md` file and its `Last updated` date
- **Agent instruction source**: Edit `CLAUDE.md`, then synchronize the identical content to `AGENTS.md`

### Enabling Instruction Synchronization

```bash
git config core.hooksPath .githooks
```

The repository-local pre-commit hook copies `CLAUDE.md` to `AGENTS.md` and stages the result when they differ. `.github/workflows/check-sync.yml` independently verifies the same invariant on pull requests that change either file and can also be run manually.

## Common Development Patterns

### Adding a New Feature Module

1. Create `webutils/function_<newfeature>.py` with the feature logic
2. Export public functions in `webutils/__init__.py`
3. Add API methods in `webui/app.py` `LCTA_API` class
4. Create section HTML fragment `webui/sections/<newfeature>.html`
5. Add the section name to `preloadAllSections()` array in `webui/sections/preload.js`
6. Add a placeholder `<div>` in `webui/index.html` with id `<newfeature>-section`
7. Create guide page `webui/guide/<newfeature>.md`
8. Add JS logic in `webui/js/features.js` or a new `webui/js/<newfeature>.js`
9. If it has config items, update `config_default.json` and `config_check.json`

### Adding a New Config Item

1. Add default value to `config_default.json`
2. Add type entry to `config_check.json`
3. If it needs a tooltip, follow `prompts/tooltip.md`
4. UI reads via `ConfigManager.get("path.to.key")`

### Adding a New Modal Operation

Follow existing modal pattern in `webui/app.py`: Python method starts operation → creates modal → callback chain updates progress → modal closes on completion.

## Debugging

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
| Instruction Sync | `.github/workflows/check-sync.yml` | Pull requests changing `CLAUDE.md`/`AGENTS.md`, manual dispatch |

Release workflow: windows-latest runner, MSYS2/MinGW-w64 for C compilation, mirrors `build.ps1` logic.

## Key Constraints

- **Python 3.9.6** exactly for embedded Python packaging (build.ps1 downloads this version)
- **Windows only** — uses Win32 API, pywebview, MSYS2
- **`build.ps1` MUST be UTF-8 with BOM** (PowerShell requirement for Chinese text)
- **Build/release sync** — changes to gcc flags or C structure must update BOTH `build.ps1` AND `.github/workflows/release.yml`
- **Instruction-file sync** — `CLAUDE.md` and `AGENTS.md` must remain byte-for-byte identical; use the repository hook or copy manually before commit
- **etcpak==0.9.8 pinned** — version 0.9.9 crashes
- **aria2 1.37.0 pinned** — local and CI builds must keep the same official release URL, retry/size validation, and `tools/aria2/` artifact layout
- **GPL-3.0 launcher scope** — treat `launcher/` as separately licensed even though its Python implementation imports shared root modules
