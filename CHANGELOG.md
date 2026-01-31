# Changelog

All notable changes to this project will be documented in this file.

This project follows Semantic Versioning (SemVer).

---

## v5.20.35 – 2026-01-31

### Fixed
- WebUI: Discovery **Start** button now always triggers a backend request (added a safe fallback hook so clicks can’t silently do nothing).
- WebUI: Table sorting is restored even if the initial `/state` fetch fails (sort handlers are now bound on server-rendered rows too).
- WebUI: Status snapshots are now part of the server-rendered table as well (no more “layout shift” / missing dots before first refresh).

### Improved
- WebUI: Discovery side panel is wider for easier use.
- WebUI: “Show only new” toggle is now clearly **dark-mode** styled.
- WebUI: Status chip alignment tightened: fixed width, left-aligned text, right-aligned dots.

## v5.17.31 – 2026-01-31

### Fixed
- WebUI: Actions dropdown icons are back to the original **minimal inline SVG** style (no emoji icons).
- WebUI: Network discovery **Start** now actually starts the worker process (missing `webui/discovery_worker.py` prevented discovery from running).

### Improved
- WebUI: Status column is now **fixed width** (matches the widest status label) for a cleaner table.
- WebUI: Status snapshots (last 3 dots) are **right-aligned**, while status text stays left-aligned.

## v5.16.30 – 2026-01-31

### Fixed
- WebUI: **First load** now binds all table handlers (actions menu, multi-select, interval edit) immediately – no more “works only after Run now”.
- WebUI: Status text is consistent on first load (**OK / NOT RESPONDING / DISABLED**) instead of raw **UP/DOWN**.
- WebUI: Actions menu now reliably works on first load (and stays working after live refresh).
- WebUI: Restored the **minimalist icons** (no SVG swap after refresh).
- WebUI: Network discovery **Start** now always fires and shows clear feedback on **start / error / running**.
- WebUI: Discovery now falls back to **/api/discover-status polling** if SSE is blocked by a proxy, so progress still updates.

### Improved
- WebUI: Discovery panel is a bit wider, and the “Show only new” toggle is darker in idle state.
- WebUI: Added automatic **live polling** of /state at the configured refresh interval.

## v5.16.24 – 2026-01-31

### Fixed
- WebUI: **Network discovery Start button** now works (a JS scoping bug prevented the request from firing).

### Improved
- WebUI: **Network discovery** panel is **wider** for easier use.
- WebUI: **Show only new** toggle is now a proper **dark-mode switch**.
- WebUI: Added **Scope** selector: Auto (gateway first) / RFC1918 10.* / 172.16-31.* / 192.168.* / All / Custom CIDR.
- WebUI: Added a second status line showing **what is being scanned right now** (CIDR + host range).
- WebUI: Discovery results rendering is **debounced** to avoid UI lag when many devices are found.

### Changed
- Backend: Discovery scan plan now starts **gateway-first** and can follow RFC1918 ordering when a scope is selected.
- Backend: Discovery SSE stream now emits a dedicated **“scanning …”** status per subnet for true real-time feedback.

## v5.9.23 – 2026-01-31

### Rebuilt
- WebUI: **Network discovery** rebuilt again – now a **side panel** (no popup-stress) with **real-time** results via SSE.
- Backend: Discovery runs as a **separate worker** using **nmap only**, to avoid UI lag and to keep scanning even if you close the panel.

### Added
- Device list filtering (name / IP / MAC / vendor) + **Show only new** toggle.
- Clear chips in the list: **New**, **Already added**, **Added now**.
- Better add-flow: click a device → prefilled name + IP, endpoint suggestions, **Add & keep open**.

### Improved
- Safer scanning defaults (profile: Safe/Normal/Fast) + automatic subnet chunking to /24 with a safety cap.
- Smoother UX: progress bar, status line, and "Search again" appears only when a scan is finished.

### Fixed
- Network discovery no longer blocks the browser thread / causes lag during scan.
- "Failed to fetch" is now surfaced as a readable error in the panel when the backend fails.

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

---

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

---

## v5.0.18-stable – 2026-01-31

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

---

## v4.6.0-stable – 2026-01-29

> This release consolidates all changes from **v1.0.0 → v4.6.0** into a single, consistent changelog entry.

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
