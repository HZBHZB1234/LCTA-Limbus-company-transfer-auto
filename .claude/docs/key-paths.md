# LCTA Key Path Tracing

<!-- Last updated: 2026-08-06 -->


Feature-to-code call chain traces. Each section maps a user-visible feature to the exact files in execution order.

> 注：`webui/app.py` 为组装薄壳，`LCTA_API` 各方法实际定义在 `webui/app_api/` 对应功能域 mixin 中；`webui/app.py LCTA_API.xxx()` 的调用链描述仍然成立（方法经继承暴露，前端 JS 无感知）。

---

## 1. Translation Installation — LLC (零协会)

```
JS: user clicks install button
  → webui/js/features.js           click handler → pywebview.api.install_llc()
  → webui/app.py                   LCTA_API.install_llc()
  → webutils/function_llc.py       download & install LLC pack
    → webFunc/GithubDownload.py    fetch from GitHub Releases API
    → webutils/utils/io.py          zip extraction, 7z integration
  → webui/app.py                   callback: progress → JS modal update
```

## 2. Translation Installation — OurPlay

```
JS: user clicks install button (PC or Android source)
  → webui/app.py                   LCTA_API.install_ourplay() or .install_ourplay_new()
  → webutils/function_ourplay_pc.py   PC source download
    OR webutils/function_ourplay_android.py  Android source download
    → webFunc/GithubDownload.py    fetch from GitHub
    → webutils/utils/io.py         extract & apply
```

## 3. LLM Auto-Translation (核心功能)

```
JS: user configures & clicks translate
  → webui/app.py                   LCTA_API.translate()
  → webutils/function_translate.py orchestration entry
  → translateFunc/pipeline.py      TranslationPipeline.run()
    Stage 1: translateFunc/get_proper.py     fetch proper nouns from remote
    Stage 2: translateFunc/matcher/engine.py build AC automaton matcher
                                              load KR/JP/EN/CN effect names and use
                                              JP/EN entries to reject Korean substring false positives
    Stage 3: translateFunc/processor.py      process priority files first
    Stage 4: translateFunc/workers.py        WorkerPool concurrent translation
      → translateFunc/builder/prompt.py      construct LLM prompts
      → translateFunc/builder/request.py     build API requests; split by rendered
                                               input length
      → translateFunc/builder/stages.py      split Stage 0 disambiguation terms and
                                               Stage 2 source/translation pairs by
                                               rendered input length; prune per-part refs
      → translateFunc/translate_request.py   call LLM API, parse response
      → translateFunc/validator.py           rule-based post-processing (skill files only,
                                              controlled by enable_rule_validation config):
                                              validate [ID] bracket spacing → auto-fix
                                              validate effect refs from source → warning
      → translateFunc/processor.py           run split Stage 0 calls before translation;
                                               run split Stage 2 self-check calls and
                                               remap local correction IDs to global IDs
    Stage 5: translateFunc/matcher/engine.py post-translation proper matching
    Stage 6: translateFunc/pipeline.py       aggregate results → PipelineSummary
  → webutils/function_translate.py  write output files
  → webui/app.py                    callback: summary → JS modal
```

Files involved: `webui/app.py`, `webutils/function_translate.py`, `translateFunc/pipeline.py`, `translateFunc/config.py`, `translateFunc/processor.py`, `translateFunc/validator.py`, `translateFunc/workers.py`, `translateFunc/translate_request.py`, `translateFunc/get_proper.py`, `translateFunc/builder/prompt.py`, `translateFunc/builder/request.py`, `translateFunc/builder/stages.py`, `translateFunc/matcher/engine.py`, `translateFunc/matcher/ac_automaton.py`, `translateFunc/log_bridge.py`, `translateFunc/recorder.py`, `globalManagers/LogManager.py`

### 3b. Translation Dump Recording (转储过程记录)

When `ui_default.translator.dump` is enabled, each file's translation process is recorded to a separate JSONL file:

```
webutils/function_translate.py  sets config.dump_path → logs/translation_dump/{timestamp}.jsonl
  → translateFunc/pipeline.py   creates TranslationRecorder(config.dump_path)
  → translateFunc/processor.py  FileProcessor records each file's API calls
    → translateFunc/recorder.py TranslationRecorder.write_record() appends to JSONL
```

