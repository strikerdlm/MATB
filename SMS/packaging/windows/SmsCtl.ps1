[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet("Install", "Start", "Restart", "Status", "Stop", "Upgrade", "Backup", "Restore", "Uninstall")]
  [string]$Action,
  [string]$BundleRoot,
  [string]$BackupPath,
  [string]$Root,
  [switch]$TestMode
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($TestMode -and [string]::IsNullOrWhiteSpace($Root)) { throw "TestMode requires an explicit Root" }
if (-not $TestMode -and -not [string]::IsNullOrWhiteSpace($Root)) { throw "Root is test-only" }
if ($TestMode) {
  $ProgramFilesRoot = Join-Path $Root "Program Files"
  $ProgramDataRoot = Join-Path $Root "ProgramData"
} else {
  $ProgramFilesRoot = $env:ProgramFiles
  $ProgramDataRoot = $env:ProgramData
}
$InstallRoot = Join-Path $ProgramFilesRoot "FAC ISR\SMS"
$MutableRoot = Join-Path $ProgramDataRoot "FAC ISR\SMS"
$ConfigRoot = Join-Path $MutableRoot "config"
$DataRoot = Join-Path $MutableRoot "data"
$PackageRoot = Join-Path $MutableRoot "packages"
$LogRoot = Join-Path $MutableRoot "logs"
$BackupRoot = Join-Path $MutableRoot "backups"
$StateRoot = Join-Path $MutableRoot "run"
$TaskName = "FAC ISR SMS"

function Assert-Administrator {
  if ($TestMode) { return }
  $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw "Administrator privileges are required" }
}

function Get-CurrentReleasePath {
  $pointer = Join-Path $InstallRoot "current.txt"
  if (-not (Test-Path -LiteralPath $pointer -PathType Leaf)) { throw "No current FAC ISR SMS installation" }
  $name = (Get-Content -LiteralPath $pointer -Raw).Trim()
  if ($name -notmatch '^0\.2\.0-rc\.1-[a-f0-9]{16}$') { throw "Current release pointer is invalid" }
  $path = Join-Path (Join-Path $InstallRoot "releases") $name
  if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Current immutable release is missing" }
  return $path
}

