# LCTA Key Path Tracing

<!-- Last updated: 2026-08-12 -->


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

### 3d. 翻译页 API 配置未完成提示（横幅 + 跳转）

翻译工具页顶部有红色警告横幅（`#api-config-warning`），当**所选翻译服务**的必填字段（服务 `api-setting` 中 `required: true`，对照已保存配置 `api_config` 解密后的 `currentSettings[serviceKey]`）未保存完整时显示，并列出缺失字段名；横幅内「前往配置」与「翻译服务配置」卡内的「配置汉化API」按钮均 `goAndShow('config')` 跳转「配置汉化API」页。仅警告不拦截「开始翻译」。

```
进入翻译页（section 首次加载）:
  → webui/sections/preload.js     'translate' 分支 loadAPIServicesTranslator()
  → webui/js/api-config.js        updateTranslatorApiWarning() 计算并显示/隐藏横幅
进入翻译页（后续导航，section 缓存不重载）:
  → webui/js/utils.js             initNavigation() translate-section 钩子
  → webui/js/api-config.js        updateTranslatorApiWarning() 重查（配置页保存后返回实时刷新）
切换翻译服务下拉:
  → webui/js/api-config.js        loadAPIServicesTranslator() 的 change 监听 → updateTranslatorApiWarning()
横幅/卡片「前往配置」按钮（携带当前翻译服务跳转）:
  → webui/js/api-config.js        goConfigWithTranslator() 读 .translator-service-select 当前值
                                   → 存入 pendingConfigService（一次性）→ goAndShow('config')
  → 首次进入: preload.js config 分支消费 pendingConfigService 作 cKey 回填下拉
  → 已缓存:   utils.js initNavigation config-section 钩子消费（onSectionLoaded 不重跑），
              值不同才设置 + dispatch change 刷新表单；消费后清空
核心判定:
  → getMissingRequiredSettings(serviceKey)   服务 api-setting 必填项对照 currentSettings
                                             空值/未保存 → 缺失；无必填项的服务（空翻译器/MyMemory/Linguee 等）恒通过
```

Files: `webui/sections/translate.html`（横幅 + 跳转按钮）, `webui/js/api-config.js`（`getMissingRequiredSettings`/`updateTranslatorApiWarning`/`goConfigWithTranslator`）, `webui/js/utils.js`（导航钩子）, `webui/sections/preload.js`, `webui/css/components.css`（`.api-config-warning`/`.form-group-header`）

---

## 4. CDN Optimization

```
JS: user clicks "test speed" or "optimize"
  → webui/js/cdn.js                UI logic, progress display
  → webui/app.py                   LCTA_API.cdn_test() / .cdn_optimize()
  → webutils/cdn/                  CDN logic (package)
    → subprocess: tools/cfst/cfst.exe    CloudflareSpeedTest binary
    → parse: tools/cfst/result_cf.csv    speed test results
    → modify: system hosts file    apply optimal CDN IP

Launcher mode (auto-start):
  → launcher/cdn.py                run_cdn_optimization()
    → check cache TTL              if cdn_cache_ttl > 0 and last_cdn_test_time within window → skip
    → ConfigManager.set()          store last_cdn_test_time on success
```

Files: `webui/js/cdn.js`, `webui/app.py`, `webutils/cdn/`, `launcher/cdn.py`, `tools/cfst/cfst.exe`, `tools/cfst/ip.txt`

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
    Phase cdn:
      pipeline.emit(PHASE_CDN)          → launcher/cdn.py (CDN optimize with cache TTL)
                                         forwards selector percentages/messages to GUI stage progress
    Phase resource_update:
      pipeline.emit(PHASE_RESOURCE_UPDATE) → resource_updater/service.py
        → resource_updater/core.py      compare SHA-256 fingerprint and configured completed scopes
                                        download official localize ZIPs + populate Unity Bundle cache
                                        → progress_callback(channel, message, fraction) updates GUI stage progress
    Phase prepare_mod (if enabled):
      pipeline.emit(PHASE_PREPARE_MOD)  → launcher/game_launch.py prepare_mod(
                                         steam_argv, progress_callback, cancel_event)，
                                         各步骤间 check_cancel()（cancel_event 触发即中止）
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

Launcher auto-update config (与「汉化包下载」页共用一套配置):
  → webui/sections/launcher-config.html     仅保留更新模式 (launcher.work.update) 与各集成开关
                                             汉化包下载细节（压缩格式/下载来源/代理/字体/基板包等）
                                             已在 Launcher 页移除，只由「汉化包下载」页配置
  → launcher/updates.py                     LLCUpdate/MachineUpdate/OurPlayUpdate/LMGUpdate
                                             改读 ConfigManager().get('ui_default')
                                             .{zero,machine,ourplay}（不再读 launcher.{zero,machine,ourplay}）

## 6. Game Speed Modification

