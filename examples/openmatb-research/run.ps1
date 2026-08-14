param([string]$OutputDir = "")
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
if (-not $OutputDir) { $OutputDir = Join-Path $RepoRoot "examples/output/openmatb-research" }
$Python = if ($env:MATB_PYTHON) { $env:MATB_PYTHON } else { "python" }
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw "MATB Python executable not found: $Python"
}
Set-Location $RepoRoot
& $Python examples/openmatb-research/run_example.py --output-dir $OutputDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
