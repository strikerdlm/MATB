param([string]$BaseUrl = $env:BASE_URL)

$ErrorActionPreference = "Stop"
if (-not $BaseUrl) { $BaseUrl = "http://127.0.0.1:8000" }
$BaseUrl = $BaseUrl.TrimEnd("/")
# P01 is deliberately synthetic; native sessions validate P[digits] identifiers.
$participantId = "P01"

Invoke-RestMethod -Uri "$BaseUrl/health" | Out-Host
$participants = @(Invoke-RestMethod -Uri "$BaseUrl/participants")
if ($participants.id -contains $participantId) {
    Write-Host "Synthetic sUAS participant already exists; continuing."
} else {
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/participants" -ContentType "application/json" `
        -Body '{"id":"P01","enrollment_date":"2026-08-14"}' | Out-Host
}
Invoke-RestMethod -Uri "$BaseUrl/simulation/scenarios" | Out-Host
$prepared = Invoke-RestMethod -Method Post -Uri "$BaseUrl/simulation/sessions" -ContentType "application/json" `
    -Body '{"participant_id":"P01","visit_ordinal":1,"scenario_id":"reference_area_search","locale":"en"}'
$sessionId = $prepared.id
$controllerLeaseValue = $prepared.controller_lease
Clear-Variable prepared
$controllerHeaderName = "X-Simulation-Controller"
$headers = @{ $controllerHeaderName = $controllerLeaseValue }
Invoke-RestMethod -Method Post -Uri "$BaseUrl/simulation/sessions/$sessionId/start" -Headers $headers `
    -ContentType "application/json" -Body '{"block_id":"PRACTICE"}' | Out-Host
Invoke-RestMethod -Uri "$BaseUrl/simulation/sessions/$sessionId/state" | Out-Host
Invoke-RestMethod -Method Post -Uri "$BaseUrl/simulation/sessions/$sessionId/finish" -Headers $headers `
    -ContentType "application/json" -Body '{"disposition":"complete"}' | Out-Host
Invoke-RestMethod -Uri "$BaseUrl/simulation/sessions/$sessionId/debrief" | Out-Host
Invoke-RestMethod -Uri "$BaseUrl/simulation/sessions/$sessionId/artifacts" | Out-Host
Clear-Variable headers
Clear-Variable controllerLeaseValue
Clear-Variable controllerHeaderName
