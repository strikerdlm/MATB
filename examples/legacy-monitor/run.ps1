param(
    [ValidateSet("uav", "fighter", "combined", "experiment")]
    [string]$Mode = "combined",
    [string]$OutputDir = ""
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
if (-not $OutputDir) { $OutputDir = Join-Path $RepoRoot "examples/output/legacy-monitor" }
Set-Location $RepoRoot

$Arguments = @($Mode, "--headless", "--event-delay", "0.05", "--seed", "42")
if ($Mode -eq "experiment") {
    $Arguments += @("--participant-id", "SYNTH-P01", "--session-id", "SYNTH-S01", "--research-output-dir", $OutputDir)
}
& python -m aircraft_monitor @Arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