```
JS: user adjusts speed slider
  → webui/js/speed.js               slider change handler
  → webui/app.py                    LCTA_API.set_speed()
  → webutils/function_speed.py      openspeedy DLL injection
    → subprocess: openspeedy        inject DLL → hook game time APIs

First-time gate (risk notice):
  → webui/js/risk-gate.js          RiskGate.gatePage('speed') — 未同意
      speed.disclaimer_accepted 时渲染 data-risk-overlay 覆盖层，
      勾选"我已了解并自愿承担上述风险"→ acceptConsent() 写配置后解锁页面

Launcher integration switch (launcher.work.speed / launcher.work.speed_factor):
  checkbox lives ONLY on webui/sections/launcher-config.html 「工作模式配置」
  → webui/js/risk-gate.js          gateLauncherSection() — 未同意时勾选回滚并
                                    就地弹出同意弹窗（showConsentModal）
  → webui/js/speed.js 游戏加速页仅保留集成介绍 + goAndShow('launcher-config') 跳转按钮

Launcher mode:
  → launcher/speed_hotkey.py        Ctrl+Shift+S → toggle speed
    → foreground check              verify LimbusCompany.exe is active
    → injection check               SpeedManager.is_injected() (self-tracked injection state)
    → log each stage                hotkey press, injection, speed toggle, DLL unload
    → .NET STA thread               WinForms slider window (System.Threading.Thread)
    → openspeedy                    inject DLL
```

Files: `webui/js/speed.js`, `webui/js/risk-gate.js`, `webui/app.py`, `webutils/function_speed.py`, `launcher/speed_hotkey.py`

## 6.5 Input Bypass (CommonLib 输入反检测)

```
First-time gate (risk notice):
  → webui/js/risk-gate.js          RiskGate.gatePage('input_bypass') — 未同意
      input_bypass.disclaimer_accepted 时渲染覆盖层，同意后解锁页面

User toggles input bypass on Launcher config page
  → webui/sections/launcher-config.html              checkbox (launcher.work.input_bypass) +
                                                     goAndShow('launcher-config')
  → webui/js/input-bypass.js                         模式/计数/波动值配置（auto|manual）→ update_config_batch
  → webui/sections/input-bypass.html                 手动字段：4 个计数 + 波动值(%)；比例自动计算

Launcher startup:
  → launcher/main.py                                pipeline init → InputBypassManager.apply()
  → webutils/function_input_bypass.py apply()        reads launcher.work.input_bypass_* config
    → build_config(mode, armed, values)              clamp counts (≥0); volatility [0,50];
                                                      ratio auto = synth/(real+synth) (<0.9)
    → _write_config()                                writes 80-byte RHConfig to shared map
  → inject(pid)                                     remote-thread LoadLibraryW rawinput_hook.dll；
                                                      注入后经 psapi EnumProcessModules 按 DLL
                                                      文件名取真实 64 位 HMODULE（失败回退远程
                                                      线程退出码，避免句柄截断）
    → hooks/rawinput_hook.dll                        detours CommonLib RawInput exports;
                                                      auto: zero synth counts/ratios,
                                                      manual: real/synth counts from config,
                                                        ratio auto-calculated; volatility(±%)
                                                        jitters counts each RH_JITTER_MS window
                                                        so values aren't constant;
                                                      detach_hook 卸载前先恢复残留 detour
                                                      （防止跳转指向已卸载代码）
Status query (WebUI / status bar):
  → get_status()                                    running / pid / dll_exists / injected /
                                                    armed / mode / commonlib_found / installed
```

Files: `webutils/function_input_bypass.py`, `hooks/rawinput_hook.c`, `hooks/build.ps1`, `build.ps1`, `.github/workflows/release.yml`, `tests/test_input_bypass.py`

## 6.6 Cheat Toolbox (作弊工具箱, MinHook detour, 密钥门 + 私有分发 + 插件模型)

> 实现代码全部位于**私有仓库 LCTA_CheatingCore**（根目录克隆被 gitignore 排除），
> 构建期扫描 `hooks/*.c` 逐个编译为 DLL 后经 `scripts/cheat_encrypt.py` 加密为
> `cheat_core/cheat_core.bin` 随包分发；运行期需输入解密密钥（可经已知明文
> 碰撞分析恢复，属"门槛"而非"加密"，见私有仓库 README）。
> 解锁后私有仓库 `cheatcore/registry.py` 以**插件描述符**自动注册（宿主
> `webutils/cheat_plugins.py` 读取），**主仓库不感知具体工具**（工具名/API/
> 配置键/Launcher 元数据全部来自注册表）。工具箱页面 = `webui/sections/cheat.html`
> + `webui/js/cheat.js`（单页多工具卡片；当前含伤害倍率，命名空间 `cheat-damage-*`；
> 新增工具只需改私有仓库：C 源 + 管理器 + registry.py 注册 + 前端卡片）。

