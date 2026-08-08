# LCTA Development Guide

<!-- Last updated: 2026-08-08 -->

## How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# WebUI mode (full desktop app)
python start_webui.py

# Launcher mode (game launcher only)
python start_webui.py -launcher
```

> pythonnet 引导:所有入口(`start_webui.py` / launcher 模块 / `scripts/test_environment.py`)统一经 `webutils/clr_bootstrap.py::ensure_clr()` 以 netfx 运行时导入 clr。依赖版本已在 `requirements.txt` 固定(`pythonnet==3.0.5`, `clr_loader==0.2.10`, `pywebview==6.2.1`),请勿随意升级 clr_loader(0.2.8 以下存在 netfx 加载缺陷)。若 `import clr` 失败,错误信息会包含真实异常与修复指引,不会再自动回退 coreclr/mono。

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

### Cheat Core（作弊工具箱）构建

伤害倍率实现位于私有仓库 `LCTA_CheatingCore`（公共仓库根目录克隆或 `.build_cache/cheat_core` 预克隆，缺失时构建**跳过**该功能）。构建步骤（`build.ps1` 与 `.github/workflows/release.yml` 同步）：

1. 扫描 `hooks/*.c` 逐个 gcc 编译同名 DLL（含 `vendor/minhook/`，缓存键含 minhook 源码；新增作弊工具自动编译）
2. `python scripts/cheat_encrypt.py build --src <clone> --key <clone>/keys/current.txt --out cheat_core.bin`
3. 复制到三个产物 `code/cheat_core/cheat_core.bin`

CI 通过 `secrets.LCTA_CHEAT_TOKEN`（PAT）克隆私有仓库。本地开发无需构建 blob：运行时加载器自动检测仓库根 `LCTA_CheatingCore/` 克隆（或 `LCTA_CHEAT_DEV_SRC` 环境变量），免密钥直连源码；开发前先运行 `LCTA_CheatingCore\hooks\build.ps1` 编译 DLL。密钥轮换见私有仓库 README。

## How to Test

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_config.py

# Run text-beautification engine coverage
pytest tests/test_fancy_conditions.py tests/test_fancy_v2.py tests/test_fancy_performance.py

# Run LLM text-beautification coverage
pytest tests/test_llm_fancy.py

# Run official-resource updater coverage
pytest tests/test_resource_updater.py

# Run CheatCore 密钥门/加密分发测试（工具箱实现测试已迁往私有仓库 LCTA_CheatingCore）
pytest tests/test_cheat_core.py
```

Key test files: `tests/test_config.py`, `tests/test_translate.py`, `tests/test_webui.py`, `tests/test_validator.py`, `tests/test_fancy_conditions.py`, `tests/test_fancy_v2.py`, `tests/test_fancy_performance.py`, `tests/test_llm_fancy.py`, `tests/test_resource_updater.py`, `tests/test_input_bypass.py`, `tests/test_cheat_core.py`

> 作弊工具箱管理器测试（`tests/test_cheat_damage_hook.py`）已随实现迁往私有仓库，在私有仓库内运行 `pytest tests/`（需要 Windows）。公共仓库侧 `tests/test_cheat_core.py` 覆盖加密/解密/解锁/锁定全链路（纯逻辑，跨平台）。

## Project Conventions

- **Module naming**: Feature modules in `webutils/` use `function_<feature>.py` pattern
- **Config access**: Always use `ConfigManager.get("dotted.path")`, never read `config.json` directly
- **Logging**: Use `LogManager` singleton, not `print()` or root `logging`
- **Bridge pattern**: New JS-accessible methods go in the `LCTA_API` feature-domain mixin under `webui/app_api/`（按方法归属选 `core.py`/`config.py`/`translation.py`/`packages.py`/`download.py`/`fancy.py`/`windows.py`/`cdn.py`/`speed.py`/`update.py`/`drops.py`/`resources.py`）; `webui/app.py` 只组装 `LCTA_API(CoreMixin, ...)` 与 `main()`。pywebview 通过 `dir()` 暴露继承方法，JS 调用方式不变（`pywebview.api.<method>()`）。注意：mixin 模块各自持有可能被测试 `@patch` 的模块级名字（如 `clean_config_main`、`ConfigManager`），patch 目标需写 `webui.app_api.<模块>`
- **Public API**: New webutils functions must be exported in `webutils/__init__.py`
- **Launcher license scope**: `launcher/` is GPL-3.0-licensed, but its Python modules currently reuse shared `webutils/`, `webFunc/`, and `globalManagers/` code; do not assume import isolation
- **Official resource state**: Launcher uses the local SHA-256 of `LimbusCompany.exe`; fingerprints and token-scoped download caches live under `%LOCALAPPDATA%/LCTA/resource-updater/`, not the packaged code directory
- **Official resource logging**: Backend resource-update diagnostics must go through the `LogManager` singleton; the updater page shows task status/progress but does not maintain a separate UI log card
- **Official resource UI**: Keep the manual updater inside the main SPA (`sections/resource-updater.html` + `js/resource-updater.js`); `LCTA_API` delegates prefixed bridge calls to the shared `ResourceUpdaterAPI`. The auto-download switch is configured on the Launcher page only (see AGENTS.md Launcher 集成规范); the updater page reads `launcher.resource_update.enabled` from the config cache and only shows an integration intro + jump button. Retry settings (`retry_max`/`retry_delay`/`connection_limit`) are configured on the updater page; a persisted last-result panel offers a 「重试失败项」 button that re-runs the update while already-downloaded files are skipped
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
3. Add API methods in the matching `LCTA_API` mixin under `webui/app_api/`（核心管道/配置/翻译/汉化包下载等按域选择；窗口类桥接见 `webui/*_api.py`）
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

Follow existing modal pattern in `webui/app_api/`（`CoreMixin` 提供 `add_modal_log`/`update_modal_progress`/`check_modal_running` 等全套）：Python method starts operation → creates modal → callback chain updates progress → modal closes on completion.

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