function Assert-PortableRelativePath([string]$Relative) {
  if ([string]::IsNullOrEmpty($Relative) -or $Relative -notmatch '^[A-Za-z0-9_./@+\-]+$') { throw "Bundle path is not portable" }
  $components = $Relative.Split('/')
  if ($components -contains "" -or $components -contains "." -or $components -contains "..") { throw "Bundle path contains an ambiguous component" }
  foreach ($component in $components) {
    if ($component.EndsWith('.')) { throw "Bundle path has a non-portable trailing dot" }
    $stem = $component.Split('.')[0].ToUpperInvariant()
    if ($stem -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$') { throw "Bundle path uses a reserved Windows name" }
  }
}

function Test-BundleInventory([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Container)) { throw "BundleRoot is required and must be a directory" }
  $rootItem = Get-Item -LiteralPath $Path -Force
  if ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Bundle root cannot be a reparse point" }
  foreach ($item in Get-ChildItem -LiteralPath $Path -Recurse -Force) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Bundle reparse points are forbidden: $($item.FullName)" }
    Assert-PortableRelativePath ([IO.Path]::GetRelativePath($Path, $item.FullName).Replace('\', '/'))
  }
  $inventoryPath = Join-Path $Path "inventory.json"
  $trustedInventoryPath = Join-Path $Path "inventory.tsv"
  $releasePath = Join-Path $Path "release.json"
  $runtimePath = Join-Path $Path "runtime\node.exe"
  if (-not (Test-Path -LiteralPath $inventoryPath -PathType Leaf) -or -not (Test-Path -LiteralPath $trustedInventoryPath -PathType Leaf) -or -not (Test-Path -LiteralPath $runtimePath -PathType Leaf)) { throw "Bundle inventory or Node runtime is missing" }
  $inventory = Get-Content -LiteralPath $inventoryPath -Raw | ConvertFrom-Json
  if ($inventory.schemaVersion -ne "1.0" -or $null -eq $inventory.files) { throw "Unsupported bundle inventory" }
  $expected = @{}
  foreach ($entry in $inventory.files) {
    $relative = [string]$entry.path
    Assert-PortableRelativePath $relative
    if ([IO.Path]::IsPathRooted($relative) -or $expected.ContainsKey($relative)) { throw "Unsafe or duplicate inventory path" }
    $expected[$relative] = $entry
  }
  $actual = @(Get-ChildItem -LiteralPath $Path -Recurse -File -Force | Where-Object { $_.FullName -ne $inventoryPath -and $_.FullName -ne $trustedInventoryPath })
  if ($actual.Count -ne $expected.Count) { throw "Bundle inventory path set mismatch" }
  foreach ($file in $actual) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Bundle reparse points are forbidden" }
    $relative = [IO.Path]::GetRelativePath($Path, $file.FullName).Replace('\', '/')
    Assert-PortableRelativePath $relative
    if (-not $expected.ContainsKey($relative)) { throw "Unexpected bundle file: $relative" }
    $entry = $expected[$relative]
    $digest = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -ne [string]$entry.sha256 -or $file.Length -ne [long]$entry.sizeBytes) { throw "Bundle inventory mismatch: $relative" }
  }
  $trusted = @{}
  foreach ($line in Get-Content -LiteralPath $trustedInventoryPath) {
    $fields = $line.Split("`t")
    if ($fields.Count -ne 4) { throw "Trusted bundle inventory record is invalid" }
    $relative = [string]$fields[0]
    Assert-PortableRelativePath $relative
    if ($trusted.ContainsKey($relative) -or [string]$fields[1] -notmatch '^[a-f0-9]{64}$' -or [string]$fields[2] -notmatch '^[0-9]+$' -or [string]$fields[3] -notmatch '^[0-7]{3}$') { throw "Trusted bundle inventory record is unsafe or duplicate" }
    $trusted[$relative] = @{ sha256 = [string]$fields[1]; sizeBytes = [long]$fields[2] }
  }
  $trustedFiles = @($actual) + @(Get-Item -LiteralPath $inventoryPath)
  if ($trusted.Count -ne $trustedFiles.Count) { throw "Trusted bundle inventory path set mismatch" }
  foreach ($file in $trustedFiles) {
    $relative = [IO.Path]::GetRelativePath($Path, $file.FullName).Replace('\', '/')
    if (-not $trusted.ContainsKey($relative)) { throw "Trusted bundle inventory is missing: $relative" }
    $record = $trusted[$relative]
    if ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.sha256 -or $file.Length -ne $record.sizeBytes) { throw "Trusted bundle inventory mismatch: $relative" }
  }
  $release = Get-Content -LiteralPath $releasePath -Raw | ConvertFrom-Json
  if ($release.release -ne "fac-isr-sms@0.2.0-rc.1" -or $release.target -ne "win32-x64" -or $release.nodeVersion -ne "22.23.2" -or $release.internet -ne "disabled" -or $release.operationalReady -ne $false -or $release.production -ne $true -or $release.runtimeProvenance -ne "official-node-signed-checksums") { throw "Bundle release metadata is invalid" }
  $buildProperty = $release.PSObject.Properties["buildId"]
  return @{ InventoryPath = $inventoryPath; BuildId = $(if ($null -ne $buildProperty) { [string]$buildProperty.Value } else { "release" }) }
}

function Set-RestrictedAcl([string]$Path, [bool]$IsDirectory, [bool]$ServiceWrite = $true) {
  if ($TestMode -and $env:OS -ne "Windows_NT") { return }
  $inheritance = if ($IsDirectory) { "(OI)(CI)" } else { "" }
  $servicePermission = if ($ServiceWrite) { "F" } else { "RX" }
  & icacls.exe $Path "/inheritance:r" "/grant:r" "NT AUTHORITY\SYSTEM:${inheritance}F" "BUILTIN\Administrators:${inheritance}F" "NT AUTHORITY\LOCAL SERVICE:${inheritance}${servicePermission}" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Failed to apply restricted ACL to $Path" }
}

function Assert-PrivateKeyAcl([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "TLS private key is missing: $Path" }
  $item = Get-Item -LiteralPath $Path -Force
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "TLS private key cannot be a reparse point" }
  $allowed = @("S-1-5-18", "S-1-5-19", "S-1-5-32-544")
  $acl = Get-Acl -LiteralPath $Path
  foreach ($rule in $acl.Access) {
    $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
    if ($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and $sid -notin $allowed) { throw "TLS private key ACL grants access to $sid" }
  }
}

function Initialize-MutableLayout {
  foreach ($path in @($ConfigRoot, (Join-Path $ConfigRoot "tls"), $DataRoot, $PackageRoot, $LogRoot, $BackupRoot, $StateRoot)) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    Set-RestrictedAcl $path $true
  }
}

