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

if ($BackendPort -eq $FrontendPort) {
    throw "Relocation smoke ports must be different."
}

try {
    & (Join-Path $launcherRoot "Initialize-MatbUas.ps1") `
        -SkipTests -DataRoot $dataRoot
    if ($LASTEXITCODE -ne 0) { throw "MATB relocation preparation failed." }

    & (Join-Path $launcherRoot "Test-MatbUasEnvironment.ps1") `
        -DataRoot $dataRoot -BackendPort $BackendPort -FrontendPort $FrontendPort
    if ($LASTEXITCODE -ne 0) { throw "MATB relocation diagnostics failed." }

    & (Join-Path $launcherRoot "Invoke-MatbUasProfile.ps1") `
        -WorkloadProfile PRACTICE -Ticks 10 -DataRoot $dataRoot
    if ($LASTEXITCODE -ne 0) { throw "MATB relocation profile failed." }

    & (Join-Path $launcherRoot "Test-MatbUasRun.ps1") -DataRoot $dataRoot
    if ($LASTEXITCODE -ne 0) { throw "MATB relocated run verification failed." }

    & (Join-Path $launcherRoot "Start-MatbUasConsole.ps1") `
        -BackendPort $BackendPort -FrontendPort $FrontendPort `
        -NoBrowser -NoWait -DataRoot $dataRoot
    if ($LASTEXITCODE -ne 0) { throw "MATB relocated console failed to start." }
    $started = $true

    $health = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/health" -f $BackendPort) -TimeoutSec 5
    if ($health.status -ne "ok") { throw "MATB relocated backend health was not ok." }
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
        & (Join-Path $launcherRoot "Stop-MatbUasConsole.ps1") -DataRoot $dataRoot
    }
    if (Test-Path -LiteralPath $dataRoot) {
        Remove-Item -LiteralPath $dataRoot -Recurse -Force
    }
}

foreach ($port in @($BackendPort, $FrontendPort)) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($listener) { throw "MATB relocation smoke left port $port open." }
}

Write-Host "Windows MATB relocation smoke passed."