Each JSONL line contains: `timestamp`, `file_name`, `text_blocks` (actual input), `reference` (proper_terms/affects/models), `api_calls[]` (system_prompt, user_prompt, raw_response, parsed, status per stage), `outcome`, `elapsed_seconds`.

Log simplification: verbose data (raw LLM responses) is removed from `logs/app.log` and stored only in the dump JSONL file.

Files involved: `webutils/function_translate.py`, `translateFunc/recorder.py`, `translateFunc/pipeline.py`, `translateFunc/processor.py`, `translateFunc/config.py`

### 3c. Translation Diagnostic Viewer

```
Translation page: user clicks "查看翻译日志"
  → webui/app.py                           open_translation_log_viewer()
  → webui/translation-log-viewer.html      standalone pywebview window
  → user chooses one .jsonl in native file dialog
  → webui/js/translation-log-viewer.js     filters, pagination, detail, export
  → webui/app.py                           TranslationLogViewerAPI
  → webutils/function_translation_logs.py  v2 JSONL index/query/read/export
  → selected JSONL file                    read-only source
```

The viewer does not scan directories or provide content search. It only accepts the file explicitly selected by the user and requires current `schema_version: 2` JSONL records. Lists use cached summaries and byte offsets; full prompts, AI responses, HTTP details, and exception chains are loaded only when a record is opened.

---

## 4. CDN Optimization

```
JS: user clicks "test speed" or "optimize"
  → webui/js/cdn.js                UI logic, progress display
  → webui/app.py                   LCTA_API.cdn_test() / .cdn_optimize()
  → webutils/cdn/                  CDN logic (package)
    → subprocess: CFST/cfst.exe    CloudflareSpeedTest binary
    → parse: CFST/result_cf.csv    speed test results
    → modify: system hosts file    apply optimal CDN IP

Launcher mode (auto-start):
  → launcher/cdn.py                run_cdn_optimization()
    → check cache TTL              if cdn_cache_ttl > 0 and last_cdn_test_time within window → skip
    → ConfigManager.set()          store last_cdn_test_time on success
```

Files: `webui/js/cdn.js`, `webui/app.py`, `webutils/cdn/`, `launcher/cdn.py`, `CFST/cfst.exe`, `CFST/ip.txt`

## 5. Game Launch (with Mods)

```
Launcher mode: start_webui.py -launcher
  → start_webui.py                    _manage_launcher_console() — early console mgmt before imports
  → launcher/main.py                  ConfigManager() → LaunchPipeline()
    → launcher/pipeline.py            LaunchPipeline created; cancel_event for GUI abort
    → launcher/gui_progress.py        (if gui_mode) create_progress_window() + register_to_pipeline()
                                       renders config summary, vertical phases, overall/stage progress,
                                       expandable logs, status badge, and cancel/exit action

  Pipeline phases (emit order):
    Phase init:
      pipeline.emit(PHASE_INIT)         → GUI shows phase indicator
    Phase check_update:
      pipeline.emit(PHASE_CHECK_UPDATE) → launcher/updates.py (Factory pattern)
                                         → main.py reports network/check/install milestones to stage progress
    Phase resource_update:
      pipeline.emit(PHASE_RESOURCE_UPDATE) → resource_updater/service.py
        → resource_updater/core.py      compare SHA-256 fingerprint and configured completed scopes
                                        download official localize ZIPs + populate Unity Bundle cache
                                        → progress_callback(channel, message, fraction) updates GUI stage progress
    Phase cdn:
      pipeline.emit(PHASE_CDN)          → launcher/cdn.py (CDN optimize with cache TTL)
                                         forwards selector percentages/messages to GUI stage progress
    Phase prepare_mod (if enabled):
      pipeline.emit(PHASE_PREPARE_MOD)  → launcher/game_launch.py prepare_mod()
                                         reports stepped progress for cleanup/detection/text/assets/audio
                                        → launcher/patch.py (Unity asset patching)
                                        → launcher/sound.py (sound replacement)
                                        → launcher/changes.py (text data patches)
    Phase launch:
      → subprocess.Popen(steam_argv)   ← Non-blocking, stored in pipeline.context
      pipeline.emit(PHASE_LAUNCH)       → GUI shows process-creation progress
    Phase running:
      pipeline.emit(PHASE_RUNNING)      → game_launch.py start_speed_hotkey()
                                        → GUI marks overall progress complete and shows PID + uptime + hotkey hints
      → _wait_for_game(poll + cancel_event check)
    Phase exit:
      pipeline.emit(PHASE_EXIT)         → game_launch.py cleanup_mod_assets()
                                        → game_launch.py stop_speed_hotkey()
                                        → GUI shows "游戏已退出"

  Cancel flow:
    GUI FormClosing → three-way confirm dialog (YesNoCancel when game running)
      → Yes:     pipeline.cancel() → terminate game + exit launcher
      → No:      close launcher only (game continues running)
      → Cancel:  keep launcher open
      → _wait_for_game on Cancel: detects cancel_event → terminate game process
      → PHASE_EXIT callbacks still fire for cleanup
```

