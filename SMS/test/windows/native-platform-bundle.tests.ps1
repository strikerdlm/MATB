[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ($env:OS -ne "Windows_NT") { throw "This suite must run on native Windows; WSL is not evidence" }
if ((node --version).Trim() -ne "v22.23.2") { throw "Native Windows packaging tests require Node 22.23.2" }

$SmsRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$Installer = Join-Path $SmsRoot "packaging\windows\SmsCtl.ps1"
$TestRoot = Join-Path ([IO.Path]::GetTempPath()) ("fac-isr-sms-native-{0}" -f [guid]::NewGuid().ToString("N"))

function Assert-True([bool]$Condition, [string]$Message) {
  if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

function Write-Bundle([string]$Name, [bool]$FailMigration = $false) {
  $bundle = Join-Path $TestRoot $Name
  $files = @{
    "release.json" = (@{ release = "fac-isr-sms@0.2.0-rc.1"; target = "win32-x64"; buildId = $Name; operationalReady = $false } | ConvertTo-Json -Compress)
    "app\scripts\start-edge.mjs" = "process.stdout.write('listening\n');"
    "app\scripts\edge-healthcheck.mjs" = "process.exit(0);"
    "app\apps\edge-api\dist\admin\cli.js" = "process.stdout.write('admin\n');"
    "app\apps\console\dist\index.html" = "<!doctype html><title>SMS</title>"
    "config\sms.env.template" = "SMS_DEPLOYMENT_MODE=standalone`r`nSMS_NETWORK=disabled"
    "install\windows\Migrate.ps1" = $(if ($FailMigration) { "throw 'controlled migration failure'" } else { 'param([string]$DataRoot,[string]$BuildId); Set-Content -LiteralPath (Join-Path $DataRoot "migration.marker") -Value $BuildId -NoNewline' })
  }
  foreach ($entry in $files.GetEnumerator()) {
    $path = Join-Path $bundle $entry.Key
    New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null
    [IO.File]::WriteAllText($path, [string]$entry.Value, [Text.UTF8Encoding]::new($false))
  }
  $runtime = Join-Path $bundle "runtime\node.exe"
  New-Item -ItemType Directory -Path (Split-Path $runtime) -Force | Out-Null
  Copy-Item -LiteralPath (Get-Command node.exe).Source -Destination $runtime
  $inventory = @()
  foreach ($file in Get-ChildItem -LiteralPath $bundle -Recurse -File | Sort-Object FullName) {
    $relative = [IO.Path]::GetRelativePath($bundle, $file.FullName).Replace('\', '/')
    $inventory += @{ path = $relative; sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); sizeBytes = $file.Length; mode = 292 }
  }
  @{ schemaVersion = "1.0"; inventoryPath = "inventory.json"; files = $inventory } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $bundle "inventory.json") -Encoding utf8NoBOM
  return $bundle
}

function Invoke-Sms([string]$Action, [string]$Bundle, [string]$Backup) {
  $arguments = @{ Action = $Action; Root = $TestRoot; TestMode = $true }
  if ($Bundle) { $arguments.BundleRoot = $Bundle }
  if ($Backup) { $arguments.BackupPath = $Backup }
  & $Installer @arguments
}

function Set-ServiceOnlyAcl([string]$Path) {
  & icacls.exe $Path "/inheritance:r" "/grant:r" "NT AUTHORITY\SYSTEM:F" "BUILTIN\Administrators:F" "NT AUTHORITY\LOCAL SERVICE:R" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "icacls failed for $Path" }
}

