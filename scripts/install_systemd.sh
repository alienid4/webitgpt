#!/usr/bin/env bash
set -euo pipefail

APP_HOME="${INSPECTION_HOME:-/opt/webitgpt}"
RUN_USER="${WEBITGPT_USER:-sysinfra}"
RUN_GROUP="${WEBITGPT_GROUP:-itagent}"
BUILD_TIME="${WEBITGPT_BUILD_TIME:-$(date '+%Y-%m-%d %H:%M:%S %:z')}"
MONGO_URI_VALUE="${MONGO_URI:-mongodb://localhost:27017}"
MONGO_DB_VALUE="${MONGO_DB:-webitgpt}"

if [ "$(id -u)" -ne 0 ]; then
  echo "install_systemd.sh must run as root (use sudo)" >&2
  exit 1
fi

cat >/etc/systemd/system/webitgpt.service <<EOF
[Unit]
Description=Webitgpt v1.0 Inspection Webapp (GPT-5.5 version)
After=network.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${APP_HOME}/webapp
Environment="INSPECTION_HOME=${APP_HOME}"
Environment="MONGO_URI=${MONGO_URI_VALUE}"
Environment="MONGO_DB=${MONGO_DB_VALUE}"
Environment="PYTHONPATH=${APP_HOME}"
Environment="WEBITGPT_BUILD_TIME=${BUILD_TIME}"
ExecStart=${APP_HOME}/venv/bin/gunicorn \\
  -w 4 -b 0.0.0.0:8002 \\
  --timeout 300 --graceful-timeout 30 \\
  --access-logfile ${APP_HOME}/logs/access.log \\
  --error-logfile ${APP_HOME}/logs/error.log \\
  app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/webitgpt-edge.service <<EOF
[Unit]
Description=webitgpt Edge Agent (GPT-5.5 version)
After=network.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${APP_HOME}
Environment="INSPECTION_HOME=${APP_HOME}"
Environment="MONGO_URI=${MONGO_URI_VALUE}"
Environment="MONGO_DB=${MONGO_DB_VALUE}"
Environment="PYTHONPATH=${APP_HOME}"
Environment="WEBITGPT_BUILD_TIME=${BUILD_TIME}"
ExecStart=${APP_HOME}/venv/bin/python ${APP_HOME}/edge/edge_agent.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/webitgpt-ipam-reconcile.service <<EOF
[Unit]
Description=webitgpt IPAM nmap reconcile scheduler
After=network.target mongod.service

[Service]
Type=oneshot
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${APP_HOME}
Environment="INSPECTION_HOME=${APP_HOME}"
Environment="MONGO_URI=${MONGO_URI_VALUE}"
Environment="MONGO_DB=${MONGO_DB_VALUE}"
Environment="PYTHONPATH=${APP_HOME}"
ExecStart=${APP_HOME}/venv/bin/python ${APP_HOME}/scripts/weekly_ipam_reconcile.py
StandardOutput=append:${APP_HOME}/logs/ipam_reconcile.log
StandardError=append:${APP_HOME}/logs/ipam_reconcile.log
EOF

cat >/etc/systemd/system/webitgpt-ipam-reconcile.timer <<EOF
[Unit]
Description=Check webitgpt IPAM nmap reconcile schedule

[Timer]
OnCalendar=*-*-* *:0/5:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable webitgpt.service webitgpt-edge.service webitgpt-ipam-reconcile.timer
systemctl restart webitgpt.service webitgpt-edge.service
systemctl restart webitgpt-ipam-reconcile.timer

if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port=8002/tcp >/dev/null
  firewall-cmd --permanent --add-port=9444/tcp >/dev/null
  firewall-cmd --reload >/dev/null
fi

echo "webitgpt.service=$(systemctl is-active webitgpt.service || true)"
echo "webitgpt-edge.service=$(systemctl is-active webitgpt-edge.service || true)"
echo "webitgpt-ipam-reconcile.timer=$(systemctl is-active webitgpt-ipam-reconcile.timer || true)"
