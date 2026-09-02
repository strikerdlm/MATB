[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("PRACTICE", "LOW", "MEDIUM", "HIGH")]
    [string]$WorkloadProfile,

    [string]$Scenario = "reference_area_search",

    [ValidateRange(0, 10000000)]
    [int]$Ticks = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")

$repoRoot = Get-MatbUasRepoRoot
$pythonPath = Get-MatbUasPython -RepoRoot $repoRoot
$scenarioPath = Join-Path $repoRoot ("scenarios\suas\{0}.yaml" -f $Scenario)
if (-not (Test-Path -LiteralPath $scenarioPath -PathType Leaf)) {
    throw "Scenario not found: $scenarioPath"
}

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
if ($Ticks -eq 0) {
    $ticksText = & $pythonPath -c "from pathlib import Path; import sys; from matb_integration.suas.engine.runtime import TICK_MS; from matb_integration.suas.scenarios.loader import load_scenario; loaded=load_scenario(Path(sys.argv[1])); print(loaded.definition.blocks[sys.argv[2]].duration_ms // TICK_MS)" $scenarioPath $WorkloadProfile
    if ($LASTEXITCODE -ne 0 -or -not $ticksText) {
        throw "Could not derive the configured duration for $WorkloadProfile."
    }
    $Ticks = [int]($ticksText | Select-Object -Last 1)
}

$dataRoot = Get-MatbUasDataRoot -RepoRoot $repoRoot
$runsRoot = Join-Path $dataRoot "runs"
New-MatbUasDirectory -Path $runsRoot
$timestamp = [DateTime]::Now.ToString("yyyyMMdd-HHmmssfff")
$runDirectory = Join-Path $runsRoot ("{0}-{1}-{2}" -f $timestamp, $Scenario, $WorkloadProfile)
$sessionId = "SYNTH-WIN-$WorkloadProfile-$timestamp"

Write-Host "MATB UAS technical simulation" -ForegroundColor Cyan
Write-Host "Scenario: $Scenario"
Write-Host "Profile:  $WorkloadProfile"
Write-Host "Ticks:    $Ticks"
Write-Warning "This headless run is a technical simulation, not a valid participant session."

Push-Location $repoRoot
try {
    & $pythonPath -m matb_integration.suas.cli validate $scenarioPath
    if ($LASTEXITCODE -ne 0) {
        throw "Scenario validation failed."
    }

    & $pythonPath -m matb_integration.suas.cli record $scenarioPath `
        --block $WorkloadProfile `
        --ticks $Ticks `
        --session-id $sessionId `
        --output $runDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Scenario recording failed."
    }

    $verificationText = & $pythonPath -m matb_integration.suas.cli verify $runDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Replay or checksum verification failed for $runDirectory"
    }
    $verification = $verificationText | Select-Object -Last 1 | ConvertFrom-Json
    if ($verification.status -ne "match" -or $verification.checksum_status -ne "match" -or $verification.replay_status -ne "match") {
        throw "The technical run did not produce a complete match."
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "MATCH: replay and checksums verified." -ForegroundColor Green
Write-Host "Artifacts: $runDirectory"
