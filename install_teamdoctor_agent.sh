#!/bin/bash
set -euo pipefail

API_URL=""
TOKEN=""
CONTACT=""
PASSWORD=""
AUTOSTART="true"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR"

usage() {
  cat <<'USAGE'
Usage:
  bash install_teamdoctor_agent.sh --api-url URL (--contact EMAIL --password PASS | --token JWT) [options]

Options:
  --api-url URL          Backend API URL (required)
  --token JWT            API token (optional bootstrap; may expire)
  --contact EMAIL        User contact/email
  --password PASS        User password
  --install-dir PATH     Bundle directory (default: current scripts folder)
  --no-autostart         Do not install/start autostart services
  -h, --help             Show help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-url)
      API_URL="${2:-}"
      shift 2
      ;;
    --token)
      TOKEN="${2:-}"
      shift 2
      ;;
    --contact)
      CONTACT="${2:-}"
      shift 2
      ;;
    --password)
      PASSWORD="${2:-}"
      shift 2
      ;;
    --install-dir)
      INSTALL_DIR="${2:-}"
      shift 2
      ;;
    --no-autostart)
      AUTOSTART="false"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$API_URL" ]]; then
  echo "--api-url is required"
  usage
  exit 1
fi

if [[ -z "$TOKEN" ]] && ([[ -z "$CONTACT" ]] || [[ -z "$PASSWORD" ]]); then
  echo "Provide both --contact and --password (recommended), or --token"
  usage
  exit 1
fi

if [[ ! -d "$INSTALL_DIR/screener" ]] || [[ ! -d "$INSTALL_DIR/active_apps_agent" ]]; then
  echo "❌ Missing agents folders in $INSTALL_DIR"
  echo "Expected:"
  echo "  $INSTALL_DIR/screener"
  echo "  $INSTALL_DIR/active_apps_agent"
  exit 1
fi

install_autostart_linux() {
  echo "🟢 Enabling Linux autostart for screener"
  (
    cd "$INSTALL_DIR/screener"
    bash install_autostart_linux.sh
    systemctl --user restart teamdoctor-screener.service
  )

  echo "🟢 Enabling Linux autostart for active_apps_agent"
  (
    cd "$INSTALL_DIR/active_apps_agent"
    bash install_autostart_linux.sh
    systemctl --user restart teamdoctor-active-apps-agent.service
  )

  echo "✅ Both agents are running as systemd user services"
  systemctl --user --no-pager --full status teamdoctor-screener.service || true
  systemctl --user --no-pager --full status teamdoctor-active-apps-agent.service || true
}

install_autostart_macos() {
  echo "🟢 Enabling macOS autostart for screener"
  (
    cd "$INSTALL_DIR/screener"
    bash install_autostart_macos.sh
  )

  echo "🟢 Enabling macOS autostart for active_apps_agent"
  (
    cd "$INSTALL_DIR/active_apps_agent"
    bash install_autostart_macos.sh
  )

  echo "✅ Both agents are configured in launchd"
}

SETUP_ARGS=(--api-url "$API_URL" --non-interactive)
if [[ -n "$TOKEN" ]]; then
  SETUP_ARGS+=(--token "$TOKEN")
fi

# Always persist USER_CONTACT/USER_PASSWORD when provided.
# This lets agents re-login automatically after JWT expiration.
if [[ -n "$CONTACT" && -n "$PASSWORD" ]]; then
  SETUP_ARGS+=(--contact "$CONTACT" --password "$PASSWORD")
elif [[ -n "$TOKEN" ]]; then
  echo "⚠️ Token-only mode selected. Agent cannot auto-relogin after JWT expiration."
  echo "   Recommended: pass --contact and --password too."
fi

echo "⚙️ Installing screener environment"
(
  cd "$INSTALL_DIR/screener"
  bash setup.sh "${SETUP_ARGS[@]}"
)

echo "⚙️ Installing active_apps_agent environment"
(
  cd "$INSTALL_DIR/active_apps_agent"
  ACTIVE_SETUP_ARGS=("${SETUP_ARGS[@]}" --no-autostart)
  bash setup.sh "${ACTIVE_SETUP_ARGS[@]}"
)

if [[ "$AUTOSTART" == "true" ]] && [[ "$OSTYPE" == "linux-gnu"* ]] && command -v systemctl >/dev/null 2>&1; then
  install_autostart_linux
elif [[ "$AUTOSTART" == "true" ]] && [[ "$OSTYPE" == "darwin"* ]]; then
  install_autostart_macos
else
  echo "🚀 Starting both agents in current terminal"
  bash "$INSTALL_DIR/run_teamdoctor_agents.sh"
fi

echo ""
echo "Done. Logs command:"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
  echo "journalctl --user -u teamdoctor-screener.service -f"
  echo "journalctl --user -u teamdoctor-active-apps-agent.service -f"
elif [[ "$OSTYPE" == "darwin"* ]]; then
  echo "tail -f '$INSTALL_DIR/screener/screener.launchd.out.log'"
  echo "tail -f '$INSTALL_DIR/active_apps_agent/active_apps_agent.launchd.out.log'"
fi