function Add-ImmutableRelease([string]$Path) {
  $verified = Test-BundleInventory $Path
  $hash = (Get-FileHash -LiteralPath $verified.InventoryPath -Algorithm SHA256).Hash.ToLowerInvariant().Substring(0, 16)
  $releaseName = "0.2.0-rc.1-$hash"
  $releases = Join-Path $InstallRoot "releases"
  $destination = Join-Path $releases $releaseName
  New-Item -ItemType Directory -Path $releases -Force | Out-Null
  $created = $false
  if (-not (Test-Path -LiteralPath $destination)) {
    $staging = Join-Path $releases ".staging-$releaseName-$PID"
    Copy-Item -LiteralPath $Path -Destination $staging -Recurse
    Test-BundleInventory $staging | Out-Null
    Move-Item -LiteralPath $staging -Destination $destination
    Get-ChildItem -LiteralPath $destination -Recurse -Force | ForEach-Object { $_.IsReadOnly = $true }
    Set-RestrictedAcl $destination $true $false
    $created = $true
  }
  return @{ Name = $releaseName; Path = $destination; BuildId = $verified.BuildId; Created = $created }
}

function Set-CurrentRelease([string]$Name) {
  $temporary = Join-Path $InstallRoot "current.txt.new"
  [IO.File]::WriteAllText($temporary, "$Name`r`n", [Text.UTF8Encoding]::new($false))
  Move-Item -LiteralPath $temporary -Destination (Join-Path $InstallRoot "current.txt") -Force
}

function Register-SmsTask {
  if ($TestMode) {
    [IO.File]::WriteAllText((Join-Path $StateRoot "task.json"), '{"trigger":"AtStartup","account":"LocalService","restartCount":999}', [Text.UTF8Encoding]::new($false))
    return
  }
  $release = Get-CurrentReleasePath
  $launcher = Join-Path $release "install\windows\Start-Sms.ps1"
  $taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "{0}" -ReleaseRoot "{1}" -ConfigurationPath "{2}"' -f $launcher, $release, (Join-Path $ConfigRoot "sms.env")) -WorkingDirectory $release
  $trigger = New-ScheduledTaskTrigger -AtStartup
  $principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\LOCAL SERVICE" -LogonType ServiceAccount -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
  Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
}

function Assert-RuntimeSecurity {
  Assert-PrivateKeyAcl (Join-Path $ConfigRoot "tls\server.key")
  Assert-PrivateKeyAcl (Join-Path $ConfigRoot "tls\export.key")
  if (-not (Test-Path -LiteralPath (Join-Path $ConfigRoot "tls\server.crt") -PathType Leaf)) { throw "TLS certificate is missing" }
}

function Set-SmsProcessEnvironment {
  foreach ($line in Get-Content -LiteralPath (Join-Path $ConfigRoot "sms.env")) {
    if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) { continue }
    $separator = $line.IndexOf('=')
    if ($separator -lt 1) { throw "Invalid SMS environment configuration line" }
    $name = $line.Substring(0, $separator)
    if ($name -notmatch '^SMS_[A-Z0-9_]+$') { throw "Invalid SMS environment variable name" }
    [Environment]::SetEnvironmentVariable($name, $line.Substring($separator + 1), "Process")
  }
}

function Assert-SmsReadiness {
  Set-SmsProcessEnvironment
  $release = Get-CurrentReleasePath
  & (Join-Path $release "runtime\node.exe") (Join-Path $release "app\scripts\edge-healthcheck.mjs") --ready *> $null
  if ($LASTEXITCODE -ne 0) { throw "FAC ISR SMS installed process is not technically ready" }
}

function Start-Sms {
  Assert-RuntimeSecurity
  if ($TestMode) {
    Add-Content -LiteralPath (Join-Path $StateRoot "lifecycle.log") -Value "start-attempt"
    Set-SmsProcessEnvironment
    $release = Get-CurrentReleasePath
    & (Join-Path $release "runtime\node.exe") (Join-Path $release "app\scripts\start-edge.mjs") *> $null
    if ($LASTEXITCODE -ne 0) { throw "FAC ISR SMS controlled start failed" }
    [IO.File]::WriteAllText((Join-Path $StateRoot "service.state"), "running ready`r`n", [Text.UTF8Encoding]::new($false))
  } else {
    Start-ScheduledTask -TaskName $TaskName
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
      try { Assert-SmsReadiness; $ready = $true; break } catch { }
      Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "FAC ISR SMS did not become ready" }
  }
}

function Stop-Sms {
  if ($TestMode) {
    New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
    Add-Content -LiteralPath (Join-Path $StateRoot "lifecycle.log") -Value "stop"
    [IO.File]::WriteAllText((Join-Path $StateRoot "service.state"), "stopped`r`n", [Text.UTF8Encoding]::new($false))
  } else {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  }
}

