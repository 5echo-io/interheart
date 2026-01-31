## 4.10.16 - 2026-01-31

- Fix: Prevent WebUI from wiping the targets table on first load when `state.db` exists but has an empty `targets` table (falls back to CLI if CLI has targets).

## 4.10.15 - 2026-01-31

- Fix: WebUI table now populates immediately on page load even before the first-ever run (fallback to CLI when state DB is missing).
- Fix: “Run now” modal no longer gets stuck in a fake running state (reaps finished CLI process; treats zombie PID as finished).
- UX: Run now live line no longer overwrites useful progress output with a generic “Running…”.

## 4.10.14 - 2026-01-31

- Fix: WebUI `/state` now reads the **real** runtime table (`runtime`) instead of legacy `state` table, so targets render immediately without needing **Run now**.
- Fix: Information + Edit modals now populate correctly again (`/api/info` added + DB-backed).
- Fix: Enabled/Disabled status in UI now follows `targets.enabled` + `runtime.status` reliably (no more "everything looks disabled").

## 4.10.13 - 2026-01-31

- Fix: WebUI no longer clears the targets table on transient `/state` errors (uses last known good state).
- Fix: Enabling a target keeps **STARTING** (even if DB still reports last_status=`disabled`) until the first OK / NOT RESPONDING.
- Fix: Targets no longer get stuck visually in **DISABLED** after Enable/Run now.

## 4.10.12 - 2026-01-30

- Fix: WebUI target listing/status parsing updated to match current CLI table format (targets now render immediately on page load).
- Fix: Actions menu now correctly shows only **Enable** or **Disable** (never both), even before the first refresh poll.
- UI: Status label updated from **FAILED** to **NOT RESPONDING**.

## 4.10.11 - 2026-01-30

- Fix: WebUI regression where targets table/footer could disappear due to malformed HTML markup.
- Fix: Restored correct page structure so existing targets render normally (no data loss).

## 4.10.10 - 2026-01-30

- Fix: New targets start in **STARTING** (no initial UNKNOWN).
- Fix: Enable keeps **STARTING** until first OK / NOT RESPONDING.
- Fix: Bulk **Delete** always requires confirmation modal.
- Fix: Logs modal shows clean lines (timestamp + message only).
- UX: Endpoint URL shows copy icon on hover (click to copy).
- UX: Removed row side-panel workflow (back to modal-first).
- UX: Uptime history now renders striped ticks (green / yellow / red) and windows align to local midnight.

## v4.10.9
- Fixed: **Name** column now matches the row height exactly (no more taller “Name” cells).
- Fixed: Hover behavior: checkbox shows, and the ping check/X icon hides while hovering or when the row is selected.
- Fixed: Actions menu **Enable/Disable** item is properly left-aligned (keeps flex layout when toggled).
- UX: Side panel is now **solid (not transparent)**, uses full height, and opens with a subtle **backdrop blur/dim** (click backdrop to close).
- UX: Target information modal: **Endpoint** moved to full-width and “Live status” swapped to the side.
- Run now: “Show details” stays **collapsed** while the run is active (no auto-open).
- Logs: Added **timestamps** (journalctl short-iso) so the log view is actually useful for debugging.
- UX: Bulkbar is now **sticky** while scrolling (stays at the top of the card).
- UX: Keyboard shortcuts: **Esc** closes side panel/modals, **Enter** toggles side panel for focused/selected row.

## v4.10.8
- Fixed: Restored **1s row blink** on new ping (was accidentally removed) while keeping the check/X indicator visible for **5s**.
- Fixed: Cleaned up a broken CSS block that could cause weird layout behavior.
- UI: Pinned row details panel no longer reserves empty space — it now **slides in from the right** as an overlay.
- UI: Name column now stays a consistent height (long names use ellipsis + tooltip).
- UX: Bulk bar shows **Delete** and **Clear** buttons again (always visible when 1+ rows selected).
- UX: “Remove” renamed to **Delete** across UI (Actions menu + bulk bar + confirm modal).
- UX: Side panel actions are now **icon buttons with tooltips**, and only the relevant **Enable/Disable** toggle is shown.
- UX: Clicking the same row again closes the side panel.

## v4.10.7
- Fixed: Row selection + Actions menu no longer causes subtle column misalignment (layout is now stable while interacting).
- UI: Ping feedback is now **icon-only** (no full-row blink) and the check/X indicator stays visible for **3s**.
- UI: Status chip content is now left-aligned (keeps the same width, reads cleaner).
- UI: Enable/Disable/Clear selection state no longer gets “stuck” after clearing bulk selection.
- UI: Dark-mode checkbox styling updated to blend with the theme.
- UI: “Name” header aligned with target names (selection gutter no longer shifts the header).
- Run now: Quiet mode by default + optional “Show details” fold-out for recent output.
- UX: Added **Pinned row details** side panel (click a row to inspect, with quick actions + log excerpt).

