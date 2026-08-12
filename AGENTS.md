# Project Knowledge Base

Before you grep or explore blindly, check these pre-built docs for rapid orientation.

## Quick Reference (AI-First)
- `.claude/docs/architecture.md` — Project overview, tech stack, layered architecture, design patterns, key interfaces
- `.claude/docs/modules.md` — Source directory map: every key file listed with its purpose
- `.claude/docs/key-paths.md` — Feature-to-code traces: call chains from user click to backend execution
- `.claude/docs/dev-guide.md` — How to run, build, test, and common development patterns

## When to Read What
- Starting a new task or unfamiliar with the codebase: read `architecture.md` + `modules.md`
- User asks "where is X implemented" or "how does feature Y work": read `key-paths.md`
- User asks how to run, build, test, or debug: read `dev-guide.md`
- Need deeper understanding of rationale and decisions: read `docs/architecture.md`
- Need detailed setup or release instructions: read `docs/development.md`

## Maintenance
After completing a task with significant code changes (new/renamed files, new features, new entry points, new dependencies), or when making structural changes to files, you MUST update the relevant `.claude/docs/` file(s) to reflect the changes. Update the `<!-- Last updated: YYYY-MM-DD -->` comment at the top of any file you modify.

# Project Rules

- When trying to editing `build.ps1`, go to `\prompts\build.ps1.md` to check the rules. Do not read it when not trying to editing `build.ps1`.
- When modifying the build process (compile flags, linker options, C source structure, etc.), you MUST update both `build.ps1` AND `.github/workflows/release.yml` in sync. These two files share the same gcc compile commands and should always stay consistent.
- When adding a new JS file under `webui/` (or moving it into the bundle scope), you MUST add it to the `js_files` list in `.github/InitCode.py` (the `js/bundle.js` bundling step). Files missing from this list are silently excluded from the packaged app, causing undefined reference errors at runtime (e.g. `quickStartManager` was undefined because `quick-start.js` was not bundled). Keep the order consistent with `<script>` order in `webui/index.html`.
- When adding or modifying configuration items that need hover tooltips, go to `\prompts\tooltip.md` to check the rules. Do not read it when not working on tooltip-related changes.
- **Launcher 集成规范**: 对于"需要在别处配置详情、但可集成进 Launcher"的功能（如文本美化、调爪文本、游戏资源预下载、游戏加速等），决定是否集成的复选框**必须且只能**放在 `webui/sections/launcher-config.html`（放入「工作模式配置」卡片，可附"相关设置请在 XX 页面配置"提示）；源页面只放集成功能介绍 + 跳转按钮（`goAndShow('launcher-config')`）。禁止在 Launcher 页与源页面重复放置同一配置控件（重复面板会导致双份配置、状态不同步）。
- **作弊工具箱 Launcher 集成动态配置规范**: 作弊工具箱插件的 Launcher 集成配置键（私有仓库 registry 的 `enabled_key`，形如 `launcher.work.*`）**不写入** `webui/js/core.js` 的静态 `configKeyMap`，由 `cheat-shell.js renderLauncherPlugins()` 在渲染 Launcher 配置页集成开关时动态处理：① 渲染前先 `await pywebview.api.cheat_core_status()` 触发 `ensure_unlocked()`（持久化密钥自动解锁 → 插件注册），否则新会话未先打开过作弊工具箱页时插件未注册、Launcher 页不显示集成开关；② 用 `configManager.registerConfigKey(checkbox_id, enabled_key)` 把开关动态登记进前端 `configKeyMap`，使其纳入 `bindConfigAutoSave` 自动保存 / `applyConfigToUI` 回填 / 缓存管理；③ change 处理器只保留风险同意门控，未同意回滚时须同步覆盖 `configManager.pendingUpdates` 防止异步门控期间误落盘，值持久化一律经 configManager 单一路径。
- **更新日志维护**: 每当实现一个新功能（含新增/修改行为的功能改动）时，必须编辑 `webui/assets/update.md`，在当前最新版本章节下追加对应条目（或在尚无版本章节时新增章节），保持与现有条目一致的格式与语气。