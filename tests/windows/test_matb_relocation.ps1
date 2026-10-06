[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int]$BackendPort = 18080,
    [ValidateRange(1, 65535)][int]$FrontendPort = 13180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$launcherRoot = Join-Path $repoRoot "windows-launchers\scripts"
$dataRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("MATB external data ñ {0}" -f [guid]::NewGuid())
$started = $false
$previousNoPause = $env:MATB_NO_PAUSE
$env:MATB_NO_PAUSE = '1'

if ($BackendPort -eq $FrontendPort) {
    throw "Relocation smoke ports must be different."
}

try {
    & (Join-Path $launcherRoot "Initialize-MatbUas.ps1") `
        -SkipTests -DataRoot $dataRoot -BackendPort $BackendPort -FrontendPort $FrontendPort
    if ($LASTEXITCODE -ne 0) { throw "MATB relocation preparation failed." }

    & (Join-Path $launcherRoot "Test-MatbUasEnvironment.ps1") `
        -DataRoot $dataRoot -BackendPort $BackendPort -FrontendPort $FrontendPort
    if ($LASTEXITCODE -ne 0) { throw "MATB relocation diagnostics failed." }

    foreach ($shortcut in @('10 - Simular PRACTICE.cmd', '11 - Simular LOW.cmd',
        '12 - Simular MEDIUM.cmd', '13 - Simular HIGH.cmd')) {
        & (Join-Path $repoRoot "windows-launchers/$shortcut") -Ticks 10 -DataRoot $dataRoot
        if ($LASTEXITCODE -ne 0) { throw "MATB profile shortcut failed: $shortcut" }
    }
    & (Join-Path $repoRoot 'windows-launchers/90 - Verificar ultima simulacion.cmd') -DataRoot $dataRoot
    if ($LASTEXITCODE -ne 0) { throw "MATB relocated run verification failed." }
    & (Join-Path $repoRoot 'windows-launchers/91 - Abrir resultados MATB UAS.cmd') -ListOnly -DataRoot $dataRoot
    if ($LASTEXITCODE -ne 0) { throw 'MATB results shortcut failed.' }

    & (Join-Path $launcherRoot "Start-MatbUasConsole.ps1") `
        -BackendPort $BackendPort -FrontendPort $FrontendPort `
        -NoBrowser -NoWait -DataRoot $dataRoot
    if ($LASTEXITCODE -ne 0) { throw "MATB relocated console failed to start." }
    $started = $true

    $health = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/health" -f $BackendPort) -TimeoutSec 5
    if ($health.status -ne "ok") { throw "MATB relocated backend health was not ok." }
    $statePath = Join-Path $dataRoot 'service/service-state.json'
    $first = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    # Exercise Explorer's actual .cmd -> Windows PowerShell 5.1 -> pwsh path.
    $startCmd = Join-Path $repoRoot 'Start MATB.cmd'
    & $startCmd -NoBrowser -DataRoot $dataRoot -BackendPort $BackendPort -FrontendPort $FrontendPort
    if ($LASTEXITCODE -ne 0) { throw 'Start MATB.cmd failed to restart the healthy console.' }
    $second = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($first.backend_pid -eq $second.backend_pid -or $first.frontend_pid -eq $second.frontend_pid) {
        throw 'A second launch reused a previous service.'
    }
    $config = Invoke-RestMethod -Uri "http://127.0.0.1:$FrontendPort/api/runtime-config"
    if ($config.backend_port -ne $BackendPort) { throw 'Frontend is pointing at the wrong backend.' }
    # Missing state must still recover the live listeners and venv children.
    '{}' | Set-Content -LiteralPath $statePath
    $legacyStart = Join-Path $repoRoot 'windows-launchers/01 - Abrir consola UAS.cmd'
    & $legacyStart -NoBrowser -DataRoot $dataRoot -BackendPort $BackendPort -FrontendPort $FrontendPort
    if ($LASTEXITCODE -ne 0) { throw 'Legacy .cmd failed with occupied untracked ports.' }
    foreach ($oldPid in @($second.backend_pid, $second.frontend_pid)) {
        if (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) { throw "Old service survived restart: $oldPid" }
    }
    $diagnoseCmd = Join-Path $repoRoot 'Diagnose MATB.cmd'
    & $diagnoseCmd -DataRoot $dataRoot -BackendPort $BackendPort -FrontendPort $FrontendPort
    if ($LASTEXITCODE -ne 0) { throw 'Diagnose MATB.cmd did not report the restarted station ready.' }
} catch {
    $logRoot = Join-Path $dataRoot "service\logs"
    foreach ($name in @("backend.stderr.log", "frontend.stderr.log", "frontend.stdout.log")) {
        $logPath = Join-Path $logRoot $name
        if (Test-Path -LiteralPath $logPath -PathType Leaf) {
            $logTail = Get-Content -LiteralPath $logPath -Tail 50
            Write-Warning "$name (last 50 lines)`n$($logTail -join [Environment]::NewLine)"
        }
    }
    throw
} finally {
    if ($started) {
        $stopCmd = Join-Path $repoRoot 'Stop MATB.cmd'
        & $stopCmd -DataRoot $dataRoot -BackendPort $BackendPort -FrontendPort $FrontendPort
        if ($LASTEXITCODE -ne 0) { throw 'Stop MATB.cmd failed.' }
    }
    if (Test-Path -LiteralPath $dataRoot) {
        $expectedParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
        $resolved = [IO.Path]::GetFullPath($dataRoot)
        if ((Split-Path -Parent $resolved) -ne $expectedParent -or (Split-Path -Leaf $resolved) -notlike 'MATB external data ñ *') {
            throw 'Unsafe relocation test cleanup directory.'
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    $env:MATB_NO_PAUSE = $previousNoPause
}

foreach ($port in @($BackendPort, $FrontendPort)) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($listener) { throw "MATB relocation smoke left port $port open." }
}

Write-Host "Windows MATB relocation smoke passed."
