#!/bin/bash
set -euo pipefail

API_URL=""
USER_CONTACT=""
USER_PASSWORD=""
API_TOKEN=""
NON_INTERACTIVE="false"

usage() {
    cat <<'USAGE'
Usage:
  bash setup.sh [options]

Options:
  --api-url URL           API base URL, e.g. https://api-team-doctor.tenzorsoft.uz
  --contact EMAIL         User contact/email (recommended for auto relogin)
  --password PASS         User password (recommended for auto relogin)
  --token TOKEN           API token (optional; useful as immediate bootstrap)
  --non-interactive       Do not prompt, just create environment files
  -h, --help              Show this help
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
VENV_DIR="$SCRIPT_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"

echo "🚀 Installing Screener..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ python3 is not installed"
    exit 1
fi

echo "✅ python3 found: $(python3 --version 2>/dev/null || echo python3)"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "📦 Creating virtual environment..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
else
    echo "📦 Virtual environment already exists"
fi

echo "⬆️ Updating pip/setuptools/wheel..."
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel

echo "📥 Installing Python dependencies..."
"$VENV_PYTHON" -m pip install -r requirements.txt

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "📝 Created .env from .env.example"
fi

if [ ! -f ".env" ]; then
    cat > .env <<'ENVFILE'
API_URL=https://api-team-doctor.tenzorsoft.uz
USER_CONTACT=
USER_PASSWORD=
API_TOKEN=
POLL_INTERVAL=5
REQUEST_TIMEOUT=10
UPLOAD_SCREENSHOTS=true
KEEP_LOCAL_SCREENSHOTS=false
HEARTBEAT_INTERVAL=60
SCREENSHOT_INTERVAL=300
IDLE_THRESHOLD_SECONDS=120
ENVFILE
    echo "📝 Created default .env"
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

if [ -n "$API_URL" ]; then
    upsert_env "API_URL" "$API_URL"
fi
if [ -n "$USER_CONTACT" ]; then
    upsert_env "USER_CONTACT" "$USER_CONTACT"
fi
if [ -n "$USER_PASSWORD" ]; then
    upsert_env "USER_PASSWORD" "$USER_PASSWORD"
fi
if [ -n "$API_TOKEN" ]; then
    upsert_env "API_TOKEN" "$API_TOKEN"
fi

if [ "$NON_INTERACTIVE" = "true" ] && [ -n "$API_TOKEN" ] && { [ -z "$USER_CONTACT" ] || [ -z "$USER_PASSWORD" ]; }; then
    echo "⚠️ Token-only setup: after JWT expiration auto relogin will not work."
    echo "   Add USER_CONTACT and USER_PASSWORD to .env for stable autostart."
fi

if [ "$NON_INTERACTIVE" != "true" ]; then
    if [ -z "$API_URL" ]; then
        read -r -p "API_URL (Enter to keep current): " input || true
        if [ -n "${input:-}" ]; then
            upsert_env "API_URL" "$input"
        fi
    fi

    if [ -n "$API_TOKEN" ]; then
        echo "ℹ️ API_TOKEN set. For auto relogin after token expiration, add USER_CONTACT/USER_PASSWORD."
    fi

    read -r -p "USER_CONTACT (Enter to keep current): " input || true
    if [ -n "${input:-}" ]; then
        upsert_env "USER_CONTACT" "$input"
    fi

    read -r -s -p "USER_PASSWORD (Enter to keep current): " input || true
    echo
    if [ -n "${input:-}" ]; then
        upsert_env "USER_PASSWORD" "$input"
    fi
fi

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "🐧 Linux detected"
    if [ -z "${DISPLAY:-}" ] && [ "${XDG_SESSION_TYPE:-}" != "wayland" ]; then
        echo "⚠️ DISPLAY is not set. Run screener on employee desktop session, not headless server."
    fi
fi

echo
echo "✅ Setup completed"
echo "Run: bash run.sh"
echo "Optional autostart (Linux): bash install_autostart_linux.sh"
