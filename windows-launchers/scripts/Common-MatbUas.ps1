Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

function Get-MatbUasNode {
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $nodeCommand) {
        throw "Node.js was not found. Install Node.js 20 or newer and run setup again."
    }
    $versionText = (& $nodeCommand.Source --version 2>$null | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0 -or $versionText -notmatch '^v(?<major>\d+)\.') {
        throw "The Node.js version could not be determined."
    }
    if ([int]$Matches.major -lt 20) {
        throw "Node.js 20 or newer is required; found $versionText."
    }
    return $nodeCommand.Source
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
    Stop-Process -Id $ProcessId -ErrorAction Stop
    try {
        Wait-Process -Id $ProcessId -Timeout 10 -ErrorAction Stop
    } catch {
        $remaining = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($remaining) {
            Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        }
    }
    return $true
}

function Read-MatbUasState {
    param([Parameter(Mandatory)][string]$StatePath)
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
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