function Test-SmsRunning {
  if ($TestMode) {
    $state = Join-Path $StateRoot "service.state"
    return (Test-Path -LiteralPath $state -PathType Leaf) -and ((Get-Content -LiteralPath $state -Raw).Trim() -eq "running ready")
  }
  return (Get-ScheduledTask -TaskName $TaskName).State -eq "Running"
}

function Remove-ImmutableRelease([string]$Name) {
  $path = Join-Path (Join-Path $InstallRoot "releases") $Name
  if (Test-Path -LiteralPath $path -PathType Container) {
    Get-ChildItem -LiteralPath $path -Recurse -Force | ForEach-Object { $_.IsReadOnly = $false }
    Remove-Item -LiteralPath $path -Recurse -Force
  }
}

function New-SmsBackup {
  New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
  $path = Join-Path $BackupRoot ("fac-isr-sms-{0}-{1}.zip" -f (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"), $PID)
  Compress-Archive -LiteralPath $DataRoot, $PackageRoot -DestinationPath $path -CompressionLevel Optimal
  Set-RestrictedAcl $path $false
  Write-Output $path
}

function Restore-SmsBackup([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "BackupPath is required and must be a file" }
  $staging = Join-Path $MutableRoot ".restore-$PID"
  $rollback = Join-Path $MutableRoot ".rollback-$PID"
  if ($TestMode) { Add-Content -LiteralPath (Join-Path $StateRoot "lifecycle.log") -Value "restore" }
  Expand-Archive -LiteralPath $Path -DestinationPath $staging
  foreach ($item in Get-ChildItem -LiteralPath $staging -Recurse -Force) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { Remove-Item -LiteralPath $staging -Recurse -Force; throw "Backup reparse points are forbidden" }
    Assert-PortableRelativePath ([IO.Path]::GetRelativePath($staging, $item.FullName).Replace('\', '/'))
  }
  New-Item -ItemType Directory -Path $rollback | Out-Null
  $stagedData = Join-Path $staging "data"
  $stagedPackages = Join-Path $staging "packages"
  if (-not (Test-Path -LiteralPath $stagedData -PathType Container) -or -not (Test-Path -LiteralPath $stagedPackages -PathType Container)) {
    Remove-Item -LiteralPath $staging, $rollback -Recurse -Force
    throw "Backup does not contain both data and packages"
  }
  $oldDataMoved = $false
  $oldPackagesMoved = $false
  try {
    if (Test-Path -LiteralPath $DataRoot) {
      Move-Item -LiteralPath $DataRoot -Destination (Join-Path $rollback "data")
      $oldDataMoved = $true
    }
    if ($TestMode -and $env:SMS_TEST_FAIL_RESTORE_AFTER_OLD_DATA_MOVE -eq "1") { throw "controlled restore failure after staging original data" }
    if (Test-Path -LiteralPath $PackageRoot) {
      Move-Item -LiteralPath $PackageRoot -Destination (Join-Path $rollback "packages")
      $oldPackagesMoved = $true
    }
    Move-Item -LiteralPath $stagedData -Destination $DataRoot
    Move-Item -LiteralPath $stagedPackages -Destination $PackageRoot
    Remove-Item -LiteralPath $rollback, $staging -Recurse -Force
    Set-RestrictedAcl $DataRoot $true
    Set-RestrictedAcl $PackageRoot $true
  } catch {
    $originalFailure = $_.Exception.Message
    $recoveryFailures = @()
    if ($oldDataMoved) {
      try {
        if (Test-Path -LiteralPath $DataRoot) { Remove-Item -LiteralPath $DataRoot -Recurse -Force }
        Move-Item -LiteralPath (Join-Path $rollback "data") -Destination $DataRoot
      } catch { $recoveryFailures += "data: $($_.Exception.Message)" }
    }
    if ($oldPackagesMoved) {
      try {
        if (Test-Path -LiteralPath $PackageRoot) { Remove-Item -LiteralPath $PackageRoot -Recurse -Force }
        Move-Item -LiteralPath (Join-Path $rollback "packages") -Destination $PackageRoot
      } catch { $recoveryFailures += "packages: $($_.Exception.Message)" }
    }
    if ($recoveryFailures.Count -gt 0) { throw "Restore failed and original-state recovery is incomplete; recovery remains at ${rollback}: $($recoveryFailures -join '; ')" }
    Remove-Item -LiteralPath $staging, $rollback -Recurse -Force -ErrorAction SilentlyContinue
    throw "Restore failed; original data and packages were recovered: $originalFailure"
  }
}

Assert-Administrator
switch ($Action) {
  "Install" {
    Initialize-MutableLayout
    $release = Add-ImmutableRelease $BundleRoot
    Set-CurrentRelease $release.Name
    if ($TestMode -and $env:SMS_TEST_MUTATE_SOURCE_AFTER_STAGE -eq "1") {
      $sourceTemplate = Get-Item -LiteralPath (Join-Path $BundleRoot "config\sms.env.template")
      $sourceTemplate.IsReadOnly = $false
      [IO.File]::WriteAllText($sourceTemplate.FullName, "SMS_SOURCE_MUTATED=1`r`n", [Text.UTF8Encoding]::new($false))
    }
    $configuration = Join-Path $ConfigRoot "sms.env"
    if (-not (Test-Path -LiteralPath $configuration)) {
      $template = (Get-Content -LiteralPath (Join-Path $release.Path "config\sms.env.template") -Raw).Replace("@PROGRAMDATA_SMS@", $MutableRoot).Replace("@PROGRAMFILES_SMS@", $InstallRoot)
      [IO.File]::WriteAllText($configuration, $template, [Text.UTF8Encoding]::new($false))
    }
    Set-RestrictedAcl $configuration $false
    Register-SmsTask
    Write-Output "installed $($release.Name)"
  }
  "Start" { Start-Sms }
  "Restart" { Stop-Sms; Start-Sms }
  "Status" {
    if ($TestMode) {
      $state = Get-Content -LiteralPath (Join-Path $StateRoot "service.state") -Raw
      Write-Output $state.Trim()
      if ($state.Trim() -ne "running ready") { exit 3 }
    } else {
      $task = Get-ScheduledTask -TaskName $TaskName
      Write-Output $task.State
      if ($task.State -ne "Running") { exit 3 }
      Assert-SmsReadiness
    }
  }
  "Stop" { Stop-Sms }
  "Backup" {
    $wasRunning = Test-SmsRunning
    if ($wasRunning) { Stop-Sms }
    try { New-SmsBackup } finally { if ($wasRunning) { Start-Sms } }
  }
  "Restore" {
    $wasRunning = Test-SmsRunning
    if ($wasRunning) { Stop-Sms }
    try { Restore-SmsBackup $BackupPath } finally { if ($wasRunning) { Start-Sms } }
  }
  "Upgrade" {
    $oldPointer = (Get-Content -LiteralPath (Join-Path $InstallRoot "current.txt") -Raw).Trim()
    $release = Add-ImmutableRelease $BundleRoot
    $wasRunning = Test-SmsRunning
    if ($wasRunning) { Stop-Sms }
    $rollbackBackup = $null
    try {
      $rollbackBackup = New-SmsBackup
      if ($TestMode -and $env:SMS_TEST_FAIL_MIGRATION_AFTER_STAGE -eq "1") { throw "controlled migration failure after staging" }
      $migration = Join-Path $release.Path "install\windows\Migrate.ps1"
      if (Test-Path -LiteralPath $migration) { & $migration -DataRoot $MutableRoot -BuildId $release.BuildId }
      if (-not $?) { throw "migration returned failure" }
      Set-CurrentRelease $release.Name
      Register-SmsTask
      if ($wasRunning) { Start-Sms }
      Write-Output "upgraded from $oldPointer to $($release.Name)"
    } catch {
      if ($wasRunning) { Stop-Sms }
      if ($null -ne $rollbackBackup) { Restore-SmsBackup $rollbackBackup }
      Set-CurrentRelease $oldPointer
      Register-SmsTask
      if ($release.Created -and $release.Name -ne $oldPointer) { Remove-ImmutableRelease $release.Name }
      if ($wasRunning) { Start-Sms }
      throw "Upgrade failed; data, immutable pointer, and prior service state were rolled back: $($_.Exception.Message)"
    }
  }
  "Uninstall" {
    Stop-Sms
    if (-not $TestMode) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $InstallRoot) { Get-ChildItem -LiteralPath $InstallRoot -Recurse -Force | ForEach-Object { $_.IsReadOnly = $false }; Remove-Item -LiteralPath $InstallRoot -Recurse -Force }
    if (Test-Path -LiteralPath $ConfigRoot) { Remove-Item -LiteralPath $ConfigRoot -Recurse -Force }
    if (Test-Path -LiteralPath $LogRoot) { Remove-Item -LiteralPath $LogRoot -Recurse -Force }
    Write-Output "uninstalled; data preserved at $DataRoot"
  }
}
