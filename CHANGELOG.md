# Changelog

All notable changes to this project will be documented in this file.

This project follows Semantic Versioning (SemVer).

---

## [Unreleased]

### Added
- WebUI: Changelog button in footer with modal preview.
- WebUI: API endpoint for changelog preview in the UI.
- WebUI Discovery: modal popup for adding found devices (replaces bottom card form).

### Changed
- WebUI: Information modal copy icons moved to the left.
- WebUI Discovery: restart now resets streaming/polling state for fresh results.
- WebUI Discovery: IP address and Endpoint URL right-aligned in Information modal.
- WebUI: scrollbar styling updated to follow dark mode theme.
- WebUI: "Full changelog" button no longer shows underline.

### Fixed
- WebUI Discovery: resume no longer auto-pauses after successful resume (added grace period).
- WebUI Discovery: pause/resume error toasts only show when status check confirms failure.
- WebUI Discovery: backend prevents auto-pause immediately after resume operation.
- WebUI Discovery: avoid false pause/resume failure toasts when backend state is correct.
- WebUI Discovery: Found counter no longer resets when toggling New devices.
- WebUI Discovery: restart repopulates device list during the next scan.
- WebUI Discovery: keep progress bar in running state during startup.
- WebUI Discovery: Pause handles missing worker without error spam.
- WebUI Discovery: KPI spacing tightened and percent aligned with status text.
- WebUI Discovery: Pause now succeeds when status is running but worker PID is missing.
- WebUI Discovery: Pause no longer reports "already stopped" during active scans.
- WebUI Discovery: Restart confirmation uses a modal instead of a browser prompt.
- WebUI Discovery: Paused state no longer flips back to running automatically.
- WebUI Discovery: Pause waits for worker PID before marking paused.
- WebUI Discovery: Resume falls back to restarting when no worker exists.
- WebUI Discovery: Devices list updates via fallback polling when SSE is blocked.
- WebUI Discovery: Progress layout flipped (percent/status left, KPIs right).
- WebUI Discovery: Pause keeps animations stopped and preserves Resume/Restart buttons.
- WebUI Discovery: orphaned discovery workers are cleaned up on WebUI start.
- WebUI Discovery: status reattaches to running or paused workers even when meta is stale.
- WebUI Discovery: workers no longer reset discovery state on import.
- WebUI Discovery: already-added devices now display their target name for easier identification.
- WebUI Discovery: modal popup now opens correctly when clicking discovered devices (fixed delegated click handler).
- WebUI Discovery: pause/resume no longer shows false "failed" messages (optimistic UI updates with delayed error toasts).
- WebUI Discovery: increased spacing between Subnets and Found KPIs for better readability.
- WebUI Discovery: Pause no longer shows "Pause failed" toast when worker is already stopped or when status is idle/done/cancelled.
- WebUI Discovery: Click handler for discovered devices now properly opens the add modal when clicking on any part of a device item.
- WebUI Discovery: Resume button now hides Reset button when active.
- WebUI Discovery: Reset button properly cancels and kills running/paused workers, allowing fresh scans to start.
- WebUI Discovery: Add device modal redesigned with distinct visual styling (green accent) to differentiate from manual add modal.
- WebUI Discovery: IP address field in add modal is visually locked with lock icon indicator.
- WebUI Discovery: Removed "Restart scan" button (Reset button provides the correct functionality).

## v5.44.0-beta.1 – 2026-02-02

### Added
- WebUI Discovery: Pause/Resume/Restart scan controls.

### Changed
- WebUI Discovery: Progress layout stabilized (percent/status column) and Subnets/Found spacing tightened.
- WebUI Discovery: Progress bar visuals improved (pulsing green fill + animated dotted remainder).
- WebUI Discovery: Devices list controls redesigned for cleaner search/toggle UX.

### Fixed
- WebUI Run now: remove duplicate completion toast.

## v5.43.0-beta.6 – 2026-02-01

### Added
- WebUI Discovery: Pause/Resume flow (Stop pauses the scan; Resume continues without restarting).

### Changed
- WebUI Discovery: Progress bar animation updated (dotted shimmer on unfilled area + gentle green pulse on fill) and progress UI is hidden until a scan starts.
- WebUI Discovery: Layout tweaks for clearer hierarchy (KPIs left, controls right, spacing adjustments).
- Discovery: "safe" nmap profile tuned for slightly faster scans (lower host timeout, no scan delay, conservative parallelism).

### Fixed
- WebUI Discovery: Button states and device list behavior improved when pausing/resuming and when starting a new scan (clears previous run events).
- WebUI Discovery: Fixed backend regressions that prevented Scan/Stop from working (worker status checks + pause/resume event logging).
- WebUI Discovery: Devices section padding restored (removed an extra modal-body close tag).
- WebUI: Information modal copy fields now keep labels left-aligned while values (IP/URL) are right-aligned.
- CLI: `interheart self-test` now fails fast with a clear message when not run with `sudo`.

## v5.43.0-beta.5 – 2026-02-01

### Added
- CLI: `interheart self-test` and `interheart self-test-output` for quick validation and log retrieval.

### Changed
- WebUI Discovery: Refined scan UX (progress bar effects, spacing, clearer device list layout, safer Stop action).
- WebUI Discovery: Scan execution tuned to be a bit faster, while keeping a conservative per-subnet timeout to avoid hangs.

### Fixed
- WebUI Discovery: Persisted discovery state is reset on WebUI startup to avoid showing stale "Cancelled" state after restart/update.
- WebUI Discovery: Start/Stop button state now correctly returns to “Scan now” after cancel/complete.

## v5.43.0-beta.3 – 2026-02-01

