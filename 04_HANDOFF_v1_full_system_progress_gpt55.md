# v1.0 完整系統進度回報 (GPT-5.5)

## 摘要
- 狀態: completed and deployed
- patch tarball: `patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`
- 本機檢查: `python -m compileall webapp scripts edge` ok, `python -m pytest -q` 2 passed
- 遠端部署: completed on `192.168.1.221:/opt/webitgpt`
- 遠端測試: `pytest -q` 2 passed
- systemd: `webitgpt.service` active, `webitgpt-edge.service` active
- firewall: `8002/tcp` and `9444/tcp` opened
- browser path: local tunnel `http://127.0.0.1:8002/hosts` reaches deployed 221 service
- 實績功能驗證: `scripts/functional_validation.py` 69/69 passed
- 實績報告: `data/functional_validation_latest.json`

## 遠端 smoke
- `http://127.0.0.1:8002/health` ok
- `http://127.0.0.1:8002/ready` ok, Mongo `webitgpt` ok
- `http://127.0.0.1:8002/metrics` ok
- `http://127.0.0.1:8002/api/v1/hosts` rejects missing token and works with Bearer token
- Edge stub `http://127.0.0.1:9444/health` ok
- PC can reach `http://192.168.1.221:8002/health`

## 完成清單
- [x] 1.1 骨架 + Mongo
- [x] 1.2 hosts schema
- [x] 1.3 per-host 目錄 service
- [x] 1.4 Auth + MFA setup/verify + LDAP placeholder + session
- [x] 1.5 `/hosts` 列表頁: filter, paging, saved views
- [x] 1.6 `/hosts/{asset_seq}` 編輯頁
- [x] 1.7 `/hosts/new` 4 入口: single manual, multi manual, CSV file/paste, JSON file/paste, network scan stub
- [x] 1.8 Runner 抽象
- [x] 1.9 自檢: 單台與限量全站 read-only self-check
- [x] 1.10 DEBUG + mask
- [x] 1.11 API v1
- [x] 1.12 superadmin 6+2: feature toggle/audit verify/validation/token pages
- [x] 1.13 AI chat + provider settings
- [x] 1.14 observability
- [x] 1.15 tests + patch

## Phase 2-7 已補進本版的完成品功能
- [x] Phase 2 VMware: vCenter credential UI/API, masked password, inventory API/page
- [x] Phase 3 AIX: ssh_raw platform readiness, platform status page/API, no Ansible YAML path
- [x] Phase 4 AS400: AS400 platform readiness/status, reserved runner boundary
- [x] Phase 5 Housekeeping: task registry, disk alert, backup verify placeholder, dry-run/manual run UI/API
- [x] Phase 6 Compliance: rules collection, default TWGCB-like rules, evaluate_host, findings store, dashboard, CSV export
- [x] Phase 7 Inspections/NMON/Reports/Topology/Notifications: daily inspection run/report, NMON status, executive report summary, topology table, notification channels/test event
- [x] AI/MCP/OpenAPI: MCP manifest/tool endpoint with token scope, OpenAPI auto-doc, AI provider settings

## 59 項實績驗證
- health, ready, metrics
- superadmin login
- MFA setup page
- SuperAdmin feature toggle + audit chain page
- Feature flag update API
- AI provider page
- AI provider settings API with masked API key
- Security audit page + compliance rules
- Housekeeping page + disk alert run
- Notifications page + email test event
- Reports page + summary API
- Topology/dependencies page
- Platforms page + AIX/AS400/VMware status
- VMware page + masked vCenter credential + inventory API
- NMON page + status API
- Inspections page + limited daily inspection run + today API
- MCP manifest + MCP list_hosts tool via `mcp:read` token
- OpenAPI auto-doc
- API token issue by JSON API
- API token issue by SuperAdmin token page
- API v1 rejects missing Bearer token
- API v1 host list with Bearer token
- Hosts page filter + saved views visible
- Saved view create
- Host create, update, soft delete, restore
- Multi-host manual entry
- Seed host self-check
- Limited global self-check
- DEBUG snapshot with masked output
- `phase_readonly_mode` blocks monitored-host writes
- Audit hash chain verify
- CSV import/export
- JSON import
- per-host `meta.json`, self-check file, debug snapshot file written

