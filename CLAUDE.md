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
After completing a task with significant code changes (new/renamed files, new features, new entry points, new dependencies), offer to update the relevant `.claude/docs/` file(s). Update the `<!-- Last updated: YYYY-MM-DD -->` comment at the top of any file you modify.

# Project Rules

- When trying to editing `build.ps1`, go to `\prompts\build.ps1.md` to check the rules. Do not read it when not trying to editing `build.ps1`.
- When modifying the build process (compile flags, linker options, C source structure, etc.), you MUST update both `build.ps1` AND `.github/workflows/release.yml` in sync. These two files share the same gcc compile commands and should always stay consistent.
- When adding or modifying configuration items that need hover tooltips, go to `\prompts\tooltip.md` to check the rules. Do not read it when not working on tooltip-related changes.