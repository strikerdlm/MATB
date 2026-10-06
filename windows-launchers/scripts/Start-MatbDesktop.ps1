[CmdletBinding()]
param([ValidateSet("es_CO", "en_EN", "fr_FR")][string]$Language = "es_CO", [string]$DataRoot = "")
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")
$repoRoot = Get-MatbUasRepoRoot
$dataRoot = Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $DataRoot
$launcherLock = Enter-MatbLauncherLock -RepoRoot $repoRoot
try {
Stop-MatbConsoleInstance -RepoRoot $repoRoot -DataRoot $dataRoot
$python = Get-MatbUasPython -RepoRoot $repoRoot
if (-not (Test-MatbUasPythonDependencies -RepoRoot $repoRoot -PythonPath $python)) {
    throw "MATB packages are incomplete or incompatible. Run Install MATB.cmd."
}
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$sessionRoot = Join-Path $dataRoot ("desktop/{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), [guid]::NewGuid().ToString("N"))
New-MatbUasDirectory -Path $sessionRoot
Write-Host "Desktop OpenMATB data: $sessionRoot"
# Windowed on the first display works on a single-monitor Windows station.
$nativeScript = '"' + (Join-Path $repoRoot 'openmatb/main.py') + '"'
$nativeSessionRoot = '"' + $sessionRoot + '"'
$native = Start-Process -FilePath $python -ArgumentList @($nativeScript, '--language', $Language,
    '--windowed', '--display-index', '0', '--session-dir', $nativeSessionRoot) -WorkingDirectory (Join-Path $repoRoot 'openmatb') -WindowStyle Hidden -PassThru
# Release before waiting: a second double-click must be able to restart it.
} finally {
    $launcherLock.ReleaseMutex()
    $launcherLock.Dispose()
}
$native.WaitForExit()
if ($native.ExitCode -ne 0) { throw "OpenMATB exited with code $($native.ExitCode). Run Diagnose MATB.cmd." }