```
Sidebar entry (常驻显示，与 speed/input-bypass 同级):
  → webui/index.html                #cheat-btn 无 display:none/data-hidden-default，
                                     侧边栏「常用工具」组内常驻；侧边栏搜索可命中
  → webui/js/utils.js               导航生命周期绑定 cheatPage.init/stop

Key gate (解锁门) + first-time gate (risk notice):
  → webui/js/cheat-shell.js               cheatPage 壳（init/stop 生命周期，
                                          utils.js 导航绑定）：cheat_core_status() 查状态
                                          → 未解锁显示密钥门；已解锁/自动解锁后经
                                          cheat_plugins_list() 遍历插件，逐个
                                          cheat_core_get_section_html/js(webui.*) 拉取
                                          解密 HTML/JS，new Function 注入后调
                                           initCheatPage()（解密 JS 挂到 window）；
                                           另暴露 cheatCoreLockAndReload()（「锁定」按钮）；
                                           renderLauncherPlugins() 按注册表动态渲染
                                           Launcher 配置页的插件集成开关（渲染前先
                                           cheat_core_status() 触发 ensure_unlocked()
                                           自动解锁 → 插件注册，见下）
  → webui/sections/cheat.html             公共版本 = 密钥门 UI（密钥输入 + 解锁按钮 +
                                          功能数据缺失提示）；完整工具箱 UI 来自私有仓库
  → webui/js/risk-gate.js          RiskGate.gatePage('cheat') → 未同意
      cheat.disclaimer_accepted 时渲染覆盖层，同意后解锁页面。
      该服务标记 hideUntilConsent：同意前 Launcher 配置页的插件集成
      区整组隐藏（refreshLauncherVisibility），需先在源页面同意；
      同意写入在 acceptConsent() 与每次进入 launcher-config 页时刷新可见性。
      cheat 服务额外带 agreementSections（作者承诺/使用者义务/服务可用性
      说明，追加于公共风险须知后）与专属 consentLabel，仅作弊工具箱显示

Launcher 集成（动态渲染，AGENTS 规则：开关仍只出现在 launcher-config.html）:
  → webui/sections/launcher-config.html            占位容器 #cheat-plugin-launcher
                                                      （data-risk-service=cheat）
  → webui/js/cheat-shell.js renderLauncherPlugins() ① 渲染前先 cheat_core_status()
                                                      触发 ensure_unlocked()（持久化
                                                      密钥自动解锁 → 插件注册），否则
                                                      新会话未打开作弊页时插件未注册、
                                                      开关不显示；② 按插件 launcher
                                                      元数据生成 checkbox（enabled_key/
                                                      checkbox_id/label/hint），并把
                                                      configManager.registerConfigKey(
                                                      checkbox_id, enabled_key) 动态登记
                                                      进 configKeyMap（纳入 bindConfig
                                                      AutoSave/applyConfigToUI/缓存管理）；
                                                      ③ change 仅做风险同意门控，值由
                                                      bindConfigAutoSave 持久化，未同意
                                                      回滚时覆盖 configManager.pendingUpdates
                                                      防止误落盘；同意后仍手动写值
  → 私有仓库 webui/sections/cheat.html         倍率(0.1-1000)、日志开关、偏移 API、
                                                      注入/弹出/立即刷新偏移、锁定按钮
                                                      （配置经 update_config_batch 落库）

Unlock (解锁链路) + 插件注册:
  → webui/app_api/cheat_core.py CheatCoreMixin        cheat_core_status/unlock/lock/
                                                      get_section_html/get_script_js/
                                                      cheat_plugins_list/cheat_plugin_invoke
  → webutils/cheat_core.py
      ensure_unlocked()           dev 克隆存在 → 直接解锁（source=dev）；
                                  否则 blob 缺失 → blob_missing；数据损坏 → blob_corrupt
                                  （保留密钥不清除）；配置有持久化密钥 → 自动 unlock；
                                  否则 need_key
      unlock(key)                 解析 blob → 解密 → anchor + 逐文件 SHA-256 校验
                                  → dest 路径净化（拒绝 .. 段/盘符/绝对路径）后
                                    释放到 %LOCALAPPDATA%/LCTA/cheat-core/
                                  → sys.path 插入 → import cheatcore（get_package）
                                  → _reload_plugins() 触发插件注册
      lock()                      清配置密钥 + 内存态 + 插件注册 + sys.path + 删除运行时目录
  → webutils/cheat_plugins.py CheatPluginHost（公共仓库，替代旧门面）
      reload()                    读 cheatcore.get_plugins() 描述符 + 播种配置默认值
      list()                      插件摘要（id/name/webui/config/launcher）
      invoke(action, args)        按注册表 api 白名单分发到声明该 action 的插件管理器（未解锁/未知操作抛错）
      run_launcher_phase(phase)   查 enabled_key + consent 后调 on_start/on_stop
      close_all()                 atexit 兜底调各插件 close

Launcher startup:
  → launcher/main.py                                PHASE_RUNNING → start_cheat_plugins()
  → launcher/game_launch.py start_cheat_plugins()   先 cheat_core.ensure_unlocked()（未解锁
                                                      log「作弊工具箱未解锁」后跳过），通过后
                                                      CheatPluginHost.run_launcher_phase('start')
  → CheatPluginHost → 私有仓库 cheat_damage_hook.py start_launcher()（注册表 on_start）
      决策点日志（INFO，供 launcher 日志面板/日志页排查）：
      未启用 enabled_key →「未启用（key），跳过注入」；未同意风险 →「未同意风险须知」
      后台线程启动时预解析偏移（预热缓存/填充状态，缓存命中零成本；不可用则
      log「偏移不可用（reason），跳过注入」提前返回）→
      等 LimbusCompany.exe（180s，检测到进程 log PID）→ apply()（缓存快路径）
      → inject(pid)（成功 log 偏移来源/版本/过期标记）
  → 私有仓库 cheatcore/cheat_damage_hook.py
      resolve_offsets()                             GameAssembly.dll SHA-256 版本锚定
        - 缓存命中（hash 一致）→ 直接用缓存
        - hash 变化（游戏更新）→ 拉 API (web.lcta.top/cheat_damage.json)
          · API 已发布新版 → 更新 %LOCALAPPDATA%/LCTA/cheat-damage/offsets-cache.json
          · API 未发布 / 网络失败 → 旧缓存降级 + stale 标记
      apply()                                       writes 16584-byte DHConfig to shared map
                                                      (Local\LCTA_CheatDamage_Config)
      inject(pid)                                   remote-thread LoadLibraryW cheat_damage.dll
  → 私有仓库 hooks/cheat_damage.dll + vendor/minhook
                                                      waits GameAssembly.dll → VerifyPrologue
                                                      (16B, from shared config) →
                                                      MH_CreateHook on
                                                      GetTakeAttackDmgMultiplier
                                                      (enemy-only ×multiplier; 0→multiplier)
      Damage log (cheat_damage_log on):
      → DLL hk_GetTakeAttackDmgMultiplier           per effective event writes
                                                      "target=.. attacker=.. crit=.. mul X -> X"
                                                      to shared ring buffer log_ring[128][128]
                                                      (slot = head%128, head monotonic)
      → _start_drain_thread()                        background 0.5s loop started by
                                                      _open_map(); _drain_and_log() reads
                                                      delta via drain_new_log_entries() →
                                                      LogManager.log() → logs/app.log;
                                                      overflow → dropped warning; close()
                                                      stops thread + final flush (atexit
                                                      registered in webui/app.py)
Runtime update recovery (game hot-updates, manual trigger):
  → DLL prologue check fails → verified=0, last_error=3
  → user triggers via WebUI「立即刷新偏移」(refresh_offsets force) or relaunch
  → refresh_offsets() (force) → apply() with retry_requested=1
  → DLL MH_DisableHook → re-verify → re-install with new offsets (no restart)
Status query (WebUI):
  → get_status()                                    running / pid / injected / gameassembly_found /
                                                    verified / installed / last_error_text /
                                                    log_count / last_log / offsets_source /
                                                     offsets_stale / game_version
```