C launcher fallback (launcher.c):
  - Python always started with CREATE_NO_WINDOW + pipe-captured stdout/stderr
  - If Python exits with non-zero code: AllocConsole → display captured output
  - Normal exit (code 0): C exits silently, console managed by Python layer

## 6. Game Speed Modification

```
JS: user adjusts speed slider
  → webui/js/speed.js               slider change handler
  → webui/app.py                    LCTA_API.set_speed()
  → webutils/function_speed.py      openspeedy DLL injection
    → subprocess: openspeedy        inject DLL → hook game time APIs

Launcher integration switch (launcher.work.speed / launcher.work.speed_factor):
  checkbox lives ONLY on webui/sections/launcher-config.html 「工作模式配置」
  → webui/js/speed.js 游戏加速页仅保留集成介绍 + goAndShow('launcher-config') 跳转按钮

Launcher mode:
  → launcher/speed_hotkey.py        Ctrl+Shift+S → toggle speed
    → foreground check              verify LimbusCompany.exe is active
    → injection check               SpeedManager.is_injected() (self-tracked injection state)
    → log each stage                hotkey press, injection, speed toggle, DLL unload
    → .NET STA thread               WinForms slider window (System.Threading.Thread)
    → openspeedy                    inject DLL
```

Files: `webui/js/speed.js`, `webui/app.py`, `webutils/function_speed.py`, `launcher/speed_hotkey.py`

## 7. Rule Editor — File Edit → Smart Ruleset Generation

New workflow (v5.1+): user edits game JSON files directly and generates rules from changes.

```
User opens rule editor
  → webui/app.py LCTA_API.open_rule_editor()       spawn second pywebview window
  → webui/rule-editor.html + js/rule-editor.js      loads

User browses files in sidebar, double-clicks a file
  → api.get_file_content(path)                      read JSON from game Lang dir
  → webui/app.py RuleEditorAPI.get_file_content()
    → webutils/rule_editor/browser.py get_file_content()

User types in sidebar search input
  → filterFilesByKeyword(keyword)                    local filename/category filter only
User presses Enter or clicks "搜索"
  → performSearch()                                  increments searchRequestId; disables button
    → api.search_files(keyword, caseSensitive)
      → webutils/rule_editor/browser.py search_files()   raw UTF-8-SIG text occurrence count
                                                     (BOM and invalid JSON remain searchable)
    → ignore response if a newer search/clear occurred
    → renderSearchCategories()                       grouped content-search results

File content loaded into editable CodeMirror (file-edit tab)
  → state.currentFile set, fileOriginalContent saved for diff
  → Ctrl+F/H opens CodeMirror search panel
    → pointer-capture drag + requestAnimationFrame transform
    → setSearchPanelPosition() clamps panel inside editor and restores position across tabs

User edits text in CodeMirror, clicks "比较变更"
  → diffAndTrackChanges()
    → getFileEditorDoc()                            get current CodeMirror text
    → diffJson(originalParsed, parsed)              recursive JSON diff
    → extractChangesFromDiff()                      convert to [{file, field_path, item_id, old_val, new_val}]
    → renderChangeList()                            show changes in bottom panel

User clicks "保存到游戏" (optional direct save)
  → saveEditedFile()
    → api.save_file_content(path, raw)              writes to game Lang file
    → webutils/rule_editor/browser.py save_file_content()

User clicks "智能生成规则集" (from changes panel or ruleset-edit tab)
  → generateRulesFromChanges()
    → state.smartChanges = state.pendingChanges
    → openSmartGeneration()                         existing smart gen dialog
      → api.analyze_changes(changes)                LCS grouping + 5-dimension scoring
      → webutils/rule_editor/generate.py analyze_changes()
      → showSmartGenDialog(groups)                  L1-L4 tiered scope selectors
    → user selects scope → applySmartGroup()
      → builds rule → pushes to state.currentRuleset.rules
      → api.save_ruleset()                          persists to fancy/{name}.json
```

