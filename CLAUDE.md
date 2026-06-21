# Project Rules

- When trying to editing `build.ps1`, go to `\prompts\build.ps1.md` to check the rules. Do not read it when not trying to editing `build.ps1`.
- When modifying the build process (compile flags, linker options, C source structure, etc.), you MUST update both `build.ps1` AND `.github/workflows/release.yml` in sync. These two files share the same gcc compile commands and should always stay consistent.
- When adding or modifying configuration items that need hover tooltips, go to `\prompts\tooltip.md` to check the rules. Do not read it when not working on tooltip-related changes.