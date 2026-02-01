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