Key files: `webui/rule-editor.html`, `webui/js/rule-editor.js`, `webui/app.py` (RuleEditorAPI), `webutils/rule_editor/`

## 8. Text Beautification — Compile and Apply Rules

```
WebUI user applies text beautification
  → webui/js/features.js FancyManager              collects built-in/user rules + enable map
  → pywebview.api.fancy_main(configList, enableMap, modal.id)
  → webui/app.py LCTA_API.fancy_main()             passes modal_id through to fancy_main

Launcher finishes an enabled translation update
  → launcher/updates.py UpdateBase.run()
    → load_fancy_folder_rules()                     append user v2/bus rulesets
    → read config fancy_allow                       default {}

Both paths
  → webutils/function_fancy.py fancy_main(gamePath, package, rulesets, enableMap, modal_id=None)
    → _select_enabled_rulesets()                    discard disabled rules before compilation
    → compile each enabled ruleset in original order
      → webutils/fancy/engine.py compile_rulesets()  v2 conditions/actions
      → webutils/fancy/bus.py compile_bus_ruleset() bus selectors/replacements + exact/dynamic file index
      → CompiledRules.requires_skill_color
        → webutils/fancy/builtin_func.py SkillColorHandler.prepare() only when an enabled rule needs it
          → function_resource.py load_text_assets() (skips objects with missing/None containers)
          → fingerprinted-by-folder-name tmp/fancy/skill-colors.json cache (top-level account folders only)
    → scan language-package *.json files
      → v2/bus per-file matching and bus directory exclusions
        → bus reuses deduplicated matcher results and exact-file indexes
      → read UTF-8-SIG JSON
      → apply_rules()/apply_bus() in ruleset order
        → bus reuses resolved paths/string leaves and selector indexes within each file
      → compare final JSON with original and atomically replace only when changed
    → FancyRunStats                                  scanned/matched/changed/value/time/cache data
    → state-change logs via LogManager.log_modal_process() (规则集加载/编译完成/技能颜色缓存命中或重建/开始处理/完成汇总/每文件错误) —
      pushed to the modal when modal_id is given, otherwise plain file/console INFO on app.log;
      per-file error detail still logs to `fancy` logger with traceback
```

```
Fancy page 保存当前 / 保存全部
  → webui/js/features.js FancyManager.saveCurrent()/saveAll()
  → pywebview.api.save_ruleset(name, payload)        main-window LCTA_API method
  → webutils/rule_editor/rules.py save_ruleset()
    → validate + compile, then save_ruleset_to_folder() → fancy/{name}.json
```

```
Bus import button
  → webui/js/features.js importBusRules()
  → webui/app.py LCTA_API.import_bus_rules()
  → webutils/function_fancy.py import_bus_rules_file()
    → webutils/fancy/bus.py is_bus_ruleset() or is_tiaozhua_config() or is_fl_config() or is_lcje_config()
    → validate or mechanically convert (LCJE accepts both 文件→路径 maps and `{mods:[{file,path,old,new}]}` records, converting each path to an exact-file `set`; FL converts file diffs through id matching/list positions to `set` rules)
    → save disabled-by-default user ruleset under fancy/
```

Key files: `webui/js/features.js`, `webui/app.py`, `launcher/updates.py`, `webutils/function_fancy.py`, `webutils/fancy/engine.py`, `webutils/fancy/bus.py`, `webutils/fancy/builtin_func.py`, `webutils/function_resource.py`

## 9. Config Management

