# webitgpt v1.0.0.0

GPT-5.5 implementation of the v1.0 IT inspection rewrite.

- Deploy home: `/opt/webitgpt`
- Web port: `8002`
- Edge stub port: `9444`
- Mongo DB: `webitgpt`

During parallel review, `phase_readonly_mode` defaults to enabled. Read-only collection actions may run, but writes to monitored hosts are blocked.

Useful commands on secansible:

```bash
cd /opt/webitgpt
source venv/bin/activate
python scripts/bootstrap.py
python scripts/functional_validation.py --base-url http://127.0.0.1:8002 --output data/functional_validation_latest.json
sudo INSPECTION_HOME=/opt/webitgpt bash scripts/install_systemd.sh
```
