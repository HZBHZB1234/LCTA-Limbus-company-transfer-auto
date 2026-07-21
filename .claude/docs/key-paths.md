# LCTA Key Path Tracing

<!-- Last updated: 2026-07-21 -->

Feature-to-code call chain traces. Each section maps a user-visible feature to the exact files in execution order.

---

## 1. Translation Installation — LLC (零协会)

```
JS: user clicks install button
  → webui/js/features.js           click handler → pywebview.api.install_llc()
  → webui/app.py                   LCTA_API.install_llc()
  → webutils/function_llc.py       download & install LLC pack
    → webFunc/GithubDownload.py    fetch from GitHub Releases API
    → webutils/functions.py        zip extraction, 7z integration
  → webui/app.py                   callback: progress → JS modal update
```

## 2. Translation Installation — OurPlay

```
JS: user clicks install button (PC or Android source)
  → webui/app.py                   LCTA_API.install_ourplay() or .install_ourplay_new()
  → webutils/function_ourplay.py   PC source download
    OR webutils/function_ourplay_new.py  Android source download
    → webFunc/GithubDownload.py    fetch from GitHub
    → webutils/functions.py        extract & apply
```

## 3. LLM Auto-Translation (核心功能)

```
JS: user configures & clicks translate
  → webui/app.py                   LCTA_API.translate()
  → webutils/function_translate.py orchestration entry
  → translateFunc/pipeline.py      TranslationPipeline.run()
    Stage 1: translateFunc/get_proper.py     fetch proper nouns from remote
    Stage 2: translateFunc/matcher/engine.py build AC automaton matcher
    Stage 3: translateFunc/processor.py      process priority files first
    Stage 4: translateFunc/workers.py        WorkerPool concurrent translation
      → translateFunc/builder/prompt.py      construct LLM prompts
      → translateFunc/builder/request.py     build API requests
      → translateFunc/translate_request.py   call LLM API, parse response
    Stage 5: translateFunc/matcher/engine.py post-translation proper matching
    Stage 6: translateFunc/pipeline.py       aggregate results → PipelineSummary
  → webutils/function_translate.py  write output files
  → webui/app.py                    callback: summary → JS modal
```

Files involved: `webui/app.py`, `webutils/function_translate.py`, `translateFunc/pipeline.py`, `translateFunc/config.py`, `translateFunc/processor.py`, `translateFunc/workers.py`, `translateFunc/translate_request.py`, `translateFunc/get_proper.py`, `translateFunc/builder/prompt.py`, `translateFunc/builder/request.py`, `translateFunc/builder/stages.py`, `translateFunc/matcher/engine.py`, `translateFunc/matcher/ac_automaton.py`, `translateFunc/log_bridge.py`, `globalManagers/LogManager.py`

## 4. CDN Optimization

```
JS: user clicks "test speed" or "optimize"
  → webui/js/cdn.js                UI logic, progress display
  → webui/app.py                   LCTA_API.cdn_test() / .cdn_optimize()
  → webutils/function_cdn.py       CDN logic
    → subprocess: CFST/cfst.exe    CloudflareSpeedTest binary
    → parse: CFST/result_cf.csv    speed test results
    → modify: system hosts file    apply optimal CDN IP

Launcher mode (auto-start):
  → launcher/cdn.py                run_cdn_optimization()
    → check cache TTL              if cdn_cache_ttl > 0 and last_cdn_test_time within window → skip
    → ConfigManager.set()          store last_cdn_test_time on success
```

Files: `webui/js/cdn.js`, `webui/app.py`, `webutils/function_cdn.py`, `launcher/cdn.py`, `CFST/cfst.exe`, `CFST/ip.txt`

## 5. Game Launch (with Mods)