```
Write: JS form change
  → pywebview.api.save_config()
  → webui/app.py                    LCTA_API.save_config()
  → globalManagers/ConfigManager.py ConfigManager.set(key, value)
  → write config.json               auto-save to disk

Read: ConfigManager.get(key)        dotted-path access, falls back to config_default.json

Key launcher config items:
  launcher.work.cdn_optimize (bool)     auto CDN optimize on launch
  launcher.work.cdn_auto_apply (bool)   auto write optimal IP to hosts
  launcher.work.cdn_cache_ttl (str)     cache validity in hours (0 = always retest)
  launcher.resource_update.enabled      enable fingerprint-gated official resource pre-download
  launcher.resource_update.localize     update official localize files
  launcher.resource_update.bundle       pre-populate Unity AssetBundle cache
  launcher.resource_update.lang_*       selected jp/en/kr localize scopes
  launcher.resource_update.jobs         concurrent download count
  launcher.resource_update.engine       auto / aria2 / builtin
  launcher.resource_update.retry_max    auto-retry rounds on transient download failure (0 = off)
  launcher.resource_update.retry_delay  seconds between retry rounds (min 5)
  launcher.resource_update.connection_limit  aria2 connections per file (1–16, default 8)

Validate: config_check.json         JSON schema mapping keys → types ("str", "bool", etc.)
          config_default.json       default values template
```

Files: `globalManagers/ConfigManager.py`, `config.json`, `config_default.json`, `config_check.json`, `webui/app.py`, `webutils/load.py`

## 10. Auto-Update

```
JS: user clicks "check for updates" or auto-check on startup
  → webui/app.py                    LCTA_API.check_update()
  → webutils/update.py              GitHub Releases API
    → webFunc/GithubDownload.py     fetch latest release info
    → compare versions              current vs latest tag
  → download & extract              fetch ZIP, extract, replace files
```

Files: `webui/app.py`, `webutils/update.py`, `webFunc/GithubDownload.py`

## 11. Manual Update from Local Package

```
JS: user clicks "从本地更新包手动更新" in debug settings
  → webui/js/features.js            manualUpdateFromLocalZip()
    → pywebview.api.browse_file()   file picker dialog
    → confirm modal                 user confirms update
  → webui/app.py                    LCTA_API.perform_update_from_file()
    → extract zip                   validate start_webui.py + requirements.txt
    → webutils/update.py            Updater.install_requirements()
    → webutils/update.py            Updater.update_files()
  → restart required                manual program restart needed
```

Files: `webui/js/features.js`, `webui/app.py`, `webutils/update.py`

## 12. Drag-and-Drop File Installation

```
JS: user drags files onto window
  → js/features.js                  DragDropManager — drag counter, mask UI
    → on drop → onFileDropCallback(files)
  → webui/app.py                    on_drop() → passes file paths as JSON to JS
  → js/features.js                  setupDragDropCallback() receives files
    → pywebview.api.handle_dropped_files(files)
  → webui/app.py                    LCTA_API.handle_dropped_files(files_data)
    → webutils/drop/              evalFile() per file (detect.py → REGISTRY.detect), makeMessage() aggregation (message.py)
    → confirm modal                 user confirms operation
  → webui/app.py                    LCTA_API.eval_dropped_files(file_info, modal_id)
  → webutils/drop/eval_files.py evalFiles()
    → handler lookup:             REGISTRY.handler_for(file_type) → 对应分支处理器类
    → full/nofont:                handlers/translation.py install_translation_package() (7z support)
    → FLmod/jsononly:             handlers/archive_mod.py extract_zip_smartly() or copytree to mod_path
    → carra/bank/textFile/...:    handlers/copy_mod.py copy to mod_path
    → busimport:                  handlers/bus_import.py import_bus_rules_file() to fancy/
    → update:                     handlers/update.py Updater() via webutils/update.py
    → progress:                   LogManager modal callbacks
```

Files: `webui/js/features.js`, `webui/app.py`, `webutils/drop/`, `webutils/function_fancy.py`, `webutils/fancy/bus.py`, `webutils/update.py`

## 13. WebUI Startup Bootstrap

