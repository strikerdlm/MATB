[CmdletBinding()]
param([switch]$NoPrerequisiteInstall, [switch]$SkipTests, [string]$DataRoot = "")

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-MatbBootstrap.ps1")
if ($env:OS -ne "Windows_NT") { throw "This installer requires native Windows 10/11 (64-bit)." }
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "openmatb/main.py"))) {
    throw "Extract the complete MATB ZIP or clone the repository before running the installer."
}
$logRoot = Join-Path $repoRoot "exports/windows-install"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$logPath = Join-Path $logRoot ("setup-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
Start-Transcript -Path $logPath | Out-Null
try {
    Write-Host "MATB Windows setup: Research Console and desktop OpenMATB" -ForegroundColor Cyan
    Write-Host "The first setup downloads packages and builds the console. Keep this window open."
    Update-MatbBootstrapPath
    $powerShell = Get-MatbBootstrapPowerShell
    if (-not $powerShell) {
        if ($NoPrerequisiteInstall) { throw "PowerShell 7+ is missing." }
        Install-MatbBootstrapPackage -PackageId "Microsoft.PowerShell" -ExtraArguments @("--installer-type", "wix")
        $powerShell = Get-MatbBootstrapPowerShell
    }
    if (-not $powerShell) { throw "PowerShell 7 was not found after installation. Restart Windows if requested and rerun setup." }
    $python = Get-MatbBootstrapPython
    if (-not $python) {
        if ($NoPrerequisiteInstall) { throw "Python 3.12 64-bit is missing." }
        Install-MatbBootstrapPackage -PackageId "Python.Python.3.12" -ExtraArguments @("--scope", "user", "--architecture", "x64")
        $python = Get-MatbBootstrapPython
    }
    if (-not $python) { throw "Python 3.12 64-bit was not found after installation. Rerun setup after closing other installers." }
    $node = Get-MatbBootstrapNode
    if (-not $node) {
        if ($NoPrerequisiteInstall) { throw "Node.js 20.9+ is missing." }
        Install-MatbBootstrapPackage -PackageId "OpenJS.NodeJS.22"
        $node = Get-MatbBootstrapNode
    }
    if (-not $node) { throw "Node.js was not found after installation. Restart Windows if requested and rerun setup." }

    # Do not use a global/Conda Python implicitly. Initialize creates .venv-suas.
    $prepare = @("-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        (Join-Path $PSScriptRoot "Initialize-MatbUas.ps1"), "-BasePython", $python)
    if ($SkipTests) { $prepare += "-SkipTests" }
    if ($DataRoot) { $prepare += @("-DataRoot", $DataRoot) }
    & $powerShell @prepare
    if ($LASTEXITCODE -ne 0) { throw "MATB preparation failed (exit $LASTEXITCODE). See $logPath" }
    Write-Host "Setup completed. Double-click Start MATB.cmd or Start OpenMATB.cmd." -ForegroundColor Green
} catch {
    Write-Host ("Setup failed: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "Installation log: $logPath"
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
