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
} finally {
    if ($null -eq $savedPython) { Remove-Item Env:MATB_PYTHON -ErrorAction SilentlyContinue } else { $env:MATB_PYTHON = $savedPython }
    if ($null -eq $savedVenv) { Remove-Item Env:MATB_VENV -ErrorAction SilentlyContinue } else { $env:MATB_VENV = $savedVenv }
    if ($null -eq $savedDataRoot) { Remove-Item Env:MATB_DATA_ROOT -ErrorAction SilentlyContinue } else { $env:MATB_DATA_ROOT = $savedDataRoot }
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}

Write-Host "Windows MATB launcher portability tests passed."