```
start_webui.py main()
  → if -launcher flag: start_launcher()        (launcher mode, see section 5)
  → else: webui/app.py:main()                 (WebUI mode)
    → globalManagers/ConfigManager.py          init singleton, load config.json
    → globalManagers/LogManager.py             init logger
    → webui/app.py LCTA_API.__init__()         register all pywebview API methods
    → pywebview.create_window()                create native window
    → webui/index.html loads                   HTML/CSS/JS
      → js/init.js                             DOMContentLoaded → init()
      → js/features.js                         async init():
        → sections/preload.js                  loadSection('dashboard') — only dashboard preloaded
        → DragDropManager init                 drag-and-drop setup
        → initListManagers()                   creates managers (containers may not exist yet)
        → initNavigation()                     click handlers registered
    → pywebviewready event fires               JS ↔ Python bridge active
      → pywebview.api.get_startup_data()       single call returns full startup bundle
      → _pendingWelcomeContent                 deferred rendering for welcome section
      → configManager.applyConfigToUI()        null-guarded, skips unloaded sections
      → toggle functions                       all null-guarded
      → fancyManager.init() / quickStartManager.init()  null-guarded DOM access
      → check_show() / init_github() / init_log()
      → fire-and-forget:                       change_icon, init_cache, set_attr(http_port)

  User navigates to a section:
    → initNavigation async handler             await loadSection(name)
      → sections/preload.js                    fetch HTML → inject → onSectionLoaded(name)
        → [console.log]                        per-section debug log
        → section-specific init:               toggle funcs, list manager ref updates,
                                               select box values, DOM ref rebuilds
        → configManager.applyConfigToUI()      re-apply for newly injected elements
        → initTooltips() / initPasswordToggles()
      → section callbacks:                     refreshInstallPackageList, cdnManager.init, etc.
      → AnimationManager.fadeIn()
```

Files: `start_webui.py`, `webui/app.py`, `webui/index.html`, `webui/js/init.js`, `webui/js/core.js`, `webui/js/features.js`, `webui/js/modals.js`, `webui/sections/preload.js`, `webui/js/utils.js`

## 14. 调爪 Text Package Download & Import

```
User clicks 「下载(导入)调爪文本修改包」(download.html)
  → js/features.js downloadTiaozhua()
    → ProgressModal
    → configManager.updateConfigValues(collectConfigFromUI())   persist tiaozhua-install
    → pywebview.api.download_lanzou_tiaozhua(modal.id)
      → webui/app.py LCTA_API.download_lanzou_tiaozhua()
        → webutils/function_lanzou_tiaozhua.py function_lanzou_tiaozhua_main(modal_id)
          → fetch_file_list()                     qaiu /v2/getFileList?url=wwyi.lanzoub.com/b014wpn02j&pwd=fib6
          → check_tiaozhua()                      version = date in "0.xxx26.7.25.7z" filename
          → cache guard (cache_path/tiaozhua_version.txt, tiaozhua.7z)
          → download_tiaozhua()                   get_direct_download(fileId with ?webpage= token)
                                                 → download_with(parser url 302) → cache_path/tiaozhua.7z
          → if install: install_tiaozhua()        decompress_7z (7-Zip exe) → temp dir
              → scan root *.json → is_tiaozhua_config/is_bus_ruleset
              → import_bus_rules_file()           save as ruleset in fancy ruleset folder
```

Launcher auto path: `launcher/updates.py UpdateBase.post_update` → `run_tiaozhua` (launcher.work.tiaozhua) → sets `ui_default.tiaozhua.install` → `function_lanzou_tiaozhua_main('安装调爪JSON')`.

Files: `webutils/function_lanzou_tiaozhua.py`, `webutils/utils/io.py` (decompress_7z), `webutils/utils/net.py` (download_with), `webutils/function_fancy.py` (import_bus_rules_file), `webui/app.py`, `webui/js/features.js`, `webui/sections/download.html`, `webui/sections/launcher-config.html`, `launcher/updates.py`

## 15. Three-Step Quick Start

