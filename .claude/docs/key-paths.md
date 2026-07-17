# LCTA Key Path Tracing

<!-- Last updated: 2026-07-17 -->

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
```

Files: `webui/js/cdn.js`, `webui/app.py`, `webutils/function_cdn.py`, `CFST/cfst.exe`, `CFST/ip.txt`

## 5. Game Launch (with Mods)

```
Launcher mode: start_webui.py -launcher
  → launcher/main.py               main_pre() → main_after_mod() → main_after_game()
    Phase 1 (main_pre):
      → launcher/updates.py         check translation pack updates
      → launcher/cdn.py             optimize CDN if configured
    Phase 2 (main_after_mod):
      → launcher/game_launch.py     launch game with mod patching
        → launcher/patch.py         Unity asset patching
        → launcher/modfolder.py     mod detection & management
    Phase 3 (main_after_game):
      → launcher/speed_hotkey.py    register Ctrl+Shift+S hotkey
      → launcher/sound.py           apply sound mods
```

Files: `start_webui.py`, `launcher/main.py`, `launcher/updates.py`, `launcher/cdn.py`, `launcher/game_launch.py`, `launcher/patch.py`, `launcher/modfolder.py`, `launcher/speed_hotkey.py`, `launcher/sound.py`, `launcher/changes.py`

## 6. Game Speed Modification

```
JS: user adjusts speed slider
  → webui/js/speed.js               slider change handler
  → webui/app.py                    LCTA_API.set_speed()
  → webutils/function_speed.py      openspeedy DLL injection
    → subprocess: openspeedy        inject DLL → hook game time APIs

Launcher mode:
  → launcher/speed_hotkey.py        Ctrl+Shift+S → toggle speed
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

## 9. WebUI Startup Bootstrap

```
start_webui.py main()
  → if -launcher flag: launcher/main.py       (launcher mode)
  → else: webui/app.py:main()                 (WebUI mode)
    → globalManagers/ConfigManager.py          init singleton, load config.json
    → globalManagers/LogManager.py             init logger
    → webui/app.py LCTA_API.__init__()         register all pywebview API methods
    → pywebview.create_window()                create native window
    → webui/index.html loads                   HTML/CSS/JS
      → js/init.js                             bootstrap
      → js/core.js                             bind pywebview.api events
      → js/features.js                         init feature pages
    → pywebviewready event fires               JS ↔ Python bridge active
```

Files: `start_webui.py`, `webui/app.py`, `globalManagers/ConfigManager.py`, `globalManagers/LogManager.py`, `webui/index.html`, `webui/js/init.js`, `webui/js/core.js`
