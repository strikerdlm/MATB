[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$DataRoot,
  [Parameter(Mandatory = $true)][string]$BuildId
)

$ErrorActionPreference = "Stop"
$release = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$database = Join-Path $DataRoot "data\edge.sqlite"
if (Test-Path -LiteralPath $database -PathType Leaf) {
  & (Join-Path $release "runtime\node.exe") (Join-Path $release "app\apps\edge-api\dist\admin\cli.js") diagnose --database $database
  if ($LASTEXITCODE -ne 0) { throw "sms-admin migration diagnostics failed" }
}
