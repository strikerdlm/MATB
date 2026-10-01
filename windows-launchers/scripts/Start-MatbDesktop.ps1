[CmdletBinding()]
param([ValidateSet("es_CO", "en_EN", "fr_FR")][string]$Language = "es_CO", [string]$DataRoot = "")
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")
$repoRoot = Get-MatbUasRepoRoot
$python = Get-MatbUasPython -RepoRoot $repoRoot
if (-not (Test-MatbUasPythonDependencies -RepoRoot $repoRoot -PythonPath $python)) {
    throw "MATB packages are incomplete or incompatible. Run Install MATB.cmd."
}
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$dataRoot = Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $DataRoot
$sessionRoot = Join-Path $dataRoot ("desktop/{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), [guid]::NewGuid().ToString("N"))
New-MatbUasDirectory -Path $sessionRoot
Write-Host "Desktop OpenMATB data: $sessionRoot"
# Windowed on the first display works on a single-monitor Windows station.
& $python (Join-Path $repoRoot "openmatb/main.py") --language $Language --windowed --display-index 0 --session-dir $sessionRoot
if ($LASTEXITCODE -ne 0) { throw "OpenMATB exited with code $LASTEXITCODE. Run Diagnose MATB.cmd." }
