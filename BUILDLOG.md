# BUILDLOG

Technical build notes intended for iterative zip handoffs.

---

## 2026-02-01
- Branch: dev
- Version: 5.43.1-beta.1
- Build ID: zip-handoff
- Changes:
  - WebUI Discovery: reset persisted discovery state on WebUI startup.
  - CLI: added `self-test` and `self-test-output`.
  - Codebase: added standardized file headers across code files.
- Notes:
  - Discovery state is now intentionally cleared on each restart/update of the WebUI service.
