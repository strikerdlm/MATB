[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
. (Join-Path $repoRoot 'windows-launchers/scripts/Common-MatbUas.ps1')
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('MATB restart ñ ' + [guid]::NewGuid())
$processes = [Collections.Generic.List[object]]::new()
$node = Get-MatbUasNode
function Assert-True($Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function New-TestPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
    $listener.Stop()
    return $port
}
function Start-TestListener([int]$Port, [int]$ChildPort = 0) {
    $process = Start-Process -FilePath $node -ArgumentList @(('"' + $fixture + '"'), $Port, $ChildPort) -WindowStyle Hidden -PassThru
    $processes.Add($process)
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while (-not (Test-MatbUasTcpPort -HostName '127.0.0.1' -Port $Port)) {
        if ($process.HasExited -or [DateTime]::UtcNow -gt $deadline) { throw 'Test listener failed.' }
        Start-Sleep -Milliseconds 100
    }
    return $process
}
try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    $fixture = Join-Path $tempRoot 'listener.cjs'
    @'
const port = Number(process.argv[2]);
const childPort = Number(process.argv[3]);
if (childPort) require('child_process').spawn(process.execPath, [__filename, String(childPort), '0'], {stdio:'ignore'});
require('net').createServer(s => s.end()).listen(port, '127.0.0.1');
'@ | Set-Content -LiteralPath $fixture -Encoding utf8
    $port = New-TestPort
    $childPort = New-TestPort
    $otherPort = New-TestPort
    $tree = Start-TestListener $port $childPort
    $other = Start-TestListener $otherPort
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while (-not (Test-MatbUasTcpPort -HostName '127.0.0.1' -Port $childPort)) {
        if ([DateTime]::UtcNow -gt $deadline) { throw 'Test child failed.' }
        Start-Sleep -Milliseconds 100
    }
    $treeSnapshot = Get-MatbUasProcessInfo -ProcessId $tree.Id
    $staleSnapshot = $treeSnapshot | Select-Object *
    $staleSnapshot.CreationDate = $treeSnapshot.CreationDate.AddSeconds(-20)
    Assert-True (-not (Test-MatbProcessSnapshot $staleSnapshot)) 'A reused PID must not pass identity checks.'
    $dataRoot = Join-Path $tempRoot 'data'
    New-Item -ItemType Directory -Path (Join-Path $dataRoot 'service') -Force | Out-Null
    '{}' | Set-Content -LiteralPath (Join-Path $dataRoot 'service/service-state.json')
    'saved participant result' | Set-Content -LiteralPath (Join-Path $dataRoot 'keep.csv')
    # Corrupt/lost state must not prevent stopping the exact occupied ports.
    Stop-MatbConsoleInstance -RepoRoot $tempRoot -DataRoot $dataRoot -BackendPort $port -FrontendPort $childPort
    Assert-True (-not (Test-MatbUasTcpPort -HostName '127.0.0.1' -Port $port)) 'Parent port remained open.'
    Assert-True (-not (Test-MatbUasTcpPort -HostName '127.0.0.1' -Port $childPort)) 'Child port remained open.'
    Assert-True (-not (Test-MatbProcessSnapshot $treeSnapshot)) 'Parent process survived the stop.'
    Assert-True (Test-MatbUasTcpPort -HostName '127.0.0.1' -Port $otherPort) 'An unrelated service was stopped.'
    Assert-True ((Get-Content -LiteralPath (Join-Path $dataRoot 'keep.csv')).Trim() -eq 'saved participant result') 'Saved data changed.'
    Stop-MatbConsoleInstance -RepoRoot $tempRoot -DataRoot $dataRoot -BackendPort $port -FrontendPort $childPort

    # A stale success stamp must not admit a partially deleted node_modules.
    $frontend = Join-Path $tempRoot 'frontend'
    New-Item -ItemType Directory -Path (Join-Path $frontend 'node_modules') -Force | Out-Null
    '{}' | Set-Content -LiteralPath (Join-Path $frontend 'package-lock.json')
    (Get-FileHash -LiteralPath (Join-Path $frontend 'package-lock.json')).Hash |
        Set-Content -LiteralPath (Join-Path $frontend 'node_modules/.matb-package-lock.sha256')
    Assert-True (-not (Test-MatbFrontendDependencies -FrontendRoot $frontend -NodePath $node)) 'Missing modules were accepted.'
} finally {
    foreach ($process in $processes) {
        if (-not $process.HasExited) {
            $snapshot = @(Get-CimInstance Win32_Process)
            $entry = $snapshot | Where-Object ProcessId -eq $process.Id | Select-Object -First 1
            if ($entry) { Stop-MatbProcessTree -RootProcess $entry -Snapshot $snapshot }
        }
    }
    $expectedParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
    $resolved = [IO.Path]::GetFullPath($tempRoot)
    if ((Split-Path -Parent $resolved) -ne $expectedParent -or (Split-Path -Leaf $resolved) -notlike 'MATB restart ñ *') {
        throw 'Unsafe test cleanup directory.'
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Host 'Windows restart, process tree, corrupt state, retained data and incomplete dependency checks passed.'
