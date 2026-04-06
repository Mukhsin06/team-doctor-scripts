# TeamDoctor Screener: инструкция для сотрудника

Скринер запускается на вашем компьютере (не на сервере).

## 1) Linux

### Установка и запуск

```bash
cd screener
bash setup.sh --api-url https://api-team-doctor.tenzorsoft.uz --contact 'YOUR_EMAIL' --password 'YOUR_PASSWORD'
bash run.sh
```

### Автозапуск после перезагрузки

```bash
cd screener
bash install_autostart_linux.sh
systemctl --user status teamdoctor-screener.service
```

Логи:

```bash
journalctl --user -u teamdoctor-screener.service -f
```

## 2) macOS

### Установка и запуск

```bash
cd screener
bash setup.sh --api-url https://api-team-doctor.tenzorsoft.uz --contact 'YOUR_EMAIL' --password 'YOUR_PASSWORD'
bash run.sh
```

### Автозапуск после перезагрузки

```bash
cd screener
bash install_autostart_macos.sh
launchctl list | grep uz.tenzorsoft.teamdoctor.screener
```

Логи:

```bash
tail -f screener/screener.launchd.out.log
```

## 3) Windows (PowerShell)

### Установка и запуск

```powershell
cd screener
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -ApiUrl "https://api-team-doctor.tenzorsoft.uz" -Contact "YOUR_EMAIL" -Password "YOUR_PASSWORD"
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1
```

### Автозапуск после перезагрузки

```powershell
cd screener
powershell -ExecutionPolicy Bypass -File .\install_autostart_windows.ps1
Get-ScheduledTask -TaskName TeamDoctorScreener | Format-List
```

## Важно

- Рекомендуется вход по `contact + password`, чтобы агент сам перелогинивался при истечении JWT.
- Если используете токен, он может истечь и тогда потребуется обновление токена.
- На macOS нужно разрешить: Screen Recording + Accessibility + Input Monitoring.
- Скринер начинает снимать экран по `/start` и останавливается по `/stop`.
