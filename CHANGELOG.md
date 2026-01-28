# Changelog
All notable changes to this project will be documented in this file.

This project follows Semantic Versioning (SemVer).

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
