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

# AST parsing catches malformed quoting on the same scripts that Explorer runs.
foreach ($script in Get-ChildItem (Join-Path $repoRoot "windows-launchers/scripts") -Filter *.ps1) {
    $tokens = $null; $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($script.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw "PowerShell parse failed: $($script.Name): $errors" }
}
Write-Host "MATB installer version and script checks passed."
