[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 3100,
    [switch]$NoBrowser,
    [switch]$NoWait,
    [string]$DataRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")

if ($BackendPort -eq $FrontendPort) {
    throw "Backend and frontend ports must be different."
}

$repoRoot = Get-MatbUasRepoRoot
$frontendUrl = "http://127.0.0.1:$FrontendPort/start"
$backendHealth = "http://127.0.0.1:$BackendPort/health"
$dataRoot = Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $DataRoot
$serviceRoot = Join-Path $dataRoot "service"
$statePath = Join-Path $serviceRoot "service-state.json"

# Avoid rebuilding underneath an already healthy console. If no healthy
# tracked console exists, make this launcher a one-click prepare-and-start path.
$runningState = Read-MatbUasState -StatePath $statePath
if ($runningState) {
    $runningBackend = Test-MatbUasTrackedProcess `
        -ProcessId ([int]$runningState.backend_pid) `
        -ExpectedExecutable ([string]$runningState.backend_executable) `
        -ExpectedStartedAtUtc $runningState.backend_started_at_utc `
        -Role backend -Port ([int]$runningState.backend_port) -RepoRoot $repoRoot
    $runningFrontend = Test-MatbUasTrackedProcess `
        -ProcessId ([int]$runningState.frontend_pid) `
        -ExpectedExecutable ([string]$runningState.frontend_executable) `
        -ExpectedStartedAtUtc $runningState.frontend_started_at_utc `
        -Role frontend -Port ([int]$runningState.frontend_port) -RepoRoot $repoRoot
    if ($runningBackend -and $runningFrontend -and
        (Test-MatbUasHttp -Uri $backendHealth) -and
        (Test-MatbUasHttp -Uri $frontendUrl)) {
        Write-Host "MATB UAS is already running."
        if (-not $NoBrowser) { Start-Process $frontendUrl }
        return
    }
    # A tracked but unhealthy/old console must release .next and the database
    # before preparation repairs dependencies or rebuilds the frontend.
    if ($runningFrontend) {
        Stop-MatbUasTrackedProcess -ProcessId ([int]$runningState.frontend_pid) -ExpectedExecutable ([string]$runningState.frontend_executable) -ExpectedStartedAtUtc $runningState.frontend_started_at_utc -Role frontend -Port ([int]$runningState.frontend_port) -RepoRoot $repoRoot | Out-Null
    }
    if ($runningBackend) {
        Stop-MatbUasTrackedProcess -ProcessId ([int]$runningState.backend_pid) -ExpectedExecutable ([string]$runningState.backend_executable) -ExpectedStartedAtUtc $runningState.backend_started_at_utc -Role backend -Port ([int]$runningState.backend_port) -RepoRoot $repoRoot | Out-Null
    }
    Remove-MatbUasStateFile -StatePath $statePath -DataRoot $dataRoot
}

& (Join-Path $PSScriptRoot "Initialize-MatbUas.ps1") -SkipTests -DataRoot $dataRoot

$pythonPath = Get-MatbUasPython -RepoRoot $repoRoot
$nodePath = Get-MatbUasNode
$frontendRoot = Join-Path $repoRoot "webui\frontend"
$backendRoot = Join-Path $repoRoot "webui\backend"
$nextCli = Join-Path $frontendRoot "node_modules\next\dist\bin\next"
$buildId = Join-Path $frontendRoot ".next\BUILD_ID"
if (-not (Test-Path -LiteralPath $nextCli -PathType Leaf) -or
    -not (Test-Path -LiteralPath $buildId -PathType Leaf)) {
    throw "The frontend is not prepared. Run '00 - Preparar MATB UAS.cmd' first."
}

$dbRoot = Join-Path $serviceRoot "db"
$artifactRoot = Join-Path $serviceRoot "runs"
$logRoot = Join-Path $serviceRoot "logs"
foreach ($directory in @($dataRoot, $serviceRoot, $dbRoot, $artifactRoot, $logRoot)) {
    New-MatbUasDirectory -Path $directory
}

$existingState = Read-MatbUasState -StatePath $statePath
if ($existingState) {
    $backendTracked = Test-MatbUasTrackedProcess `
        -ProcessId ([int]$existingState.backend_pid) `
        -ExpectedExecutable ([string]$existingState.backend_executable) `
        -ExpectedStartedAtUtc $existingState.backend_started_at_utc `
        -Role backend `
        -Port ([int]$existingState.backend_port) `
        -RepoRoot $repoRoot
    $frontendTracked = Test-MatbUasTrackedProcess `
        -ProcessId ([int]$existingState.frontend_pid) `
        -ExpectedExecutable ([string]$existingState.frontend_executable) `
        -ExpectedStartedAtUtc $existingState.frontend_started_at_utc `
        -Role frontend `
        -Port ([int]$existingState.frontend_port) `
        -RepoRoot $repoRoot
    if ($backendTracked -and $frontendTracked -and
        (Test-MatbUasHttp -Uri $backendHealth) -and
        (Test-MatbUasHttp -Uri $frontendUrl)) {
        Write-Host "MATB UAS is already running."
        if (-not $NoBrowser) {
            Start-Process $frontendUrl
        }
        return
    }
    if ($frontendTracked) {
        Stop-MatbUasTrackedProcess -ProcessId ([int]$existingState.frontend_pid) -ExpectedExecutable ([string]$existingState.frontend_executable) -ExpectedStartedAtUtc $existingState.frontend_started_at_utc -Role frontend -Port ([int]$existingState.frontend_port) -RepoRoot $repoRoot | Out-Null
    }
    if ($backendTracked) {
        Stop-MatbUasTrackedProcess -ProcessId ([int]$existingState.backend_pid) -ExpectedExecutable ([string]$existingState.backend_executable) -ExpectedStartedAtUtc $existingState.backend_started_at_utc -Role backend -Port ([int]$existingState.backend_port) -RepoRoot $repoRoot | Out-Null
    }
    Remove-MatbUasStateFile -StatePath $statePath -DataRoot $dataRoot
}

if (Test-MatbUasTcpPort -HostName "127.0.0.1" -Port $BackendPort) {
    throw "Port $BackendPort is already in use by an untracked process."
}
if (Test-MatbUasTcpPort -HostName "127.0.0.1" -Port $FrontendPort) {
    throw "Port $FrontendPort is already in use by an untracked process."
}

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:MATB_DB_PATH = Join-Path $dbRoot "matb-webui.db"
$env:MATB_SIMULATION_OUTPUT_DIR = $artifactRoot
$env:MATB_SIMULATION_SCENARIO_DIR = Join-Path $repoRoot "scenarios\suas"
$env:MATB_OPENMATB_PYTHON = $pythonPath
$env:MATB_OPENMATB_OUTPUT_DIR = $artifactRoot
$env:MATB_DESCRIPTIVE_WHEELHOUSE = Join-Path $serviceRoot "wheels"
$env:MATB_FRONTEND_ORIGINS = "http://127.0.0.1:$FrontendPort,http://localhost:$FrontendPort"
$env:MATB_BACKEND_PORT = [string]$BackendPort
$env:API_URL = "http://127.0.0.1:$BackendPort"
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:$BackendPort"
$sourceProvenance = Get-MatbUasSourceProvenance -RepoRoot $repoRoot
$env:MATB_SOURCE_COMMIT = $sourceProvenance.Commit
if ($null -eq $sourceProvenance.Dirty) {
    Remove-Item Env:MATB_SOURCE_DIRTY -ErrorAction SilentlyContinue
} else {
    $env:MATB_SOURCE_DIRTY = $sourceProvenance.Dirty.ToString().ToLowerInvariant()
}

$backendOut = Join-Path $logRoot "backend.stdout.log"
$backendErr = Join-Path $logRoot "backend.stderr.log"
$frontendOut = Join-Path $logRoot "frontend.stdout.log"
$frontendErr = Join-Path $logRoot "frontend.stderr.log"
$backendProcess = $null
$frontendProcess = $null
$startupCompleted = $false

try {
    $backendProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", [string]$BackendPort) `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr `
        -PassThru

    $quotedNextCli = '"' + $nextCli.Replace('"', '\"') + '"'
    $frontendProcess = Start-Process `
        -FilePath $nodePath `
        -ArgumentList @($quotedNextCli, "start", "--hostname", "127.0.0.1", "--port", [string]$FrontendPort) `
        -WorkingDirectory $frontendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $frontendOut `
        -RedirectStandardError $frontendErr `
        -PassThru

    $state = [ordered]@{
        state_version = 1
        status = "starting"
        repo_root = $repoRoot
        data_root = $dataRoot
        supervisor_pid = $PID
        started_at_utc = [DateTime]::UtcNow.ToString("o")
        backend_pid = $backendProcess.Id
        backend_executable = $pythonPath
        backend_started_at_utc = $backendProcess.StartTime.ToUniversalTime().ToString("o")
        backend_port = $BackendPort
        frontend_pid = $frontendProcess.Id
        frontend_executable = $nodePath
        frontend_started_at_utc = $frontendProcess.StartTime.ToUniversalTime().ToString("o")
        frontend_port = $FrontendPort
        frontend_url = $frontendUrl
        source_commit = $sourceProvenance.Commit
        source_dirty = $sourceProvenance.Dirty
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8

    Wait-MatbUasHttp -Uri $backendHealth -Processes @($backendProcess, $frontendProcess)
    Wait-MatbUasHttp -Uri $frontendUrl -Processes @($backendProcess, $frontendProcess)
    $state.status = "running"
    $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
    $startupCompleted = $true

    Write-Host "MATB UAS console is running." -ForegroundColor Green
    Write-Host "Console:  $frontendUrl"
    Write-Host "Backend:  $backendHealth"
    Write-Host "Data:     $serviceRoot"
    Write-Host "Logs:     $logRoot"
    $sourceTree = if ($null -eq $sourceProvenance.Dirty) {
        "unverified"
    } elseif ($sourceProvenance.Dirty) {
        "dirty"
    } else {
        "clean"
    }
    Write-Host "Source:   $($sourceProvenance.Commit) ($sourceTree)"
    if ($sourceProvenance.Commit -eq "unavailable" -or $sourceProvenance.Dirty -ne $false) {
        Write-Warning "Source provenance is provisional; Experiment Designer previews will preserve that warning."
    }
    if (-not $NoBrowser) {
        Start-Process $frontendUrl
    }
    if ($NoWait) {
        return
    }

    Write-Host "Press Ctrl+C here or use '99 - Detener MATB UAS.cmd' to stop."
    while (-not $backendProcess.HasExited -and -not $frontendProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
    $latestState = Read-MatbUasState -StatePath $statePath
    if ($latestState -and $latestState.status -ne "stopping") {
        throw "A MATB service exited unexpectedly. Inspect $logRoot"
    }
} finally {
    if (-not $NoWait -or -not $startupCompleted) {
        if ($frontendProcess -and -not $frontendProcess.HasExited) {
            Stop-MatbUasTrackedProcess -ProcessId $frontendProcess.Id -ExpectedExecutable $nodePath -ExpectedStartedAtUtc ($frontendProcess.StartTime.ToUniversalTime()) -Role frontend -Port $FrontendPort -RepoRoot $repoRoot | Out-Null
        }
        if ($backendProcess -and -not $backendProcess.HasExited) {
            Stop-MatbUasTrackedProcess -ProcessId $backendProcess.Id -ExpectedExecutable $pythonPath -ExpectedStartedAtUtc ($backendProcess.StartTime.ToUniversalTime()) -Role backend -Port $BackendPort -RepoRoot $repoRoot | Out-Null
        }
        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            Remove-MatbUasStateFile -StatePath $statePath -DataRoot $dataRoot
        }
    }
}