## 對照 inventory
- [x] 主機列表與 CRUD: `/hosts`, `/hosts/{asset_seq}`, `/api/hosts`
- [x] CSV 範本: `/api/hosts/csv/template`
- [x] CSV 匯入/匯出: `/api/hosts/csv/import`, `/api/hosts/csv/export`
- [x] JSON 匯入: `/api/hosts/json/import`
- [x] 多台手動建檔: `/hosts/import/manual`
- [x] Saved views: `/api/hosts/saved-views`, `/hosts/saved-views`
- [x] 三件套: 編輯 / 自檢 / DEBUG
- [x] 第 4 件套資安: UI stub, Phase 6 實作
- [x] 4 role 基礎: viewer / admin / super / superadmin
- [x] Audit log hash chain: append + verify route
- [x] Edge stub: port 9444, `/health`, `/cmd`
- [x] Soft delete / restore: `/api/hosts/{asset_seq}`, `/api/hosts/{asset_seq}/restore`
- [x] VMware: `/vmware`, `/api/vmware/inventory`, `/api/vmware/credentials`
- [x] Platforms: `/platforms`, `/api/platforms/status`
- [x] Housekeeping: `/housekeeping`, `/api/housekeeping/tasks`, `/api/housekeeping/run/*`
- [x] Compliance: `/security_audit`, `/api/compliance/dashboard`, `/api/compliance/evaluate/*`
- [x] Reports/Topology: `/reports`, `/dependencies`, `/api/reports/summary`
- [x] Inspections/NMON: `/inspections`, `/nmon`, `/api/inspections/*`, `/api/nmon/status`
- [x] Notifications: `/notifications`, `/api/notifications/*`
- [x] MCP/OpenAPI: `/mcp/manifest`, `/mcp/tools/*`, `/api/v1/openapi.json`

## Feature flags 實際註冊
- v3.17 flags: audit, packages, perf, twgcb, summary, security_audit, history, dependencies
- CMDB: cmdb_csv_import, cmdb_saved_views, cmdb_manual_input, cmdb_network_scan, cmdb_extension_fields, cmdb_bulk_actions, cmdb_undo_30s
- Host actions: host_self_check, host_self_check_global, host_debug_snapshot, host_security_audit_button
- Platform: host_type_linux, host_type_windows, host_type_vmware, host_type_aix, host_type_as400
- API/AI/system/compliance/notify flags from `feature_flags.py`
- Coexistence flag: `phase_readonly_mode=True`

## 已知 limitation
- LDAP integration is a placeholder; local `superadmin/change-me` is seeded by bootstrap.
- WinRM command execution is scaffolded, with Phase 1 placeholder response.
- AIX/AS400 deep live collection remains behind platform runner boundaries until real endpoints are provided.
- Network scan, NMON deploy, remediation, package install, SSH key deploy, and other monitored-host write actions are blocked by `phase_readonly_mode` during parallel review.
- Mongo was not available on this PC, so DB seed was not executed locally.
- Functional validation intentionally leaves test hosts and saved views in `webitgpt` for auditability.

## 仍需真實環境接線
- VMware: real vCenter endpoint for live pyvmomi collection.
- AIX: real AIX host or command output corpus for POSIX parser hardening.
- AS400: confirm available protocol (SSH/DDM/ODBC/5250) before live collection.
- Notifications: real SMTP/Slack/Teams/JIRA/Webhook targets.
- Write actions: winner decided後再關閉 `phase_readonly_mode` and enable remediation/NMON deploy/SSH key deploy.

## Overnight continuation update
- Added SuperAdmin user management, password reset, lock toggle, MFA backup codes.
- Added System Health dashboard, Backup manifest, DR dry-run, Patch rollback plan.
- Added dark mode toggle and Alt-key shortcuts.
- Latest functional validation: 69/69 passed.

## Function audit hardening update
- Fixed local usability issue: `127.0.0.1:8002/hosts` tunnel restored and Startup shortcut added.
- Replaced visible mojibake in base navigation and login page.
- Converted visible stubs into usable read-only/dry-run workflows:
  - Host Security button now runs compliance evaluate.
  - Network Scan now gives CIDR preview candidates instead of a disabled stub.
  - Inspections page now has Run inspection now.
  - NMON page now has Preview deploy plan.
  - Reports page now exports summary CSV.
  - SuperAdmin fake tabs replaced with real anchors/links.
- Hardened host schema normalization: accepts Chinese values and common English aliases for status/environment/DC.
- Manual function audit: `data/manual_function_audit_latest.json`, 36/36 passed.
- Latest full functional validation after hardening: `data/functional_validation_latest.json`, 69/69 passed.

