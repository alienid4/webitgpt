# UI Text Cleanup Map

This file tracks user-facing text that should be clean before formal operations handoff.

## Priority

1. Account inventory and AP account inventory.
2. Core impact topology and notification exports.
3. CMDB import, asset quality, and data quality reports.
4. System health, audit logs, and post-install verification.

## Rules

- New text must be readable Traditional Chinese or plain English.
- Do not add new mojibake strings.
- Existing mojibake can remain only when tests depend on legacy strings; clean it in focused UI cleanup patches.
- Buttons should describe the action, not the implementation detail.
- Risk labels must use operational language such as `缺 owner`, `高權限未納 PAM`, `超過 180 天未登入`.

## Current Clean Anchors

- `AP 帳號盤點`
- `AP 風險分類`
- `資料品質`
- `安裝後驗證`
- `可信度`
