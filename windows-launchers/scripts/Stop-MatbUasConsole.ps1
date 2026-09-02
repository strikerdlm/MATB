[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")

$repoRoot = Get-MatbUasRepoRoot
$dataRoot = Get-MatbUasDataRoot -RepoRoot $repoRoot
$statePath = Join-Path $dataRoot "service\service-state.json"
$state = Read-MatbUasState -StatePath $statePath
if (-not $state) {
    Write-Host "No tracked MATB UAS console is running."
    return
}

$stateRepo = [System.IO.Path]::GetFullPath([string]$state.repo_root)
if (-not $stateRepo.Equals($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "The service state belongs to a different MATB repository. Refusing to stop it."
}

$state.status = "stopping"
$state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8

$frontendStopped = Stop-MatbUasTrackedProcess `
    -ProcessId ([int]$state.frontend_pid) `
    -ExpectedExecutable ([string]$state.frontend_executable) `
    -ExpectedStartedAtUtc $state.frontend_started_at_utc `
    -Role frontend `
    -Port ([int]$state.frontend_port) `
    -RepoRoot $repoRoot
$backendStopped = Stop-MatbUasTrackedProcess `
    -ProcessId ([int]$state.backend_pid) `
    -ExpectedExecutable ([string]$state.backend_executable) `
    -ExpectedStartedAtUtc $state.backend_started_at_utc `
    -Role backend `
    -Port ([int]$state.backend_port) `
    -RepoRoot $repoRoot

if (-not $frontendStopped -or -not $backendStopped) {
    $state.status = "attention_required"
    $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
    throw "One or more tracked processes did not pass identity checks and were left running."
}

Remove-MatbUasStateFile -StatePath $statePath -DataRoot $dataRoot
Write-Host "MATB UAS console stopped." -ForegroundColor Green
