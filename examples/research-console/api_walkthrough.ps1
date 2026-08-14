param(
    [string]$BaseUrl = $env:BASE_URL,
    [string]$OutputDir = $env:OUTPUT_DIR
)

$ErrorActionPreference = "Stop"
if (-not $BaseUrl) { $BaseUrl = "http://127.0.0.1:8000" }
$BaseUrl = $BaseUrl.TrimEnd("/")
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
if (-not $OutputDir) { $OutputDir = Join-Path $RepoRoot "examples/output/research-console" }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$participantId = "SYNTH-P01"

Invoke-RestMethod -Uri "$BaseUrl/health" | Out-Host
$participants = @(Invoke-RestMethod -Uri "$BaseUrl/participants")
if ($participants.id -contains $participantId) {
    Write-Host "Synthetic participant already exists; continuing."
} else {
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/participants" -ContentType "application/json" `
        -Body '{"id":"SYNTH-P01","enrollment_date":"2026-08-14"}' | Out-Host
}
$csv = Get-Item (Join-Path $RepoRoot "examples/openmatb-research/fixtures/low.csv")
Invoke-RestMethod -Method Post -Uri "$BaseUrl/ingest" -Form @{
    participant_id = $participantId; visit_ordinal = "1"; workload_level = "LOW"; file = $csv
} | Out-Host
$analysis = Invoke-RestMethod -Method Post -Uri "$BaseUrl/analysis/run"
$analysisStatuses = [ordered]@{}
foreach ($property in $analysis.q1.PSObject.Properties) {
    $analysisStatuses[$property.Name] = $property.Value.status
}
$allowedAnalysisStatuses = @("ok", "insufficient_data", "not_estimable")
$invalidAnalysisStatuses = @($analysisStatuses.Values | Where-Object { $_ -notin $allowedAnalysisStatuses })
if ($analysisStatuses.Count -eq 0 -or $invalidAnalysisStatuses.Count -ne 0) {
    throw "Analysis response contains missing or unsupported q1 status"
}
[pscustomobject]@{ analysis_status = $analysisStatuses } | ConvertTo-Json -Depth 4 | Write-Host
Invoke-RestMethod -Uri "$BaseUrl/tracker" | Out-Host
Invoke-RestMethod -Uri "$BaseUrl/exports/research-context" | Out-Host
Invoke-WebRequest -Method Post -Uri "$BaseUrl/exports/research-bundle" -ContentType "application/json" `
    -Body '{"figures":[]}' -OutFile (Join-Path $OutputDir "research-bundle.zip")
Write-Host "Wrote $(Join-Path $OutputDir 'research-bundle.zip')"
