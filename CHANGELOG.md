# Changelog

All notable changes to this project will be documented in this file.

This project follows Semantic Versioning (SemVer).

---

## v5.0.18 – 2026-01-31

> This release consolidates all changes from **v4.6.0 → v5.0.18** into a single, consistent changelog entry.

### Added
- WebUI: Network scan (“Search network”) for discovering devices across local subnets and VLANs, including progress, results, and an **Add target** flow.
- WebUI: Bulk actions (Enable, Disable, Test, Delete, Clear selection).
- WebUI: Target modals for **Information** and **Edit** (update targets without deleting and re-adding).
- WebUI: Logs viewer with level filters (INFO / WARN / ERROR), copy functionality, and exports (CSV / XLSX / PDF).
- WebUI: Status snapshots (small recent history dots) per target.
- CLI: Additional read/edit commands to support WebUI features.
- Installer: Simple interactive install / update / uninstall wizard for hosted scripts.
- Debugging: Backend diagnostics for “empty table” and state-source issues  
  (systemd journal + `/var/lib/interheart/webui_debug.log`) and `/api/debug-state`.

### Changed
- Status semantics and labels clarified in the UI  
  (e.g. **OK**, **HEARTBEAT FAILED**, **NOT RESPONDING**, **STARTING…**, **DISABLED**).
- Disabled targets now render with a **neutral grey** status indicator (instead of warning yellow).
- Heartbeat failures retry aggressively (every **5 seconds**) to recover as quickly as possible.
- WebUI action and refresh behavior tuned to avoid interrupting user interaction  
  (menus no longer auto-collapse due to state refresh).
- Layout and UX improvements across tables, modals, and controls  
  (more consistent spacing, widths, and readability).
- WebUI systemd service adjusted for local-operations usage so it can read logs and write runtime data without sudo prompts.

### Fixed
- WebUI: Targets no longer require **Run now** before appearing after opening the page.
- WebUI: Prevent targets from briefly appearing and then disappearing on first load  
  (no premature table clearing before the first state poll).
- WebUI: **Run now** modal no longer gets stuck in a false running state  
  (finished processes are reaped; zombie PIDs are treated as completed).
- WebUI: Correct runtime status source is now used  
  (runtime table instead of legacy state data).
- WebUI: Actions menu stability fixes  
  (enable/disable visibility, alignment, and no hidden dropdowns when few rows exist).
- WebUI: Sorting and header rendering regressions fixed  
  (stable header row and correct sort indicators).
- WebUI: Network scan reliability improvements  
  (better subnet discovery, improved progress reporting, cancel / rescan behavior).
- WebUI: Log formatting fixes  
  (clean timestamps and reliable exports).
- Permissions: Resolved issues writing run output files and reading systemd journal logs without interactive sudo prompts.

---

## v4.6.0 – 2026-01-29

> This release consolidates all changes from **v1.0.0 → v4.6.0** into a single, consistent changelog entry.

---

## v5.0.18 – 2026-01-28

### Added
- `interheart run-now` command to force immediate checks of all targets  
  (ignores per-target intervals).
- Runtime progress output written to `/var/lib/interheart/runtime.json` for real-time WebUI updates.
- Run summary modal with clear metrics and progress bar.
- Visual row feedback in the table (active row highlight and success/fail blink).
- Custom confirmation modal for **Remove target**  
  (replaces browser `confirm()`).
- UI polish pass: softer “glass” feel, smoother hover states, and improved dropdown animations.
- **Run now** modal always shows a clear **Running…** state and a visual summary  
  (even when runtime data is unavailable).

### Changed
- WebUI systemd service now runs as `root` (local usage) to:
  - read `journalctl`
  - write runtime and output files
  - eliminate the need for internal `sudo`
- WebUI no longer uses `sudo` internally for `interheart` or `journalctl` calls.
- **Run now** in WebUI always calls `interheart run-now` for consistent behavior.
- **Run now** execution is now **non-blocking**:
  - runs in the background
  - WebUI polls runtime and result endpoints for live status
- Run summary modal now shows meaningful metrics even when no targets were due.
- Add Target modal layout updated:
  - **Add target** and **Cancel** buttons swapped
  - Name / IP / Interval on one line, Endpoint below
- Logs modal:
  - Reads logs using `journalctl -o cat` for clean Interheart output without syslog prefixes
  - Improved header layout and consistent icon rendering

### Fixed
- WebUI **Run now** previously failed with `permission denied` when writing  
  `/var/lib/interheart/run_last_output.txt` – now resolved.
- Logs modal previously failed due to sudo password prompt  
  (`sudo: a terminal is required`) – eliminated.
- **Run now** progress previously appeared static until completion because the request was blocking – progress now updates live.
- Logs modal **Copy** button icon was missing in some builds – now uses a guaranteed inline SVG.
- Run summary modal previously showed `0/0` and felt inactive when no targets were due – corrected.
- **Run now** modal previously appeared “inactive” with no visible updates – now reliably updates during and after execution.
