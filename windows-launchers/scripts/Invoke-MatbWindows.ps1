[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet("Console", "Desktop", "Diagnose", "Stop", "Profile", "Verify", "Results")][string]$Action,
    [string]$DataRoot = "",
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 3100,
    [switch]$NoBrowser,
    [ValidateSet('PRACTICE', 'LOW', 'MEDIUM', 'HIGH')][string]$WorkloadProfile = 'PRACTICE',
    [ValidateRange(0, 10000000)][int]$Ticks = 0,
    [switch]$ListOnly
)
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
    Profile = "Invoke-MatbUasProfile.ps1"
    Verify = "Test-MatbUasRun.ps1"
    Results = "Open-MatbUasResults.ps1"
}
$forward = @()
if ($DataRoot) { $forward += @('-DataRoot', $DataRoot) }
if ($Action -in @('Console', 'Stop', 'Diagnose')) { $forward += @('-BackendPort', $BackendPort, '-FrontendPort', $FrontendPort) }
if ($Action -eq 'Profile') { $forward += @('-WorkloadProfile', $WorkloadProfile, '-Ticks', $Ticks) }
if ($Action -eq 'Results' -and $ListOnly) { $forward += '-ListOnly' }
if ($Action -eq 'Console') {
    $forward += '-NoWait'
    if ($NoBrowser) { $forward += '-NoBrowser' }
}
& $powerShell -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot $scripts[$Action]) @forward
exit $LASTEXITCODE
