#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request


LINUX_SERVICES = [
    "teamdoctor-screener.service",
    "teamdoctor-active-apps-agent.service",
]
MACOS_LABELS = [
    "uz.tenzorsoft.teamdoctor.screener",
    "uz.tenzorsoft.teamdoctor.active-apps-agent",
]
WINDOWS_TASKS = [
    "TeamDoctorScreener",
    "TeamDoctorActiveAppsAgent",
]


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _first_non_empty(*values: str | None) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _run(cmd: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def _http_json(
    *,
    api_url: str,
    token: str | None,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    url = f"{api_url.rstrip('/')}{path}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(url=url, data=body, headers=headers, method=method.upper())
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace").strip()
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {details or exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"Request failed {method} {path}: {exc}") from exc

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"Non-JSON response for {method} {path}: {raw[:200]}") from exc


def _check_autostart(*, skip: bool) -> None:
    if skip:
        print("⚠️ Autostart check skipped")
        return

    system = platform.system().lower()
    failures: list[str] = []

    if system == "linux":
        for service in LINUX_SERVICES:
            rc_enabled, out_enabled, _ = _run(["systemctl", "--user", "is-enabled", service])
            rc_active, out_active, _ = _run(["systemctl", "--user", "is-active", service])
            print(f"service {service}: enabled={out_enabled or 'unknown'} active={out_active or 'unknown'}")
            if rc_enabled != 0 or out_enabled not in {"enabled", "static"}:
                failures.append(f"{service} is not enabled")
            if rc_active != 0 or out_active != "active":
                failures.append(f"{service} is not active")

    elif system == "darwin":
        rc, out, err = _run(["launchctl", "list"])
        if rc != 0:
            raise RuntimeError(f"launchctl list failed: {err or out}")
        for label in MACOS_LABELS:
            present = label in out
            print(f"launchd {label}: {'loaded' if present else 'missing'}")
            if not present:
                failures.append(f"{label} is not loaded in launchd")

    elif system == "windows":
        for task_name in WINDOWS_TASKS:
            rc, out, err = _run(["schtasks", "/Query", "/TN", task_name])
            print(f"task {task_name}: {'found' if rc == 0 else 'missing'}")
            if rc != 0:
                failures.append(f"Task Scheduler job '{task_name}' is missing ({err or out})")
    else:
        print(f"⚠️ Autostart check is not implemented for platform '{system}'")
        return

    if failures:
        raise RuntimeError("Autostart check failed:\n- " + "\n- ".join(failures))


def _wait_for_work_state(
    *,
    api_url: str,
    token: str,
    expected_open: bool,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_dashboard: dict[str, Any] = {}
    while time.monotonic() <= deadline:
        last_dashboard = _http_json(api_url=api_url, token=token, method="GET", path="/api/v1/me/dashboard")
        state = last_dashboard.get("current_state") or {}
        work_open = bool(state.get("work_open"))
        if work_open == expected_open:
            return last_dashboard
        time.sleep(poll_interval_seconds)
    raise RuntimeError(
        f"Timed out waiting for work_open={expected_open}. Last state: "
        f"{json.dumps((last_dashboard.get('current_state') or {}), ensure_ascii=False)}"
    )


def _resolve_token(*, api_url: str, env_values: dict[str, str]) -> str:
    token = _first_non_empty(env_values.get("API_TOKEN"))
    contact = _first_non_empty(env_values.get("USER_CONTACT"))
    password = _first_non_empty(env_values.get("USER_PASSWORD"))

    if token:
        try:
            _http_json(api_url=api_url, token=token, method="GET", path="/api/v1/me/dashboard")
            return token
        except Exception:
            print("⚠️ API_TOKEN is invalid/expired, trying USER_CONTACT + USER_PASSWORD login")

    if not contact or not password:
        raise RuntimeError(
            "No valid token and no USER_CONTACT/USER_PASSWORD found. "
            "Run installer first so agents have credentials in .env"
        )

    login_payload = {"contact": contact, "password": password}
    response = _http_json(
        api_url=api_url,
        token=None,
        method="POST",
        path="/api/v1/auth/login",
        payload=login_payload,
    )
    fresh_token = _first_non_empty(response.get("token"), response.get("access_token"))
    if not fresh_token:
        raise RuntimeError("Login succeeded but token is missing in response")
    return fresh_token


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "E2E check for TeamDoctor agents lifecycle: autostart, /start -> activity, /stop -> no activity."
        )
    )
    parser.add_argument("--scripts-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--poll-interval-seconds", type=int, default=2)
    parser.add_argument("--skip-autostart-check", action="store_true")
    args = parser.parse_args()

    scripts_dir = Path(args.scripts_dir).resolve()
    screener_env = scripts_dir / "screener" / ".env"
    active_env = scripts_dir / "active_apps_agent" / ".env"

    env_values = {}
    env_values.update(_read_env_file(active_env))
    env_values.update(_read_env_file(screener_env))

    api_url = _first_non_empty(env_values.get("API_URL"), "https://api-team-doctor.tenzorsoft.uz").rstrip("/")
    print(f"API_URL={api_url}")
    print(f"SCRIPTS_DIR={scripts_dir}")

    _check_autostart(skip=args.skip_autostart_check)

    token = _resolve_token(api_url=api_url, env_values=env_values)
    print("✅ API auth is ready")

    print("Step 1/6: force stop to start from clean state")
    _http_json(api_url=api_url, token=token, method="POST", path="/api/v1/me/events/stop")
    dashboard = _wait_for_work_state(
        api_url=api_url,
        token=token,
        expected_open=False,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    print(f"✅ work_open=false (session={((dashboard.get('current_state') or {}).get('work_session_id'))})")

    print("Step 2/6: verify /active_apps is idle before start")
    inactive = _http_json(api_url=api_url, token=token, method="POST", path="/api/v1/active_apps")
    if inactive.get("session_id") is not None or inactive.get("activity") is not None:
        raise RuntimeError(f"Expected null activity before /start, got: {json.dumps(inactive, ensure_ascii=False)}")
    print("✅ /active_apps is idle before /start")

    print("Step 3/6: call /start")
    _http_json(api_url=api_url, token=token, method="POST", path="/api/v1/me/events/start")
    dashboard = _wait_for_work_state(
        api_url=api_url,
        token=token,
        expected_open=True,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    current_state = dashboard.get("current_state") or {}
    work_session_id = str(current_state.get("work_session_id") or "").strip()
    if not work_session_id:
        raise RuntimeError("work_open is true but work_session_id is empty")
    print(f"✅ work_open=true session_id={work_session_id}")

    print("Step 4/6: verify live active apps after /start")
    active_response: dict[str, Any] | None = None
    deadline = time.monotonic() + args.timeout_seconds
    while time.monotonic() <= deadline:
        active_response = _http_json(api_url=api_url, token=token, method="POST", path="/api/v1/active_apps")
        session_id = str(active_response.get("session_id") or "").strip()
        activity = active_response.get("activity")
        if session_id and isinstance(activity, dict) and activity:
            app_name = str(activity.get("app_name") or "").strip().lower()
            capture_mode = str(activity.get("capture_mode") or "").strip()
            if app_name and app_name != "inactive" and capture_mode != "active_apps_agent_inactive":
                break
        time.sleep(args.poll_interval_seconds)

    if not active_response:
        raise RuntimeError("No response from /active_apps after /start")
    if str(active_response.get("session_id") or "").strip() != work_session_id:
        raise RuntimeError(
            f"/active_apps returned unexpected session_id. expected={work_session_id} got={active_response.get('session_id')}"
        )
    activity_payload = active_response.get("activity")
    if not isinstance(activity_payload, dict) or not activity_payload:
        raise RuntimeError(f"/active_apps activity payload is empty: {json.dumps(active_response, ensure_ascii=False)}")
    if str(activity_payload.get("app_name") or "").strip().lower() == "inactive":
        raise RuntimeError(
            "active_apps_agent is connected but still reports inactive after /start. "
            "Check agent process and dashboard polling."
        )
    print(
        "✅ /active_apps returns live payload "
        f"(app_name={activity_payload.get('app_name')}, capture_mode={activity_payload.get('capture_mode')})"
    )

    print("Step 5/6: verify heartbeat exists for active work session")
    heartbeats = _http_json(api_url=api_url, token=token, method="GET", path="/api/v1/heartbeats?limit=20")
    items = heartbeats.get("items") or []
    matched = next((item for item in items if str(item.get("session_id") or "") == work_session_id), None)
    if matched is None:
        raise RuntimeError(
            f"No heartbeat found for session {work_session_id}. Last payload: {json.dumps(heartbeats, ensure_ascii=False)}"
        )
    print(
        "✅ heartbeat recorded "
        f"(occurred_at={matched.get('occurred_at')}, state={matched.get('state')}, app={matched.get('app_name')})"
    )

    print("Step 6/6: call /stop and verify activity stops")
    _http_json(api_url=api_url, token=token, method="POST", path="/api/v1/me/events/stop")
    _wait_for_work_state(
        api_url=api_url,
        token=token,
        expected_open=False,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    stopped = _http_json(api_url=api_url, token=token, method="POST", path="/api/v1/active_apps")
    if stopped.get("session_id") is not None or stopped.get("activity") is not None:
        raise RuntimeError(f"Expected null activity after /stop, got: {json.dumps(stopped, ensure_ascii=False)}")
    print("✅ /stop confirmed: /active_apps is idle")

    print("🎉 E2E check passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"❌ E2E check failed: {exc}")
        raise SystemExit(1)
