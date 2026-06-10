$ErrorActionPreference = "Stop"
$env:API_URL = "http://127.0.0.1:8000"
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
Set-Location $PSScriptRoot
& npm.cmd run dev *>&1 | Tee-Object -FilePath (Join-Path $PSScriptRoot "next.combined.log")
