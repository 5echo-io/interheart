# Changelog

All notable changes to this project will be documented in this file.

This project follows Semantic Versioning (SemVer).

---

## v5.0.18 – 2026-01-31

> This release consolidates all changes from **v4.6.0 → v5.0.18** into a single, consistent changelog entry.

### Added
- WebUI: Network scan (“Search network”) for discovering devices across local subnets/VLANs, with progress, results, and “Add target” flow.
- WebUI: Bulk actions (Enable, Disable, Test, Delete, Clear selection).
- WebUI: Target modals for **Information** and **Edit** (update targets without deleting/re-adding).
- WebUI: Logs viewer with level filters (INFO/WARN/ERROR), copy, and exports (CSV/XLSX/PDF).
- WebUI: Status snapshots (small recent history dots) per target.
- CLI: Additional read/edit commands to support the WebUI features.
- Installer: Simple interactive install/update/uninstall wizard for script hosting.
- Debug: Backend diagnostics for “empty table” / state source issues (journal + `/var/lib/interheart/webui_debug.log`) and `/api/debug-state`.

### Changed
- Status semantics and labels made clearer in UI (e.g. **OK**, **HEARTBEAT FAILED**, **NOT RESPONDING**, **STARTING..**, **DISABLED**).
- Disabled targets now render with a **neutral grey** status indicator (not warning yellow).
- Heartbeat failures retry aggressively (every **5 seconds**) to recover as fast as possible.
- WebUI actions/refresh behavior tuned to avoid interrupting user interaction (menus don’t auto-collapse just because state refreshes).
- Layout/UX improvements across table, modals, and controls (more consistent spacing, widths, and readability).
- WebUI systemd service adjusted for local-ops usage so it can read logs/write runtime without sudo prompts.

### Fixed
- WebUI: Targets no longer require “Run now” before showing up after opening the page.
- WebUI: Prevent targets from briefly showing then disappearing on first load (no premature table-clearing before the first state poll).
- WebUI: “Run now” modal no longer gets stuck in a fake running state (reaps finished process; treats zombie PID as finished).
- WebUI: Properly reads runtime status (uses the correct runtime table instead of legacy state data).
- WebUI: Actions menu stability fixes (enable/disable visibility, alignment, and no hidden dropdowns when few rows exist).
- WebUI: Sorting/header rendering regressions fixed (stable header row, working sort direction indicators).
- WebUI: Network scan reliability improvements (better subnet discovery, better progress reporting, cancel/scan-again behavior).
- WebUI: Logs formatting fixes (timestamps cleaned, exports work reliably).
- Permissions: Resolved issues writing run output / reading journal without interactive sudo prompts.

[4.6.0] - 2026-01-29
Fixed
WebUI "Run now" no longer fails with permission denied writing /var/lib/interheart/run_last_output.txt.
Logs modal no longer fails due to sudo password prompt (sudo: a terminal is required...).
Changed
WebUI systemd service now runs as root (local-only use case) so the UI can read journal and write runtime/output files without sudo.
WebUI no longer uses sudo internally for interheart and journalctl calls.
[4.5.0] - 2026-01-28
Changed
Logs modal now reads journal output using journalctl -o cat to remove syslog prefixes and show clean interheart log lines only.
Run Now is now non-blocking: WebUI starts interheart run-now as a background process and polls runtime + result endpoints for real-time progress.
Fixed
Run Now progress previously appeared static until completion because the web request was blocking. Progress now updates while running.
[4.4.0] - 2026-01-28
Added
interheart run-now command to force-check all targets immediately (ignores per-target schedules).
Runtime progress output to /var/lib/interheart/runtime.json for live UI progress updates.
Custom "Confirm remove" modal (replaces browser confirm()).
Changed
Run Now WebUI now calls interheart run-now by default for expected behavior.
Run summary modal now displays meaningful metrics and progress based on runtime + forced execution.
Fixed
Logs "Copy" button icon was not visible in some builds: now uses a guaranteed inline SVG icon.
Run summary modal previously showed 0/0 and felt inactive when no targets were due.
[4.3.0] - 2026-01-28
Added
UI polish pass: softer “glass” feel, smoother hover states, and improved dropdown animation.
Run Now modal now shows a clear “Running…” state and always renders a visual summary (even if runtime progress is not available).
Changed
Add Target modal: swapped the positions of “Add target” and “Cancel”.
Logs modal: improved header button alignment and ensured the Copy button always has an icon.
Fixed
Run Now modal sometimes appeared “inactive” (no visible updates). It now reliably updates on completion and shows progress state immediately.
[4.2.0] - 2026-01-28
Added
Run summary modal with metrics and progress bar.
Row visualization: working row highlight + success/fail blink.
Confirm prompt before Remove action.
Changed
“Last sent” renamed to “Last response”.
Add Target modal layout: Name/IP/Interval on one line, Endpoint below.
Logs modal: cleaner layout, unified sizing, better filtering/copy UX.
