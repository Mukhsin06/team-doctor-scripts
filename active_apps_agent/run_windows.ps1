$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$venvPython = Join-Path $scriptDir 'venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
  throw "venv\Scripts\python.exe not found. Run setup_windows.ps1 first."
}

& $venvPython "main.py"
