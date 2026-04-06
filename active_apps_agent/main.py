#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import websocket
from dotenv import load_dotenv
from pynput import keyboard, mouse

load_dotenv()

API_URL = os.getenv("API_URL", "https://api-team-doctor.tenzorsoft.uz").rstrip("/")
USER_CONTACT = os.getenv("USER_CONTACT", "").strip()
USER_PASSWORD = os.getenv("USER_PASSWORD", "").strip()
API_TOKEN = os.getenv("API_TOKEN", "").strip()
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))
IDLE_THRESHOLD_SECONDS = int(os.getenv("IDLE_THRESHOLD_SECONDS", "120"))
DASHBOARD_POLL_INTERVAL_SECONDS = max(2, int(os.getenv("DASHBOARD_POLL_INTERVAL_SECONDS", "5")))


def _clean_text(value: str | None, max_len: int = 512) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def _strip_invisible_marks(value: str | None) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    out = []
    for ch in text:
        if unicodedata.category(ch) == "Cf":
            continue
        out.append(ch)
    return _clean_text("".join(out))


def _guess_app_name(window_title: str | None) -> str | None:
    title = _strip_invisible_marks(window_title)
    if not title:
        return None
    candidates = [title, title.split(" - ")[-1], title.split(" — ")[-1], title.split(" | ")[-1]]
    for candidate in candidates:
        text = _clean_text(candidate, max_len=128)
        if not text:
            continue
        if text.lower() in {"new tab", "untitled", "home", "document"}:
            continue
        return text
    return None