构建（build.ps1 与 release.yml 同步）：
- 源码来源：根目录 `LCTA_CheatingCore/` 克隆（CI 用 `secrets.LCTA_CHEAT_TOKEN`
  git clone 到 `cheat_core/`）；缺失则跳过（产物不含作弊工具箱功能）
- 扫描 `hooks/*.c` 逐个 gcc 编译同名 DLL（含 vendor/minhook）→ `python scripts/cheat_encrypt.py
  build --src <clone> --key <clone>/keys/current.txt --out cheat_core.bin`
- 复制到三个目录 `code/cheat_core/cheat_core.bin`

Files: `webutils/cheat_core.py`, `webutils/cheat_plugins.py`（插件宿主）, `scripts/cheat_encrypt.py`, `webui/app_api/cheat_core.py`（含 cheat_plugins_list/invoke）, `webui/sections/cheat.html`（密钥门）, `webui/sections/launcher-config.html`（#cheat-plugin-launcher 占位）, `webui/js/cheat-shell.js`, `webui/js/risk-gate.js`（cheat 无 launcherCheckboxId）, `launcher/game_launch.py`, `tests/test_cheat_core.py`；私有仓库：`cheatcore/registry.py`（插件契约）, `cheatcore/cheat_damage_hook.py`（含 start/stop_launcher）, `hooks/cheat_damage.c`, `vendor/minhook/`, `webui/*`, `tools/gen_cheat_damage_json.py`（自动生成偏移 JSON）, `keys/current.txt`, `manifest.json`, `docs/CHEAT_TOOLBOX.md`, `tests/test_cheat_damage_hook.py`, `tests/test_registry.py`

## 6.7 Steam 启动器设置（写入/清除 LaunchOptions 到 localconfig.vdf）

```
WebUI Launcher配置页 steam命令旁「写入Steam启动选项」/「清除启动项」按钮
  → webui/js/modals.js applySteamLaunchOptions() / clearSteamLaunchOptions()
      → pywebview.api.run_func('get_steam_launcher_status')
      → webui/app_api/core.py CoreMixin.get_steam_launcher_status（set_function 注册）
      → webutils/function_steam_launcher.py get_steam_launcher_status()
          → get_steam_path()              注册表 HKCU\SOFTWARE\Valve\Steam\SteamPath（分隔符归一化）
          → resolve_localconfig_path()    主: config/loginusers.vdf MostRecent==1 账号
                                          回退: 扫描 userdata\*（含 1973530 条目优先）
          → is_lcta_launch_options()      ' -launcher %command%' 判定 LCTA 型
          → get_current_launch_command()  当前 LCTA 命令（get_steam_command，异常→None）
          → state: missing/unconfigured/lcta_current/lcta_stale/lcta/other + is_current_lcta
          → is_steam_running()            tasklist 检测 steam.exe
  → 弹窗确认（只显示状态文本；Steam 运行中先警告）
  → 写入: run_func('set_steam_launch_options', command)
    webutils/function_steam_launcher.py set_steam_launch_options()
      → 备份 localconfig.vdf → localconfig.vdf.lcta.bak
      → vdf.load → apps["1973530"].LaunchOptions = get_steam_command()（utils/misc.py）
      → vdf.dump 按原 BOM 状态写回
  → 清除: run_func('clear_steam_launch_options')
    webutils/function_steam_launcher.py clear_steam_launch_options()
      → 备份 → apps[GAME_ID].pop('LaunchOptions')（保留 LastPlayed 等字段）→ vdf.dump 写回；未配置时幂等
  → 结果 showMessage + refreshSteamLauncherStatus() 刷新状态文本

页面加载: webui/sections/preload.js 'launcher-config' 分支调 refreshSteamLauncherStatus()
```

