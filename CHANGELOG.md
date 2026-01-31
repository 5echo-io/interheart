# Changelog

All notable changes to this project will be documented in this file.

This project follows Semantic Versioning (SemVer).

---

## v5.3.21 – 2026-01-31

### Improved
- WebUI: **Search network** now uses **nmap only** (no silent fallback), with better timeouts and clearer scan logging.
- WebUI: More reliable subnet discovery by reading routes from **all routing tables** and broadening /32 interface addresses to a practical scan range.
- WebUI: Cleaner scan UX (renamed actions to **Start search / Search again**, clearer device list wording).

### Fixed
- WebUI: API calls now surface readable errors instead of generic **“Failed to fetch”**.
- WebUI: Scan modal now shows an inline error banner when the backend reports a scan error (e.g. missing nmap).

### Notes
- This release intentionally **requires `nmap`** for scanning. If missing, the UI will tell you exactly what to install.

## v5.1.20 – 2026-01-31

### Changed
- WebUI: Rebuilt **Search network** from scratch with a real background worker (keeps scanning even if you close the modal).
- WebUI: Search results now show **all discovered devices** (not only “new”), including **Name, IP, MAC** (when available), and optional vendor.
- WebUI: Clear states in the results list: **Already added** (existing targets) and **Added** (added during the current scan session).

### Fixed
- WebUI: Network scan no longer finishes instantly due to a missing backend worker.
- WebUI: Custom scan scope now works correctly (local + custom ranges).

### Notes
- If `nmap` is installed, Interheart uses it automatically for faster and more accurate discovery.
- MAC addresses are typically only available for devices on the same L2 subnet (across routed VLANs they may show as blank, depending on network setup).

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
- WebUI: Included the missing scan worker entrypoint so “Search network” actually runs (scan_worker.py).
- WebUI: Logs formatting fixes (timestamps cleaned, exports work reliably).
- Permissions: Resolved issues writing run output / reading journal without interactive sudo prompts.