## Gap-fill update against 25/145 checklist
- Added visible modules: `/accounts`, `/software`, `/services`, `/ssh-keys`, `/changes`.
- Added APIs: `/api/inventory/<kind>`, `/api/inventory/<kind>/collect`, `/api/ssh-keys/plan`, `/api/changes`.
- Compliance rule types now cover 8 kinds: account, package, port, process, service, file, setting, ip.
- Built-in compliance rules now include 8 defaults: ACC, PORT, SSH setting, FILE, PACKAGE, PROCESS, SERVICE, IP.
- Housekeeping registry expanded to 20 tasks, covering host artifacts, reports, Mongo counters, edge staleness, audit verify, backup verify, patch keep, disk alert.
- Feature flags rewritten with clean labels and expanded to 53 keys.
- Mongo bootstrap collections expanded for inventory/change/nmon/login-attempt records.
- Local verification after changes: `python -m compileall webapp scripts edge` ok, `python -m pytest -q` 2 passed.
- Patch rebuilt locally: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`.
- Deployed after 192.168.1.221 recovered.
- Remote bootstrap wrote the gap-fill schema/rules successfully; `webitgpt.service` and `webitgpt-edge.service` active.
- Latest full functional validation after gap-fill: `data/functional_validation_latest.json`, 80/80 passed.

## Overnight continuation update - 2026-05-10 09:06 +08:00
- Repaired corrupted Python/template literals in source: host schema enums, CSV sample rows, bootstrap seed data, MCP descriptions, host create/list pages, inventory titles, base navigation, tests, and `scripts/functional_validation.py`.
- Added JSON API for SuperAdmin lock/unlock: `POST /api/superadmin/users/<username>/lock`; functional validation now checks create, lock, unlock, and password reset.
- Preserved Phase parallel review rule: monitored-host write guard remains enforced by `phase_readonly_mode`; no remediation/NMON deploy/SSH-key deploy path was enabled.
- Rebuilt local patch package: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`.
- Local verification blocker: Windows `py.exe` is present but reports `No installed Python found`, so `python -m compileall webapp scripts edge` and `python -m pytest -q` could not run on this PC.
- Deployment blocker: `192.168.1.221` pings, but SSH 22 returns `Permission denied` and web 8002 is closed from this PC, so deploy/sync/remote functional validation did not run in this continuation.
- Local saved validation file currently present: `data/functional_validation_latest.json` has a visible 80 passed / 0 failed header from the prior deployed gap-fill run, but `ConvertFrom-Json` cannot parse it because old corrupted detail strings broke JSON quoting. The repaired `scripts/functional_validation.py` should regenerate a valid report once the app is reachable.

## Deployment environment package update - 2026-05-10 09:10 +08:00
- Applied PC/deployment environment package: target `/opt/webitgpt`, Mongo DB `webitgpt`, web port 8002, edge port 9444, Python 3.9.25 compatibility.
- Added/confirmed required deployment artifacts: `requirements.txt`, root patch `install.sh`, `scripts/install.sh`, `scripts/install_systemd.sh`, `scripts/bootstrap.py`, `scripts/start_dev.sh`.
- `scripts/install.sh` now performs backup, non-rsync install fallback, venv/pip install, bootstrap, systemd install/restart, health check, rollback, and install audit log append.
- Fixed deploy blocker on Rocky 9.7: target host does not have `rsync`, so backup/rollback/copy fallback now uses `tar`/`cp` while preserving `data`, `logs`, `tmp`, `backup`, and `venv`.
- Removed Python 3.10-only union type syntax from deployed code; remote verification uses `/opt/webitgpt/venv/bin/python` 3.9.25.
- Rebuilt patch: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz` (clean package, no persistent data/cache).
- Deployed to `192.168.1.221:/opt/webitgpt`; `webitgpt.service` and `webitgpt-edge.service` active.
- Remote verification: Python 3.9.25 compileall ok, pytest 2 passed, `/health` ok, edge `/health` ok.
- Latest full functional validation on 221: `data/functional_validation_latest.json`, 82 passed / 0 failed.
- Windows local tunnel verified: `http://127.0.0.1:8002/health` and `/hosts` return 200 through SSH forward.

## Navigation and version update - 2026-05-10 09:55 +08:00
- Raised app/API/health/OpenAPI/MCP version to `1.0.0.1`.
- Reworked top navigation from flat English links to Chinese grouped navigation:
  - `📊 總覽`: 儀表板、今日巡檢、系統拓撲
  - `📋 資產`: 主機管理、帳號盤點、軟體盤點、服務管理、SSH Key
  - `🛡 合規資安`: 安全稽核、NMON效能
  - `⚙ 系統`: 平台支援、變更管理、系統管理
