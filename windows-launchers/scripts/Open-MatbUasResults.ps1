[CmdletBinding()]
param(
    [switch]$ListOnly,
    [string]$DataRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbUas.ps1")

$repoRoot = Get-MatbUasRepoRoot
$dataRoot = Get-MatbUasDataRoot -RepoRoot $repoRoot -DataRoot $DataRoot
$logRoot = Join-Path $dataRoot "service\logs"
$targets = [System.Collections.Generic.List[string]]::new()
$latestRun = Get-MatbUasLatestSealedRun -RepoRoot $repoRoot -DataRoot $dataRoot
if ($latestRun) {
    $targets.Add($latestRun.FullName)
}
if (Test-Path -LiteralPath $logRoot -PathType Container) {
    $targets.Add([System.IO.Path]::GetFullPath($logRoot))
}
if ($targets.Count -eq 0) {
    throw "No sealed technical runs or service logs exist yet. Run the console or a profile first."
}

$resolvedRoot = [System.IO.Path]::GetFullPath($dataRoot).TrimEnd('\') + '\'
foreach ($target in $targets) {
    $resolvedTarget = [System.IO.Path]::GetFullPath($target)
    if (-not $resolvedTarget.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to open a path outside the MATB Windows data root."
    }
    Write-Host "Opening: $resolvedTarget"
    if (-not $ListOnly) {
        $explorerArgument = '"' + $resolvedTarget + '"'
        Start-Process -FilePath "explorer.exe" -ArgumentList $explorerArgument
    }
}

if ($latestRun) {
    Write-Host "Use shortcut 90 to recompute replay and checksum verification." -ForegroundColor Cyan
}
