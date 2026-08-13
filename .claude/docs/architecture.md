# LCTA Architecture Overview

<!-- Last updated: 2026-08-13 -->

## Project Purpose

LCTA (Limbus Company Transfer Auto / 边狱公司工具箱) is a comprehensive desktop toolkit for the game *Limbus Company*. Core feature: **Chinese localization/translation management** with automatic LLM-based translation updates. Also provides CDN optimization (with cache TTL to avoid redundant speed tests), an integrated game launcher with mod support, official localize/AssetBundle pre-download, 调爪 text modification package download/import, manual update from local zip, input bypass (CommonLib input count anti-detection via RawInput hook DLL + shared memory), **Metadata 恢复**（IL2CPP global-metadata.dat 解密参数自动恢复：IDA 定位器插件一键安装 + 离线四阶段流水线 extract/verify/solve/apply，输出可直接供修复版 Il2CppDumper 消费的正式 profile，移植自私有仓库 LimbusMetadataRecovery）, and various game optimization tools. **FMOD bank 音频工具**：bank 解包/重打包、.rebank fsb 补丁模组导出与转换、启动期自动补丁（哈希缓存，未变更直接复用），FMOD/FSBANK DLL 缺失时可一键自动下载（官方 GitHub release，`ui_default.bank.dll_url` 可覆盖，安装至 `%LOCALAPPDATA%/LCTA/fmod-dlls`）。 Damage multiplier (MinHook detour on GameAssembly.dll with API-fetched offsets + hash-anchored caching and auto-invalidation) is **gated behind a decryption key**: implementation lives in the private repo `LCTA_CheatingCore`, XOR-encrypted into `cheat_core/cheat_core.bin` at build time, and only decrypted/loaded at runtime after the user enters the key (recoverable via known-plaintext analysis — a friction gate, not real crypto). Version 5.0.3, MIT-licensed (launcher/ is GPL-3.0).

## Tech Stack