- Brand/header/footer now display `國泰證券巡檢系統 / webitgpt v1.0.0.1`.
- Local tunnel verified: `/health` returns `1.0.0.1`; `/hosts` returns 200 and contains Chinese grouped navigation.
- Rebuilt patch: `dist/patch_webitgpt_v1.0.0.1-nav-zh.tar.gz`.
- Deployed to 221 and reran full remote validation: `82 passed / 0 failed`.

## Overnight continuation update - 2026-05-11 08:39 +08:00
- Read automation memory, current handoff, current local validation report, recent source files, and package list before editing.
- Repaired locally corrupted display/source files that had broken Python strings and malformed Jinja/HTML:
  - `webapp/routes/api_superadmin.py`
  - `webapp/services/system_service.py`
  - `webapp/templates/base.html`
  - `webapp/templates/superadmin.html`
  - `webapp/templates/users.html`
  - `webapp/templates/system_health.html`
  - `webapp/templates/backup_dr.html`
  - `webapp/templates/patches.html`
  - `tests/test_ui_contracts.py`
- Preserved the Phase parallel review guard: `phase_readonly_mode` still blocks monitored-host writes through `webapp.decorators.monitored_write_blocked`; SSH key, inspection, and compliance rollback/remediation planning remain dry-run/blocked while the flag is true.
- Confirmed requested full-system surfaces are present in source: SuperAdmin user create/lock/reset/backup codes, Backup manifest, DR dry-run, Patch rollback plan, dark mode toggle, Alt-key shortcuts, system health dashboard, and parseable validation report page input.
- Recovered `data/functional_validation_latest.json` into valid JSON with the previous deployed validation summary: `82 passed / 0 failed`, marked `stale=true` because no fresh run completed in this continuation.
- Rebuilt requested package: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz` (local size `1306548` bytes). Runtime directories (`data`, `logs`, `tmp`, `backup`, `dist`, `venv`) are excluded from package payload.
- Local verification blockers: this Windows shell still has no Python (`python` not found; `py -0p` reports no installed Pythons; WSL is not installed), so `python -m compileall webapp scripts edge` and `python -m pytest -q` could not run locally.
- Deployment/remote validation blockers: `192.168.1.221` pings, but TCP 22 and 8002 both fail from this PC; SSH reports `Permission denied`/closed. Deploy, remote compile/pytest, `scripts/functional_validation.py`, and syncing a fresh `data/functional_validation_latest.json` back locally did not run.
- Packaging note: a temporary `_stage_*` directory was created under `dist` while building because `C:\tmp` was not writable and recursive cleanup commands are blocked by policy. The package excludes `dist`, so this staging directory is not inside the tarball.

## Overnight continuation update - 2026-05-12 08:47 +08:00
- Read the latest handoff, local validation report, source files, package list, and phase-readonly guard before editing.
- Fixed local source corruption that would block import/render:
  - `webapp/routes/api_superadmin.py`: replaced corrupted SuperAdmin feature label maps with valid labels and kept feature toggles, users, token, Backup/DR, system health, and patch rollback routes intact.
  - `webapp/templates/base.html`: restored valid app-shell Jinja, role labels, dark-mode toggle, keyboard-shortcut script include, and navigation links.
  - `webapp/templates/dependencies.html`: restored the missing topology template so `/dependencies` can render against the enriched topology data from `legacy_parity_service.py`.
- Preserved the Phase parallel review rule: `phase_readonly_mode=True` remains the default flag, and `webapp.decorators.monitored_write_blocked` still returns 403 for monitored-host write actions.
- Reconfirmed requested v1.0 surfaces in source: SuperAdmin user create/lock/reset/backup codes, Backup manifest, DR dry-run, Patch rollback dry-run plan, dark mode toggle, Alt-key shortcuts, and system health dashboard.
- Local verification attempted after edits:
  - `python -m compileall webapp scripts edge`: blocked because this Windows shell has no `python`.
  - `python -m pytest -q`: blocked because this Windows shell has no `python`.
- Deployment/remote validation blocker remains: `192.168.1.221` TCP 22 and 8002 both fail from this PC, so deploy, remote pytest, `scripts/functional_validation.py`, and syncing a fresh validation report could not run.
- Latest local validation report remains stale but parseable: `data/functional_validation_latest.json`, 82 passed / 0 failed, `stale=true`.
- Rebuilt requested package after fixes: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`, size `1333595` bytes.