Files: `webutils/function_steam_launcher.py`, `webutils/__init__.py`, `webui/app_api/core.py`（set_function 注册）, `webui/sections/launcher-config.html`, `webui/js/modals.js`, `webui/sections/preload.js`, `tests/test_steam_launcher.py`

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
    → openSmartGenerationV3()                       当前主流程 (V3)
      → analyzeChangesV3(changes)
        → api.analyze_changes_v3(changes)           webutils/rule_editor/generate.py analyze_changes_v3()
        → 回退 analyzeChangesLocallyV3()            JS 本地分析
      → 按 (old_val, new_val, field_path) 分桶成组，每组附 _raw_changes 原始变更
      → 合并候选 = 语义验证（_detect_merge_candidates / detectMergeCandidatesLocally）：
        一组的规则(action_preview，字面全局替换)能推广覆盖另一组全部变更即可合并
      → _autoMergeCandidates() + _mergeTwoGroups() 自动合并高置信候选（保留推广方规则，不拼接冗余 action）
    → user selects scope → applyV3Group() / applyAllV3WithDedup()
      → builds rule → pushes to state.currentRuleset.rules
      → api.save_ruleset()                          persists to fancy/{name}.json
```

> 注：V1/V2 旧流程（analyze_changes / analyze_changes_v2 + _cluster_changes LCS 分组）仍保留，但入口已走 V3。

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
    → compile each enabled ruleset, ordered bus-first
      → webutils/fancy/engine.py compile_rulesets()  v2 conditions/actions
      → webutils/fancy/bus.py compile_bus_ruleset() bus selectors/replacements + exact/dynamic file index
      (fancy_main fixed execution order: all bus 文本替换 rulesets run before all v2 文本美化 rulesets,
       stable within each engine — see _compile_mixed_rulesets)
      → CompiledRules.requires_skill_color
        → webutils/fancy/builtin_func.py SkillColorHandler.prepare() only when an enabled rule needs it
          → function_resource.py load_text_assets() (skips objects with missing/None containers)
          → fingerprinted-by-folder-name tmp/fancy/skill-colors.json cache (top-level account folders only)
    → scan language-package *.json files
      → v2/bus per-file matching and bus directory exclusions
        → bus reuses deduplicated matcher results and exact-file indexes
      → read UTF-8-SIG JSON
      → apply_bus() before apply_rules() in bus-first order
        → bus reuses resolved paths/string leaves and selector indexes within each file
      → compare final JSON with original and atomically replace only when changed
    → FancyRunStats                                  scanned/matched/changed/value/time/cache data
    → state-change logs via LogManager.log_modal_process() (规则集加载/编译完成/技能颜色缓存命中或重建/开始处理/完成汇总/每文件错误) —
      pushed to the modal when modal_id is given, otherwise plain file/console INFO on app.log;
      per-file error detail still logs to `fancy` logger with traceback
  → API 层 LCTA_API.fancy_main() 返回 {"success": bool, "message": str}；文件循环头 check_running
    支持取消（取消返回 "已取消"，前端 modal.cancel()）
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
  → download & extract              fetch ZIP, extract (tempfile 临时目录，非应用目录内 updateCache)
  → webutils/update.py              Updater.install_requirements() 按包名比对（spec 归一化防误判）：
      - 新版本不再声明的旧依赖永久保留，不执行 pip uninstall；`delete_updating` 配置已移除
      - 新增/版本变动依赖在 GUI 内先用默认 PyPI 源安装
      - 默认源为网络失败 → 仅本次命令切换清华源重试；仍失败则中止文件替换，
        提示关闭系统代理/加速器后重试，不写 pending
      - 最终为 DLL 占用/权限/构建等非网络失败 → 仅该安装项写入
        %LOCALAPPDATA%/LCTA/pending_pip_ops.json；非 GUI 调用不得创建 pending
  → webutils/update.py              Updater.update_files() 替换文件（失败 return False 并还原
                                       install_requirements 写入的 pending 安装项；缓存仅清理自建
                                       临时目录，调用方传入的缓存目录保留）
  → restart required                manual program restart needed（非网络失败的依赖安装在重启后重试；
                                       更新完成提示按 pending 存在性联动"请重启程序"文案）
  → start_webui.py init_env()       下次启动：直接导入 globalManagers/pending_pip_ops.py（纯标准库，
                                       不触发 webutils 包导入），ctypes MessageBoxW 弹原生进度窗，
                                       apply_pending_pip_ops() 在加载任何第三方库之前仅重试安装
```

> 注：`perform_update_in_modal` 已把 modal_id 传给 Updater（下载阶段可取消），返回 `{"success": bool, "message": str}`；取消返回 `"已取消"` + `del_modal_list`。前端 `doUpdate` 对 `"已取消"` 走 `modal.cancel()`。

Files: `webui/app.py`, `webutils/update.py`, `webFunc/GithubDownload.py`, `start_webui.py`

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

> 注：`perform_update_from_file` 在依赖与文件替换之间已有 `check_modal_running` 检查点，取消返回 `"已取消"` + `del_modal_list`；前端特判 `"已取消"` 走 `modal.cancel()`。

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
    → font:                       handlers/font.py save_cache_font() replace cache ChineseFont.ttf
    → busimport:                  handlers/bus_import.py import_bus_rules_file() to fancy/
    → update:                     handlers/update.py Updater() via webutils/update.py
    → progress:                   LogManager modal callbacks
