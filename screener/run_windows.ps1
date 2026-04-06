$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$python = Join-Path $scriptDir 'venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  Write-Error "venv not found. Run .\\setup_windows.ps1 first."
  exit 1
}

& $python -u (Join-Path $scriptDir 'main.py')
