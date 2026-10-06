[CmdletBinding()]
param(
    [string]$DataRoot = "",
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 3100
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")
$repoRoot = Get-MatbUasRepoRoot
$dataRoot = Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $DataRoot
$launcherLock = Enter-MatbLauncherLock -RepoRoot $repoRoot
try {
    Stop-MatbConsoleInstance -RepoRoot $repoRoot -DataRoot $dataRoot -BackendPort $BackendPort -FrontendPort $FrontendPort
    Write-Host "MATB console and native windows stopped. Saved data retained." -ForegroundColor Green
} finally {
    $launcherLock.ReleaseMutex()
    $launcherLock.Dispose()
}