try {
  New-Item -ItemType Directory -Path $TestRoot | Out-Null
  & node (Join-Path $SmsRoot "scripts\edge-healthcheck.mjs") --ready *> $null
  Assert-True ($LASTEXITCODE -ne 0) "readiness passed without an installed HTTPS listener"
  $first = Write-Bundle "build-a"
  Invoke-Sms "Install" $first $null | Out-Null
  $installRoot = Join-Path $TestRoot "Program Files\FAC ISR\SMS"
  $mutableRoot = Join-Path $TestRoot "ProgramData\FAC ISR\SMS"
  Assert-True (Test-Path -LiteralPath (Join-Path $installRoot "current.txt")) "immutable current pointer was not installed"
  $taskContract = Get-Content -LiteralPath (Join-Path $mutableRoot "run\task.json") -Raw | ConvertFrom-Json
  Assert-True ($taskContract.trigger -eq "AtStartup" -and $taskContract.account -eq "LocalService" -and $taskContract.restartCount -ge 3) "at-startup Local Service restart policy is missing"

  $tls = Join-Path $mutableRoot "config\tls"
  foreach ($name in @("server.crt", "server.key", "export.key")) { Set-Content -LiteralPath (Join-Path $tls $name) -Value "controlled fixture" }
  & icacls.exe (Join-Path $tls "server.key") "/grant" "Everyone:R" | Out-Null
  $rejected = $false
  try { Invoke-Sms "Start" $null $null } catch { $rejected = $_.Exception.Message -match "ACL" }
  Assert-True $rejected "an exposed TLS key ACL was accepted"
  Set-ServiceOnlyAcl (Join-Path $tls "server.key")
  Set-ServiceOnlyAcl (Join-Path $tls "export.key")
  Invoke-Sms "Start" $null $null | Out-Null
  Assert-True ((Invoke-Sms "Status" $null $null) -match "running ready") "service did not report readiness"
  Set-Content -LiteralPath (Join-Path $mutableRoot "run\service.state") -Value "failed"
  Invoke-Sms "Restart" $null $null | Out-Null
  Assert-True ((Invoke-Sms "Status" $null $null) -match "running ready") "service did not recover after restart"

  $database = Join-Path $mutableRoot "data\edge.sqlite"
  Set-Content -LiteralPath $database -Value "original database bytes" -NoNewline
  $activePackage = Join-Path $mutableRoot "packages\active-policy.json"
  Set-Content -LiteralPath $activePackage -Value "original package bytes" -NoNewline
  $backup = (Invoke-Sms "Backup" $null $null | Select-Object -Last 1).Trim()
  Set-Content -LiteralPath $database -Value "damaged" -NoNewline
  Set-Content -LiteralPath $activePackage -Value "damaged package" -NoNewline
  Invoke-Sms "Restore" $null $backup | Out-Null
  Assert-True ((Get-Content -LiteralPath $database -Raw) -eq "original database bytes") "backup restore did not recover exact data"
  Assert-True ((Get-Content -LiteralPath $activePackage -Raw) -eq "original package bytes") "backup restore did not recover exact packages"

  $second = Write-Bundle "build-b"
  Invoke-Sms "Upgrade" $second $null | Out-Null
  Assert-True ((Invoke-Sms "Status" $null $null) -match "running ready") "successful upgrade did not restart the prior running service"
  Assert-True ((Get-Content -LiteralPath (Join-Path $mutableRoot "migration.marker") -Raw) -eq "build-b") "upgrade migration did not run"
  $upgradedPointer = Get-Content -LiteralPath (Join-Path $installRoot "current.txt") -Raw
  $failing = Write-Bundle "build-c" $true
  $failed = $false
  try { Invoke-Sms "Upgrade" $failing $null } catch { $failed = $_.Exception.Message -match "migration" }
  Assert-True $failed "failed migration was accepted"
  Assert-True ((Get-Content -LiteralPath (Join-Path $installRoot "current.txt") -Raw) -eq $upgradedPointer) "failed upgrade changed the immutable pointer"
  Assert-True ((Get-Content -LiteralPath $database -Raw) -eq "original database bytes") "failed upgrade did not restore data"
  Assert-True ((Get-Content -LiteralPath $activePackage -Raw) -eq "original package bytes") "failed upgrade did not restore packages"
  Assert-True ((Invoke-Sms "Status" $null $null) -match "running ready") "failed upgrade did not restart the old release"

  $junctionBundle = Write-Bundle "junction-build"
  New-Item -ItemType Directory -Path (Join-Path $TestRoot "junction-target") | Out-Null
  New-Item -ItemType Junction -Path (Join-Path $junctionBundle "app\unsafe-junction") -Target (Join-Path $TestRoot "junction-target") | Out-Null
  $junctionRejected = $false
  try { Invoke-Sms "Install" $junctionBundle $null } catch { $junctionRejected = $_.Exception.Message -match "reparse" }
  Assert-True $junctionRejected "bundle directory junction was accepted"

  Invoke-Sms "Stop" $null $null | Out-Null
  Invoke-Sms "Uninstall" $null $null | Out-Null
  Assert-True (-not (Test-Path -LiteralPath $installRoot)) "uninstall retained immutable files"
  Assert-True ((Get-Content -LiteralPath $database -Raw) -eq "original database bytes") "uninstall removed operational data"
  Assert-True ((Get-Content -LiteralPath $activePackage -Raw) -eq "original package bytes") "uninstall removed active packages"
  Write-Output "Windows native lifecycle: PASS"
} finally {
  if (Test-Path -LiteralPath $TestRoot) {
    Get-ChildItem -LiteralPath $TestRoot -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object { $_.IsReadOnly = $false }
    Remove-Item -LiteralPath $TestRoot -Recurse -Force
  }
}
