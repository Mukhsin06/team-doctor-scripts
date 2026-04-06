#!/usr/bin/env bash
set -euo pipefail

API_URL=""
USER_CONTACT=""
USER_PASSWORD=""
API_TOKEN=""
AUTOSTART="true"
NON_INTERACTIVE="false"

usage() {
  cat <<'USAGE'
Usage:
  bash setup.sh --api-url URL [options]

Options:
  --api-url URL           API base URL, e.g. https://api-team-doctor.tenzorsoft.uz
  --contact EMAIL         User contact/email for auto login
  --password PASS         User password for auto login
  --token TOKEN           API token (optional bootstrap)
  --no-autostart          Do not install/start Linux autostart service
  --non-interactive       Do not prompt, only write provided values
  -h, --help              Show help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-url)
      API_URL="${2:-}"
      shift 2
      ;;
    --contact)
      USER_CONTACT="${2:-}"
      shift 2
      ;;
    --password)
      USER_PASSWORD="${2:-}"
      shift 2
      ;;
    --token)
      API_TOKEN="${2:-}"
      shift 2
      ;;
    --no-autostart)
      AUTOSTART="false"
      shift
      ;;
    --non-interactive)
      NON_INTERACTIVE="true"
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

if [[ -z "$API_TOKEN" ]] && ([[ -z "$USER_CONTACT" ]] || [[ -z "$USER_PASSWORD" ]]); then
  echo "Provide both --contact and --password for auto login, or pass --token"
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
VENV_DIR="$SCRIPT_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 is not installed"
  exit 1
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "📦 Creating virtual environment"
  rm -rf "$VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

echo "⬆️ Installing Python dependencies"
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -r requirements.txt

if [[ ! -f ".env" ]] && [[ -f ".env.example" ]]; then
  cp .env.example .env
fi

if [[ ! -f ".env" ]]; then
  cat > .env <<'ENVFILE'
API_URL=https://api-team-doctor.tenzorsoft.uz
USER_CONTACT=
USER_PASSWORD=
API_TOKEN=
REQUEST_TIMEOUT=10
IDLE_THRESHOLD_SECONDS=120
ENVFILE
fi

upsert_env() {
  local key="$1"
  local value="$2"
  local escaped
  escaped=$(printf '%s' "$value" | sed 's/[&/]/\\&/g')

  if grep -qE "^${key}=" .env; then
    sed -i "s/^${key}=.*/${key}=${escaped}/" .env
  else
    echo "${key}=${value}" >> .env
  fi
}

upsert_env "API_URL" "$API_URL"
if [[ -n "$USER_CONTACT" ]]; then
  upsert_env "USER_CONTACT" "$USER_CONTACT"
fi
if [[ -n "$USER_PASSWORD" ]]; then
  upsert_env "USER_PASSWORD" "$USER_PASSWORD"
fi
if [[ -n "$API_TOKEN" ]]; then
  upsert_env "API_TOKEN" "$API_TOKEN"
fi

if [[ "$NON_INTERACTIVE" != "true" ]]; then
  if [[ -z "$USER_CONTACT" ]]; then
    read -r -p "USER_CONTACT (Enter to keep current): " input || true
    if [[ -n "${input:-}" ]]; then
      upsert_env "USER_CONTACT" "$input"
    fi
  fi

  if [[ -z "$USER_PASSWORD" ]]; then
    read -r -s -p "USER_PASSWORD (Enter to keep current): " input || true
    echo
    if [[ -n "${input:-}" ]]; then
      upsert_env "USER_PASSWORD" "$input"
    fi
  fi
fi

if [[ "$AUTOSTART" == "true" ]] && [[ "$OSTYPE" == "linux-gnu"* ]] && command -v systemctl >/dev/null 2>&1; then
  echo "🟢 Installing Linux autostart"
  bash install_autostart_linux.sh
  systemctl --user restart teamdoctor-active-apps-agent.service
  echo "✅ active_apps_agent is running as systemd user service"
elif [[ "$AUTOSTART" == "true" ]] && [[ "$OSTYPE" == "darwin"* ]]; then
  echo "🟢 Installing macOS autostart"
  bash install_autostart_macos.sh
  echo "✅ active_apps_agent is configured for launchd"
else
  echo "✅ Setup completed"
  echo "Run manually: bash run.sh"
fi

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
  echo "Logs: journalctl --user -u teamdoctor-active-apps-agent.service -f"
elif [[ "$OSTYPE" == "darwin"* ]]; then
  echo "Logs:"
  echo "  tail -f active_apps_agent/active_apps_agent.launchd.out.log"
  echo "  tail -f active_apps_agent/active_apps_agent.launchd.err.log"
fi
