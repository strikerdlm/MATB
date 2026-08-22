$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Set-Location (Join-Path $RepoRoot "SMS")

npm ci
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

npm run build:packages
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

node ../examples/sms-platform/package-tour.mjs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
