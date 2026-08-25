[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$ReleaseRoot,
  [Parameter(Mandatory = $true)][string]$ConfigurationPath
)

$ErrorActionPreference = "Stop"
foreach ($line in Get-Content -LiteralPath $ConfigurationPath) {
  if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) { continue }
  $separator = $line.IndexOf('=')
  if ($separator -lt 1) { throw "Invalid SMS environment configuration line" }
  $name = $line.Substring(0, $separator)
  $value = $line.Substring($separator + 1)
  if ($name -notmatch '^SMS_[A-Z0-9_]+$') { throw "Invalid SMS environment variable name" }
  [Environment]::SetEnvironmentVariable($name, $value, "Process")
}
[Environment]::SetEnvironmentVariable("SMS_CONSOLE_DIRECTORY", (Join-Path $ReleaseRoot "app\apps\console\dist"), "Process")
& (Join-Path $ReleaseRoot "runtime\node.exe") (Join-Path $ReleaseRoot "app\scripts\start-edge.mjs")
exit $LASTEXITCODE