class ActiveAppsAgent:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.api_token = API_TOKEN or None
        self.last_input_monotonic = time.monotonic()
        self.is_running = True
        self.state_lock = threading.Lock()
        self.mouse_listener = None
        self.keyboard_listener = None
        self.work_active = False
        self.current_work_session_id = None
        self.last_work_state_check_monotonic = 0.0

    def _run_text_command(self, command: list[str]) -> str:
        if not command:
            return ""
        if shutil.which(command[0]) is None:
            return ""
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=5)
            return (result.stdout or "").strip()
        except Exception:
            return ""

    def _linux_active_metadata(self) -> tuple[str | None, str | None]:
        app_name = None
        window_title = None

        window_id = self._run_text_command(["xdotool", "getactivewindow"])
        if window_id:
            window_title = self._run_text_command(["xdotool", "getwindowname", window_id]) or None
            pid_text = self._run_text_command(["xdotool", "getwindowpid", window_id])
            if pid_text.isdigit():
                try:
                    app_name = Path(f"/proc/{pid_text}/comm").read_text(encoding="utf-8").strip() or None
                except Exception:
                    pass
            if not app_name:
                app_name = self._run_text_command(["xdotool", "getwindowclassname", window_id]) or None

        if not app_name or not window_title:
            active_line = self._run_text_command(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
            match = re.search(r"window id # (0x[0-9a-fA-F]+)", active_line)
            if match:
                xid = match.group(1)
                if not window_title:
                    name_line = self._run_text_command(["xprop", "-id", xid, "_NET_WM_NAME"])
                    parts = name_line.split("=", 1)
                    if len(parts) == 2:
                        window_title = parts[1].strip().strip('"') or window_title
                if not app_name:
                    class_line = self._run_text_command(["xprop", "-id", xid, "WM_CLASS"])
                    parts = class_line.split("=", 1)
                    if len(parts) == 2:
                        values = [v.strip().strip('"') for v in parts[1].split(",")]
                        if values:
                            app_name = values[-1] or values[0] or app_name

        return app_name, window_title

    def _linux_background_windows(self, active_window_title: str | None) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        raw = self._run_text_command(["wmctrl", "-lx"])
        if not raw:
            return rows
        for line in raw.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            wm_class = (parts[3] or "").strip()
            title = (parts[4] or "").strip()
            if not title:
                continue
            if active_window_title and title == active_window_title:
                continue
            app_candidate = wm_class.split(".")[-1].strip() if wm_class else ""
            app_name = _clean_text(app_candidate, max_len=128) or "Unknown"
            window_title = _clean_text(_strip_invisible_marks(title), max_len=512)
            if not window_title:
                continue
            rows.append({"app_name": app_name, "window_title": window_title})
        return rows[:20]

    def _active_window_metadata(self) -> dict:
        app_name = None
        window_title = None
        background_windows: list[dict[str, str]] = []

        if sys.platform == "darwin":
            script = """
            tell application "System Events"
                set frontApp to first application process whose frontmost is true
                set appName to name of frontApp
                set windowTitle to ""
                try
                    if exists front window of frontApp then
                        set windowTitle to name of front window of frontApp
                    end if
                end try
                return appName & linefeed & windowTitle
            end tell
            """
            output = self._run_text_command(["osascript", "-e", script])
            if output:
                lines = output.splitlines()
                app_name = (lines[0] or "").strip() or None
                if len(lines) > 1:
                    window_title = "\n".join(lines[1:]).strip() or None
        elif sys.platform.startswith("linux"):
            app_name, window_title = self._linux_active_metadata()
            background_windows = self._linux_background_windows(window_title)
        elif sys.platform.startswith("win"):
            script = (
                "Add-Type @'\n"
                "using System;\n"
                "using System.Runtime.InteropServices;\n"
                "using System.Text;\n"
                "public static class Win32 {\n"
                "  [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();\n"
                "  [DllImport(\"user32.dll\", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);\n"
                "  [DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);\n"
                "}\n"
                "'@;"
                "$hwnd=[Win32]::GetForegroundWindow();"
                "$sb=New-Object System.Text.StringBuilder 1024;"
                "[void][Win32]::GetWindowText($hwnd,$sb,$sb.Capacity);"
                "$pid=0; [void][Win32]::GetWindowThreadProcessId($hwnd,[ref]$pid);"
                "$proc=Get-Process -Id $pid -ErrorAction SilentlyContinue;"
                "Write-Output ($proc.ProcessName); Write-Output ($sb.ToString())"
            )
            output = self._run_text_command(["powershell", "-NoProfile", "-Command", script])
            if output:
                lines = output.splitlines()
                app_name = (lines[0] or "").strip() or None
                if len(lines) > 1:
                    window_title = "\n".join(lines[1:]).strip() or None

        window_title = _strip_invisible_marks(window_title)
        app_name = _strip_invisible_marks(app_name) or _guess_app_name(window_title)
        app_name = _clean_text(app_name, max_len=128) or "Unknown"
        window_title = _clean_text(window_title, max_len=512)
        background_apps = sorted({row["app_name"] for row in background_windows if row.get("app_name")})[:20]
        return {
            "app_name": app_name,
            "window_title": window_title,
            "active_app": app_name,
            "active_window_title": window_title,
            "background_windows": background_windows,
            "background_apps": background_apps,
            "platform": sys.platform,
            "capture_mode": "active_apps_agent_ws",
        }

    def _build_activity(self) -> dict:
        idle_for_seconds = max(0, int(time.monotonic() - self.last_input_monotonic))
        state = "idle" if idle_for_seconds >= int(IDLE_THRESHOLD_SECONDS) else "active"
        meta = self._active_window_metadata()
        return {
            "state": state,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "app_name": meta.get("app_name") or "Unknown",
                "window_title": meta.get("window_title"),
                "active_app": meta.get("active_app"),
                "active_window_title": meta.get("active_window_title"),
                "background_apps": meta.get("background_apps") or [],
                "background_windows": meta.get("background_windows") or [],
                "idle_for_seconds": idle_for_seconds,
                "source": "active_apps_agent_ws",
                "platform": meta.get("platform") or sys.platform,
                "capture_mode": meta.get("capture_mode") or "active_apps_agent_ws",
                "activity_state": state,
            },
        }

    def _build_inactive_activity(self) -> dict:
        idle_for_seconds = max(0, int(time.monotonic() - self.last_input_monotonic))
        return {
            "state": "idle",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "app_name": "inactive",
                "window_title": "work session is not running",
                "idle_for_seconds": idle_for_seconds,
                "source": "active_apps_agent_ws",
                "platform": sys.platform,
                "capture_mode": "active_apps_agent_inactive",
                "activity_state": "inactive",
                "work_session_active": False,
            },
        }

    def _ws_url(self) -> str:
        parsed = urlparse(API_URL)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        netloc = parsed.netloc or parsed.path
        return f"{scheme}://{netloc}/api/v1/agent/active_apps/ws"

    def login(self) -> bool:
        if not USER_CONTACT or not USER_PASSWORD:
            return False
        try:
            response = self.session.post(
                f"{API_URL}/api/v1/auth/login",
                json={"contact": USER_CONTACT, "password": USER_PASSWORD},
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                return False
            data = response.json()
            token = (data.get("token") or data.get("access_token") or "").strip()
            if not token:
                return False
            with self.state_lock:
                self.api_token = token
            return True
        except Exception:
            return False

    def _sync_work_state(self) -> bool:
        with self.state_lock:
            token = self.api_token
        if not token and not self.login():
            return False
        with self.state_lock:
            token = self.api_token
        if not token:
            return False

        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(2):
            try:
                response = self.session.get(
                    f"{API_URL}/api/v1/me/dashboard",
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
            except Exception:
                return False

            if response.status_code == 401:
                if not self.login():
                    return False
                with self.state_lock:
                    token = self.api_token
                if not token:
                    return False
                headers = {"Authorization": f"Bearer {token}"}
                continue

            if response.status_code != 200:
                return False

            try:
                payload = response.json()
            except Exception:
                return False

            current_state = payload.get("current_state") or {}
            work_open = bool(current_state.get("work_open"))
            work_session_id = str(current_state.get("work_session_id") or "").strip() or None
            with self.state_lock:
                self.work_active = work_open
                self.current_work_session_id = work_session_id
                self.last_work_state_check_monotonic = time.monotonic()
            return True

        return False

    def _ensure_work_state_fresh(self, *, force: bool = False) -> None:
        with self.state_lock:
            last_check = float(self.last_work_state_check_monotonic or 0.0)
        now = time.monotonic()
        if not force and (now - last_check) < DASHBOARD_POLL_INTERVAL_SECONDS:
            return
        if not self._sync_work_state():
            with self.state_lock:
                self.last_work_state_check_monotonic = now

    def _is_work_active(self) -> bool:
        with self.state_lock:
            return bool(self.work_active)

    def on_input(self, *args, **kwargs) -> None:
        self.last_input_monotonic = time.monotonic()

    def start_input_watch(self) -> None:
        self.mouse_listener = mouse.Listener(on_click=lambda *args, **kwargs: self.on_input())
        self.keyboard_listener = keyboard.Listener(on_press=lambda *args, **kwargs: self.on_input())
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def run(self) -> None:
        self.start_input_watch()
        self._ensure_work_state_fresh(force=True)
        while self.is_running:
            with self.state_lock:
                token = self.api_token
            if not token and not self.login():
                time.sleep(2)
                continue
            with self.state_lock:
                token = self.api_token
            ws = None
            try:
                ws = websocket.create_connection(
                    self._ws_url(),
                    timeout=REQUEST_TIMEOUT,
                    header=[f"Authorization: Bearer {token}"],
                )
                ws.settimeout(1)
                print("✅ active_apps_agent: websocket connected")
                while self.is_running:
                    self._ensure_work_state_fresh()
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    except Exception:
                        break
                    if not raw:
                        continue
                    try:
                        message = json.loads(raw)
                    except Exception:
                        continue
                    if str(message.get("type") or "") != "activity.request":
                        continue
                    request_id = str(message.get("request_id") or "").strip()
                    if not request_id:
                        continue
                    self._ensure_work_state_fresh()
                    snapshot = self._build_activity() if self._is_work_active() else self._build_inactive_activity()
                    ws.send(
                        json.dumps(
                            {
                                "type": "activity.response",
                                "request_id": request_id,
                                "state": snapshot.get("state"),
                                "occurred_at": snapshot.get("occurred_at"),
                                "payload": snapshot.get("payload"),
                            }
                        )
                    )
            except KeyboardInterrupt:
                self.is_running = False
                break
            except Exception:
                time.sleep(2)
            finally:
                try:
                    ws.close()
                except Exception:
                    pass


def main() -> None:
    agent = ActiveAppsAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
