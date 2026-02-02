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

