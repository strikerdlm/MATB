[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
. (Join-Path $repoRoot "windows-launchers/scripts/Common-MatbUas.ps1")

foreach ($case in @(
    @{ Version = "v18.20.0"; Accepted = $false },
    @{ Version = "v20.0.0"; Accepted = $false },
    @{ Version = "v20.8.1"; Accepted = $false },
    @{ Version = "v20.9.0"; Accepted = $true },
    @{ Version = "v22.23.2"; Accepted = $true },
    @{ Version = "v24.0.0"; Accepted = $true },
    @{ Version = "nonsense"; Accepted = $false }
)) {
    $actual = Test-MatbUasNodeVersion -VersionText $case.Version
    if ($actual -ne $case.Accepted) { throw "Node version admission failed for $($case.Version)" }
}

# A fresh launch must select the same compatible runtime as installation, even
# when an older portable Node precedes it in PATH and Program Files is empty.
& {
    $oldNode = { $global:LASTEXITCODE = 0; 'v18.20.0' }
    $newNode = { $global:LASTEXITCODE = 0; 'v22.23.2' }
    function Get-Command {
        param($Name, $CommandType, $ErrorAction, [switch]$All)
        [pscustomobject]@{ Source = $oldNode }
        if ($All) { [pscustomobject]@{ Source = $newNode } }
    }
    function Test-Path { param($LiteralPath, $PathType); return $true }
    function Split-Path { param($Parent); return '/compatible-node' }
    $savedProgramFiles = $env:ProgramFiles
    $savedPath = $env:PATH
    try {
        $env:ProgramFiles = ''
        $selected = Get-MatbUasNode
        if ($selected.ToString() -ne $newNode.ToString()) { throw 'Launch selected an incompatible Node.' }
        if (-not $env:PATH.StartsWith('/compatible-node')) { throw 'Selected Node was not placed first in PATH.' }
    } finally {
        $env:ProgramFiles = $savedProgramFiles
        $env:PATH = $savedPath
    }
}

# AST parsing catches malformed quoting on the same scripts that Explorer runs.
foreach ($script in Get-ChildItem (Join-Path $repoRoot "windows-launchers/scripts") -Filter *.ps1) {
    $tokens = $null; $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($script.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw "PowerShell parse failed: $($script.Name): $errors" }
}
Write-Host "MATB installer version and script checks passed."