## Overnight continuation update - 2026-05-13 08:34 +08:00
- Read the latest handoff, local validation report, dirty git state, SuperAdmin routes, system services, UI shell, feature flags, validation script, and package inventory before editing.
- Confirmed the apparent mojibake in PowerShell output is a console decoding issue; raw UTF-8 file reads show the SuperAdmin labels/templates are valid.
- Fixed validation drift in `scripts/functional_validation.py`: `backup_manifest_api` now expects current app version `1.0.1.47` instead of stale `1.0.1.18`.
- Preserved the Phase parallel review rule: `phase_readonly_mode` remains default true, and `webapp.decorators.monitored_write_blocked` still returns 403 for monitored-host write actions.
- Reconfirmed requested full-system surfaces in source: SuperAdmin user create/lock/unlock/reset/backup codes, Backup manifest, DR dry-run, Patch rollback dry-run plan, dark mode toggle, Alt-key shortcuts, and system health dashboard.
- Rebuilt requested compatibility package: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`, size `1356066` bytes. Package content excludes runtime `data`, `logs`, `tmp`, `backup`, `dist`, `.git`, `__pycache__`, and `*.pyc`.
- Local verification attempted:
  - `python -m compileall webapp scripts edge`: blocked because `python` is not installed in this Windows shell.
  - `python -m pytest -q`: blocked because `python` is not installed in this Windows shell.
  - `py -m compileall webapp scripts edge` and `py -m pytest -q`: blocked because the Python launcher reports no installed Python.
- Deployment/remote validation blocker remains: `192.168.1.221` pings, but TCP 22 fails with `Permission denied`/closed and HTTP `192.168.1.221:8002/health` cannot connect. Deploy, remote pytest, `scripts/functional_validation.py`, and syncing a fresh remote validation report did not run.
- Latest local validation report remains stale but parseable: `data/functional_validation_latest.json`, 82 passed / 0 failed, `stale=true`, timestamp refreshed to this continuation.

## Overnight continuation update - 2026-05-15 08:38 +08:00
- Read the latest handoff, local validation JSON, dirty git state, SuperAdmin routes, system services, feature flags, app shell, validation script, package inventory, and the Phase read-only guard before editing.
- Repaired executable corruption in the SuperAdmin/validation surface:
  - `webapp/routes/api_superadmin.py`: restored valid route module for feature flags, users, password reset, lock/unlock, backup codes, Backup/DR, system health, patch rollback planning, logs/jobs/settings/audit, remote tools, and developer console upload/notes.
  - `webapp/services/feature_flags.py`: restored valid DEFAULT_FLAGS with all existing keys/defaults/categories; `phase_readonly_mode=True` remains the default.
  - `webapp/templates/base.html`, `superadmin.html`, `users.html`, `system_health.html`, `backup_dr.html`, `patches.html`, and `validation.html`: replaced malformed Jinja/HTML with valid UI contracts, preserving dark mode, Alt-key shortcuts, nav ordering, user management, Backup/DR, patch rollback, and health dashboard entry points.
  - `tests/test_ui_contracts.py`: replaced corrupted unterminated assertions with parseable contract tests for navigation, SuperAdmin, Backup/DR, rollback, phase-readonly, inventory/topology, and dev-console surfaces.
- Fixed validation drift in `scripts/functional_validation.py`: `backup_manifest_api` now compares the manifest version with `/health` instead of a stale hard-coded version.
- Preserved the Phase parallel review rule: no monitored-host write action was enabled; `webapp.decorators.monitored_write_blocked` still returns `403` with `Phase parallel review: monitored-host writes are locked` while `phase_readonly_mode` is true.
- Verification attempted:
  - `python -m compileall webapp scripts edge`: blocked, `python` command not found.
  - `python -m pytest -q`: blocked, `python` command not found.
  - `py -m compileall webapp scripts edge`: blocked, Python launcher reports `No installed Python found`.
  - `py -m pytest -q`: blocked, Python launcher reports `No installed Python found`.
  - Static quote-balance scan of Python files found only intentional raw heredoc/regex lines after repairs.
- Rebuilt requested compatibility package: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`, size `1358852` bytes. Package excludes runtime `data`, `logs`, `tmp`, `backup`, `dist`, `venv`, `.git`, `__pycache__`, and `*.pyc`.
- Deployment/remote validation blocker remains: `192.168.1.221` pings, but TCP 22 and 8002 both fail from this PC. Deploy, remote pytest, `scripts/functional_validation.py`, and syncing a fresh remote validation report did not run.
- Latest local validation report remains stale but parseable: `data/functional_validation_latest.json`, 82 passed / 0 failed, `stale=true`, timestamp/note refreshed for 2026-05-15.

