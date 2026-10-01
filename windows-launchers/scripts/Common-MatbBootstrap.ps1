# Compatible with the Windows PowerShell 5.1 shipped with Windows 10/11.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Update-MatbBootstrapPath {
    $paths = @($env:PATH, [Environment]::GetEnvironmentVariable("Path", "Machine"),
        [Environment]::GetEnvironmentVariable("Path", "User"))
    $env:PATH = ($paths | Where-Object { $_ }) -join [IO.Path]::PathSeparator
}

function Get-MatbBootstrapPowerShell {
    $ErrorActionPreference = "Continue"
    $command = Get-Command pwsh.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $candidates = @()
    if ($command) { $candidates += $command.Source }
    if ($env:ProgramFiles) { $candidates += Join-Path $env:ProgramFiles "PowerShell/7/pwsh.exe" }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $version = & $candidate -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.Major' 2>$null
        if ($LASTEXITCODE -eq 0 -and [int]($version | Select-Object -Last 1) -ge 7) { return $candidate }
    }
    return $null
}

function Get-MatbBootstrapPython {
    $ErrorActionPreference = "Continue"
    $candidates = @()
    $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        $selected = & $launcher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $selected) { $candidates += ($selected | Select-Object -Last 1) }
    }
    if ($env:LOCALAPPDATA) { $candidates += Join-Path $env:LOCALAPPDATA "Programs/Python/Python312/python.exe" }
    if ($env:ProgramFiles) { $candidates += Join-Path $env:ProgramFiles "Python312/python.exe" }
    $command = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command -and $command.Source -notlike "*WindowsApps*") { $candidates += $command.Source }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $compatible = & $candidate -c "import sys; print(int(sys.version_info[:2] == (3,12) and sys.maxsize > 2**32))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $compatible -eq "1") { return [IO.Path]::GetFullPath($candidate) }
    }
    return $null
}

function Get-MatbBootstrapNode {
    $ErrorActionPreference = "Continue"
    $command = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $candidates = @()
    if ($command) { $candidates += $command.Source }
    if ($env:ProgramFiles) { $candidates += Join-Path $env:ProgramFiles "nodejs/node.exe" }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $version = & $candidate --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $version -match '^v(?<version>\d+\.\d+\.\d+)$' -and
            [version]$Matches.version -ge [version]"20.9.0") {
            # npm.cmd and later launchers must discover the same installation.
            $env:PATH = (Split-Path -Parent $candidate) + [IO.Path]::PathSeparator + $env:PATH
            return $candidate
        }
    }
    return $null
}

function Install-MatbBootstrapPackage {
    param([Parameter(Mandatory)][string]$PackageId, [string[]]$ExtraArguments = @())
    $winget = Get-Command winget.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $winget) {
        throw "WinGet is unavailable. Install/update Microsoft App Installer from the Microsoft Store, then rerun Install MATB.cmd. Manual runtime links are in WINDOWS.md."
    }
    Write-Host "Installing $PackageId with Windows Package Manager..." -ForegroundColor Cyan
    & $winget.Source install --id $PackageId --exact --source winget --accept-source-agreements --accept-package-agreements @ExtraArguments
    $installExit = $LASTEXITCODE
    Update-MatbBootstrapPath
    if ($installExit -ne 0 -and $installExit -ne 3010) {
        throw "WinGet failed for $PackageId (exit $installExit). Review the installer message, then rerun Install MATB.cmd."
    }
}
