Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbBootstrap.ps1")
. (Join-Path $PSScriptRoot "Common-MatbLifecycle.ps1")

function Get-MatbUasRepoRoot {
    $candidate = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
    if (-not (Test-Path -LiteralPath (Join-Path $candidate "requirements-dev.txt") -PathType Leaf)) {
        throw "MATB repository root could not be resolved from $PSScriptRoot"
    }
    return $candidate
}

function Test-MatbUasPythonVersion {
    param([Parameter(Mandatory)][string]$PythonPath)

    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        return $false
    }
    try {
        $versionText = (& $PythonPath -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null | Select-Object -Last 1)
        if ($LASTEXITCODE -ne 0 -or -not $versionText) {
            return $false
        }
        return ([version]$versionText -ge [version]"3.12")
    } catch {
        return $false
    }
}

function Resolve-MatbUasExecutable {
    param(
        [Parameter(Mandatory)][string]$Candidate,
        [Parameter(Mandatory)][string]$RepoRoot
    )

    $selected = $Candidate.Trim()
    if (-not $selected) {
        return $null
    }
    $looksLikePath = [System.IO.Path]::IsPathRooted($selected) -or
        $selected.Contains([System.IO.Path]::DirectorySeparatorChar) -or
        $selected.Contains([System.IO.Path]::AltDirectorySeparatorChar) -or
        $selected.StartsWith(".")
    if ($looksLikePath) {
        $path = if ([System.IO.Path]::IsPathRooted($selected)) {
            $selected
        } else {
            Join-Path $RepoRoot $selected
        }
        return [System.IO.Path]::GetFullPath($path)
    }
    $command = Get-Command $selected -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
        return [System.IO.Path]::GetFullPath($command.Source)
    }
    return $null
}

function Get-MatbUasPython {
    param([Parameter(Mandatory)][string]$RepoRoot)

    $candidates = [System.Collections.Generic.List[string]]::new()
    if ($env:MATB_PYTHON) {
        $candidates.Add($env:MATB_PYTHON)
    }
    if ($env:MATB_VENV) {
        $venvRoot = if ([System.IO.Path]::IsPathRooted($env:MATB_VENV)) {
            $env:MATB_VENV
        } else {
            Join-Path $RepoRoot $env:MATB_VENV
        }
        $candidates.Add((Join-Path $venvRoot "Scripts\python.exe"))
    }
    $candidates.Add((Join-Path $RepoRoot ".venv-suas\Scripts\python.exe"))
    $candidates.Add((Join-Path $RepoRoot ".venv-console\Scripts\python.exe"))
    if ($env:USERPROFILE) {
        $candidates.Add((Join-Path $env:USERPROFILE "Miniconda3\envs\matb\python.exe"))
        $candidates.Add((Join-Path $env:USERPROFILE "Anaconda3\envs\matb\python.exe"))
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        if (-not $candidate) {
            continue
        }
        $fullPath = Resolve-MatbUasExecutable -Candidate $candidate -RepoRoot $RepoRoot
        if (-not $fullPath) {
            continue
        }
        if ($seen.ContainsKey($fullPath)) {
            continue
        }
        $seen[$fullPath] = $true
        if (Test-MatbUasPythonVersion -PythonPath $fullPath) {
            return $fullPath
        }
    }

    throw "No compatible MATB Python was found. Run '00 - Preparar MATB UAS.cmd' first."
}

function Test-MatbUasNodeVersion {
    param([Parameter(Mandatory)][string]$VersionText)
    if ($VersionText -notmatch '^v(?<version>\d+\.\d+\.\d+)$') { return $false }
    return ([version]$Matches.version -ge [version]"20.9.0")
}

function Get-MatbUasNode {
    $nodePath = Get-MatbBootstrapNode
    if (-not $nodePath) { throw "Node.js 20.9 or newer was not found. Run Install MATB.cmd." }
    return $nodePath
}