## Overnight continuation update - 2026-05-16 08:38 +08:00
- Read automation memory, latest handoff, local validation JSON, repo status, version/config, feature flags, SuperAdmin routes, system service, base shell, functional validation script, package list, and the Phase read-only guard before acting.
- Confirmed current source is `1.0.1.94 / deep-check-network-sn`; `scripts/make_patch.sh`, `scripts/functional_validation.py`, and `webapp/config.py` are in sync for the current version/patch.
- Preserved the Phase parallel review rule: `phase_readonly_mode=True` remains registered by default, and `webapp.decorators.monitored_write_blocked` still returns `403` with `Phase parallel review: monitored-host writes are locked`.
- Reconfirmed requested full-system surfaces in source: SuperAdmin user create/lock/unlock/reset/backup codes, Backup manifest, DR dry-run, Patch rollback dry-run plan, dark mode toggle, Alt-key shortcuts, and system health dashboard.
- Local verification:
  - `python -m compileall webapp scripts edge`: passed using `C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\platform\bundledpython\python.exe`.
  - `python -m pytest -q`: blocked because the available Python does not have `pytest`, and network-restricted `pip install -r requirements.txt` failed with socket permission errors.
  - Fallback direct test runner: 45 test functions passed / 0 failed, with temporary import stubs for `pymongo`, `pyotp`, and `bson`; this is not a replacement for real pytest/Mongo integration.
- Rebuilt requested compatibility package: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`, size `1398685` bytes. Package listing validates no `.git`, `data`, `logs`, `tmp`, `backup`, `dist`, `__pycache__`, or `*.pyc` payload entries.
- Deployment/remote validation blocker remains: `192.168.1.221` SSH 22 returns `Permission denied`; HTTP `192.168.1.221:8002/health` cannot connect. Deploy, remote compile/pytest, `scripts/functional_validation.py`, and syncing a fresh remote validation report did not run.
- Latest local validation report remains stale but parseable: `data/functional_validation_latest.json`, 82 passed / 0 failed, `stale=true`, timestamp/note refreshed for 2026-05-16.

## Overnight continuation update - 2026-05-17 08:43 +08:00
- Read latest local validation JSON, dirty handoff diff, version/config, package inventory, SuperAdmin routes, system service, UI shell, long-operation JS, and Phase read-only guard before editing.
- Fixed current UI/runtime blockers found in local files:
  - `webapp/templates/base.html`: restored valid Traditional Chinese app shell, role labels, dark-mode toggle, global search, navigation, and version/patch footer.
  - `webapp/static/js/ui_tools.js` and `webapp/static/js/admin_tools.js`: restored valid JavaScript strings for form/API busy states, dark mode, nav ordering, Alt-key shortcut routing, API button status, topology zoom/fullscreen, and score rings.
  - `webapp/templates/superadmin.html`, `users.html`, `backup_dr.html`, `patches.html`, `system_health.html`, `validation.html`, `dev_console.html`, `_partials/dev_tabs.html`, `system_settings.html`, `system_logs.html`, `system_jobs.html`, `operation_logs.html`, `feature_parity.html`, and `dependencies.html`: replaced mojibake/broken tags with valid UI text and preserved SuperAdmin user create/lock/reset/backup codes, Backup/DR dry-run, Patch rollback dry-run, system health dashboard, dev console, validation report, and topology controls.
  - `tests/test_ui_contracts.py`: removed a UTF-8 BOM that blocked direct Python execution in this Windows shell.
- Version metadata synchronized for the behavior fix:
  - `webapp/config.py`: `1.0.2.54 / full-system-ui-repair`.
  - `scripts/make_patch.sh`: default package name updated to `patch_webitgpt_v1.0.2.54-full-system-ui-repair`.
  - `scripts/functional_validation.py`: UI version/patch check updated to `1.0.2.54 / full-system-ui-repair`.
- Preserved the Phase parallel review rule: `phase_readonly_mode=True` remains the default feature flag, and `webapp.decorators.monitored_write_blocked` still returns `403` with `Phase parallel review: monitored-host writes are locked`.
- Local verification:
  - `python -m compileall -f webapp scripts edge tests`: passed using `C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\platform\bundledpython\python.exe`.
  - `node --check webapp/static/js/ui_tools.js`: passed.
  - `node --check webapp/static/js/admin_tools.js`: passed.
  - `python -m pytest -q`: blocked because the bundled Python has no `pytest` package.
  - Focused UI contract direct run: 14 passed / 0 failed.
  - Fallback direct test runner: 70 test functions passed / 0 failed, with 4 import/fixture-dependent checks skipped because Flask/pytest fixtures are unavailable locally.
- Packaging:
  - `dist/patch_webitgpt_v1.0.2.54-full-system-ui-repair.tar.gz`, size `1443770` bytes.
  - Requested compatibility package rebuilt: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`, size `1443507` bytes.
  - Native PowerShell/tar packaging was used because `bash scripts/make_patch.sh` maps to WSL here and WSL is not installed. Package listing check found no `.git`, `data`, `logs`, `tmp`, `backup`, `dist`, `venv`, `__pycache__`, or `*.pyc` payload entries.
