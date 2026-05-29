# Operations Hardening Roadmap

## Keep Blocked Until Formal Approval

- Security remediation.
- Account disablement.
- Patch apply on monitored hosts.
- Rollback execution on monitored hosts.

These actions must stay under `phase_readonly_mode` until approval workflow, backup evidence, rollback verification, and audit review are accepted.

## Required Before Write Actions

- Change ticket id.
- Approver.
- Target asset list.
- Pre-check evidence.
- Backup artifact path.
- Rollback command or manual rollback SOP.
- Market-hours decision.
- Audit log entry for both blocked and approved actions.

## Recommended Next Gate

Use a dry-run report first. The dry-run must show exactly which host, account, service, or file would change, and why.
