[CmdletBinding()]
param(
    [string]$DataRoot = "",
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 3100
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$repoRoot = Get-MatbUasRepoRoot
$dataRoot = Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $DataRoot
$statePath = Join-Path $dataRoot "service\service-state.json"
$logRoot = Join-Path $dataRoot "service\logs"
$issues = [System.Collections.Generic.List[string]]::new()

function Write-DiagnosticLine {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$Value,
        [ValidateSet("ok", "info", "warning")][string]$Kind = "info"
    )
    $color = switch ($Kind) {
        "ok" { "Green" }
        "warning" { "Yellow" }
        default { "Gray" }
    }
    Write-Host ("{0,-18} {1}" -f ($Label + ":"), $Value) -ForegroundColor $color
}

function Add-DiagnosticIssue {
    param([Parameter(Mandatory)][string]$Message)
    $issues.Add($Message)
    Write-DiagnosticLine -Label "Attention" -Value $Message -Kind warning
}

Write-Host "MATB UAS diagnostics" -ForegroundColor Cyan
Write-DiagnosticLine -Label "Repository" -Value $repoRoot
Write-DiagnosticLine -Label "PowerShell" -Value $PSVersionTable.PSVersion.ToString() -Kind ok

$pythonPath = $null
try {
    $pythonPath = Get-MatbUasPython -RepoRoot $repoRoot
    $pythonVersion = & $pythonPath -c "import platform; print(platform.python_version())" 2>$null | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $pythonVersion) {
        throw "version check failed"
    }
    Write-DiagnosticLine -Label "Python" -Value ("{0} ({1})" -f $pythonVersion, $pythonPath) -Kind ok
    & $pythonPath -c "import fastapi, pydantic, sqlmodel, uvicorn, yaml" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Add-DiagnosticIssue -Message "MATB Python dependencies are incomplete; run shortcut 00."
    } else {
        Write-DiagnosticLine -Label "Python packages" -Value "available" -Kind ok
    }
} catch {
    Add-DiagnosticIssue -Message $_.Exception.Message
}

try {
    $nodePath = Get-MatbUasNode
    $nodeVersion = & $nodePath --version 2>$null | Select-Object -Last 1
    Write-DiagnosticLine -Label "Node" -Value ("{0} ({1})" -f $nodeVersion, $nodePath) -Kind ok
} catch {
    Add-DiagnosticIssue -Message $_.Exception.Message
}

$frontendRoot = Join-Path $repoRoot "webui\frontend"
$nextCli = Join-Path $frontendRoot "node_modules\next\dist\bin\next"
$buildId = Join-Path $frontendRoot ".next\BUILD_ID"
$buildRootStamp = Join-Path $frontendRoot ".next\.matb-build-root"
$buildMatchesLocation = $false
if (Test-Path -LiteralPath $buildRootStamp -PathType Leaf) {
    $stampedRoot = (Get-Content -LiteralPath $buildRootStamp -Raw).Trim()
    $buildMatchesLocation = $stampedRoot.Equals($frontendRoot, [System.StringComparison]::OrdinalIgnoreCase)
}
if ((Test-Path -LiteralPath $nextCli -PathType Leaf) -and
    (Test-Path -LiteralPath $buildId -PathType Leaf) -and $buildMatchesLocation) {
    Write-DiagnosticLine -Label "Frontend" -Value "dependencies and production build available" -Kind ok
} else {
    Add-DiagnosticIssue -Message "The frontend is missing, stale, or was built at another repository location; run shortcut 00."
}

$scenarioPath = Join-Path $repoRoot "scenarios\suas\reference_area_search.yaml"
if ($pythonPath -and (Test-Path -LiteralPath $scenarioPath -PathType Leaf)) {
    Push-Location $repoRoot
    try {
        $scenarioText = & $pythonPath -m matb_integration.suas.cli validate $scenarioPath 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $scenarioText) {
            Add-DiagnosticIssue -Message "The reference UAS scenario did not validate."
        } else {
            $scenario = $scenarioText | Select-Object -Last 1 | ConvertFrom-Json
            Write-DiagnosticLine -Label "Scenario" -Value ("{0} ({1}...)" -f $scenario.scenario_id, $scenario.scenario_sha256.Substring(0, 12)) -Kind ok
        }
    } catch {
        Add-DiagnosticIssue -Message ("Scenario validation failed: {0}" -f $_.Exception.Message)
    } finally {
        Pop-Location
    }
} elseif (-not (Test-Path -LiteralPath $scenarioPath -PathType Leaf)) {
    Add-DiagnosticIssue -Message "The reference UAS scenario is missing."
}

