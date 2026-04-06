#!/usr/bin/env bash
set -euo pipefail

if ! command -v systemctl >/dev/null 2>&1; then
  echo "❌ systemctl not found. This script requires systemd user services."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_FILE="$SERVICE_DIR/teamdoctor-active-apps-agent.service"

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_FILE" <<SERVICE
[Unit]
Description=TeamDoctor Active Apps Agent (user session)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/env bash $SCRIPT_DIR/run.sh
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
SERVICE

systemctl --user daemon-reload
systemctl --user enable --now teamdoctor-active-apps-agent.service

echo "✅ Linux autostart installed"
echo "Status: systemctl --user status teamdoctor-active-apps-agent.service"
echo "Logs:   journalctl --user -u teamdoctor-active-apps-agent.service -f"
