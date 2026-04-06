# TeamDoctor Agents Install

You can send employees only this `scripts/` folder.

These installers will:
- install both agents: `screener` and `active_apps_agent`
- write `API_URL`, `USER_CONTACT`, `USER_PASSWORD`
- enable autostart for the current OS

## Linux / macOS

1. Send the whole `scripts/` folder to the employee.
2. Ask them to open Terminal in that folder.
3. Run:

```bash
bash install_teamdoctor_agent.sh --api-url https://api-team-doctor.tenzorsoft.uz --contact USER_CONTACT --password USER_PASSWORD
```

If autostart is not needed:

```bash
bash install_teamdoctor_agent.sh --api-url https://api-team-doctor.tenzorsoft.uz --contact USER_CONTACT --password USER_PASSWORD --no-autostart
```

## Windows

1. Send the whole `scripts/` folder to the employee.
2. Ask them to open PowerShell in that folder.
3. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_teamdoctor_agents.ps1 -ApiUrl https://api-team-doctor.tenzorsoft.uz -Contact USER_CONTACT -Password USER_PASSWORD
```

If autostart is not needed:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_teamdoctor_agents.ps1 -ApiUrl https://api-team-doctor.tenzorsoft.uz -Contact USER_CONTACT -Password USER_PASSWORD -NoAutostart
```

## Notes

- Install location by default:
  - current `scripts/` folder
- Keep `screener/`, `active_apps_agent/`, and install scripts together inside this same folder.
- Python will be used from the employee machine.
- On Linux/macOS the employee should run the installer from a desktop user session, not from a headless server session.

## E2E Check (/start -> /stop)

After desktop login + installer, run from `scripts/`:

```bash
python3 e2e_start_stop_check.py
```

What it verifies:
- both agents autostart registration is present and active (Linux/macOS/Windows)
- before `/start`: `POST /api/v1/active_apps` returns idle (`session_id=null`, `activity=null`)
- after `/start`: agent returns live app activity and heartbeat is written for running work session
- after `/stop`: `POST /api/v1/active_apps` returns idle again

Optional flags:

```bash
python3 e2e_start_stop_check.py --timeout-seconds 90 --poll-interval-seconds 2
python3 e2e_start_stop_check.py --skip-autostart-check
```
# team-doctor-scripts
