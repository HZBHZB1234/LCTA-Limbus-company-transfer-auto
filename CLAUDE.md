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