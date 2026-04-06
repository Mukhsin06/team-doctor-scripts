param(
  [Parameter(Mandatory=$true)][string]$ApiUrl,
  [string]$Token = "",
  [string]$Contact = "",
  [string]$Password = ""
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not $Token -and (-not $Contact -or -not $Password)) {
  throw "Provide -Token OR both -Contact and -Password"
}

$pythonExe = $null
$pythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
  $pythonExe = "py"
  $pythonArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $pythonExe = "python"
} else {
  throw "Python not found. Install Python 3.9+ first."
}

$venvDir = Join-Path $scriptDir 'venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
  if (Test-Path $venvDir) {
    Write-Warning "Found incomplete venv at $venvDir. Recreating..."
    Remove-Item -Recurse -Force $venvDir
  }

  Write-Host "Creating venv..."
  & $pythonExe @pythonArgs -m venv $venvDir
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
    throw "Failed to create virtual environment at $venvDir. Ensure Python includes venv support."
  }
}

& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install -r requirements.txt

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
  Copy-Item ".env.example" ".env"
}
if (-not (Test-Path ".env")) {
  @"
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
"@ | Set-Content -Encoding UTF8 ".env"
}

function Set-EnvValue([string]$key, [string]$value) {
  $lines = Get-Content ".env" -ErrorAction SilentlyContinue
  $found = $false
  $newLines = @()
  foreach ($line in $lines) {
    if ($line -match "^$key=") {
      $newLines += "$key=$value"
      $found = $true
    } else {
      $newLines += $line
    }
  }
  if (-not $found) { $newLines += "$key=$value" }
  $newLines | Set-Content -Encoding UTF8 ".env"
}

Set-EnvValue "API_URL" $ApiUrl
if ($Token) {
  Set-EnvValue "API_TOKEN" $Token
}
if ($Contact) {
  Set-EnvValue "USER_CONTACT" $Contact
}
if ($Password) {
  Set-EnvValue "USER_PASSWORD" $Password
}

if ($Token -and (-not $Contact -or -not $Password)) {
  Write-Warning "Token-only setup: after token expiration auto re-login requires USER_CONTACT + USER_PASSWORD."
}

Write-Host "✅ Windows setup completed"
Write-Host "Run agent: powershell -ExecutionPolicy Bypass -File .\\run_windows.ps1"
Write-Host "Optional autostart: powershell -ExecutionPolicy Bypass -File .\\install_autostart_windows.ps1"
