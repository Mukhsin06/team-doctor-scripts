#!/usr/bin/env python3
"""
Screener Application - Takes screenshots on mouse click anywhere on screen
"""
import sys
import os
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import re
import shutil
import unicodedata
from urllib.parse import urlparse
try:
    import pillow_avif  # noqa: F401  Registers AVIF support in Pillow.
except ImportError:
    pillow_avif = None
from PIL import Image, ImageGrab
from pynput import mouse, keyboard
from pynput.mouse import Controller
import threading
import time
import tempfile
import requests
import websocket
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "https://api-team-doctor.tenzorsoft.uz").rstrip("/")
USER_CONTACT = os.getenv("USER_CONTACT", "")
USER_PASSWORD = os.getenv("USER_PASSWORD", "")
API_TOKEN = os.getenv("API_TOKEN", "").strip()
ENV_FILE = Path(__file__).parent / ".env"
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))
UPLOAD_SCREENSHOTS = os.getenv("UPLOAD_SCREENSHOTS", "true").strip().lower() in {"1", "true", "yes", "on"}
KEEP_LOCAL_SCREENSHOTS = os.getenv("KEEP_LOCAL_SCREENSHOTS", "false").strip().lower() in {"1", "true", "yes", "on"}
HEARTBEAT_INTERVAL_DEFAULT = int(os.getenv("HEARTBEAT_INTERVAL", "60"))
SCREENSHOT_INTERVAL_DEFAULT = int(os.getenv("SCREENSHOT_INTERVAL", "300"))
IDLE_THRESHOLD_DEFAULT = int(os.getenv("IDLE_THRESHOLD_SECONDS", "120"))
WS_ACTIVITY_ENABLED = os.getenv("WS_ACTIVITY_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
SCREENSHOT_EXT = ".avif"
SCREENSHOT_MIME_TYPE = "image/avif"


def _clamp_int(value, fallback: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(fallback)
    return max(min_value, min(max_value, parsed))


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
    cleaned = []
    for ch in text:
        # Drop bidi/control formatting marks that pollute window titles.
        if unicodedata.category(ch) == "Cf":
            continue
        cleaned.append(ch)
    return _clean_text("".join(cleaned))


def _guess_app_name_from_window_title(window_title: str | None) -> str | None:
    title = _strip_invisible_marks(window_title)
    if not title:
        return None
    candidates = [
        title,
        title.split(" - ")[-1],
        title.split(" — ")[-1],
        title.split(" | ")[-1],
    ]
    for raw in candidates:
        candidate = _clean_text(raw, max_len=128)
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered in {"new tab", "untitled", "document", "home"}:
            continue
        return candidate
    return None


def _persist_api_token(token: str | None) -> None:
    token_value = (token or "").strip()
    if not token_value or not ENV_FILE.exists():
        return
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return

    replaced = False
    updated: list[str] = []
    for line in lines:
        if line.startswith("API_TOKEN="):
            updated.append(f"API_TOKEN={token_value}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f"API_TOKEN={token_value}")
    try:
        ENV_FILE.write_text("\n".join(updated) + "\n", encoding="utf-8")
    except Exception:
        pass


def _ensure_avif_support() -> None:
    if pillow_avif is None:
        raise RuntimeError("AVIF support is unavailable. Install pillow-avif-plugin in the screener venv.")

class ScreenshotApp:
    def __init__(self):
        # Создаём папку для скриншотов
        self.screenshots_dir = Path(__file__).parent / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Счётчик скриншотов
        self.screenshot_count = 0
        
        # Флаг активности (зависит от API)
        self.active = False
        self.is_running = True
        self.listener = None
        self.keyboard_listener = None
        
        # API state
        self.api_token = None
        self.current_session_id = None
        self.current_work_session_id = None
        self.session = requests.Session()
        self.state_lock = threading.Lock()
        self.capture_help_printed = False
        self.display_helper_path = Path(__file__).parent / "display_helper"
        self.heartbeat_interval_seconds = _clamp_int(HEARTBEAT_INTERVAL_DEFAULT, 60, 5, 3600)
        self.screenshot_interval_seconds = _clamp_int(SCREENSHOT_INTERVAL_DEFAULT, 300, 15, 7200)
        self.idle_threshold_seconds = _clamp_int(IDLE_THRESHOLD_DEFAULT, 120, 15, 3600)
        self.last_input_monotonic = time.monotonic()
        self.last_heartbeat_sent_at = 0.0
        self.last_auto_screenshot_at = 0.0
        self.activity_ws = None
        self.activity_ws_lock = threading.Lock()
        
        print("\n" + "="*50)
        print("📸 SCREENER - Монитор с привязкой к API")
        print("="*50)
        print(f"✅ Приложение запускается...")
        print(f"📁 Скриншоты сохраняются в: {self.screenshots_dir}")
        print(f"🔌 Подключение к API: {API_URL}")
        print("🖥️ Режим: полноэкранный native capture + учёт активного окна")
        print(f"🗄️ Локальное сохранение: {'включено' if KEEP_LOCAL_SCREENSHOTS else 'выключено'}")
        self.preflight_capture_check()
        
        if API_TOKEN:
            with self.state_lock:
                self.api_token = API_TOKEN
            print("✅ Токен API получен из окружения (API_TOKEN)")
            self.check_api_state()
        else:
            if not USER_CONTACT or not USER_PASSWORD:
                print("⚠️ ОШИБКА: Укажите USER_CONTACT и USER_PASSWORD в .env (или передайте API_TOKEN)")
                sys.exit(1)
            self.login_to_api()
        
        print(f"{'='*50}")
        if self.active:
            print(f"🟢 СТАТУС: АКТИВЕН (work/start активны)")
        else:
            print(f"🔴 СТАТУС: НЕАКТИВЕН (ждем start)")
        print("="*50 + "\n")
        
        # Запускаем фоновый поллинг
        self.poll_thread = threading.Thread(target=self.poll_dashboard_loop, daemon=True)
        self.poll_thread.start()
        self.activity_thread = threading.Thread(target=self.activity_loop, daemon=True)
        self.activity_thread.start()
        if WS_ACTIVITY_ENABLED:
            self.activity_ws_thread = threading.Thread(target=self.activity_ws_loop, daemon=True)
            self.activity_ws_thread.start()
        
        # Запускаем мониторинг кликов и клавиш
        self.start_monitoring()
        
    def login_to_api(self):
        """Логинится в API и получает токен"""
        try:
            resp = self.session.post(f"{API_URL}/api/v1/auth/login", json={
                "contact": USER_CONTACT,
                "password": USER_PASSWORD
            }, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                fresh_token = (data.get("token") or data.get("access_token") or "").strip()
                with self.state_lock:
                    self.api_token = fresh_token or None
                _persist_api_token(fresh_token)
                print("✅ Успешная авторизация в API!")
                # Сразу проверяем стейт
                self.check_api_state()
            else:
                print(f"❌ Ошибка авторизации: {resp.status_code} {resp.text}")
                sys.exit(1)
        except Exception as e:
            print(f"❌ Не удалось подключиться к серверу для входа: {e}")
            sys.exit(1)

    def preflight_capture_check(self):
        """Проверяет доступ к захвату экрана и печатает понятную причину, если прав нет."""
        probe = self.screenshots_dir / f"capture_probe{SCREENSHOT_EXT}"
        try:
            self.capture_to_file(probe)
            if probe.exists():
                probe.unlink(missing_ok=True)
            print("✅ Screen capture preflight: OK")
            return
        except Exception as e:
            self.print_capture_permissions_help(e)

    def print_capture_permissions_help(self, err: Exception):
        if self.capture_help_printed:
            return
        self.capture_help_printed = True
        print("⚠️ Не удалось захватить экран.")
        print(f"⚠️ Причина: {err}")
        if sys.platform == "darwin":
            print("ℹ️ macOS: включите права Screen Recording, Accessibility и Input Monitoring")
            print("   для Terminal/iTerm/VS Code и Python, затем перезапустите терминал.")
            print("   System Settings -> Privacy & Security -> Screen Recording")
            print("   System Settings -> Privacy & Security -> Accessibility")
            print("   System Settings -> Privacy & Security -> Input Monitoring")

    def check_api_state(self):
        """Проверяет текущий статус presence через /api/v1/me/dashboard"""
        with self.state_lock:
            token = self.api_token
        if not token:
            if not (USER_CONTACT and USER_PASSWORD):
                return
            self.login_to_api()
            with self.state_lock:
                token = self.api_token
            if not token:
                return
            
        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp = self.session.get(f"{API_URL}/api/v1/me/dashboard", headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                current_state = data.get("current_state", {})
                work_open = current_state.get("work_open", False)
                work_session_id = current_state.get("work_session_id")
                # Screen capture is tied strictly to work sessions.
                session_id = work_session_id if work_open else None
                capture_settings = data.get("capture_settings") or {}

                with self.state_lock:
                    self.current_session_id = session_id
                    self.current_work_session_id = session_id
                    self.heartbeat_interval_seconds = _clamp_int(
                        capture_settings.get("heartbeat_interval_seconds"),
                        self.heartbeat_interval_seconds,
                        5,
                        3600,
                    )
                    self.screenshot_interval_seconds = _clamp_int(
                        capture_settings.get("screenshot_interval_seconds"),
                        self.screenshot_interval_seconds,
                        15,
                        7200,
                    )
                    self.idle_threshold_seconds = _clamp_int(
                        capture_settings.get("idle_threshold_seconds"),
                        self.idle_threshold_seconds,
                        15,
                        3600,
                    )
                
                # Если статус изменился
                is_active = bool(work_open)
                if is_active != self.active:
                    self.active = is_active
                    self.last_heartbeat_sent_at = 0.0
                    self.last_auto_screenshot_at = 0.0
                    status = "🟢 СТАТУС Изменен: АКТИВЕН (start активен)" if self.active else "🔴 СТАТУС Изменен: НЕАКТИВЕН (stop/left или нет work-сессии)"
                    print(f"\n{status}")
            elif resp.status_code == 401:
                if USER_CONTACT and USER_PASSWORD:
                    print("⚠️ Токен истек, переподключение...")
                    self.login_to_api()
                else:
                    print("⚠️ Токен недействителен и нет USER_CONTACT/USER_PASSWORD для перелогина")
                    with self.state_lock:
                        self.api_token = None
                        self.current_session_id = None
                        self.current_work_session_id = None
                    if self.active:
                        self.active = False
                        print("\n🔴 СТАТУС Изменен: НЕАКТИВЕН (токен недействителен)")
        except Exception as e:
            print(f"⚠️ Ошибка при проверке статуса API: {e}")
            # Fail-safe: если сервер недоступен, не продолжаем съемку "вслепую".
            with self.state_lock:
                self.current_session_id = None
                self.current_work_session_id = None
            if self.active:
                self.active = False
                print("\n🔴 СТАТУС Изменен: НЕАКТИВЕН (нет связи с API)")

    def poll_dashboard_loop(self):
        """Фоновый цикл для периодического опроса бэкенда"""
        while self.is_running:
            time.sleep(POLL_INTERVAL)
            self.check_api_state()

    def activity_loop(self):
        """Периодически отправляет heartbeat и делает авто-скриншот."""
        while self.is_running:
            time.sleep(1)
            if not self.active:
                continue

            now_mono = time.monotonic()
            heartbeat_interval = max(5, int(self.heartbeat_interval_seconds))
            screenshot_interval = max(15, int(self.screenshot_interval_seconds))

            if now_mono - self.last_heartbeat_sent_at >= heartbeat_interval:
                self.last_heartbeat_sent_at = now_mono
                threading.Thread(target=self.send_heartbeat, daemon=True).start()

            if UPLOAD_SCREENSHOTS and now_mono - self.last_auto_screenshot_at >= screenshot_interval:
                self.last_auto_screenshot_at = now_mono
                threading.Thread(target=self.take_screenshot, kwargs={"reason": "auto"}, daemon=True).start()
    
    def on_click(self, x, y, button, pressed):
        """Обработчик клика мыши"""
        if pressed:
            self.last_input_monotonic = time.monotonic()
        if pressed and self.active:
            # Запускаем снятие скрина в отдельном потоке
            click_kind = getattr(button, "name", None) or str(button)
            thread = threading.Thread(
                target=self.take_screenshot,
                kwargs={"x": x, "y": y, "reason": f"click:{click_kind}"},
            )
            thread.daemon = True
            thread.start()
    
    def on_press(self, key):
        """Обработчик нажатия клавиши"""
        try:
            self.last_input_monotonic = time.monotonic()
            # Проверяем нажата ли F10
            if key == keyboard.Key.f10:
                self.toggle_active()
            # Проверяем нажат ли Enter
            elif key == keyboard.Key.enter:
                if self.active:
                    # Получаем текущую позицию мыши
                    mouse_controller = Controller()
                    x, y = mouse_controller.position
                    thread = threading.Thread(target=self.take_screenshot, kwargs={"x": x, "y": y, "reason": "enter"})
                    thread.daemon = True
                    thread.start()
        except AttributeError:
            pass
    
    def toggle_active(self):
        """Включает/отключает скринер"""
        self.active = not self.active
        status = "🟢 АКТИВЕН" if self.active else "🔴 ОТКЛЮЧЕН"
        print(f"\n{'='*50}")
        print(f"⚙️  F10 нажат - СТАТУС: {status}")
        print("="*50)
        if self.active:
            print("📸 Скринер включен - кликайте для снятия скринов")
        else:
            print("⏸️  Скринер отключен - клики не записываются")
        print("="*50 + "\n")
    
    def _run_text_command(self, command: list[str]) -> str:
        if not command:
            return ""
        if shutil.which(command[0]) is None:
            return ""
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return (result.stdout or "").strip()
        except Exception:
            return ""

    def _display_for_point(self, x: int | float | None, y: int | float | None) -> dict | None:
        if sys.platform != "darwin":
            return None
        if not self.display_helper_path.exists():
            return None

        if x is None or y is None:
            try:
                mouse_controller = Controller()
                x, y = mouse_controller.position
            except Exception:
                return None

        try:
            result = subprocess.run(
                [str(self.display_helper_path), "display-for-point", str(x), str(y)],
                check=True,
                capture_output=True,
                text=True,
                timeout=3,
            )
            payload = json.loads((result.stdout or "").strip())
            return {
                "display_id": int(payload.get("displayId")),
                "x": float(payload.get("x")),
                "y": float(payload.get("y")),
                "width": float(payload.get("width")),
                "height": float(payload.get("height")),
            }
        except Exception:
            return None

    def _linux_active_window_metadata(self) -> tuple[str | None, str | None]:
        app_name = None
        window_title = None

        window_id = self._run_text_command(["xdotool", "getactivewindow"])
        if window_id:
            window_title = self._run_text_command(["xdotool", "getwindowname", window_id]) or None

            pid_text = self._run_text_command(["xdotool", "getwindowpid", window_id])
            if pid_text.isdigit():
                try:
                    proc_comm = Path(f"/proc/{pid_text}/comm").read_text(encoding="utf-8").strip()
                    app_name = proc_comm or None
                except Exception:
                    app_name = None

            if not app_name:
                app_name = self._run_text_command(["xdotool", "getwindowclassname", window_id]) or None

        # Fallback when xdotool is unavailable/incomplete.
        if not app_name or not window_title:
            active_line = self._run_text_command(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
            match = re.search(r"window id # (0x[0-9a-fA-F]+)", active_line)
            if match:
                xid = match.group(1)
                if not window_title:
                    name_line = self._run_text_command(["xprop", "-id", xid, "_NET_WM_NAME"])
                    if name_line:
                        # Example: _NET_WM_NAME(UTF8_STRING) = "Terminal"
                        parts = name_line.split("=", 1)
                        if len(parts) == 2:
                            window_title = parts[1].strip().strip('"') or window_title
                if not app_name:
                    class_line = self._run_text_command(["xprop", "-id", xid, "WM_CLASS"])
                    if class_line:
                        # Example: WM_CLASS(STRING) = "gnome-terminal", "Gnome-terminal"
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
            app_name = _clean_text(app_candidate, max_len=128)
            window_title = _clean_text(_strip_invisible_marks(title), max_len=512)
            if not window_title:
                continue
            rows.append(
                {
                    "app_name": app_name or "Unknown",
                    "window_title": window_title,
                }
            )
        return rows[:20]

    def get_active_window_metadata(self) -> dict:
        """Возвращает активное приложение и заголовок окна."""
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
            app_name, window_title = self._linux_active_window_metadata()
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
        app_name = _strip_invisible_marks(app_name)
        if not app_name:
            app_name = _guess_app_name_from_window_title(window_title)
        app_name = _clean_text(app_name, max_len=128)
        window_title = _clean_text(window_title, max_len=512)
        background_apps = sorted({row["app_name"] for row in background_windows if row.get("app_name")})[:20]

        return {
            # Legacy keys used by current backend analytics.
            "app_name": app_name,
            "window_title": window_title,
            # Explicit semantics for downstream logs/analytics.
            "active_app": app_name,
            "active_window_title": window_title,
            "is_foreground": True,
            "platform": sys.platform,
            "capture_mode": "clicked_display_native",
            "background_windows": background_windows,
            "background_apps": background_apps,
        }

    def _activity_ws_url(self) -> str:
        parsed = urlparse(API_URL)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        netloc = parsed.netloc or parsed.path
        return f"{scheme}://{netloc}/api/v1/agent/activity/ws"

    def _close_activity_ws(self):
        with self.activity_ws_lock:
            ws = self.activity_ws
            self.activity_ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _build_activity_payload(self) -> dict:
        idle_for_seconds = max(0, int(time.monotonic() - self.last_input_monotonic))
        state = "idle" if idle_for_seconds >= int(self.idle_threshold_seconds) else "active"
        metadata = self.get_active_window_metadata()
        return {
            "state": state,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "app_name": metadata.get("app_name") or "Unknown",
                "window_title": metadata.get("window_title"),
                "active_app": metadata.get("app_name") or "Unknown",
                "active_window_title": metadata.get("window_title"),
                "background_windows": metadata.get("background_windows") or [],
                "background_apps": metadata.get("background_apps") or [],
                "idle_for_seconds": idle_for_seconds,
                "source": "desktop_agent_native",
                "platform": metadata.get("platform") or sys.platform,
                "capture_mode": metadata.get("capture_mode") or "clicked_display_native",
                "activity_state": state,
            },
        }

    def activity_ws_loop(self):
        while self.is_running:
            with self.state_lock:
                token = self.api_token
            if not token:
                time.sleep(2)
                continue
            try:
                ws = websocket.create_connection(
                    self._activity_ws_url(),
                    timeout=REQUEST_TIMEOUT,
                    header=[f"Authorization: Bearer {token}"],
                )
                ws.settimeout(5)
                with self.activity_ws_lock:
                    self.activity_ws = ws
                while self.is_running:
                    try:
                        raw = ws.recv()
                    except Exception:
                        continue
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
                    snapshot = self._build_activity_payload()
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
            except Exception:
                time.sleep(2)
            finally:
                self._close_activity_ws()

    def send_heartbeat(self):
        """Отправляет heartbeat с активным окном."""
        self.check_api_state()
        with self.state_lock:
            token = self.api_token

        if not token:
            return

        payload = self._build_activity_payload()

        try:
            resp = self.session.post(
                f"{API_URL}/api/v1/heartbeart",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return
            if resp.status_code == 401:
                print("⚠️ Heartbeat не отправлен: токен истек, пробую перелогин")
                self.login_to_api()
                return
            print(f"⚠️ Heartbeat не отправлен: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"⚠️ Ошибка heartbeat: {e}")

    def take_screenshot(self, x=None, y=None, reason="manual"):
        """Делает скрин и сохраняет его"""
        filepath: Path | None = None
        try:
            metadata = self.get_active_window_metadata()
            target_display = self._display_for_point(x, y)
            if target_display:
                metadata["display_id"] = int(target_display["display_id"])
                metadata["display_bounds"] = {
                    "x": target_display["x"],
                    "y": target_display["y"],
                    "width": target_display["width"],
                    "height": target_display["height"],
                }
            # Генерируем имя файла с временной меткой
            captured_at = datetime.now(timezone.utc)
            timestamp = captured_at.strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]
            filename = f"screenshot_{timestamp}{SCREENSHOT_EXT}"
            if KEEP_LOCAL_SCREENSHOTS:
                filepath = self.screenshots_dir / filename
            else:
                filepath = Path(tempfile.gettempdir()) / f"td_screenshot_{timestamp}{SCREENSHOT_EXT}"
            
            # Берём скрин во временный файл (или локальный, если включено)
            self.capture_to_file(filepath, target_display=target_display)
            
            # Обновляем счётчик
            self.screenshot_count += 1
            details = []
            if metadata.get("app_name"):
                details.append(f"app={metadata['app_name']}")
            if metadata.get("window_title"):
                details.append(f"window={metadata['window_title']}")
            if metadata.get("display_id"):
                details.append(f"display={metadata['display_id']}")
            if x is not None and y is not None:
                details.append(f"координаты: {x}, {y}")
            detail_text = f" ({'; '.join(details)})" if details else ""
            
            if KEEP_LOCAL_SCREENSHOTS:
                print(f"✅ Скрин #{self.screenshot_count} сохранен: {filename} [{reason}]{detail_text}")
            else:
                print(f"✅ Скрин #{self.screenshot_count} сделан [{reason}]{detail_text}")
            if UPLOAD_SCREENSHOTS:
                self.upload_screenshot(filepath, captured_at, metadata)
            elif not KEEP_LOCAL_SCREENSHOTS:
                print("⚠️ UPLOAD_SCREENSHOTS=false и локальное сохранение отключено: скрин будет удален")
            
        except Exception as e:
            print(f"❌ Ошибка при сохранении скрина: {e}")
        finally:
            if filepath is not None and not KEEP_LOCAL_SCREENSHOTS:
                try:
                    filepath.unlink(missing_ok=True)
                except Exception:
                    pass

    def capture_to_file(self, filepath: Path, target_display: dict | None = None):
        """Сохраняет screenshot нужного экрана."""
        try:
            _ensure_avif_support()
            if sys.platform == "darwin":
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                    tmp_path = Path(tmp_file.name)
                try:
                    command = ["screencapture", "-x"]
                    if target_display and target_display.get("display_id") is not None:
                        command.extend(["-D", str(int(target_display["display_id"]))])
                    command.append(str(tmp_path))
                    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if tmp_path.exists() and tmp_path.stat().st_size > 0:
                        with Image.open(tmp_path) as screenshot:
                            screenshot.save(str(filepath), format="AVIF")
                        if filepath.exists() and filepath.stat().st_size > 0:
                            return
                finally:
                    tmp_path.unlink(missing_ok=True)
            try:
                screenshot = ImageGrab.grab(all_screens=True)
            except TypeError:
                screenshot = ImageGrab.grab()
            if target_display and all(key in target_display for key in ("x", "y", "width", "height")):
                left = int(round(target_display["x"]))
                top = int(round(target_display["y"]))
                right = left + int(round(target_display["width"]))
                bottom = top + int(round(target_display["height"]))
                try:
                    screenshot = screenshot.crop((left, top, right, bottom))
                except Exception:
                    pass
            screenshot.save(str(filepath), format="AVIF")
            return
        except Exception as primary_error:
            self.print_capture_permissions_help(primary_error)
            raise primary_error

    def upload_screenshot(self, filepath: Path, captured_at: datetime, metadata: dict | None = None):
        """Отправляет скриншот в backend, привязав к активной сессии"""
        # Перед отправкой подтягиваем актуальный статус (came/left)
        self.check_api_state()
        with self.state_lock:
            token = self.api_token
            session_id = self.current_session_id

        if not token:
            print("⚠️ Скрин не отправлен: нет токена API")
            return
        if not session_id:
            print("⚠️ Скрин не отправлен: нет активной session_id (нужен start)")
            return

        headers = {"Authorization": f"Bearer {token}"}
        data = {
            "session_id": str(session_id),
            "captured_at": captured_at.isoformat(),
        }
        if metadata:
            if metadata.get("app_name"):
                data["app_name"] = str(metadata["app_name"])
            if metadata.get("window_title"):
                data["window_title"] = str(metadata["window_title"])
        try:
            with filepath.open("rb") as image_file:
                files = {"image": (filepath.name, image_file, SCREENSHOT_MIME_TYPE)}
                resp = self.session.post(
                    f"{API_URL}/api/v1/screenshots",
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=REQUEST_TIMEOUT,
                )

            if resp.status_code == 200:
                payload = resp.json()
                print(f"☁️ Скрин отправлен в API: screenshot_id={payload.get('screenshot_id')}")
                return

            if resp.status_code == 401:
                print("⚠️ Скрин не отправлен: токен истек, пробую перелогин")
                self.login_to_api()
                return

            print(f"⚠️ Скрин не отправлен: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"⚠️ Ошибка отправки скрина: {e}")
    
    def start_monitoring(self):
        """Начинает мониторинг кликов мыши и клавиш"""
        try:
            # Мониторинг мыши
            self.listener = mouse.Listener(on_click=self.on_click)
            self.listener.start()
            
            # Мониторинг клавиатуры
            self.keyboard_listener = keyboard.Listener(on_press=self.on_press)
            self.keyboard_listener.start()
            print("✅ Click/keyboard listeners запущены")
            
            # Ждём до прерывания
            while True:
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Останавливает приложение"""
        self.is_running = False
        self._close_activity_ws()
        print(f"\n\n{'='*50}")
        print("👋 Приложение завершено")
        print(f"📊 Всего сделано скриншотов: {self.screenshot_count}")
        print(f"📁 Они находятся в: {self.screenshots_dir}")
        print(f"{'='*50}\n")
        sys.exit(0)


def main():
    try:
        app = ScreenshotApp()
    except KeyboardInterrupt:
        print(f"\n\n{'='*50}")
        print("👋 Приложение завершено")
        print(f"{'='*50}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
