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

---

## v4.6.0 - 2026-01-29

> This release consolidates all changes from **v1.0.0 → v4.6.0** into a single, consistent changelog entry.

## v5.0.18 – 2026-01-28

### Added
- `interheart run-now` kommando for å tvinge sjekk av alle targets umiddelbart (ignorerer per-target intervaller).
- Runtime progress-output til `/var/lib/interheart/runtime.json` for sanntidsoppdatering i WebUI.
- Run summary modal med tydelige metrics og progress-bar.
- Visuell rad-feedback i tabell (aktiv rad, success/fail-blink).
- Egen bekreftelsesmodal for *Remove target* (erstatter browser `confirm()`).
- UI-polish: mykere “glass”-følelse, jevnere hover-states og forbedrede dropdown-animasjoner.
- Run Now-modal viser alltid tydelig **Running…**-tilstand og visuell oppsummering (også når runtime-data mangler).

### Changed
- WebUI systemd-service kjører nå som `root` (lokal bruk) for å:
  - lese `journalctl`
  - skrive runtime- og output-filer
  - eliminere behov for `sudo` internt
- WebUI bruker ikke lenger `sudo` for `interheart`- eller `journalctl`-kall.
- Run Now i WebUI kaller nå alltid `interheart run-now` for forventet og konsistent oppførsel.
- Run Now er gjort **non-blocking**:
  - kjører i bakgrunn
  - WebUI poller runtime- og resultat-endepunkter for live status
- Run summary modal viser nå meningsfulle metrics selv når ingen targets var “due”.
- Add Target-modal:
  - Byttet plass på **Add target** og **Cancel**
  - Name / IP / Interval på én linje, Endpoint under
- Logs modal:
  - Leser nå logger via `journalctl -o cat` for rene interheart-linjer uten syslog-prefiks
  - Forbedret header-layout og konsistent ikonbruk

### Fixed
- WebUI **Run Now** feilet tidligere med `permission denied` ved skriving til  
  `/var/lib/interheart/run_last_output.txt` – dette er nå løst.
- Logs modal feilet tidligere på grunn av `sudo` passordprompt  
  (`sudo: a terminal is required`) – nå eliminert.
- Run Now-progresjon fremstod tidligere som statisk frem til ferdig kjøring fordi requesten blokkerte – progresjon oppdateres nå live.
- Logs modal **Copy**-knapp manglet ikon i enkelte builds – bruker nå garantert inline SVG.
- Run summary modal viste tidligere `0/0` og virket inaktiv når ingen targets var due – dette er korrigert.
- Run Now modal kunne tidligere fremstå som “inaktiv” uten tydelige oppdateringer – oppdaterer nå alltid korrekt under og etter kjøring.
