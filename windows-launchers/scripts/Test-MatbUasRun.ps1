[CmdletBinding()]
param(
    [string]$RunDirectory,
    [string]$DataRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")

$repoRoot = Get-MatbUasRepoRoot
$pythonPath = Get-MatbUasPython -RepoRoot $repoRoot
$dataRoot = Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $DataRoot
$runsRoot = Join-Path $dataRoot "runs"

if (-not $RunDirectory) {
    $latestRun = Get-MatbUasLatestSealedRun -RepoRoot $repoRoot -DataRoot $dataRoot
    if (-not $latestRun) {
        throw "No sealed Windows sUAS runs were found. Incomplete runs were ignored."
    }
    $RunDirectory = $latestRun.FullName
}

$resolvedRun = [System.IO.Path]::GetFullPath($RunDirectory)
$resolvedRunsRoot = [System.IO.Path]::GetFullPath($runsRoot).TrimEnd('\') + '\'
if (-not $resolvedRun.StartsWith($resolvedRunsRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "The run must be inside $runsRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $resolvedRun "manifest.json") -PathType Leaf)) {
    throw "No MATB manifest was found in $resolvedRun"
}

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
Push-Location $repoRoot
try {
    $verificationText = & $pythonPath -m matb_integration.suas.cli verify $resolvedRun
    if ($LASTEXITCODE -ne 0) {
        throw "Verification failed for $resolvedRun"
    }
    $verification = $verificationText | Select-Object -Last 1 | ConvertFrom-Json
} finally {
    Pop-Location
}

Write-Host "Run: $resolvedRun"
Write-Host "Status: $($verification.status)"
Write-Host "Checksums: $($verification.checksum_status)"
Write-Host "Replay: $($verification.replay_status)"
if ($verification.status -ne "match") {
    throw "The latest technical run does not match."
}
Write-Host "MATCH: the latest run is internally consistent." -ForegroundColor Green