## v4.10.6
- Fixed: Removed a JS syntax regression that could break Actions/selection interactions.
- UI: Row selection should be clickable again (no invisible overlay blocking the checkbox).
- UI: Added **STARTING..** state + immediate verification ping when enabling a disabled target.
- Heartbeat: On heartbeat failure, interheart retries every **5s** until success (faster recovery), while keeping normal intervals for ping failures.
- Network scan: Improved subnet discovery by including routed RFC1918 networks (VLAN-aware) and improved Scan Now behavior (no forced restart unless “Scan again”).
- UI: Added lightweight 3-day **status snapshots** (mini dots) per target.
- Styling: Dark-theme styling for scan dropdowns + status chip width adjustments.

## v4.10.4
- UI: Bulk selection bar now animates in smoothly (fade + slide down) instead of popping in.
- UI: Selection checkbox moved into the **Name** column with a reserved gutter (no layout shift) + subtler styling.
- UI: Status labels renamed for clarity: **UP → OK** and **PING FAILED → FAILED**.
- Logs: Fixed PDF/XLSX exports by installing missing Python deps (**reportlab**, **openpyxl**) + widened the Download button.
- Actions: Keep the action dropdown stable during live refresh (no auto-close while you interact).
- Network scan: Fixed subnet detection (scan uses proper network CIDRs) + scan no longer auto-starts on open; user explicitly clicks **Scan now**.
- Network scan: Scan can keep running in the background; modal provides **Abort** while running.

## v4.9.3
- Fixed: Table header layout is back to a proper single header row (no more stacked headers) + clickable sorting works as intended.
- Fixed: Actions menu + row selection no longer closes/resets every 2s refresh (refresh now updates cells without rebuilding the whole table).
- UI: Row selection checkbox is now smaller, more subtle, and fades in on hover (and highlights selected rows softly).
- UI: Actions menu icons refreshed to cleaner minimalist line icons.
- Logs: Replaced 3 download buttons with a single **Download** dropdown (CSV / XLSX / PDF).
- Logs: PDF export now includes a small footer brand: **Powered by 5echo.io**.
- Network scan: More reliable discovery — prefers ARP scan via sudo/root when possible, otherwise uses ICMP/TCP ping scan fallback.
- Network scan: Scan no longer restarts just because you close/reopen the modal; it keeps running in the background until finished or cancelled.
- Network scan: Added simple scan controls (scope + speed) and removed the noisy “Requires nmap” hint.
- Run now: Removed the extra live progress feed from the modal (kept the run summary clean).
- Installer: Added a simple interactive install/update/uninstall wizard script (for hosting at scripts.5echo.io).

## v4.9.2
- Fixed: Table headers + sorting reworked (headers are stable again, clickable, and show sort direction).
- Fixed: Target list rendering no longer loops/crashes (filter + sort play nicely together).
- Network scan: Now streams nmap output live, shows current activity, and supports **Cancel scan** + **Scan again**.
- Network scan: Found devices now include best-effort **MAC/vendor**, guessed **type** (printer/camera/switch/device) and a simple confidence score.
- UX: Scan can keep running even if you close the modal (open again anytime to see progress/result).
- Add target: Smart assist suggests **Name** from reverse DNS when you type an IP.
- Logs: Added level filter chips (ERROR/WARN/INFO), “Copy filtered” stays in sync, and exports: **CSV / XLSX / PDF**.
- Run now: Added a compact real-time “progress feed” while a run is active.
- Bulk actions: Select multiple targets to Enable/Disable/Test/Remove in one go (bulk bar appears only when something is selected).

## v4.9.1
- Fixed: “Run now” no longer crashes WebUI (“out is not defined”) and progress updates correctly.
- UI: Sorting is now done by clicking table headers (Name, IP, Status, Interval, Last ping, Last response).
- UI: Confirm remove modal simplified (removed redundant Close button) and added 3s safety countdown before “Remove” is enabled.
- UI: Information modal no longer shows “pings sent” in Uptime text; added small uptime trend sparkline.
- UI: Added clearer status split: **UP**, **PING FAIL**, **HEARTBEAT FAIL** (ping OK but endpoint failed).
- Network scan: Improved progress feedback, error handling, and cleaner layout for Subnets/Found/New counters.
- UX: Sticky table header + subtle micro-animations and loading shimmer for a more modern feel.