- Deployment/remote validation blocker remains: `192.168.1.221` pings, but TCP 22 and 8002 both fail from this PC; `/health` cannot connect. Deploy, remote compile/pytest, fresh `scripts/functional_validation.py`, and syncing a fresh remote validation report did not run.
- Latest local validation report refreshed as stale-but-parseable: `data/functional_validation_latest.json`, 82 passed / 0 failed, `stale=true`, with local compile/test/package status and 221 reachability blocker.

## Overnight continuation update - 2026-05-18 08:36 +08:00
- Read the latest handoff, local validation JSON, dirty git state, version/config, package script, SuperAdmin routes, system service, UI contracts, and Phase read-only guard before editing.
- Current source is `1.0.2.69 / opening-disk-full-threshold`; `webapp/config.py` and `scripts/make_patch.sh` are already aligned to that patch.
- Fixed validation drift in `scripts/functional_validation.py`: `ui_version_visible` now compares `/hosts` against the live `/health` version and `patch_id` instead of a stale hard-coded UI marker.
- Preserved the Phase parallel review rule: `phase_readonly_mode=True` remains default, and `webapp.decorators.monitored_write_blocked` still returns `403` with `Phase parallel review: monitored-host writes are locked`.
- Reconfirmed requested full-system surfaces in source: SuperAdmin user create/lock/unlock/reset/backup codes, Backup manifest, DR dry-run, Patch rollback dry-run plan, dark mode toggle, Alt-key shortcuts, and system health dashboard.
- Local verification:
  - `python -m compileall -f webapp scripts edge tests`: passed using `C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\platform\bundledpython\python.exe`.
  - `node --check webapp/static/js/ui_tools.js`: passed.
  - `node --check webapp/static/js/admin_tools.js`: passed.
  - `python -m pytest -q`: blocked because the bundled Python has no `pytest` package; Flask, pymongo, bson, and pyotp are also absent locally.
  - Focused UI contract direct run: 16 passed / 0 failed.
  - Fallback direct test runner with temporary import stubs: 78 passed / 0 failed, 6 Flask/pytest-fixture-dependent checks skipped.
- Rebuilt requested compatibility package: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`, size `1485199` bytes. Package listing check found no `.git`, `data`, `logs`, `tmp`, `backup`, `dist`, `.pytest_cache`, `__pycache__`, or `*.pyc` payload entries.
- Deployment/remote validation blocker: `192.168.1.221` is not reachable from this PC in this run. Ping failed or was denied, TCP 22 failed, TCP 8002 failed, and `http://192.168.1.221:8002/health` could not connect. Local `127.0.0.1:8002/health` also could not connect, so fresh `scripts/functional_validation.py`, deploy, and sync-back could not run.
- Latest local validation report refreshed as stale-but-parseable: `data/functional_validation_latest.json`, 6 local status checks passed / 0 failed, `stale=true`, preserving the previous deployed summary of 82 passed / 0 failed.

## Overnight continuation update - 2026-05-19 08:35 +08:00
- Read the latest handoff, local validation JSON, dirty git state, current source files, SuperAdmin routes/templates, system service, feature flags, UI shell, functional validation script, and Phase read-only guard before editing.
- Confirmed the visible SuperAdmin full-system surfaces are present in source: user create/lock/unlock/password reset/backup codes, Backup manifest, DR dry-run, Patch rollback dry-run plan, dark mode toggle, Alt-key shortcuts, and system health dashboard.
- Preserved the Phase parallel review rule: `phase_readonly_mode=True` remains the default feature flag, and `webapp.decorators.monitored_write_blocked` still returns `403` with `Phase parallel review: monitored-host writes are locked`.
- Synced release/package metadata for the overnight build:
  - `webapp/config.py`: `1.0.2.92 / full-system-package-metadata-sync`.
  - `scripts/make_patch.sh`: default package name updated to `patch_webitgpt_v1.0.2.92-full-system-package-metadata-sync`.
  - `scripts/functional_validation.py`: added `version_policy_1x` to enforce the required `1.X.X.X` version format during full functional validation.
  - `webapp/services/system_service.py`: added release-note entries for `1.0.2.92` and the prior `1.0.2.91 topology-overlay-unmanaged-scan`.