| Language | Layer | Notes |
|----------|-------|-------|
| Python 3.9.6+ | Backend (primary) | Business logic, translation engine, webview bridge |
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
│  webui/app.py            LCTA_API 组装壳 + main (pywebview)  │
│  webui/app_api/*.py      LCTA_API 功能域 mixin（core/config/  │
│                          packages/download/fancy/windows/    │
│                          cdn/speed/update/drops/resources）  │
│  webui/index.html + js/  frontend SPA                │
│  launcher/main.py        CLI launcher entry point    │
├─────────────────────────────────────────────────────┤
│                  BUSINESS LOGIC                      │
│  webutils/__init__.py    public API aggregation      │
│  webutils/function_*.py  feature modules             │
│  webutils/update.py      self-update via GitHub API;   │
│                          GUI-first dependency install, │
│                          Tsinghua network fallback,    │
│                          non-network failures pending  │
│                          (globalManagers/pending_pip_ops│
│                          .py 纯 stdlib，零第三方导入)   │
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
│  globalManagers/          ConfigManager, LogManager,    │
│                           pending_pip_ops (纯 stdlib)    │
│  tools/cfst/            CloudflareSpeedTest binary │
├─────────────────────────────────────────────────────┤
│               EXTERNAL TOOLS                         │
│  translatekit  openspeedy  UnityPy  pywebview  etcpak│
└─────────────────────────────────────────────────────┘
```

## The 7 Source Directories

| Directory | Role |
|-----------|------|
| `webui/` | Frontend: pywebview desktop window + HTML/CSS/JS SPA |
| `webutils/` | Business logic: one `function_*.py` per feature, all exported via `__init__.py` |
| `webFunc/` | Infrastructure: GitHub downloads, file transfer, Lanzou parsing, web notes |
| `translateFunc/` | Translation engine: multi-stage LLM pipeline with proper noun matching |
| `globalManagers/` | Cross-cutting singletons: `ConfigManager.py`, `LogManager.py`；`pending_pip_ops.py` — 延迟依赖安装（纯标准库模块，启动早期钩子在导入任何第三方库之前重试 GUI 阶段因非网络原因失败的安装；更新永久保留废弃依赖，不执行 pip uninstall） |
| `launcher/` | Standalone game launcher (GPL-3.0): mod patching, updates, CDN, speed hotkey, and an optional WinForms launch center with configuration summary, vertical phase tracking, overall/stage progress, expandable logs, runtime PID/uptime, and cancellation controls |
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
| **Cache + Auto-Invalidation** | 私有仓库 `cheatcore/cheat_damage_hook.py` | Damage-hook offsets fetched from a JSON API are cached locally keyed by the local `GameAssembly.dll` SHA-256; a game update (hash change) invalidates the cache and auto-refetches at start/apply time. The C DLL's runtime 16-byte prologue check is the backstop: on `verified=0` the recovery is **manually** triggered (WebUI「立即刷新偏移」/ relaunch) → force refresh + `retry_requested` hot reinstall without restarting the game (auto-detection loop not implemented) |
| **Key Gate + Plugin Auto-Register** | `webutils/cheat_core.py` + `webutils/cheat_plugins.py` + `webui/js/cheat-shell.js` | 作弊工具箱实现全部位于私有仓库，构建期加密为 `cheat_core.bin` 分发。运行期用户输入密钥 → 校验解密 → 释放到 `%LOCALAPPDATA%/LCTA/cheat-core/` → 动态导入 `cheatcore` 包；解锁后 `CheatPluginHost.reload()` 读私有仓库 `cheatcore/registry.py` 的插件描述符自动注册（api 白名单 / 配置 schema 播种 / Launcher 生命周期 / 前端文件），主仓库不感知具体工具。密钥可经已知明文碰撞恢复（门槛而非加密，见私有仓库 README）。未解锁时宿主无插件注册，invoke/生命周期安全短路。开发模式：仓库根 `LCTA_CheatingCore/` 克隆或 `LCTA_CHEAT_DEV_SRC` 环境变量免密钥直连。Launcher 集成开关由 `renderLauncherPlugins()` 动态渲染进 `#cheat-plugin-launcher`：渲染前先 `cheat_core_status()` 触发 `ensure_unlocked()`（保证持久化密钥会话无需先开作弊页插件即已注册），并把 `enabled_key` 经 `configManager.registerConfigKey()` 动态登记进前端 `configKeyMap`（见 AGENTS「作弊工具箱 Launcher 集成动态配置规范」） |
| **Pipeline** | `launcher/pipeline.py` | `LaunchPipeline` — phase-based event-driven pipeline (init→check_update→resource_update→cdn→prepare_mod→launch→running→exit). Modules register callbacks per phase via `on(phase, callback)`; `cancel_event` supports GUI-initiated shutdown.
| **Fingerprint Gate** | `resource_updater/service.py` | Local SHA-256 of `LimbusCompany.exe` gates Launcher pre-download without an online version check; successful resource scopes are persisted and merged so partial manual runs do not suppress missing work. `record_update_result()` marks only fully completed scopes — failed scopes stay unmarked and re-run on the next launch — and persists the last result (counts + failed item names/reasons) for the manual page |
| **Registry + Interface** | `webutils/drop/` | `DropFileHandler` 接口（检测 + 执行 + 显示名收敛于单类）; `DropFileHandlerRegistry` 按容器类型（zip/folder/json/path）有序检测、按类型分派执行，兜底 `invalid` |

## Key Interfaces

| Interface | File | Role |
|-----------|------|------|
| `LCTA_API` | `webui/app.py`（组装壳）+ `webui/app_api/*.py`（mixin） | Central hub: assembles the feature-domain mixins (`CoreMixin`/`ConfigMixin`/`TranslatorMixin`/`PackagesMixin`/`DownloadMixin`/`FancyMixin`/`WindowMixin`/`CdnMixin`/`SpeedMixin`/`UpdateMixin`/`DropMixin`/`ResourceMixin`/`MetadataRecoveryMixin`/`CgMixin`/`BankMixin`), bridges backend features to the SPA, owns the main-window `ResourceUpdaterAPI`, includes `get_startup_data()` for consolidated frontend init, opens editor windows with theme injection, and handles redesigned drag-drop file flows |
| `RuleEditorAPI` | `webui/rule_editor_api.py` | Secondary pywebview bridge for the rule editor window: wraps `webutils/rule_editor/` methods (file browser, rules CRUD, rule building, validation, smart analysis), plus `get_config_value()` for cross-window config queries (e.g. theme). Instantiated as `js_api=RuleEditorAPI()` in a separate `webview.create_window()` call |
| `QuickEditorAPI` | `webui/quick_editor_api.py` | Pywebview bridge for the quick editor window: wraps `webutils/rule_editor/quick.py` methods (diff_json, load/save/apply_quick_edits) plus shared methods from `webutils/rule_editor/browser.py` (file browser, search). Instantiated as `js_api=QuickEditorAPI()` in `open_quick_editor()` |
| `LLMFancyAPI` | `webui/llm_fancy_api.py` | Pywebview bridge for the LLM 文本美化 window: wraps `webutils/llm_fancy/` (selection scan preview, exclusion-ruleset simulation, batched LLM beautification with progress/log callbacks and cancel, ruleset build/save/auto-enable) plus config persistence (`ui_default.llm_fancy`). Instantiated as `js_api=LLMFancyAPI()` in `LCTA_API.open_llm_fancy()` |
| `Aria2DownloaderAPI` | `webui/aria2_downloader_api.py` | Pywebview bridge for the 泛用高速下载器 window: wraps the module-level singleton `webutils/function_aria2_downloader.py aria2_manager` (aria2c server start/stop, URL/magnet batch add, .torrent add, pause/resume/remove, global pause/resume/purge, folder/torrent pickers, config persistence under `ui_default.aria2_dl`). Background 1s poll pushes task snapshots to `window.__aria2DlDispatch`. Instantiated as `js_api=Aria2DownloaderAPI()` in `LCTA_API.open_aria2_downloader()`; window close stops the aria2c child process |
| `ResourceUpdaterAPI` | `resource_updater/web_api.py` | Resource-update controller owned by `LCTA_API`. Probes game files, persists updater options (incl. retry settings), runs/cancels the worker thread, records results, exposes the last update result (failure list for the manual retry button), and emits per-channel progress into the main SPA's `resource-updater.js` controller |
| `ResourceUpdater` | `resource_updater/core.py` | Extracts S/L CDN tokens, downloads token-scoped localize ZIPs, parses remote/fallback catalog data, populates Unity cache entries, and selects bundled aria2c or the built-in downloader. Transient download failures auto-retry with `retry_max`/`retry_delay` backoff; exhausted retries emit a Range probe with diagnostic headers; aria2 uses a per-file connection limit |
| `ConfigManager` | `globalManagers/ConfigManager.py` | Singleton config with dotted-path access, validation, auto-save |
| `TranslationPipeline` | `translateFunc/pipeline.py` | Orchestrates the 6-stage LLM translation pipeline |
| `CompiledRules` / `ApplyResult` | `webutils/fancy/engine.py` | Immutable compiled beautification rules plus per-file changed-path results; exposes `requires_skill_color` so resource extraction is prepared only when an enabled rule needs it |
| `CompiledBus` / `BusApplyResult` | `webutils/fancy/bus.py` | Immutable bus rules with precomputed exact/dynamic file indexes, deduplicated shared matchers, per-ruleset directory exclusions, selector indexes, ordered path execution, exact quick-edit success/failure counts, and changed-path reporting |
| `FancyRunStats` | `webutils/function_fancy.py` | Reports scanned, matched and changed files/values, elapsed time, and skill-color resource cache hits; files are rewritten atomically only when content changes |
| `DropFileHandler` / `DropFileHandlerRegistry` | `webutils/drop/handler.py` | 接口：每个分支类实现 `detect()`（快照/路径 → 类型字符串）与 `execute()`（上下文 → 结果键），声明 `file_type`/`label`; 注册表维护各容器类型的检测顺序（如 zip: full → nofont → FLmod → update → jsononly），并按类型查处理器执行，无需改动 `evalFile()` / `evalFiles()` 即可扩展新分支 |
| `BankMixin` | `webui/app_api/bank.py` | 音频工具桥接：`bank_*`（dll_status/set_dll_dir/download_dlls/get_game_banks/info/extract/rebuild/export_rebank/convert_mod/patch_full/rebank_info）逐条转发 `webutils/function_bank.py` → `webutils/bank/` 工具链（`FmodDlls` ctypes 封装 FMOD/FSBANK DLL：FSB→WAV 解码、WAV→FSB 编码 vorbis/pcm/fadpcm，bank 容器纯 Python 解析/重组，.rebank 差分导出/补丁）；`bank_download_dlls` 经 `GithubDownload.GithubRequester`（惰性单例，启动期 `init_request` 初始化）自动下载官方 `Fmod_Bank_Tools.zip` 并解压 DLL；启动期由 `launcher/bankmod.py apply_rebanks` 消费同一 `patch_banks`（哈希缓存） |
| `RiskGate` / `RISK_SERVICES` | `webui/js/risk-gate.js` | 前端风险服务统一门控（游戏加速/输入反检测/作弊工具箱）：注册表驱动，规范化免责声明文本单一来源；源页面首入覆盖层门控（`gatePage`）、Launcher 配置页勾选就地同意弹窗（`gateLauncherSection`）、同意态持久化 `{service}.disclaimer_accepted`、重读入口（`showNoticeModal`）。`hideUntilConsent` 标记的服务（作弊工具箱）未同意前在 Launcher 配置页整组隐藏（`refreshLauncherVisibility`，进入页面与 `acceptConsent` 时刷新），须先在源页面同意；Launcher 后端 `start_cheat_plugins` 经插件注册表同款检查 consent 兜底。工具箱的 Launcher 集成开关由 `cheat-shell.js` 按插件注册表动态渲染进 `#cheat-plugin-launcher`（渲染前先触发 `cheat_core_status` 自动解锁；配置键经 `configManager.registerConfigKey` 动态登记，见 AGENTS「作弊工具箱 Launcher 集成动态配置规范」）。新增风险服务只需注册一条记录 + 两个标记属性 |
| `LogManager` | `globalManagers/LogManager.py` | Singleton logger: file rotation, console, webview modal callbacks |

## Polyglot Boundaries

- **Python ↔ JS**: `pywebview` exposes `LCTA_API` instance as `window.pywebview.api` in JS. JS calls Python methods, Python calls JS via `webview.windows[0].evaluate_js()`
- **HTML <> JS**: Section HTML fragments in `webui/sections/*.html` are lazy-loaded by `preload.js` via `loadSection()` on first navigation; `onSectionLoaded()` callback re-runs per-section initialization (config, tooltips, toggle funcs, list manager DOM refs, select box values). Markdown assets loaded on-demand with fetch-caching via `_loadedMarkdowns`; welcome content deferred via `_pendingWelcomeContent`
- **C → Python**: Native `launcher.c` compiled with `-mwindows` (GUI subsystem, no console). Python process always started with `CREATE_NO_WINDOW`; stdout/stderr captured via pipe. If Python exits with non-zero code, C layer allocates an error console to display captured output. Console management (AllocConsole for legacy mode, GUI window for gui_mode) handled by `start_webui.py` before importing launcher modules.
- **Python → C binaries**: Subprocess calls to `tools/cfst/cfst.exe` (CloudflareSpeedTest), `tools/aria2/aria2c.exe` (official resource downloads), and `7zr.exe` (7-Zip, stored in `tools/7z/`)

## External Binaries

| Binary | Source | Purpose |
|--------|--------|---------|
| `cfst.exe` v2.3.5 | Bundled in `tools/cfst/` | Cloudflare CDN speed testing |
| `aria2c.exe` v1.37.0 | Downloaded during build into `tools/aria2/` | Multi-connection localize and AssetBundle downloads through localhost JSON-RPC; built-in urllib fallback remains available |
| `7zr.exe` | Downloaded at runtime from 7-zip.org into `tools/7z/` | Archive extraction |
| Embedded Python 3.9.6 | Downloaded during build | Bundled into release packages |
| `openspeedy` DLL | pip package | DLL injection for game speed acceleration |