# Changelog
All notable changes to this project will be documented in this file.

This project follows Semantic Versioning (SemVer).

## [4.9.0] - 2026-01-30

### Added
- WebUI: **Search network** modal for discovering devices across all local subnets (VLANs), with live progress and “Add target” flow.
- WebUI: Table **sorting** control (default: IP ascending).

### Fixed
- WebUI: Actions menu now correctly shows **Enable** only for disabled targets and **Disable** only for enabled targets.
- WebUI: Toast notifications now appear **bottom-right** (no longer covering menu buttons).
- WebUI: Test result popups are now human readable (e.g. “Failed. No response from <target>”).
- WebUI: Run-now progress now counts all targets correctly and uses **Force run** to check everything when you click “Run now”.
- WebUI: Logs view is cleaner and easier to scan.

### Changed
- WebUI: “Add” button renamed to **Add target**.
- WebUI: Logs button moved to the footer.

## [4.8.1] - 2026-01-29

### Added
- WebUI: **Target information** modal with full target details:
  - Name, IP, endpoint (full URL)
  - Enabled / disabled state
  - Interval
  - Last ping, last response, last latency
  - Next due (parsed from runtime state)
- WebUI: **Edit target** modal allowing live changes to:
  - Name, IP, endpoint, interval, enabled state
  - Validation before submit (IP + http/https endpoint)
- WebUI: **Activate selected** bulk action.
- WebUI: **Disable / Activate** per-target toggle in Actions menu.
- WebUI: **Copy actions** inside Information modal (name, IP, endpoint).
- WebUI: **Last run summary** dropdown/tooltip in top card
  - Parses and displays: total, due, skipped, ping_ok, ping_fail, sent, curl_fail, disabled, force, duration_ms.
- CLI: `get <name>` command for reading full target details.
- CLI: `edit <old_name> <new_name> <ip> <endpoint_url> <interval_sec> <enabled>` command.
- Runtime: `next_due` is now persisted and exposed to WebUI.

### Changed
- WebUI: Removed **Latency** and **Endpoint** columns from main table
  - Moved to Target information modal for cleaner overview.
- WebUI: Interval column width reduced.
- WebUI: Checkbox styling improved to match dark UI.
- WebUI: Table headers are now clickable for client-side sorting:
  - Name, IP, Status, Interval, Last ping.
- WebUI: Disable confirmation now uses a **toast with Undo** instead of a blocking modal.
- CLI: `run-now` outputs a single-line summary parsed by WebUI.

### Fixed
- WebUI: Fixed error `Unknown command: disable-selected`
  - Bulk disable/activate now iterates per target using existing CLI commands.
- CLI: Runtime state now stays consistent when targets are edited or renamed.
- UI: Action menu now correctly reflects enabled/disabled state.


## [4.7.0] - 2026-01-29

### Added
- WebUI: Top “mini cards” showing **Up / Down / Unknown** totals and **Last run duration**.
- WebUI: **Search** (name/IP/status) + **Quick filters** (All/Up/Down/Unknown/Disabled).
- WebUI: Bulk actions:
  - **Run selected** (run checks only for selected targets)
  - **Disable selected** (disable selected targets)
- CLI/state: **Latency measurement (ms)** from ping, stored in state and displayed in WebUI.

### Changed
- Target config extended with an `ENABLED` flag:
  - New format: `NAME|IP|ENDPOINT_URL|INTERVAL_SEC|ENABLED`
  - Backwards compatible parsing of older entries without the flag.
- WebUI uses `run-now --targets ...` for “Run selected” to avoid scanning the whole list.

### Fixed
- Sudo/journalctl handling improved (cleaner logs and fewer permission-related failures).
- More robust parsing and UI updates for runtime/state fields (including latency + disabled state).


## [4.6.0] - 2026-01-29
### Fixed
- WebUI "Run now" no longer fails with permission denied writing `/var/lib/interheart/run_last_output.txt`.
- Logs modal no longer fails due to sudo password prompt (`sudo: a terminal is required...`).

### Changed
- WebUI systemd service now runs as root (local-only use case) so the UI can read journal and write runtime/output files without sudo.
- WebUI no longer uses `sudo` internally for `interheart` and `journalctl` calls.


## [4.5.0] - 2026-01-28
### Changed
- Logs modal now reads journal output using `journalctl -o cat` to remove syslog prefixes and show clean interheart log lines only.
- Run Now is now non-blocking: WebUI starts `interheart run-now` as a background process and polls runtime + result endpoints for real-time progress.

### Fixed
- Run Now progress previously appeared static until completion because the web request was blocking. Progress now updates while running.


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
