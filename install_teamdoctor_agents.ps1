param(
  [Parameter(Mandatory=$true)][string]$ApiUrl,
  [string]$Token = "",
  [string]$Contact = "",
    [string]$Password = "",
  [string]$InstallDir = "",
  [switch]$NoAutostart
)

$ErrorActionPreference = 'Stop'

if (-not $InstallDir) {
  if ($PSScriptRoot) {
    $InstallDir = $PSScriptRoot
  } elseif ($MyInvocation.MyCommand.Path) {
    $InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path
  } else {
    $InstallDir = (Get-Location).Path
  }
}
$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)

if (-not $Token -and (-not $Contact -or -not $Password)) {
  throw "Provide -Token OR both -Contact and -Password"
}

if (-not (Test-Path (Join-Path $InstallDir 'screener'))) {
  throw "Missing $InstallDir\screener"
}
if (-not (Test-Path (Join-Path $InstallDir 'active_apps_agent'))) {
  throw "Missing $InstallDir\active_apps_agent"
}

Set-Location $InstallDir

$screenerSetup = Join-Path $InstallDir 'screener\setup_windows.ps1'
$activeAppsSetup = Join-Path $InstallDir 'active_apps_agent\setup_windows.ps1'

if (-not (Test-Path $screenerSetup)) {
  throw "Missing $screenerSetup"
}
if (-not (Test-Path $activeAppsSetup)) {
  throw "Missing $activeAppsSetup"
}

$commonArgs = @{
  ApiUrl = $ApiUrl
}

if ($Token) {
  $commonArgs.Token = $Token
}

if (($Contact -and -not $Password) -or (-not $Contact -and $Password)) {
  throw "If one of -Contact / -Password is provided, both must be provided"
}

if ($Contact -and $Password) {
  $commonArgs.Contact = $Contact
  $commonArgs.Password = $Password
} elseif (-not $Token) {
  throw "Provide -Token OR both -Contact and -Password"
}

if ($NoAutostart) {
  & $screenerSetup @commonArgs
  & $activeAppsSetup @commonArgs -NoAutostart
} else {
  & $screenerSetup @commonArgs
  & (Join-Path $InstallDir 'screener\install_autostart_windows.ps1')
  & $activeAppsSetup @commonArgs
}

Write-Host "✅ Both agents are configured on Windows"
Write-Host "Manual run: powershell -ExecutionPolicy Bypass -File `"$InstallDir\run_teamdoctor_agents.ps1`""
Write-Host "Install dir: $InstallDir"
