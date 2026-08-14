param([string]$OutputDir = "")
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
if (-not $OutputDir) { $OutputDir = Join-Path $RepoRoot "examples/output/openmatb-research" }
Set-Location $RepoRoot
python examples/openmatb-research/run_example.py --output-dir $OutputDir
