# BUILDLOG

## Build 5.43.0-beta.6 (2026-02-01)

- WebUI Discovery UI/UX pass (pause/resume, progress animation polish, layout tweaks).
- Backend: discovery status/pause/resume endpoints + tuned nmap safe profile.

Technical build notes intended for iterative zip handoffs.

---

## 2026-02-01
- Branch: dev
- Version: 5.43.0-beta.4
- Build ID: zip-handoff
- Changes:
  - WebUI Discovery: scan UX pass (progress bar effects, spacing, clearer list layout, safer Stop).
  - WebUI Discovery: nmap execution tuned (parallelism + per-CIDR timeout) for slightly faster scans and fewer hangs.
  - CLI: `self-test` and `self-test-output` available for quick validation and log retrieval.
- Notes:
  - Discovery state is now intentionally cleared on each restart/update of the WebUI service.

- 2026-02-01 | dev | 5.43.0-beta.6+build.1 | ui-build
  - Fix discovery progress animations: dotted shimmer layer under fill, green pulsing fill, hide progress until start.
  - Fix Stop/Resume flow: pause/resume uses correct PGID signalling; Stop now pauses with confirmation; Resume button works.
  - Fix discovery layout stability: ensure KPI row stays inline (Subnets/Found), keep controls aligned to the right; minor spacing cleanup.
  - Files: webui/templates/index.html, webui/static/app.css, webui/static/app.js, webui/app.py

- 2026-02-02 | dev | 5.43.0-beta.6+build.2 | bugfix
  - Fix Discovery regressions: missing Flask g import, incorrect worker running check, missing append_discovery_event alias.
  - Fix Discovery modal layout: removed an extra modal-body close tag so Devices padding is correct.
  - Fix Information modal layout: keep IP/Endpoint labels left aligned, values right aligned.
  - Fix CLI self-test usability: require sudo with clear error; list self-test commands in usage output.
  - Files: webui/app.py, webui/templates/index.html, webui/static/app.css, interheart.sh

- 2026-02-02 | dev | 5.43.0-beta.6+build.3 | bugfix
  - Fix Discovery status endpoint: restore WebUI-compatible schema (status/message/progress/cidrs/found) and re-add missing load_discovery_events_tail helper to stop 500s.
  - Fix Discovery Devices section padding: align CSS classnames and add container padding so list does not touch modal edges.
  - Fix Information modal alignment: force copyable value blocks (IP/Endpoint) to right-align while keeping labels left.
  - Fix CLI self-test reliability: always write selftest-latest.txt even when checks fail; print output path.
  - Files: webui/app.py, webui/static/app.css, interheart.sh

- 2026-02-02 | dev | 5.43.0-beta.6+build.4 | bugfix
  - Fix Discovery status endpoint stability: always include events_tail (avoid NameError when progress comes from meta).
  - Fix Discovery start safety: avoid resetting events/meta if a scan is already running/starting; prevent accidental double-start.
  - Fix Discovery Stop UX: treat "No worker running" as stopped and refresh UI state.
  - Fix CLI self-test: restore missing require_root helper in the installed interheart.sh.
  - Files: webui/app.py, webui/static/app.js, interheart.sh, VERSION

- 2026-02-02 | dev | 5.43.0-beta.6+build.5 | bugfix
  - Fix Discovery progress visibility: progress block shows immediately on start and during fallback polling.
  - Fix Discovery Stop action: Stop cancels the scan to prevent pause errors when no worker is running.
  - Files: webui/static/app.js, CHANGELOG.md, BUILDLOG.md, VERSION

- 2026-02-02 | dev | 5.44.0-beta.1+build.1 | ui-build
  - Discovery UI polish: stabilize KPI layout, tighten Subnets/Found spacing, add percent/status column.
  - Discovery controls: Stop now pauses; add Resume and Restart actions with proper state transitions.
  - Progress bar: pulsing green fill + animated dotted remainder; update devices controls UX.
  - Run now: prevent duplicate completion toast.
  - Files: webui/templates/index.html, webui/static/app.css, webui/static/app.js, CHANGELOG.md, BUILDLOG.md, VERSION

- 2026-02-02 | dev | 5.44.0-beta.1+build.2 | bugfix
  - Discovery progress: keep running state during startup and align percent with status text.
  - Discovery pause: handle missing worker by stopping cleanly without error spam.
  - Discovery KPIs: tighten Subnets/Found spacing.
  - Files: webui/templates/index.html, webui/static/app.css, webui/static/app.js, CHANGELOG.md, BUILDLOG.md, VERSION

- 2026-02-02 | dev | 5.44.0-beta.1+build.3 | bugfix
  - Discovery pause: treat missing PID as paused when status is running/starting.
  - Discovery progress: keep running animation independent of progress events.
  - Files: webui/app.py, webui/static/app.js, CHANGELOG.md, BUILDLOG.md, VERSION

- 2026-02-02 | dev | 5.44.0-beta.1+build.4 | bugfix
  - Discovery pause: avoid false "already stopped" toast and preserve paused UI state.
  - Discovery restart: move confirmation to modal and remove pause warning.
  - Files: webui/templates/index.html, webui/static/app.js, CHANGELOG.md, BUILDLOG.md, VERSION

- 2026-02-02 | dev | 5.44.0-beta.1+build.5 | bugfix
  - Discovery pause: retry until worker PID appears; preserve paused state.
  - Discovery resume: restart scan when no worker exists.
  - Discovery results: fallback polling to populate devices when SSE is blocked.
  - Discovery layout: move percent/status left, KPIs right; restart modal matches delete style.
  - Files: webui/templates/index.html, webui/static/app.css, webui/static/app.js, CHANGELOG.md, BUILDLOG.md, VERSION

- 2026-02-02 | dev | 5.44.0-beta.1+build.6 | bugfix
  - Discovery pause: stop running animation and keep Resume/Restart visible while paused.
  - Discovery pause: prevent auto-resume during pause grace window.
  - Files: webui/static/app.js, CHANGELOG.md, BUILDLOG.md, VERSION

- 2026-02-02 | dev | 5.44.0-beta.1+build.7 | bugfix
  - Discovery workers: clean up orphaned workers/nmap on WebUI start to avoid stale scans.
  - Discovery status: reattach to real workers (paused/running) when meta PID is missing.
  - Discovery workers: avoid resetting discovery state inside worker imports.
  - Files: webui/app.py, webui/discovery_worker.py, webui/scan_worker.py, CHANGELOG.md, BUILDLOG.md, VERSION