```
Launcher mode: start_webui.py -launcher
  → start_webui.py                    _manage_launcher_console() — early console mgmt before imports
  → launcher/main.py                  ConfigManager() → LaunchPipeline()
    → launcher/pipeline.py            LaunchPipeline created; cancel_event for GUI abort
    → launcher/gui_progress.py        (if gui_mode) create_progress_window() + register_to_pipeline()

  Pipeline phases (emit order):
    Phase init:
      pipeline.emit(PHASE_INIT)         → GUI shows phase indicator
    Phase check_update / cdn:
      → launcher/main.py main_pre()     → launcher/updates.py (Factory pattern)
                                        → launcher/cdn.py (CDN optimize with cache TTL)
      pipeline.emit(PHASE_CDN)
    Phase prepare_mod (if enabled):
      pipeline.emit(PHASE_PREPARE_MOD)  → launcher/game_launch.py prepare_mod()
                                        → launcher/patch.py (Unity asset patching)
                                        → launcher/sound.py (sound replacement)
                                        → launcher/changes.py (text data patches)
    Phase launch:
      → subprocess.Popen(steam_argv)   ← Non-blocking, stored in pipeline.context
      pipeline.emit(PHASE_LAUNCH)       → GUI shows "游戏运行中"
    Phase running:
      pipeline.emit(PHASE_RUNNING)      → game_launch.py start_speed_hotkey()
                                        → GUI shows PID + uptime + hotkey hints
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

Launcher mode:
  → launcher/speed_hotkey.py        Ctrl+Shift+S → toggle speed
    → foreground check              verify LimbusCompany.exe is active
    → injection check               SpeedManager.is_injected() (self-tracked injection state)
    → log each stage                hotkey press, injection, speed toggle, DLL unload
    → .NET STA thread               WinForms slider window (System.Threading.Thread)
    → openspeedy                    inject DLL
```

Files: `webui/js/speed.js`, `webui/app.py`, `webutils/function_speed.py`, `launcher/speed_hotkey.py`

## 7. Config Management

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

Validate: config_check.json         JSON schema mapping keys → types ("str", "bool", etc.)
          config_default.json       default values template
```

Files: `globalManagers/ConfigManager.py`, `config.json`, `config_default.json`, `config_check.json`, `webui/app.py`, `webutils/load.py`

## 8. Auto-Update

```
JS: user clicks "check for updates" or auto-check on startup
  → webui/app.py                    LCTA_API.check_update()
  → webutils/update.py              GitHub Releases API
    → webFunc/GithubDownload.py     fetch latest release info
    → compare versions              current vs latest tag
  → download & extract              fetch ZIP, extract, replace files
```

Files: `webui/app.py`, `webutils/update.py`, `webFunc/GithubDownload.py`

## 9. Manual Update from Local Package

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

## 10. Drag-and-Drop File Installation

```
JS: user drags files onto window
  → js/features.js                  DragDropManager — drag counter, mask UI
    → on drop → onFileDropCallback(files)
  → webui/app.py                    on_drop() → passes file paths as JSON to JS
  → js/features.js                  setupDragDropCallback() receives files
    → pywebview.api.handle_dropped_files(files)
  → webui/app.py                    LCTA_API.handle_dropped_files(files_data)
    → webutils/function_drop.py     evalFile() per file, makeMessage() aggregation
    → confirm modal                 user confirms operation
  → webui/app.py                    LCTA_API.eval_dropped_files(file_info, modal_id)
  → webutils/function_drop.py       evalFiles()
    → type detection:               evalZip() — top-level folder matching
    → full/nofont:                  install_translation_package() (7z support)
    → FLmod:                        extract_zip_smartly() or copytree to mod_path
    → jsononly:                     extract to mod_path
    → update:                       Updater() via webutils/update.py
    → progress:                     LogManager modal callbacks
```

Files: `webui/js/features.js`, `webui/app.py`, `webutils/function_drop.py`, `webutils/update.py`

## 11. WebUI Startup Bootstrap

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
      → fancyManager.init() / elderManager.init()  null-guarded DOM access
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