```

> 注：`evalFiles` 中 handler 抛 `CancelRunning` 立即上抛（不再吞成 errors），`drops.py` 捕获后返回 `"已取消"`；存在错误时不推 100% 进度。前端 `setupDragDropCallback` 的 `.then` 按 success/`已取消` 分支调用 `complete()`/`cancel()`，`.catch` 兜底关闭窗口。

Files: `webui/js/features.js`, `webui/app.py`, `webutils/drop/`, `webutils/function_fancy.py`, `webutils/fancy/bus.py`, `webutils/update.py`

## 13. WebUI Startup Bootstrap

```
start_webui.py main()
  → if -launcher flag: start_launcher()        (launcher mode, see section 5)
  → else: start_webui()                        (WebUI mode)
    → init_env()                               设置 path_/is_frozen 等环境变量
    → check_webview2_environment()             WebView2 预检（与 pywebview edgechromium 探测一致）：
                                                 .NET Framework >= 4.6.2（HKLM NDp\v4\Full
                                                 Release >= 394802）检查（注册表读取失败/版本过低
                                                 仅打印警告，不阻断启动）；
                                                 64 位机器 HKLM 走 WOW6432Node\EdgeUpdate\Clients\{4个GUID}，
                                                 HKCU 走普通路径，且版本需 >= 86.0.622.0
                                                 （非数字版本号视为不可用，不因 int() 误阻断）；
                                                 PYWEBVIEW_GUI=qt 直接放行。
                                                 仅 WebView2 缺失/过旧 → MessageBox「缺少 WebView2 Runtime 或
                                                 .NET Framework 4.6.2+」+ webbrowser 打开官方
                                                 下载页 + return（不启动窗口）
    → from webutils.clr_bootstrap import ensure_clr  导入 pythonnet（netfx）
    → webui/app.py:main()                      (WebUI mode)
    → globalManagers/ConfigManager.py          init singleton, load config.json；
                                                 `from_disk` 标记 config.json 是否真实存在于磁盘，
                                                 init_config 据此判定 first_use（缺文件回退默认配置即首启，
                                                 调用 use_default() 写盘并 first_use=True）
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
          → if install: install_tiaozhua()        decompress_7z (7zr.exe，无 7z 时自动下载) → temp dir
              → scan root *.json → is_tiaozhua_config/is_bus_ruleset
              → import_bus_rules_file()           save as ruleset in fancy ruleset folder
```

> 注：前端 configManager 保存失败时窗口会 complete(false) 关闭；`download_with` 透传 `CancelRunning`（取消 → `"已取消"` 特判），下载失败不再被伪装成成功。

Launcher auto path: `launcher/updates.py UpdateBase.post_update` → `run_tiaozhua` (launcher.work.tiaozhua) → sets `ui_default.tiaozhua.install` → `function_lanzou_tiaozhua_main('安装调爪JSON')`.

### 14b. 调爪「替换」文本包 Download & Apply

```
User clicks 「下载并应用所选调爪替换文本包」(download.html)  或 launcher 更新后
  → js/features.js downloadTiaozhuaReplace()          (下载页手动)
    → pywebview.api.download_lanzou_tiaozhua_replace(modal.id)
  → launcher/updates.py run(): ui_default.tiaozhua.replace_* 任一启用
    → function_lanzou_tiaozhua_replace_main('安装调爪替换文本包')   (launcher 自动)
      → _select_replace_packages()       3/4/8 气泡互斥，仅留编号最小者
      → fetch_file_list()
      → for num in {3,4,5,7,8}: find_replace_file(prefix "n.") → 缺失跳过
      → 版本缓存 tiaozhua_replace_<n>.zip / _version.txt → download_with(parser 302)
      → install_replace_package(): zipfile 选择性读 `文件/*.json`
          → _sanitize_zip_member_name 校验 → 写入 resolve_replace_target_dir()
          (= get_active_lang_path + config.json lang，即 fancy 目标目录)，跳过 python/
```

> 包 6（技能被动饰品BUFF美化）永不集成（与文本美化功能重复）。独立开关在**汉化包下载页与 Launcher 页各有一份相同复选框**（下载页 `dl-tiaozhua-replace-*` / Launcher 页 `lc-tiaozhua-replace-*`，两套 id 映射同一 `ui_default.tiaozhua.replace_*` 配置键，页面间经 `bindTiaozhuaReplaceSync` 实时同步、进入页面时经 `syncTiaozhuaReplaceFromConfig` 兜底刷新）；三种气泡（3彩色/4无色/8旧翻译版）互斥：前端勾选其一自动取消其余两个（两页全量）并同步保存，后端 `_select_replace_packages` 兜底仅应用编号最小者。

Files: `webutils/function_lanzou_tiaozhua.py`, `webui/app_api/download.py`, `webui/sections/launcher-config.html`, `webui/sections/download.html`, `webui/js/core.js`, `webui/js/features.js`, `webui/js/utils.js`, `launcher/updates.py`, `config_check.json`

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

## 17. Metadata 恢复（IL2CPP metadata 解密参数恢复，结构化流程）

```
JS: user opens 侧边栏「Metadata 恢复」页（首次导航懒加载）
  -> webui/sections/preload.js        loadSection('metadata-recovery') -> onSectionLoaded
  -> webui/js/metadata-recovery.js    MetadataRecoveryPage.init() 刷新插件/输出目录/游戏推导状态
      (utils.js initNavigation 每次进入页面时再次 init)

步骤 1-2（IDA 侧）：user clicks「安装定位器插件」
  -> pywebview.api.metadata_recovery_install_ida_plugin(dir)
  -> webui/app_api/metadata_recovery.py  MetadataRecoveryMixin
  -> webutils/metadata_recovery/__init__.py  find_ida_plugins_dir()（注册表+常见路径）
      install_ida_plugin() 写 <plugins>/metadata_locator_plugin.py（热键 Ctrl-Alt-Shift-M）
      + <plugins>/metadata_recovery_tools/{locate_metadata_init,report}.py
  IDA 内 Ctrl-Alt-Shift-M -> locator.py（插件/MCP 双入口）
     单遍 .text 扫描 xorshift64(13,7,17) 指令 + 字符串引用 -> 候选池
     -> 反编译级评分 -> <IDB>/locator_out/locate_candidates.json + decompile_rank*.c