### Fixed
- WebUI Discovery: Progress (percent + bar) now advances reliably even when a scanned subnet contains no devices (progress is persisted per-CIDR, not only on "device found").

## v5.43.0-beta.1 – 2026-02-01

### Added
- Backend: Lightweight debug snapshot system (always writes `/var/lib/interheart/debug_state.txt`, optional verbose logging with `INTERHEART_DEBUG=1`).
- CLI: `interheart debug` command to dump snapshot (optionally `--follow` and `--json`).

### Removed
- WebUI: Discovery “Live feed” section.

### Changed
- WebUI: Opening Discovery no longer attaches to polling/streaming unless a scan is actually running (prevents “Discovery looks active” on load).


## v5.42.52 – 2026-02-01

### Added
- CLI: `interheart debug` (and `--follow`) for quick service + journal output to support troubleshooting from terminal.

### Fixed
- WebUI: Fixed a JavaScript syntax error that broke Actions menus, multi-select bulk actions, and the Logs viewer.

## v5.42.51 – 2026-01-31

### Added
- WebUI Discovery: Live feed panel showing latest scan activity (new devices + scan status).
- WebUI Discovery: Stop-after-N-subnets toggle to limit scan scope.
- WebUI Discovery: Progress percent label and progress bar synced to scan progress.

### Improved
- WebUI Discovery: UI updates are rate-limited to reduce lag during large scans.
- WebUI Discovery: Scan start is manual (does not auto-start when opening the modal).
- WebUI Discovery: Closing the modal keeps the scan running in the background unless you press Stop.
- WebUI Discovery: Server-side guard prevents multiple concurrent scans (also across multiple browsers).
- WebUI Discovery: Default view is “New devices”; use “All results” to expand.
- WebUI: Search fields show a subtle Clear button only when text is present.
- WebUI Discovery: Selected device is highlighted; clicking it again deselects.

### Fixed
- WebUI Discovery: Debug action no longer crashes due to undefined `discoverProfile`.

---

## v5.31.50 – 2026-01-31

### Improved
- WebUI: Discovery is now shown in a **modal** (consistent with other dialogs) for cleaner UI/UX.
- WebUI: Discovery defaults to **New devices** view, with a quick **Show all** button.
- WebUI: Discovery scan settings simplified to a single **Safe** mode, and default scan cap lowered to reduce server load.
- WebUI: Added subtle **Clear** buttons in filter inputs for faster cleanup.
- WebUI: Actions menu ordering adjusted so **Edit** sits directly above **Delete**.

### Fixed
- WebUI: Discovery no longer shows duplicate device rows (deduped by IP).
- WebUI: Discovery progress and counters (Found/Subnets) stay in sync with real results.
- Backend: Discovery cancel is now much faster (kills the discovery worker process group).

---

## v5.25.47 – 2026-01-31

### Added
- WebUI: Discovery debug panel now includes a **Copy** button for quickly copying the full debug output.

### Fixed
- WebUI: Discovery Start now reflects the real backend state (handles "already running" correctly and keeps UI in sync).
- WebUI: Discovery progress updates reliably by starting fallback polling immediately (covers environments where SSE silently stalls).
- WebUI: Prevented duplicate Start requests by guarding against re-entrant Start clicks.

---

## v5.25.46 – 2026-01-31

### Fixed
- WebUI: Discovery start no longer crashes due to an undefined "targets" variable (uses lastTargets).

---

## v5.25.45 – 2026-01-31

### Added
- WebUI: Discovery **Debug** button that runs diagnostics (nmap presence, effective interface, CIDR preview, worker status, recent events, and a quick nmap smoke test) and prints copyable output.

### Improved
- WebUI: IP column sorting now defaults to **ascending** on the first IP click (no immediate flip to descending).

### Fixed
- WebUI: Discovery progress fallback polling now works correctly when SSE is blocked (the status endpoint returns the fields the UI expects).

---

## v5.23.45 – 2026-01-31

### Fixed
- WebUI: Table sorting now triggers reliably on header clicks by using a direct global sort handler (fallback for environments where delegated clicks don’t fire).

## v5.23.44 – 2026-01-31

### Fixed
- WebUI: Sorting now works even when the backend state hasn’t loaded yet (hydrates targets from the server-rendered table instead of rendering an empty list).

## v5.23.43 – 2026-01-31

### Fixed
- WebUI: Table sorting headers are now bound using **event delegation**, ensuring clicks always register (even when the table re-renders or you click inner header text).


## v5.23.42 – 2026-01-31

### Fixed
- WebUI: Table sorting now works reliably on first load (no more silent failure when the script loads before the table exists).
- WebUI: Default sort is now **IP (ascending)**.
- Discovery: The selected interface is now respected end-to-end (CIDR selection + nmap execution), preventing scans from accidentally running via VPN/overlay routes.

### Added
- WebUI: Discovery now includes an **Interface** dropdown (Auto / eth0 / wlan0 / etc.), populated from the server.

### Changed
- WebUI: Actions menu order: **Test** now appears above **Edit**.
- WebUI: “Run now” modal: removed the **Details** section (it was unreliable and confusing).

## v5.20.39 – 2026-01-31

### Fixed
- WebUI: Discovery **Start** no longer latches onto VPN/overlay networks (e.g. NetBird). Discovery now prefers **private (RFC1918)** subnets and skips common overlay interfaces by default.
- WebUI: Run modal: **Checked** now starts at **0** and reflects actual work (no more pre-populated count on “Run now”).
- WebUI: Sorting is now consistent: click column titles to sort, and default sort is **Last ping (asc)**.
- WebUI: Information modal: click **Endpoint URL** or **IP** to copy; a subtle copy icon appears on hover (no extra button required).

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
