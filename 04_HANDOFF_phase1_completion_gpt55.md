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
- 實績功能驗證: `scripts/functional_validation.py` 60/60 passed
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
