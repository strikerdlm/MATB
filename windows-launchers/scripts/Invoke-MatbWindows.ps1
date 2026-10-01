[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet("Console", "Desktop", "Diagnose", "Stop")][string]$Action)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbBootstrap.ps1")
Update-MatbBootstrapPath
$powerShell = Get-MatbBootstrapPowerShell
if (-not $powerShell) { Write-Host "Run Install MATB.cmd first." -ForegroundColor Red; exit 1 }
$scripts = @{
    Console = "Start-MatbUasConsole.ps1"
    Desktop = "Start-MatbDesktop.ps1"
    Diagnose = "Test-MatbUasEnvironment.ps1"
    Stop = "Stop-MatbUasConsole.ps1"
}
& $powerShell -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot $scripts[$Action])
exit $LASTEXITCODE
