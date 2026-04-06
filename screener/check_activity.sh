#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f ".env" ]; then
  echo "❌ .env not found in $SCRIPT_DIR"
  exit 1
fi

set -a
source .env
set +a

API_URL="${API_URL:-https://api-team-doctor.tenzorsoft.uz}"
API_TOKEN="${API_TOKEN:-}"
USER_CONTACT="${USER_CONTACT:-}"
USER_PASSWORD="${USER_PASSWORD:-}"
PID_FILE=".screener.pid"

echo "=== Screener Activity Check ==="
echo "time: $(date -Iseconds)"
echo "api:  $API_URL"
echo

echo "[1/5] Screener process"
if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${PID}" ] && kill -0 "$PID" 2>/dev/null; then
    echo "✅ running (pid=$PID)"
    ps -fp "$PID" || true
  else
    echo "⚠️ pid file exists but process is not running"
  fi
else
  echo "⚠️ pid file not found ($PID_FILE)"
fi
echo

echo "[2/5] Desktop session"
echo "XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-unknown}"
echo "DISPLAY=${DISPLAY:-unset}"
echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-unset}"
echo

echo "[3/5] Active window (best-effort)"
if command -v xdotool >/dev/null 2>&1; then
  WID="$(xdotool getactivewindow 2>/dev/null || true)"
  if [ -n "$WID" ]; then
    echo "window_id=$WID"
    echo "title=$(xdotool getwindowname "$WID" 2>/dev/null || echo unknown)"
    echo "class=$(xdotool getwindowclassname "$WID" 2>/dev/null || echo unknown)"
    PID_W="$(xdotool getwindowpid "$WID" 2>/dev/null || true)"
    if [ -n "$PID_W" ] && [ -r "/proc/$PID_W/comm" ]; then
      echo "proc=$(cat "/proc/$PID_W/comm" 2>/dev/null || echo unknown)"
    fi
  else
    echo "⚠️ could not read active window via xdotool"
  fi
else
  echo "⚠️ xdotool not installed"
fi
echo

echo "[4/5] API auth"
if [ -z "$API_TOKEN" ]; then
  if [ -n "$USER_CONTACT" ] && [ -n "$USER_PASSWORD" ]; then
    API_TOKEN="$(curl -sS "$API_URL/api/v1/auth/login" \
      -H "Content-Type: application/json" \
      -d "{\"contact\":\"$USER_CONTACT\",\"password\":\"$USER_PASSWORD\"}" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("token") or d.get("access_token") or "").strip())')"
  fi
fi

if [ -z "$API_TOKEN" ]; then
  echo "❌ no API token (set API_TOKEN or USER_CONTACT/USER_PASSWORD in .env)"
  exit 1
fi
echo "✅ token ready"
echo

echo "[5/5] Dashboard + latest heartbeat"
DASH_JSON="$(curl -sS "$API_URL/api/v1/me/dashboard" -H "Authorization: Bearer $API_TOKEN" || true)"
HB_JSON="$(curl -sS "$API_URL/api/v1/heartbeats?limit=1" -H "Authorization: Bearer $API_TOKEN" || true)"

python3 - <<'PY' "$DASH_JSON" "$HB_JSON"
import json
import sys
from datetime import datetime, timezone

dash_raw = sys.argv[1] or "{}"
hb_raw = sys.argv[2] or "{}"

try:
    dash = json.loads(dash_raw)
except Exception:
    print("❌ dashboard response is not valid JSON")
    sys.exit(1)

try:
    hb = json.loads(hb_raw)
except Exception:
    print("❌ heartbeats response is not valid JSON")
    sys.exit(1)

state = (dash.get("current_state") or {})
work_open = bool(state.get("work_open"))
work_session_id = state.get("work_session_id")
print(f"work_open={work_open}")
print(f"work_session_id={work_session_id}")

items = hb.get("items") or []
if not items:
    print("⚠️ no heartbeats found")
    sys.exit(0)

last = items[0]
occurred_at = last.get("occurred_at")
payload = last.get("payload") or {}
app_name = payload.get("app_name")
window_title = payload.get("window_title")
print(f"last_heartbeat_at={occurred_at}")
print(f"last_state={last.get('state')}")
print(f"last_app_name={app_name}")
print(f"last_window_title={window_title}")

if not occurred_at:
    print("⚠️ heartbeat without occurred_at")
    sys.exit(0)

try:
    dt = datetime.fromisoformat(str(occurred_at).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    print(f"heartbeat_age_seconds={age}")
    if age > 180:
        print("⚠️ heartbeat is stale (>180s)")
except Exception:
    print("⚠️ failed to parse heartbeat timestamp")
PY

echo
echo "✅ check completed"
