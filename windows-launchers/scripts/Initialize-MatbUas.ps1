[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipBuild,
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "PowerShell 7 or newer is required. Run this launcher with pwsh.exe."
}

$repoRoot = Get-MatbUasRepoRoot
$localPython = Join-Path $repoRoot ".venv-suas\Scripts\python.exe"

try {
    $pythonPath = Get-MatbUasPython -RepoRoot $repoRoot
} catch {
    if ($SkipInstall) {
        throw
    }
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $pyLauncher) {
        throw "Python 3.12+ was not found. Install it or define MATB_PYTHON, then run setup again."
    }
    Write-Host "Creating the repository-local Python 3.12 environment..."
    & $pyLauncher.Source -3.12 -m venv (Join-Path $repoRoot ".venv-suas")
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.12 environment creation failed."
    }
    $pythonPath = $localPython
}

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
Write-Host "Python: $pythonPath"

& $pythonPath -c "import fastapi, pydantic, sqlmodel, uvicorn, yaml" 2>$null
$pythonDependenciesReady = ($LASTEXITCODE -eq 0)
if (-not $pythonDependenciesReady) {
    if ($SkipInstall) {
        throw "MATB Python dependencies are missing and -SkipInstall was selected."
    }
    Write-Host "Installing MATB Python dependencies..."
    & $pythonPath -m pip install -r (Join-Path $repoRoot "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "MATB Python dependency installation failed."
    }
}

$nodePath = Get-MatbUasNode
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    throw "npm.cmd was not found. Install npm and run setup again."
}
Write-Host "Node: $nodePath"

$frontendRoot = Join-Path $repoRoot "webui\frontend"
$nextModule = Join-Path $frontendRoot "node_modules\next\dist\bin\next"
if (-not (Test-Path -LiteralPath $nextModule -PathType Leaf)) {
    if ($SkipInstall) {
        throw "Frontend dependencies are missing and -SkipInstall was selected."
    }
    Write-Host "Installing frontend dependencies..."
    Push-Location $frontendRoot
    try {
        & $npmCommand.Source ci
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend dependency installation failed."
        }
    } finally {
        Pop-Location
    }
}

$buildId = Join-Path $frontendRoot ".next\BUILD_ID"
if (-not $SkipBuild) {
    $needsBuild = -not (Test-Path -LiteralPath $buildId -PathType Leaf)
    if (-not $needsBuild) {
        $buildTime = (Get-Item -LiteralPath $buildId).LastWriteTimeUtc
        $sourceRoots = @(
            (Join-Path $frontendRoot "src"),
            (Join-Path $frontendRoot "public")
        )
        $newestSource = Get-ChildItem -LiteralPath $sourceRoots -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        $metadataFiles = @(
            (Join-Path $frontendRoot "package.json"),
            (Join-Path $frontendRoot "package-lock.json"),
            (Join-Path $frontendRoot "next.config.mjs"),
            (Join-Path $frontendRoot "next.config.js")
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | ForEach-Object { Get-Item -LiteralPath $_ }
        $newestMetadata = $metadataFiles | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if (($newestSource -and $newestSource.LastWriteTimeUtc -gt $buildTime) -or
            ($newestMetadata -and $newestMetadata.LastWriteTimeUtc -gt $buildTime)) {
            $needsBuild = $true
        }
    }
    if ($needsBuild) {
        Write-Host "Building the MATB frontend..."
        $env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
        Push-Location $frontendRoot
        try {
            & $npmCommand.Source run build
            if ($LASTEXITCODE -ne 0) {
                throw "MATB frontend build failed."
            }
        } finally {
            Pop-Location
        }
    } else {
        Write-Host "Frontend build is current."
    }
}

$scenarioPath = Join-Path $repoRoot "scenarios\suas\reference_area_search.yaml"
Push-Location $repoRoot
try {
    Write-Host "Validating the installed sUAS scenario..."
    & $pythonPath -m matb_integration.suas.cli validate $scenarioPath
    if ($LASTEXITCODE -ne 0) {
        throw "The installed sUAS scenario is invalid."
    }
    if (-not $SkipTests) {
        Write-Host "Running focused Windows launcher prerequisites tests..."
        # Keep unrelated per-user pytest plugins from changing this project's
        # setup result or importing undeclared global dependencies.
        $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
        & $pythonPath -m pytest -p no:cacheprovider tests\suas\test_cli.py tests\suas\test_scenario_schema.py -q
        if ($LASTEXITCODE -ne 0) {
            throw "Focused MATB tests failed."
        }
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "MATB UAS is ready for the Windows launchers." -ForegroundColor Green