function Get-MatbUasNpm {
    param([Parameter(Mandatory)][string]$NodePath)
    $npmPath = Join-Path (Split-Path -Parent $NodePath) "npm.cmd"
    if (-not (Test-Path -LiteralPath $npmPath -PathType Leaf)) {
        throw "npm.cmd is missing from the selected Node installation. Repair Node.js, then run Install MATB.cmd."
    }
    return $npmPath
}

function Move-MatbUasFrontendTestCache {
    param([Parameter(Mandatory)][string]$FrontendRoot)

    # npm ci removes node_modules. A test cache created by another Windows
    # account can be readable but not deletable by the station operator.
    # Move the directory without traversing or deleting its contents.
    $root = (Get-Item -LiteralPath $FrontendRoot -ErrorAction Stop).FullName
    $modules = Join-Path $root "node_modules"
    $cache = Join-Path $modules ".vite"
    if (-not (Test-Path -LiteralPath $cache)) { return }
    foreach ($path in @($root, $modules, $cache)) {
        $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
        if (-not $item.PSIsContainer -or
            ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "Cannot relocate frontend test cache through a file or directory link: $path"
        }
    }
    $backup = Join-Path $root (".matb-cache-backup-{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), [guid]::NewGuid().ToString("N"))
    if ((Split-Path -Parent $cache) -ne $modules -or
        (Split-Path -Parent $backup) -ne $root) {
        throw "Frontend cache paths must stay inside the frontend directory."
    }
    try {
        [System.IO.Directory]::Move($cache, $backup)
    } catch {
        throw "Cannot move frontend test cache '$cache'. Close MATB and frontend tests, then retry Install MATB.cmd. Details: $($_.Exception.Message)"
    }
    Write-Host "Previous frontend test cache preserved at: $backup"
}

function Get-MatbUasRequirements {
    param([Parameter(Mandatory)][string]$RepoRoot, [Parameter(Mandatory)][string]$PythonPath)
    $target = & $PythonPath -c "import sys; print('locked' if sys.platform == 'win32' and sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 'source')"
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect the selected Python interpreter." }
    if ($target -eq "locked") { return Join-Path $RepoRoot "release/requirements-windows-py312.lock" }
    return Join-Path $RepoRoot "requirements-dev.txt"
}

function Test-MatbUasPythonDependencies {
    param([Parameter(Mandatory)][string]$RepoRoot, [Parameter(Mandatory)][string]$PythonPath)
    $requirements = Get-MatbUasRequirements -RepoRoot $RepoRoot -PythonPath $PythonPath
    & $PythonPath (Join-Path $RepoRoot "scripts/check_python_environment.py") --requirements $requirements | Out-Host
    if ($LASTEXITCODE -ne 0) { return $false }
    & $PythonPath (Join-Path $RepoRoot "scripts/check_python_environment.py") --requirements (Join-Path $RepoRoot "requirements-dev.txt") | Out-Host
    if ($LASTEXITCODE -ne 0) { return $false }
    & $PythonPath -m pip check | Out-Host
    return ($LASTEXITCODE -eq 0)
}

function Get-MatbUasDataRoot {
    param(
        [Parameter(Mandatory)][string]$RepoRoot,
        [string]$DataRoot = ""
    )

    $selected = if ($DataRoot.Trim()) {
        $DataRoot.Trim()
    } elseif ($env:MATB_DATA_ROOT -and $env:MATB_DATA_ROOT.Trim()) {
        $env:MATB_DATA_ROOT.Trim()
    } else {
        Join-Path $RepoRoot "exports\windows-suas"
    }
    $resolved = if ([System.IO.Path]::IsPathRooted($selected)) {
        [System.IO.Path]::GetFullPath($selected)
    } else {
        [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $selected))
    }
    $unsafeRoots = [System.Collections.Generic.List[string]]::new()
    $unsafeRoots.Add([System.IO.Path]::GetPathRoot($resolved))
    $unsafeRoots.Add([System.IO.Path]::GetFullPath($RepoRoot))
    if ($env:USERPROFILE) {
        $unsafeRoots.Add([System.IO.Path]::GetFullPath($env:USERPROFILE))
    }
    $resolvedComparable = $resolved.TrimEnd('\', '/')
    foreach ($unsafeRoot in $unsafeRoots) {
        if ($resolvedComparable.Equals($unsafeRoot.TrimEnd('\', '/'), [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing unsafe MATB data root: $resolved"
        }
    }
    return $resolved
}

function Get-MatbUasSourceProvenance {
    param([Parameter(Mandatory)][string]$RepoRoot)

    $unavailable = [pscustomobject]@{
        Commit = "unavailable"
        Dirty = $null
    }
    $gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $gitCommand) {
        return $unavailable
    }

    $commit = (& $gitCommand.Source -C $RepoRoot rev-parse --verify HEAD 2>$null | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0 -or -not $commit) {
        return $unavailable
    }
    $commit = $commit.Trim().ToLowerInvariant()
    if ($commit -notmatch '^(?:[0-9a-f]{40}|[0-9a-f]{64})$') {
        return $unavailable
    }

    $status = @(& $gitCommand.Source -C $RepoRoot status --porcelain --untracked-files=normal 2>$null)
    if ($LASTEXITCODE -ne 0) {
        return [pscustomobject]@{
            Commit = $commit
            Dirty = $null
        }
    }
    return [pscustomobject]@{
        Commit = $commit
        Dirty = ($status.Count -gt 0)
    }
}

function Get-MatbUasLatestSealedRun {
    param(
        [Parameter(Mandatory)][string]$RepoRoot,
        [string]$DataRoot = ""
    )

    $runsRoot = Join-Path (Get-MatbUasDataRoot -RepoRoot $RepoRoot -DataRoot $DataRoot) "runs"
    if (-not (Test-Path -LiteralPath $runsRoot -PathType Container)) {
        return $null
    }
    return Get-ChildItem -LiteralPath $runsRoot -Directory |
        Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.FullName "manifest.json") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "checksums.sha256") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "replay-verification.json") -PathType Leaf) -and
            -not (Test-Path -LiteralPath (Join-Path $_.FullName "partial-run.json") -PathType Leaf)
        } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
}