```
User opens 「快速上手」
  → webui/js/utils.js                    lazy-load elder section route
  → webui/sections/elder.html            lightweight quick-start mount point
  → webui/js/quick-start.js              QuickStartManager.initPage()
    Step 1: choose one primary goal       package / launcher / translate / customize
    Step 2: render goal-only checks       game path, Launcher mode/options,
                                          API status, or customization destinations
      → ConfigManager.updateConfigValues() save ordinary config only when required
      → pywebview.api.browse_folder('')   optional game-folder selection
    Step 3: render action summary
      → goAndShow(target)                 download/install/launcher-config/config/
                                          translate/manage/fancy destination
```

No Markdown page parser, version tracking, dependency graph, reset API, or wizard-only config is involved.

Files: `webui/js/quick-start.js`, `webui/sections/elder.html`, `webui/js/utils.js`, `webui/sections/preload.js`, `webui/js/core.js`, `webui/assets/firstUse.md`, `webui/guide/elder.md`

## 16. Official Resource Update — Manual and Launcher Paths

```
Manual path:
  Sidebar 「游戏资源更新」（页面内含 Launcher 集成介绍 + 跳转按钮；启用开关位于 Launcher 配置页「工作模式」）
    → webui/js/utils.js goAndShow('resource-updater')
      → webui/sections/resource-updater.html + js/resource-updater.js
      → webui/app.py LCTA_API.resource_updater_start_update()
      → resource_updater/web_api.py ResourceUpdaterAPI.start_update()
        → background thread → resource_updater/core.py ResourceUpdater.run()
          → GameInfo.extract_tokens()            settings.json → S token; resources.assets → L token
          → GameInfo.catalog_url()               remote .hash location → matching catalog .bin URL
          → localize selected:
              token-scoped localize_<lang>.zip → safe extraction into
              LimbusCompany_Data/Assets/Resources_moved/Localize/<lang>/
          → Bundle selected:
              remote catalog_S1.bin with game-compatible Unity headers (local catalog fallback)
              → bundle name/cache-key parsing → Unity cache <outer>/<inner>/__data + __info
              → failed/cancelled item removes its incomplete <outer>/<inner>/ directory
          → aria2c JSON-RPC if bundled/available; urllib fallback otherwise
        → failures: per-file WARNING logs (name + error code), collected into result["failed_items"]
          ({name, url, reason}); aria2 polling progress only logs when the finished count changes
        → transient failures auto-retry up to retry_max times with retry_delay backoff
          (aria2 error state is re-queued without cleanup; builtin downloader re-attempts the file)
        → exhausted retries run a Range probe (status + cf/x-amz headers) into failed_items[].diagnostics
        → result: service.record_update_result() merges only fully completed scopes into state,
          persists last_result {success, failed, retried, failed_items}, and re-marks nothing
          on failure — the Launcher re-runs failed scopes on the next launch
        → page shows last_result: failure list + 「重试失败项」 button (re-runs the full update;
          already-downloaded files are skipped by cache/existence checks)

Launcher path:
  launcher/main.py resource_update phase
    → launcher/gui_progress.py          (if gui_mode) shows 「游戏资源更新」phase label
    → resource_updater/service.py run_launcher_resource_update()
      → local SHA-256(LimbusCompany.exe), without an online version check
      → compare %LOCALAPPDATA%/LCTA/resource-updater/launcher-state.json
      → also verify saved localize languages / Bundle scope cover current config
      → unchanged + covered: skip
      → changed or missing scope: ResourceUpdater.run()
      → record_update_result() saves the new fingerprint only for fully completed scopes;
        failed scopes stay unmarked and re-run on the next launch
    → main.py logs failures item-by-item at WARNING ("游戏资源更新失败文件: …")
      and marks the resource-update phase red (✗) + status text in the GUI when failed > 0
```

Build path: `build.ps1` and `.github/workflows/release.yml` pin aria2 1.37.0, retry/validate the official release download, and copy `aria2c.exe` plus `COPYING` when available to `tools/aria2/` in full, compatible, and update artifacts.

Files: `resource_updater/core.py`, `resource_updater/service.py`, `resource_updater/web_api.py`, `webui/sections/resource-updater.html`, `webui/js/resource-updater.js`, `webui/css/layout-extras.css`, `webui/app.py`, `webui/sections/launcher-config.html`, `launcher/main.py`, `config_default.json`, `config_check.json`, `build.ps1`, `.github/workflows/release.yml`
