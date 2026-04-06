#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/uz.tenzorsoft.teamdoctor.active-apps-agent.plist"
OUT_LOG="$SCRIPT_DIR/active_apps_agent.launchd.out.log"
ERR_LOG="$SCRIPT_DIR/active_apps_agent.launchd.err.log"

mkdir -p "$PLIST_DIR"

cat > "$PLIST_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>uz.tenzorsoft.teamdoctor.active-apps-agent</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>$SCRIPT_DIR/run.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$OUT_LOG</string>

    <key>StandardErrorPath</key>
    <string>$ERR_LOG</string>
  </dict>
</plist>
PLIST

launchctl unload "$PLIST_FILE" >/dev/null 2>&1 || true
launchctl load "$PLIST_FILE"

echo "✅ macOS autostart installed"
echo "Plist: $PLIST_FILE"
echo "Logs:"
echo "  tail -f '$OUT_LOG'"
echo "  tail -f '$ERR_LOG'"
echo "Status: launchctl list | grep uz.tenzorsoft.teamdoctor.active-apps-agent"