步骤 3（导入导出）：user picks 导出（locate_candidates.json 或目录）+ 候选 rank，clicks「载入导出」
  -> pywebview.api.metadata_recovery_load_export(path, rank)
  -> webui/app_api/metadata_recovery.py  转发 load_locator_export()
  -> webutils/metadata_recovery/__init__.py  load_locator_export()
      解析 verdict + 全候选（探测 decompile_rank{n}_{name}.c），按 rank 返回
      table_hex + decompile_text/decompile_file
  -> JS renderExport()：候选下拉 + 信息区（verdict/hex/文本就绪），自动回填 textarea/hex

步骤 4（输入文件，自动推导）：JS refreshStatus() -> metadata_recovery_status()
  -> derive_game_files(ConfigManager().get('game_path')) 推导
     <游戏>/LimbusCompany_Data/il2cpp_data/Metadata/global-metadata.dat 与
     <游戏>/GameAssembly.dll，输入框为空时自动回填；参考标准文件手动选择

步骤 6（运行）：user clicks「开始完整恢复」-> ProgressModal
  -> pywebview.api.metadata_recovery_run(config, modal.id)
  -> webui/app_api/metadata_recovery.py  后台线程 + add_modal_log / check_modal_running（取消）
  -> webutils/metadata_recovery/pipeline.py  run_recovery()
      阶段0 resolve_table_hex：导出已载入 hex；或反编译文本 byte_XXXX VA + read_rva_data(GameAssembly.dll)
      阶段1 extractor.extract_from_text()（或加载既有 candidate_profile.json）
      阶段2 verify.verify_profile()：header 解密 + 布局判定 + 节段结构门
      阶段3 solver.solve()：C1 记录大小 / C5 内容指纹 / C3 链装配 / 相4 重建 SHA-256
      阶段4 profile.build_profile()：正式 profile + 自检重建
      阶段边界 + 各 _run_* 内重操作前后均有 cancel_check() 取消点；
      取消 -> 返回 "已取消" + del_modal_list（modal_id 仅由前端注册，后端不再重复 add_modal_id）
      每阶段 report.json/md 落盘 <path_>/metadata_recovery/run_<时间戳>/
  -> 页面渲染 verdicts 徽标 + 输出文件列表

文件：webui/sections/metadata-recovery.html, webui/js/metadata-recovery.js,
      webui/app_api/metadata_recovery.py, webui/app.py, webutils/metadata_recovery/,
      webui/guide/metadata-recovery.md, .github/InitCode.py(js_files), tests/test_metadata_recovery.py
```

## 18. 泛用高速下载器（aria2c 独立窗口）

```
JS: 游戏资源更新页「打开高速下载器」按钮（resource-updater.js bindEvents）
  → pywebview.api.open_aria2_downloader()
  → webui/app_api/windows.py WindowMixin.open_aria2_downloader()
      → webview.create_window("LCTA - 高速下载器", webui/aria2-downloader.html,
                               js_api=Aria2DownloaderAPI()) + 主题注入
      → window.events.closed → aria2_manager.stop()（释放 aria2c 进程）

窗口初始化（webui/js/aria2-downloader.js init）:
  → api.get_state()          aria2c 可用性 + 服务状态 + ui_default.aria2_dl 配置快照
                             （默认目录经 shell.get_downloads_dir() 解析系统真实
                             「下载」已知文件夹；save_dir_exists=false 时显示
                             常驻警告 #adl-dir-warning，浏览成功后隐藏）
  → 可用则 api.start_server() → aria2_manager.start_server()
      → resolve_aria2_binary()（复用 resource_updater.core，随包 tools/aria2/aria2c.exe）
      → Aria2DlClient.start()  随机端口 + --rpc-secret + 并发/连接数/做种时间
                                （jobs/connection_limit/seed_time 来自配置）
      → 后台轮询线程 _poll_loop（1s）→ snapshot() → set_snapshot_callback 回调
          → window.__aria2DlDispatch({type:'snapshot', payload}) → renderTasks()
          显示名链：bittorrent.info.name → files[0].path 基名（全类型）→
          derive_display_name(url)（仅显示回退）

添加任务:
  → api.add_urls({urls, save_dir}) → aria2_manager.add_urls()
      → 保存目录必须已存在（is_dir 校验，不自动创建；缺失 → 报错「保存目录不存在」，
        不创建任务、不持久化）
      → 校验 http/https/ftp/magnet:? 前缀 + 去重 + 每行错误明细
      → client.add_uri(url, dir, out=None)   （不强制 out：落盘名由 aria2 按
        Content-Disposition 优先解析，哈希段 URL 不再落成长 hex 文件名；
        --content-disposition-default-utf8=true 保证中文文件名不乱码）
  → api.add_torrent({path, save_dir}) → aria2_manager.add_torrent()
      → 校验 .torrent 扩展名 → base64 → client.addTorrent()
  → 保存目录持久化 ui_default.aria2_dl.save_dir（仅任务添加成功时）

任务控制（每任务/全局）:
  → api.pause_task(gid)/resume_task(gid)/remove_task(gid)/pause_all()/resume_all()/purge_completed()
  → aria2_manager.pause()/resume()/remove()/...
      → aria2.pause → forcePause 兜底；remove → forceRemove → removeDownloadResult 兜底
  → 快照渲染：进度条/速度/大小/状态徽标；error 显示错误码+信息

