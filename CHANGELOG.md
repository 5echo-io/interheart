# Changelog
All notable changes to this project will be documented in this file.

This project follows Semantic Versioning (SemVer).

## [4.4.0] - 2026-01-28
### Added
- `interheart run-now` command to force-check all targets immediately (ignores per-target schedules).
- Runtime progress output to `/var/lib/interheart/runtime.json` for live UI progress updates.
- Custom "Confirm remove" modal (replaces browser `confirm()`).

### Changed
- Run Now WebUI now calls `interheart run-now` by default for expected behavior.
- Run summary modal now displays meaningful metrics and progress based on runtime + forced execution.

### Fixed
- Logs "Copy" button icon was not visible in some builds: now uses a guaranteed inline SVG icon.
- Run summary modal previously showed `0/0` and felt inactive when no targets were due.


## [4.3.0] - 2026-01-28
### Added
- UI polish pass: softer “glass” feel, smoother hover states, and improved dropdown animation.
- Run Now modal now shows a clear “Running…” state and always renders a visual summary (even if runtime progress is not available).

### Changed
- Add Target modal: swapped the positions of “Add target” and “Cancel”.
- Logs modal: improved header button alignment and ensured the Copy button always has an icon.

### Fixed
- Run Now modal sometimes appeared “inactive” (no visible updates). It now reliably updates on completion and shows progress state immediately.

## [4.2.0] - 2026-01-28
### Added
- Run summary modal with metrics and progress bar.
- Row visualization: working row highlight + success/fail blink.
- Confirm prompt before Remove action.

### Changed
- “Last sent” renamed to “Last response”.
- Add Target modal layout: Name/IP/Interval on one line, Endpoint below.
- Logs modal: cleaner layout, unified sizing, better filtering/copy UX.