- Local verification:
  - `python -m compileall -f webapp scripts edge tests`: passed using `C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\platform\bundledpython\python.exe`.
  - `node --check webapp/static/js/ui_tools.js`: passed.
  - `node --check webapp/static/js/admin_tools.js`: passed.
  - `python -m pytest -q`: blocked because the bundled Python has no `pytest` package; Flask is also unavailable locally.
  - Fallback direct test runner with temporary import stubs: 79 passed / 0 failed, 6 Flask/pytest-fixture-dependent checks skipped.
- Rebuilt requested compatibility package: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`, size `1502194` bytes, 220 tar entries. Package listing check found no `.git`, `data`, `logs`, `tmp`, `backup`, `dist`, `venv`, `.pytest_cache`, `__pycache__`, or `*.pyc` payload entries.
- Deployment/remote validation blocker remains: `192.168.1.221` ping failed or was denied, TCP 22 failed, TCP 8002 failed, and `http://192.168.1.221:8002/health` could not connect. Local `127.0.0.1:8002/health` also could not connect, so fresh `scripts/functional_validation.py` had no live target. Deploy, remote pytest, fresh functional validation, and sync-back did not run.
- Latest local validation report refreshed as stale-but-parseable: `data/functional_validation_latest.json`, 7 local status checks passed / 0 failed, `stale=true`, preserving the previous deployed summary of 82 passed / 0 failed.

## Overnight continuation update - 2026-05-20 08:38 +08:00
- Read automation memory, latest handoff, local validation JSON, dirty git state, current version/config, package script, functional validation script, SuperAdmin routes/templates, system service, UI shell, and the Phase read-only guard before editing.
- Current source is `1.0.2.96 / offline-onekey-install`; `webapp/config.py` already held the offline one-key install metadata.
- Synced remaining metadata drift:
  - `scripts/make_patch.sh`: default package name updated to `patch_webitgpt_v1.0.2.96-offline-onekey-install`.
  - `webapp/services/system_service.py`: added release-note entry for `1.0.2.96 / offline-onekey-install`.
- Fixed a local test portability gap in `tests/test_debug_bundle_service.py`: the first AI debug loop test now also redirects `AI_RUNTIME_MANIFEST` into `tmp_path`, so fallback/direct tests do not try to write under `/opt/webitgpt`.
- Preserved the Phase parallel review rule: `phase_readonly_mode=True` remains the default feature flag, and `webapp.decorators.monitored_write_blocked` still returns `403` with `Phase parallel review: monitored-host writes are locked`.
- Reconfirmed requested full-system surfaces in source: SuperAdmin user create/lock/unlock/reset/backup codes, Backup manifest, DR dry-run, Patch rollback dry-run plan, dark mode toggle, Alt-key shortcuts, and system health dashboard.
- Local verification:
  - `python -m compileall -f webapp scripts edge tests`: passed using `C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\platform\bundledpython\python.exe`.
  - `node --check webapp/static/js/ui_tools.js`: passed.
  - `node --check webapp/static/js/admin_tools.js`: passed.
  - `python -m pytest -q`: blocked because the bundled Python has no `pytest`; `werkzeug`/Flask are also unavailable locally.
  - Fallback direct test runner with temporary import stubs: 85 passed / 0 failed, 1 import-dependent check skipped (`tests/test_app.py`, missing `werkzeug`).
- Rebuilt requested compatibility package: `dist/patch_webitgpt_v1.0.0.0-cmdb-bone.tar.gz`, size `1515649` bytes, 230 tar entries. Package listing check found no `.git`, `data`, `logs`, `tmp`, `backup`, `dist`, `venv`, `.pytest_cache`, `__pycache__`, or `*.pyc` payload entries.
- Deployment/remote validation blocker remains: `192.168.1.221` ping failed or was denied, TCP 22 failed, TCP 8002 failed, and `http://192.168.1.221:8002/health` could not connect. Local `127.0.0.1:8002/health` also could not connect, so fresh `scripts/functional_validation.py`, deploy, and sync-back could not run.
- Latest local validation report refreshed as stale-but-parseable: `data/functional_validation_latest.json`, 9 local status checks passed / 0 failed, `stale=true`, preserving the previous deployed summary of 82 passed / 0 failed.