function New-MatbUasDirectory {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Test-MatbUasHttp {
    param(
        [Parameter(Mandatory)][string]$Uri,
        [int]$TimeoutSeconds = 2
    )
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSeconds
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Test-MatbUasTcpPort {
    param(
        [Parameter(Mandatory)][string]$HostName,
        [Parameter(Mandatory)][int]$Port,
        [int]$TimeoutMilliseconds = 500
    )
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connection = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $connection.AsyncWaitHandle.WaitOne($TimeoutMilliseconds)) {
            return $false
        }
        $client.EndConnect($connection)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Wait-MatbUasHttp {
    param(
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][System.Diagnostics.Process[]]$Processes,
        [int]$TimeoutSeconds = 60
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        foreach ($process in $Processes) {
            if ($process.HasExited) {
                throw "A MATB service exited before $Uri became ready."
            }
        }
        if (Test-MatbUasHttp -Uri $Uri) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Timed out waiting for $Uri"
}

function Get-MatbUasProcessInfo {
    param([Parameter(Mandatory)][int]$ProcessId)
    try {
        return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    } catch {
        return $null
    }
}

function Test-MatbUasTrackedProcess {
    param(
        [Parameter(Mandatory)][int]$ProcessId,
        [Parameter(Mandatory)][string]$ExpectedExecutable,
        [Parameter(Mandatory)][DateTime]$ExpectedStartedAtUtc,
        [Parameter(Mandatory)][ValidateSet("backend", "frontend")][string]$Role,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$RepoRoot
    )
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process -or -not $process.Path) {
        return $false
    }
    $actualExecutable = [System.IO.Path]::GetFullPath([string]$process.Path)
    $expectedFull = [System.IO.Path]::GetFullPath($ExpectedExecutable)
    if (-not $actualExecutable.Equals($expectedFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }
    try {
        $expectedStart = $ExpectedStartedAtUtc.ToUniversalTime()
        $actualStart = $process.StartTime.ToUniversalTime()
        if ([Math]::Abs(($actualStart - $expectedStart).TotalSeconds) -gt 2) {
            return $false
        }
    } catch {
        return $false
    }

    $info = Get-MatbUasProcessInfo -ProcessId $ProcessId
    if (-not $info -or -not $info.ExecutablePath -or -not $info.CommandLine) {
        # Some managed Windows environments deny Win32_Process command-line
        # access. Exact PID, executable path, and process start time still
        # provide a fail-closed identity check without matching unrelated jobs.
        return $true
    }
    $commandLine = [string]$info.CommandLine
    if ($Role -eq "backend") {
        return (
            $commandLine -match '(?i)\buvicorn\b' -and
            $commandLine -match '(?i)app\.main:app' -and
            $commandLine -match "(?i)--port\s+$Port(?:\s|$)"
        )
    }
    $normalizedCommand = $commandLine.Replace('/', '\')
    $normalizedRepo = [System.IO.Path]::GetFullPath($RepoRoot).Replace('/', '\')
    return (
        $normalizedCommand.Contains($normalizedRepo, [System.StringComparison]::OrdinalIgnoreCase) -and
        $commandLine -match '(?i)next[\\/]dist[\\/]bin[\\/]next' -and
        $commandLine -match '(?i)\bstart\b' -and
        $commandLine -match "(?i)--port\s+$Port(?:\s|$)"
    )
}

function Stop-MatbUasTrackedProcess {
    param(
        [Parameter(Mandatory)][int]$ProcessId,
        [Parameter(Mandatory)][string]$ExpectedExecutable,
        [Parameter(Mandatory)][DateTime]$ExpectedStartedAtUtc,
        [Parameter(Mandatory)][ValidateSet("backend", "frontend")][string]$Role,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$RepoRoot
    )
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return $true
    }
    if (-not (Test-MatbUasTrackedProcess -ProcessId $ProcessId -ExpectedExecutable $ExpectedExecutable -ExpectedStartedAtUtc $ExpectedStartedAtUtc -Role $Role -Port $Port -RepoRoot $RepoRoot)) {
        Write-Warning "Refusing to stop PID $ProcessId because it no longer matches the tracked MATB $Role process."
        return $false
    }
    $snapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $entry = $snapshot | Where-Object ProcessId -eq $ProcessId | Select-Object -First 1
    if ($entry) { Stop-MatbProcessTree -RootProcess $entry -Snapshot $snapshot }
    return $true
}

function Read-MatbUasState {
    param([Parameter(Mandatory)][string]$StatePath)
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        return $null
    }
    try {
        $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        foreach ($field in @('repo_root', 'status', 'supervisor_pid', 'backend_pid', 'frontend_pid',
            'backend_port', 'frontend_port', 'backend_executable', 'frontend_executable',
            'backend_started_at_utc', 'frontend_started_at_utc')) {
            if ($null -eq $state -or $field -notin $state.PSObject.Properties.Name -or $null -eq $state.$field) {
                throw "Missing state field: $field"
            }
        }
        foreach ($role in @('backend', 'frontend')) {
            if ([int]$state."${role}_pid" -le 0 -or [int]$state."${role}_port" -notin 1..65535) {
                throw 'Invalid process or port in service state.'
            }
            [void][DateTime]::Parse([string]$state."${role}_started_at_utc")
        }
        return $state
    } catch {
        Write-Warning "The MATB service state file is invalid: $StatePath"
        return $null
    }
}

function Remove-MatbUasStateFile {
    param(
        [Parameter(Mandatory)][string]$StatePath,
        [Parameter(Mandatory)][string]$DataRoot
    )
    $resolvedState = [System.IO.Path]::GetFullPath($StatePath)
    $resolvedRoot = [System.IO.Path]::GetFullPath($DataRoot).TrimEnd('\') + '\'
    if (-not $resolvedState.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a state file outside the MATB Windows data root."
    }
    if (Test-Path -LiteralPath $resolvedState -PathType Leaf) {
        Remove-Item -LiteralPath $resolvedState -Force
    }
}
