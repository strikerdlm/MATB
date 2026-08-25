[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ($env:OS -ne "Windows_NT") { throw "This suite must run on native Windows; WSL is not evidence" }
if ((node --version).Trim() -ne "v22.23.2") { throw "Native Windows packaging tests require Node 22.23.2" }

$SmsRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$Installer = Join-Path $SmsRoot "packaging\windows\SmsCtl.ps1"
$StartScript = Join-Path $SmsRoot "packaging\windows\Start-Sms.ps1"
$TestRoot = Join-Path ([IO.Path]::GetTempPath()) ("fac-isr-sms-native-{0}" -f [guid]::NewGuid().ToString("N"))

function Assert-True([bool]$Condition, [string]$Message) {
  if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

function Update-BundleInventory([string]$Bundle) {
  $inventory = @()
  foreach ($file in Get-ChildItem -LiteralPath $Bundle -Recurse -File | Where-Object { $_.Name -notin @("inventory.json", "inventory.tsv") } | Sort-Object FullName) {
    $relative = [IO.Path]::GetRelativePath($Bundle, $file.FullName).Replace('\', '/')
    $inventory += @{ path = $relative; sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); sizeBytes = $file.Length; mode = 292 }
  }
  @{ schemaVersion = "1.0"; inventoryPath = "inventory.json"; files = $inventory } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Bundle "inventory.json") -Encoding utf8NoBOM
  $inventoryJson = Get-Item -LiteralPath (Join-Path $Bundle "inventory.json")
  $trusted = @($inventory) + @(@{ path = "inventory.json"; sha256 = (Get-FileHash -LiteralPath $inventoryJson.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); sizeBytes = $inventoryJson.Length; mode = 292 })
  $lines = $trusted | ForEach-Object { "{0}`t{1}`t{2}`t{3}" -f $_.path, $_.sha256, $_.sizeBytes, "444" }
  [IO.File]::WriteAllText((Join-Path $Bundle "inventory.tsv"), (($lines -join "`n") + "`n"), [Text.UTF8Encoding]::new($false))
}

function Write-Bundle([string]$Name, [bool]$FailMigration = $false, [bool]$FailStart = $false, [bool]$Production = $true) {
  $bundle = Join-Path $TestRoot $Name
  $files = @{
    "release.json" = (@{ release = "fac-isr-sms@0.2.0-rc.1"; target = "win32-x64"; buildId = $Name; operationalReady = $false; production = $Production; runtimeProvenance = $(if ($Production) { "official-node-signed-checksums" } else { "controlled-test-fixture" }) } | ConvertTo-Json -Compress)
    "app\scripts\start-edge.mjs" = $(if ($FailStart) { "process.exit(74);" } else { "process.stdout.write('listening\n');" })
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
  Update-BundleInventory $bundle
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
  $parserRelease = Join-Path $TestRoot "parser-release"
  New-Item -ItemType Directory -Path (Join-Path $parserRelease "runtime"), (Join-Path $parserRelease "app\scripts") -Force | Out-Null
  Copy-Item -LiteralPath (Get-Command node.exe).Source -Destination (Join-Path $parserRelease "runtime\node.exe")
  $parserMarker = Join-Path $TestRoot "parser-value.txt"
  [IO.File]::WriteAllText((Join-Path $parserRelease "app\scripts\start-edge.mjs"), "import { writeFileSync } from 'node:fs'; writeFileSync(process.env.SMS_TEST_VALUE_MARKER, process.env.SMS_EXPORT_KEY_ID);", [Text.UTF8Encoding]::new($false))
  $parserConfig = Join-Path $TestRoot "parser.env"
  [IO.File]::WriteAllText($parserConfig, "SMS_TEST_VALUE_MARKER=$parserMarker`r`nSMS_EXPORT_KEY_ID=  padded value  `r`n", [Text.UTF8Encoding]::new($false))
  & $StartScript -ReleaseRoot $parserRelease -ConfigurationPath $parserConfig
  Assert-True ((Get-Content -LiteralPath $parserMarker -Raw) -eq "  padded value  ") "Start-Sms altered configuration value whitespace"
  & node (Join-Path $SmsRoot "scripts\edge-healthcheck.mjs") --ready *> $null
  Assert-True ($LASTEXITCODE -ne 0) "readiness passed without an installed HTTPS listener"
  $controlled = Write-Bundle "renamed-as-production" $false $false $false
  $controlledRejected = $false
  try { Invoke-Sms "Install" $controlled $null } catch { $controlledRejected = $_.Exception.Message -match "release metadata" }
  Assert-True $controlledRejected "a renamed controlled-runtime bundle was accepted"
  $nonportable = Write-Bundle "nonportable"
  Set-Content -LiteralPath (Join-Path $nonportable "app\unsupported[segment]") -Value "not portable"
  Update-BundleInventory $nonportable
  $nonportableRejected = $false
  try { Invoke-Sms "Install" $nonportable $null } catch { $nonportableRejected = $_.Exception.Message -match "portable" }
  Assert-True $nonportableRejected "a non-portable bundle path was accepted"
  $first = Write-Bundle "build-a"
  $originalTemplate = Get-Content -LiteralPath (Join-Path $first "config\sms.env.template") -Raw
  $env:SMS_TEST_MUTATE_SOURCE_AFTER_STAGE = "1"
  Invoke-Sms "Install" $first $null | Out-Null
  Remove-Item Env:SMS_TEST_MUTATE_SOURCE_AFTER_STAGE
  $installRoot = Join-Path $TestRoot "Program Files\FAC ISR\SMS"
  $mutableRoot = Join-Path $TestRoot "ProgramData\FAC ISR\SMS"
  Assert-True ((Get-Content -LiteralPath (Join-Path $mutableRoot "config\sms.env") -Raw) -eq $originalTemplate) "install copied configuration from mutable source input"
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
  Assert-True ((Invoke-Sms "Status" $null $null) -match "running ready") "standalone restore did not restore prior running state"
  $invalidBackup = Join-Path $TestRoot "invalid-backup.zip"
  Set-Content -LiteralPath $invalidBackup -Value "not a zip"
  try { Invoke-Sms "Restore" $null $invalidBackup | Out-Null } catch { }
  Assert-True ((Invoke-Sms "Status" $null $null) -match "running ready") "failed restore stranded the prior running service"

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
  $samePointer = Get-Content -LiteralPath (Join-Path $installRoot "current.txt") -Raw
  $env:SMS_TEST_FAIL_MIGRATION_AFTER_STAGE = "1"
  try { Invoke-Sms "Upgrade" $second $null | Out-Null } catch { }
  Remove-Item Env:SMS_TEST_FAIL_MIGRATION_AFTER_STAGE
  Assert-True ((Get-Content -LiteralPath (Join-Path $installRoot "current.txt") -Raw) -eq $samePointer) "same-artifact failure changed the immutable pointer"
  Assert-True (Test-Path -LiteralPath (Join-Path (Join-Path $installRoot "releases") $samePointer.Trim())) "same-artifact failure removed the active immutable release"
  $startFailing = Write-Bundle "build-d" $false $true
  $lifecycleLog = Join-Path $mutableRoot "run\lifecycle.log"
  Remove-Item -LiteralPath $lifecycleLog -ErrorAction SilentlyContinue
  $startFailed = $false
  try { Invoke-Sms "Upgrade" $startFailing $null } catch { $startFailed = $_.Exception.Message -match "rolled back" }
  Assert-True $startFailed "failed new-release startup was accepted"
  Assert-True ((Get-Content -LiteralPath (Join-Path $installRoot "current.txt") -Raw) -eq $upgradedPointer) "startup failure changed the immutable pointer"
  Assert-True ((Get-Content -LiteralPath $database -Raw) -eq "original database bytes") "startup failure did not restore data"
  Assert-True ((Invoke-Sms "Status" $null $null) -match "running ready") "startup failure did not restart the old release"
  $rollbackOrder = @(Get-Content -LiteralPath $lifecycleLog)
  Assert-True (($rollbackOrder -join ',') -eq "stop,start-attempt,stop,restore,start-attempt") "failed new task was not stopped before restore and old-task restart"

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