磁力派生收养:
  → 磁力元数据取回后 aria2 以新 gid 派生文件下载
  → snapshot() 内 _adopt_magnet_children()：tell_active 中未知 gid 且 dir 匹配
     已完成元数据的磁力任务 → 收养进原任务记录（任务列表连续显示）

配置（ui_default.aria2_dl）:
  → save_dir/jobs(8)/connection_limit(16)/seed_time(0=不做种)
  → 窗口「保存设置」→ api.save_window_config() 持久化；修改后下次启动下载服务生效
  → 与 resource_updater 的 aria2 实例相互独立（各自进程/随机端口/secret）
```

Files: `webui/sections/resource-updater.html`, `webui/js/resource-updater.js`, `webui/app_api/windows.py`,
      `webui/aria2_downloader_api.py`, `webui/aria2-downloader.html`, `webui/js/aria2-downloader.js`,
      `webui/css/aria2-downloader.css`, `webutils/function_aria2_downloader.py`,
      `webutils/utils/shell.py`（get_downloads_dir）, `webutils/__init__.py`,
      `webui/app.py`（atexit 清理）, `config_default.json`, `config_check.json`, `.github/InitCode.py`（HTML 本地化）, `tests/test_aria2_downloader.py`



## 19. 加载页 CG 替换（锁定 + 贴图替换）

原理（逆向自 GameAssembly.dll，详见 LimbusDecompile/docs/LOADING_CG_INJECT.md）:
  存档 save_slot_<id>.json = Base64(AES-256-CBC+PKCS7(JsonUtility JSON))
  密钥明文: HKCU\Software\ProjectMoon\LimbusCompany\LocalSave.LocalGameOptionData_*
  选图优先级: _forcedCharacterCgIdList > _cgIdList > 默认；ID 三态模型（2026-08-12 确认）：存档字符串 ID = "CG/<名>"(官方)/"BG/<名>"(自定义)，游戏 isFullPath = !StartsWith(ID,"CG/") && !StartsWith(ID,"BG/")，key = "Story_" + ID + ".png"（失败兜底 "Unit_" + ID + ".png"）；forced = List<LocalCharacterCGData>[{"id":N,"gacksung":bool}]（仅人格 CG，GetText="CG/{0}{1}"）；键形式 Story_CG/Unit_CG 为 catalog 索引/展示用（key_to_save_id 转换）；方案 A = forced 对象锁定（稳定，已验证）；方案 B = 注入 _cgIdList（不稳定，保存时被重建）
  bundle: %LOCALAPPDATA%\..\LocalLow\Unity\ProjectMoon_LimbusCompany\<h1>\<h2>\__data（unity_version 被抹除为 0.0.0，须 FALLBACK_UNITY_VERSION=6000.3.12f1）

锁定/取消锁定（即时写入，无备份）:
  JS: sections/cg.html + js/cg.js（CgPage，RiskGate.gatePage('cg') 门控）
    -> api.cg_read(save_path) / cg_apply(save_path, forced_ids)
  -> webui/app_api/cg.py（CgMixin，写操作前 is_game_running() 拒绝）
  -> webutils/cg/save.py（注册表取 key/iv -> AES 解密 -> 改 _forcedCharacterCgIdList -> 加密写回）

扫描/预览/替换（方案 A）:
  JS: api.cg_scan_ids(modal.id, force)（ProgressModal 进度 + 取消；「强制全量重扫」复选框；返回 uncached/lockable 列表）；api.cg_apply（方案 A forced 对象）/ cg_inject_pool / cg_remove_pool（方案 B 解锁池）/ cg_preview(cg_id) / cg_replace(cg_id, img, modal.id) / cg_restore(cg_id)
  -> webutils/cg/bundle.py（ThreadPoolExecutor 增量扫 __data——v3 缓存按 bundle 路径键控（{version:3, scanned_at, bundles:{path:{size,hits}}, catalog:[...]}），同路径 bundle 不可变前提：路径存在+size 一致即跳过（零 UnityPy 打开），失效路径驱逐并清理 originals 还原数据，force=True 全量重扫，v1/v2 旧缓存（BG/ 错误 ID）作废重建，replace/restore 后同步 bundle size 防误重扫；ID = Story_CG/<名>/Unit_CG/<名>（container Story/CG/、Unit/CG/ 决定前缀）；catalog_S1.json 正则提取全量 ID 并入（未缓存仅可锁定）；Sprite 贴图引用取 typetree m_RD.texture（Unity 6 无 m_RenderDataKey PPtr）；
     替换 = set_image(原 format/mipcount) -> tex.save() -> bundle.save(packer="original") + version_player="limbus_modded"；
     原贴图字节留存 cache_path/cg/originals/ 供还原）

Files: `webui/sections/cg.html`, `webui/js/cg.js`, `webui/js/risk-gate.js`（RISK_SERVICES.cg）, `webui/app_api/cg.py`,
      `webui/app.py`, `webutils/cg/save.py`, `webutils/cg/bundle.py`, `webutils/cg/__init__.py`, `webutils/__init__.py`,
      `webui/index.html`, `webui/sections/preload.js`, `webui/js/utils.js`, `webui/guide/cg.md`,
      `webui/css/components.css`（cg-chip/cg-list）, `.github/InitCode.py`（js_files）, `tests/test_cg_save.py`