$state = Read-MatbUasState -StatePath $statePath
if ($state) {
    try {
        $backendTracked = Test-MatbUasTrackedProcess `
            -ProcessId ([int]$state.backend_pid) `
            -ExpectedExecutable ([string]$state.backend_executable) `
            -ExpectedStartedAtUtc $state.backend_started_at_utc `
            -Role backend `
            -Port ([int]$state.backend_port) `
            -RepoRoot $repoRoot
        $frontendTracked = Test-MatbUasTrackedProcess `
            -ProcessId ([int]$state.frontend_pid) `
            -ExpectedExecutable ([string]$state.frontend_executable) `
            -ExpectedStartedAtUtc $state.frontend_started_at_utc `
            -Role frontend `
            -Port ([int]$state.frontend_port) `
            -RepoRoot $repoRoot
        $backendHealthy = $backendTracked -and (Test-MatbUasHttp -Uri ("http://127.0.0.1:{0}/health" -f $state.backend_port))
        $frontendHealthy = $frontendTracked -and (Test-MatbUasHttp -Uri ("http://127.0.0.1:{0}/start" -f $state.frontend_port))
        Write-DiagnosticLine -Label "Backend" -Value ("PID {0}; tracked={1}; healthy={2}" -f $state.backend_pid, $backendTracked, $backendHealthy) -Kind $(if ($backendHealthy) { "ok" } else { "warning" })
        Write-DiagnosticLine -Label "Frontend" -Value ("PID {0}; tracked={1}; healthy={2}" -f $state.frontend_pid, $frontendTracked, $frontendHealthy) -Kind $(if ($frontendHealthy) { "ok" } else { "warning" })
        if (-not $backendHealthy -or -not $frontendHealthy) {
            Add-DiagnosticIssue -Message "Tracked console services are inconsistent; inspect logs, then use shortcut 99."
        }
    } catch {
        Add-DiagnosticIssue -Message ("The service state is incomplete or invalid: {0}" -f $_.Exception.Message)
    }
} else {
    $backendPortOpen = Test-MatbUasTcpPort -HostName "127.0.0.1" -Port $BackendPort
    $frontendPortOpen = Test-MatbUasTcpPort -HostName "127.0.0.1" -Port $FrontendPort
    if ($backendPortOpen -or $frontendPortOpen) {
        Add-DiagnosticIssue -Message ("No tracked console exists, but reserved ports are occupied ({0}={1}, {2}={3})." -f $BackendPort, $backendPortOpen, $FrontendPort, $frontendPortOpen)
    } else {
        Write-DiagnosticLine -Label "Console" -Value ("stopped; ports {0} and {1} are available" -f $BackendPort, $FrontendPort) -Kind ok
    }
}

$latestRun = Get-MatbUasLatestSealedRun -RepoRoot $repoRoot -DataRoot $dataRoot
if ($latestRun) {
    $recordedStatus = "sealed"
    $replayPath = Join-Path $latestRun.FullName "replay-verification.json"
    if (Test-Path -LiteralPath $replayPath -PathType Leaf) {
        try {
            $replay = Get-Content -Raw -LiteralPath $replayPath | ConvertFrom-Json
            $recordedStatus = [string]$replay.status
        } catch {
            $recordedStatus = "unreadable replay metadata"
        }
    }
    Write-DiagnosticLine -Label "Latest run" -Value ("{0}; recorded replay={1}" -f $latestRun.Name, $recordedStatus) -Kind $(if ($recordedStatus -eq "match") { "ok" } else { "info" })
} else {
    Write-DiagnosticLine -Label "Latest run" -Value "none; incomplete runs are ignored"
}
Write-DiagnosticLine -Label "Logs" -Value $logRoot

if ($issues.Count -gt 0) {
    if (Test-Path -LiteralPath $logRoot -PathType Container) {
        Write-Host ""
        Write-Host "Recent service stderr" -ForegroundColor Yellow
        Get-ChildItem -LiteralPath $logRoot -Filter "*.stderr.log" -File |
            Where-Object Length -gt 0 |
            ForEach-Object {
                Write-Host ("--- {0}" -f $_.Name) -ForegroundColor DarkYellow
                Get-Content -LiteralPath $_.FullName -Tail 8
            }
    }
    Write-Host ""
    Write-Host ("ATTENTION: {0} diagnostic issue(s) found." -f $issues.Count) -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "READY: MATB UAS prerequisites and local state are consistent." -ForegroundColor Green
