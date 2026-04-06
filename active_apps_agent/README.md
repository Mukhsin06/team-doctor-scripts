# active_apps_agent

Separate module (independent from `screener`) that collects active/background windows and answers backend requests over WebSocket.

For one-command setup of both agents from the repo root, use:

Linux/macOS:
```bash
bash scripts/install_teamdoctor_agent.sh --api-url https://api-team-doctor.tenzorsoft.uz --contact USER_CONTACT --password USER_PASSWORD
```

Windows:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_teamdoctor_agents.ps1 -ApiUrl https://api-team-doctor.tenzorsoft.uz -Contact USER_CONTACT -Password USER_PASSWORD
```

## Setup

Linux:
```bash
cd active_apps_agent
bash setup.sh --api-url https://api-team-doctor.tenzorsoft.uz --contact USER_CONTACT --password USER_PASSWORD
```

macOS:
```bash
cd active_apps_agent
bash setup.sh --api-url https://api-team-doctor.tenzorsoft.uz --contact USER_CONTACT --password USER_PASSWORD
```

Windows:
```powershell
cd active_apps_agent
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -ApiUrl https://api-team-doctor.tenzorsoft.uz -Contact USER_CONTACT -Password USER_PASSWORD
```

These commands:
- creates `venv`
- installs dependencies
- writes `.env`
- enables autostart for the current OS
- uses `USER_CONTACT` + `USER_PASSWORD` for auto login

## Run

```bash
cd active_apps_agent
source venv/bin/activate
python3 main.py
```

Manual setup without autostart:

```bash
cd active_apps_agent
bash setup.sh --api-url https://api-team-doctor.tenzorsoft.uz --contact USER_CONTACT --password USER_PASSWORD --no-autostart
```

Windows without autostart:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -ApiUrl https://api-team-doctor.tenzorsoft.uz -Contact USER_CONTACT -Password USER_PASSWORD -NoAutostart
```

Backend WebSocket endpoint:
- `/api/v1/agent/active_apps/ws`

Backend API endpoint to request live activity:
- `POST /api/v1/active_apps` (auth only).
