[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
. (Join-Path $repoRoot "windows-launchers\scripts\Common-MatbUas.ps1")

function Assert-Equal {
    param(
        [Parameter(Mandatory)]$Actual,
        [Parameter(Mandatory)]$Expected,
        [Parameter(Mandatory)][string]$Message
    )
    if ($Actual -ne $Expected) {
        throw "$Message`nExpected: $Expected`nActual:   $Actual"
    }
}

$savedPython = $env:MATB_PYTHON
$savedVenv = $env:MATB_VENV
$savedDataRoot = $env:MATB_DATA_ROOT
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("MATB launcher tests ñ {0}" -f [guid]::NewGuid())

try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null

    $env:MATB_PYTHON = "python"
    Remove-Item Env:MATB_VENV -ErrorAction SilentlyContinue
    $resolvedPython = Get-MatbUasPython -RepoRoot $repoRoot
    $expectedPython = [System.IO.Path]::GetFullPath((Get-Command python -CommandType Application | Select-Object -First 1).Source)
    Assert-Equal $resolvedPython $expectedPython "MATB_PYTHON command discovery was not location independent."

    $relativeData = "exports\portable data ñ"
    Remove-Item Env:MATB_DATA_ROOT -ErrorAction SilentlyContinue
    $resolvedRelative = Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $relativeData
    Assert-Equal $resolvedRelative ([System.IO.Path]::GetFullPath((Join-Path $repoRoot $relativeData))) "Relative data roots must anchor to the repository."

    $environmentData = Join-Path $tempRoot "environment data"
    $explicitData = Join-Path $tempRoot "explicit data"
    $env:MATB_DATA_ROOT = $environmentData
    Assert-Equal (Get-MatbUasDataRoot -RepoRoot $repoRoot) ([System.IO.Path]::GetFullPath($environmentData)) "MATB_DATA_ROOT was ignored."
    Assert-Equal (Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $explicitData) ([System.IO.Path]::GetFullPath($explicitData)) "-DataRoot must override MATB_DATA_ROOT."

    $unsafeRejected = $false
    try {
        Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $repoRoot | Out-Null
    } catch {
        $unsafeRejected = $_.Exception.Message -match "unsafe MATB data root"
    }
    if (-not $unsafeRejected) {
        throw "The repository root was accepted as a destructive data root."
    }

    $sealedRoot = Join-Path $explicitData "runs\sealed-run"
    New-Item -ItemType Directory -Path $sealedRoot -Force | Out-Null
    foreach ($name in @("manifest.json", "checksums.sha256", "replay-verification.json")) {
        New-Item -ItemType File -Path (Join-Path $sealedRoot $name) | Out-Null
    }
    $latest = Get-MatbUasLatestSealedRun -RepoRoot $repoRoot -DataRoot $explicitData
    Assert-Equal $latest.FullName ([System.IO.Path]::GetFullPath($sealedRoot)) "Sealed-run discovery ignored the selected data root."

    $frontend = Join-Path $tempRoot "frontend ñ"
    New-Item -ItemType Directory -Path $frontend | Out-Null
    Move-MatbUasFrontendTestCache -FrontendRoot $frontend
    Assert-Equal @(Get-ChildItem -LiteralPath $frontend -Force).Count 0 "A clean install must not create a cache backup."

    $cache = Join-Path $frontend "node_modules\.vite"
    $resultsDirectory = Join-Path $cache "vitest\da39a3ee5e6b4b0d3255bfef95601890afd80709"
    New-Item -ItemType Directory -Path $resultsDirectory -Force | Out-Null
    $resultsPath = Join-Path $resultsDirectory "results.json"
    '{"testResults":[]}' | Set-Content -LiteralPath $resultsPath -NoNewline
    $dependency = Join-Path $frontend "node_modules\keep.txt"
    'dependency' | Set-Content -LiteralPath $dependency -NoNewline
    $lockPath = Join-Path $frontend "package-lock.json"
    '{"lockfileVersion":3}' | Set-Content -LiteralPath $lockPath -NoNewline
    $lockHash = (Get-FileHash -LiteralPath $lockPath).Hash

    # A live Windows file lock must produce an actionable error and preserve
    # the cache; recovery can proceed after the owning process releases it.
    $handle = [System.IO.File]::Open($resultsPath, 'Open', 'Read', 'Read')
    try {
        if ($IsWindows) {
            $lockedRejected = $false
            try {
                Move-MatbUasFrontendTestCache -FrontendRoot $frontend
            } catch {
                $lockedRejected = $_.Exception.Message -match "Close MATB and frontend tests"
            }
            Assert-Equal $lockedRejected $true "A live file lock must provide recovery instructions."
            Assert-Equal (Test-Path -LiteralPath $resultsPath) $true "A failed move must preserve the cache."
        }
    } finally {
        $handle.Dispose()
    }
    (Get-Item -LiteralPath $resultsPath).IsReadOnly = $true
    Move-MatbUasFrontendTestCache -FrontendRoot $frontend
    Assert-Equal (Test-Path -LiteralPath $cache) $false "The test cache still blocks npm ci."
    $backups = @(Get-ChildItem -LiteralPath $frontend -Directory -Force -Filter '.matb-cache-backup-*')
    Assert-Equal $backups.Count 1 "Recovery must preserve exactly one cache backup."
    $preservedResults = Join-Path $backups[0].FullName "vitest\da39a3ee5e6b4b0d3255bfef95601890afd80709\results.json"
    Assert-Equal (Get-Content -LiteralPath $preservedResults -Raw) '{"testResults":[]}' "Recovery changed the cached results."
    Assert-Equal (Get-Content -LiteralPath $dependency -Raw) 'dependency' "Recovery changed an installed dependency."
    Assert-Equal (Get-FileHash -LiteralPath $lockPath).Hash $lockHash "Recovery changed the dependency lock."
    Move-MatbUasFrontendTestCache -FrontendRoot $frontend
    Assert-Equal @(Get-ChildItem -LiteralPath $frontend -Directory -Force -Filter '.matb-cache-backup-*').Count 1 "Repeated recovery must be a no-op without a cache."

    if ($IsWindows) {
        $externalCache = Join-Path $tempRoot "external cache"
        New-Item -ItemType Directory -Path $externalCache | Out-Null
        New-Item -ItemType Junction -Path $cache -Target $externalCache | Out-Null
        try {
            $linkRejected = $false
            try {
                Move-MatbUasFrontendTestCache -FrontendRoot $frontend
            } catch {
                $linkRejected = $_.Exception.Message -match "directory link"
            }
            Assert-Equal $linkRejected $true "Cache recovery must reject directory links."
            Assert-Equal (Test-Path -LiteralPath $externalCache) $true "Recovery changed an external cache."
        } finally {
            [System.IO.Directory]::Delete($cache)
        }
    }
} finally {
    if ($null -eq $savedPython) { Remove-Item Env:MATB_PYTHON -ErrorAction SilentlyContinue } else { $env:MATB_PYTHON = $savedPython }
    if ($null -eq $savedVenv) { Remove-Item Env:MATB_VENV -ErrorAction SilentlyContinue } else { $env:MATB_VENV = $savedVenv }
    if ($null -eq $savedDataRoot) { Remove-Item Env:MATB_DATA_ROOT -ErrorAction SilentlyContinue } else { $env:MATB_DATA_ROOT = $savedDataRoot }
    if (Test-Path -LiteralPath $tempRoot) {
        $resolvedTemp = (Get-Item -LiteralPath $tempRoot).FullName
        $expectedParent = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\', '/')
        if ((Split-Path -Parent $resolvedTemp) -ne $expectedParent -or
            (Split-Path -Leaf $resolvedTemp) -notlike 'MATB launcher tests ñ *') {
            throw "Refusing to remove a test directory outside the temporary test root."
        }
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}

Write-Host "Windows MATB launcher portability tests passed."
