# Screener

Desktop agent for TeamDoctor: captures screenshots and sends heartbeats/screenshots to backend API.

## Requirements

- Python 3.9+
- Desktop session (GUI). Do not run on headless backend server.
- Linux/macOS/Windows

## Quick install

```bash
cd screener
bash setup.sh --api-url https://api-team-doctor.tenzorsoft.uz --contact user@example.com --password 'secret'
```

Or bootstrap with API token:

```bash
bash setup.sh --api-url https://api-team-doctor.tenzorsoft.uz --token '<JWT_TOKEN>'
```

This will:

- create `venv`
- install dependencies
- create `.env`
- write passed API credentials/settings into `.env`

## One-command install for both agents (Linux/macOS)

Run from any folder:

```bash
bash -c "$(curl -fsSL https://gitlab.tenzorsoft.com/tenzorsoft/team-doctor/team-doctor-backend/-/raw/abdusami/scripts/install_teamdoctor_agent.sh)" -- --api-url https://api-team-doctor.tenzorsoft.uz --contact 'user@example.com' --password 'secret'
```

This configures both `screener` and `active_apps_agent`.

If your GitLab is private, user must be logged in / have git access configured on machine.

## Run

```bash
cd screener
bash run.sh
```

## Autostart (all OS)

### Linux (systemd user)

```bash
cd screener
bash install_autostart_linux.sh
```

Useful commands:

```bash
systemctl --user status teamdoctor-screener.service
journalctl --user -u teamdoctor-screener.service -f
systemctl --user restart teamdoctor-screener.service
```

### macOS (LaunchAgents)

```bash
cd screener
bash install_autostart_macos.sh
launchctl list | grep uz.tenzorsoft.teamdoctor.screener
```

### Windows (Task Scheduler, PowerShell)

```powershell
cd screener
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -ApiUrl "https://api-team-doctor.tenzorsoft.uz" -Token "JWT_TOKEN"
powershell -ExecutionPolicy Bypass -File .\install_autostart_windows.ps1
Get-ScheduledTask -TaskName TeamDoctorScreener | Format-List
```

## Environment (.env)

Base template: `.env.example`

Main vars:

- `API_URL`
- `USER_CONTACT` + `USER_PASSWORD` (recommended for auto relogin)
- `API_TOKEN` (optional bootstrap)
- `POLL_INTERVAL`
- `HEARTBEAT_INTERVAL`
- `SCREENSHOT_INTERVAL`
- `IDLE_THRESHOLD_SECONDS`

Default `POLL_INTERVAL` is `5` seconds for faster reaction after `/start` and `/stop`.

## Notes

- If you see `DISPLAY is not set` or X11 errors, agent is running without GUI.
- Agent must run on employee computer, not inside backend container.
- Employee-friendly step-by-step guide: `EMPLOYEE_SETUP.md`
- On successful relogin agent persists fresh `API_TOKEN` into `.env`.
- Heartbeat app log fields: `active_app`, `active_window_title`, `activity_state`, `duration_since_input_seconds`, `is_foreground`.
