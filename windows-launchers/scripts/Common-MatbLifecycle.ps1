# Windows service lifecycle shared by start, stop, setup and desktop launchers.
function Enter-MatbLauncherLock {
    param([Parameter(Mandatory)][string]$RepoRoot)
    $bytes = [Text.Encoding]::UTF8.GetBytes([IO.Path]::GetFullPath($RepoRoot).ToLowerInvariant())
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '') }
    finally { $sha.Dispose() }
    $mutex = [Threading.Mutex]::new($false, "Local\MATB-launcher-$hash")
    try {
        try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
        if (-not $acquired) { throw 'Another MATB launcher is preparing or restarting this installation. Wait for it to finish.' }
        return $mutex
    } catch { $mutex.Dispose(); throw }
}

function Get-MatbPortOwners {
    param([int[]]$Ports)
    # Query listeners only: an outbound browser connection is never an owner.
    @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { $_.LocalPort -in $Ports } |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

function Test-MatbProcessSnapshot {
    param([Parameter(Mandatory)]$Snapshot)
    $current = Get-MatbUasProcessInfo -ProcessId ([int]$Snapshot.ProcessId)
    return ($current -and $current.CreationDate -eq $Snapshot.CreationDate -and
        $current.ExecutablePath -eq $Snapshot.ExecutablePath)
}

function Stop-MatbProcessTree {
    param([Parameter(Mandatory)]$RootProcess, [Parameter(Mandatory)][object[]]$Snapshot)
    # Capture descendants before killing the parent (venv Python and Next dev
    # have child listeners). Never follow a recycled PID or kill all node/python.
    $tree = [Collections.Generic.List[object]]::new()
    $tree.Add($RootProcess)
    for ($index = 0; $index -lt $tree.Count; $index++) {
        $parent = $tree[$index]
        foreach ($child in $Snapshot) {
            if ($child.ParentProcessId -eq $parent.ProcessId -and
                $child.CreationDate -ge $parent.CreationDate -and
                $child.ProcessId -notin @($tree | ForEach-Object ProcessId)) {
                $tree.Add($child)
            }
        }
    }
    foreach ($entry in $tree) {
        $processIdToStop = [int]$entry.ProcessId
        if ($processIdToStop -le 4 -or $processIdToStop -eq $PID -or -not $entry.ExecutablePath) {
            throw "Cannot safely restart process $processIdToStop. Close the application using the selected MATB ports and retry."
        }
    }
    foreach ($entry in $tree) {
        if (-not (Test-MatbProcessSnapshot -Snapshot $entry)) { continue }
        $process = Get-Process -Id $entry.ProcessId -ErrorAction SilentlyContinue
        if (-not $process) { continue }
        Write-Host "Closing previous application process $($entry.ProcessId) ($($entry.Name))..."
        if ($process.MainWindowHandle -ne 0 -and $process.CloseMainWindow()) {
            [void]$process.WaitForExit(1000)
        }
        if (-not $process.HasExited -and (Test-MatbProcessSnapshot -Snapshot $entry)) {
            Stop-Process -InputObject $process -Force -ErrorAction Stop
            if (-not $process.WaitForExit(10000)) { throw "Process $($entry.ProcessId) did not stop." }
        }
    }
}

function Stop-MatbConsoleInstance {
    param(
        [Parameter(Mandatory)][string]$RepoRoot,
        [Parameter(Mandatory)][string]$DataRoot,
        [int]$BackendPort = 8000,
        [int]$FrontendPort = 3100
    )
    $statePath = Join-Path $DataRoot 'service\service-state.json'
    $state = Read-MatbUasState -StatePath $statePath
    if ($state -and -not ([IO.Path]::GetFullPath($state.repo_root)).Equals($RepoRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The selected data directory belongs to a different MATB installation. Use its launcher or a separate data directory.'
    }
    $ports = @($BackendPort, $FrontendPort)
    $roots = [Collections.Generic.HashSet[int]]::new()
    if ($state -and ([IO.Path]::GetFullPath($state.repo_root)).Equals($RepoRoot, [StringComparison]::OrdinalIgnoreCase)) {
        $state.status = 'stopping'
        $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
        foreach ($role in @('backend', 'frontend')) {
            $port = [int]$state."${role}_port"
            $ports += $port
            if (Test-MatbUasTrackedProcess -ProcessId $state."${role}_pid" -ExpectedExecutable $state."${role}_executable" -ExpectedStartedAtUtc $state."${role}_started_at_utc" -Role $role -Port $port -RepoRoot $RepoRoot) {
                [void]$roots.Add([int]$state."${role}_pid")
            }
        }
    }
    $snapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    foreach ($owner in @(Get-MatbPortOwners -Ports $ports)) {
        $server = $snapshot | Where-Object ProcessId -eq $owner | Select-Object -First 1
        # Recover the venv/reload/Next parent as well when the state file was lost.
        # Shells and unrelated parent applications are never promoted to roots.
        while ($server) {
            $parent = $snapshot | Where-Object ProcessId -eq $server.ParentProcessId | Select-Object -First 1
            if (-not $parent -or $parent.CreationDate -gt $server.CreationDate -or
                $parent.Name -notmatch '^(?:pythonw?|node)\.exe$' -or
                $parent.CommandLine -notmatch '(?i)(?:\buvicorn\b.*app\.main:app|next[\\/]dist[\\/](?:bin[\\/]next|server[\\/]lib[\\/]start-server)|npm-cli\.js.*\b(?:dev|start)\b)') { break }
            $server = $parent
        }
        if ($server) { [void]$roots.Add([int]$server.ProcessId) }
    }
    $nativePath = Join-Path $RepoRoot 'openmatb\main.py'
    $nativePattern = '(?i)(?:^|[\s"])' + [regex]::Escape($nativePath) + '(?:[\s"]|$)'
    foreach ($entry in $snapshot) {
        if ($entry.CommandLine -and $entry.CommandLine.Replace('/', '\') -match $nativePattern) {
            [void]$roots.Add([int]$entry.ProcessId)
        }
    }
    # Refuse our own parent chain even if passed an unexpected port.
    $ancestorId = $PID
    $ancestors = [Collections.Generic.HashSet[int]]::new()
    while ($ancestorId -gt 0 -and $ancestors.Add($ancestorId)) {
        $ancestor = $snapshot | Where-Object ProcessId -eq $ancestorId | Select-Object -First 1
        if (-not $ancestor) { break }
        $ancestorId = [int]$ancestor.ParentProcessId
    }
    foreach ($rootId in $roots) {
        if ($ancestors.Contains($rootId)) { throw "Refusing to stop the launcher's own process tree ($rootId)." }
        $entry = $snapshot | Where-Object ProcessId -eq $rootId | Select-Object -First 1
        if ($entry) { Stop-MatbProcessTree -RootProcess $entry -Snapshot $snapshot }
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $remaining = @(Get-MatbPortOwners -Ports $ports)
        if (-not $remaining.Count) { break }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($remaining.Count) { throw "MATB ports remain occupied by PID(s): $($remaining -join ', '). Close that application and retry." }
    Remove-MatbUasStateFile -StatePath $statePath -DataRoot $DataRoot
}

function Test-MatbFrontendDependencies {
    param([Parameter(Mandatory)][string]$FrontendRoot, [Parameter(Mandatory)][string]$NodePath)
    $stamp = Join-Path $FrontendRoot 'node_modules\.matb-package-lock.sha256'
    if (-not (Test-Path -LiteralPath $stamp -PathType Leaf)) { return $false }
    $hash = (Get-FileHash -LiteralPath (Join-Path $FrontendRoot 'package-lock.json') -Algorithm SHA256).Hash
    if ((Get-Content -LiteralPath $stamp -Raw).Trim() -ne $hash) { return $false }
    # A matching stamp alone does not detect a half-deleted installation.
    Push-Location $FrontendRoot
    try {
        & $NodePath -e 'for (const p of ["next/dist/bin/next", "react", "react-dom", "maplibre-gl/package.json", "typescript"]) require.resolve(p)' 2>$null
        return ($LASTEXITCODE -eq 0)
    } finally { Pop-Location }
}
