[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipBuild,
    [switch]$SkipTests,
    [switch]$ServicesStopped,
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 3100,
    [string]$DataRoot = "",
    [string]$BasePython = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "PowerShell 7 or newer is required. Run this launcher with pwsh.exe."
}

$repoRoot = Get-MatbUasRepoRoot
$resolvedDataRoot = Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $DataRoot
$setupLock = Enter-MatbLauncherLock -RepoRoot $repoRoot
try {
if (-not $ServicesStopped) {
    Stop-MatbConsoleInstance -RepoRoot $repoRoot -DataRoot $resolvedDataRoot -BackendPort $BackendPort -FrontendPort $FrontendPort
}
$localPython = Join-Path $repoRoot ".venv-suas\Scripts\python.exe"

try {
    if (-not $env:MATB_PYTHON -and -not $env:MATB_VENV -and
        -not (Test-MatbUasPythonVersion -PythonPath $localPython)) {
        throw "A repository-local environment must be created."
    }
    $pythonPath = Get-MatbUasPython -RepoRoot $repoRoot
} catch {
    if ($SkipInstall) {
        throw
    }
    if ($env:MATB_PYTHON -or $env:MATB_VENV) {
        throw "The explicitly selected MATB_PYTHON/MATB_VENV is incompatible. Correct it before running setup."
    }
    . (Join-Path $PSScriptRoot "Common-MatbBootstrap.ps1")
    $basePythonPath = if ($BasePython) {
        Resolve-MatbUasExecutable -Candidate $BasePython -RepoRoot $repoRoot
    } else { Get-MatbBootstrapPython }
    if (-not $basePythonPath -or -not (Test-MatbUasPythonVersion -PythonPath $basePythonPath)) {
        throw "Python 3.12 64-bit was not found. Run Install MATB.cmd."
    }
    Write-Host "Creating the repository-local Python 3.12 environment..."
    & $basePythonPath -m venv (Join-Path $repoRoot ".venv-suas")
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.12 environment creation failed."
    }
    $pythonPath = $localPython
}

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
Write-Host "Python: $pythonPath"
Write-Host "Data:   $resolvedDataRoot"

$pythonDependenciesReady = Test-MatbUasPythonDependencies -RepoRoot $repoRoot -PythonPath $pythonPath
if (-not $pythonDependenciesReady) {
    if ($SkipInstall) {
        throw "MATB Python dependencies are missing and -SkipInstall was selected."
    }
    Write-Host "Installing MATB Python dependencies..."
    $pythonRequirements = Get-MatbUasRequirements -RepoRoot $repoRoot -PythonPath $pythonPath
    & $pythonPath -m pip install -r $pythonRequirements -r (Join-Path $repoRoot "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "MATB Python dependency installation failed."
    }
}
if (-not (Test-MatbUasPythonDependencies -RepoRoot $repoRoot -PythonPath $pythonPath)) {
    throw "Python packages remain incompatible after installation. Inspect pip's diagnostic output."
}
& $pythonPath -c "import fastapi, pydantic, pyglet, pylsl, rstr, sqlmodel, uvicorn, yaml"
if ($LASTEXITCODE -ne 0) { throw "A required MATB runtime package could not be imported." }

# Exports replay offline only when wheels match the selected interpreter.
$wheelRoot = Join-Path $resolvedDataRoot "service/wheels"
$wheelTool = Join-Path $repoRoot "tools/prepare_study_wheels.py"
& $pythonPath $wheelTool $wheelRoot --check
if ($LASTEXITCODE -ne 0) {
    if ($SkipInstall) { throw "Offline export wheels are missing. Run Install MATB.cmd." }
    Write-Host "Preparing offline calculator wheels for study exports..."
    & $pythonPath $wheelTool $wheelRoot
    if ($LASTEXITCODE -ne 0) { throw "Offline calculator wheel preparation failed." }
    & $pythonPath $wheelTool $wheelRoot --check
    if ($LASTEXITCODE -ne 0) { throw "Offline calculator wheels did not pass verification." }
}

$nodePath = Get-MatbUasNode
$npmPath = Get-MatbUasNpm -NodePath $nodePath
Write-Host "Node: $nodePath"

$frontendRoot = Join-Path $repoRoot "webui\frontend"
$nextModule = Join-Path $frontendRoot "node_modules\next\dist\bin\next"
$packageLock = Join-Path $frontendRoot "package-lock.json"
$dependencyStamp = Join-Path $frontendRoot "node_modules\.matb-package-lock.sha256"
$packageLockHash = (Get-FileHash -LiteralPath $packageLock -Algorithm SHA256).Hash.ToLowerInvariant()
$frontendDependenciesReady = Test-MatbFrontendDependencies -FrontendRoot $frontendRoot -NodePath $nodePath
if (-not $frontendDependenciesReady) {
    if ($SkipInstall) {
        throw "Frontend dependencies are missing and -SkipInstall was selected."
    }
    Move-MatbUasFrontendTestCache -FrontendRoot $frontendRoot
    Write-Host "Installing frontend dependencies..."
    Push-Location $frontendRoot
    try {
        & $npmPath ci --prefer-offline --maxsockets=4 --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend dependency installation failed. If npm reports EPERM, close MATB and frontend tests, then retry Install MATB.cmd. See WINDOWS.md."
        }
        $packageLockHash | Set-Content -LiteralPath $dependencyStamp -Encoding ascii -NoNewline
        if (-not (Test-MatbFrontendDependencies -FrontendRoot $frontendRoot -NodePath $nodePath)) {
            Remove-Item -LiteralPath $dependencyStamp -Force
            throw 'Frontend packages are still incomplete. See the npm output above.'
        }
    } finally {
        Pop-Location
    }
}

$buildId = Join-Path $frontendRoot ".next\BUILD_ID"
$buildRootStamp = Join-Path $frontendRoot ".next\.matb-build-root"
if (-not $SkipBuild) {
    $needsBuild = (
        -not (Test-Path -LiteralPath $buildId -PathType Leaf) -or
        -not (Test-Path -LiteralPath $buildRootStamp -PathType Leaf)
    )
    if (-not $needsBuild) {
        $stampedRoot = (Get-Content -LiteralPath $buildRootStamp -Raw).Trim()
        if (-not $stampedRoot.Equals($frontendRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            $needsBuild = $true
        }
    }
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
            (Join-Path $frontendRoot "next.config.js"),
            (Join-Path $frontendRoot "tsconfig.json"),
            (Join-Path $frontendRoot "tailwind.config.ts"),
            (Join-Path $frontendRoot "postcss.config.js")
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
            & $npmPath run build
            if ($LASTEXITCODE -ne 0) {
                throw "MATB frontend build failed."
            }
            $frontendRoot | Set-Content -LiteralPath $buildRootStamp -Encoding utf8 -NoNewline
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
Write-Host "MATB Research Console and desktop OpenMATB are ready for the Windows launchers." -ForegroundColor Green
} finally {
    $setupLock.ReleaseMutex()
    $setupLock.Dispose()
}
