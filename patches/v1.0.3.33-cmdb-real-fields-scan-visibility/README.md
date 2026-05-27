# v1.0.3.33 CMDB Real Fields / Scan Visibility Patch

This patch updates an installed webitgpt host.

It includes:

- real CMDB Chinese header aliases for CSV import;
- network scan summary fields for discovered, CMDB-managed, unmanaged, and visible rows;
- wider TCP discovery ports plus fallback to default `nmap <CIDR>`;
- UI labels that make scan counts visible to operators.

Apply from the extracted patch directory:

```bash
sudo bash install_patch_v1.0.3.33.sh /opt/webitgpt
```

Verify:

```bash
curl -fsS http://127.0.0.1:8002/health
cd /opt/webitgpt
./venv/bin/python -m pytest -q tests/test_cmdb_real_fields_and_scan_summary.py tests/test_asset_account_ui.py
```
