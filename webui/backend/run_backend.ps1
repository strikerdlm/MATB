$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = $env:MATB_PYTHON
if (-not $python -and $env:CONDA_PREFIX) {
    $candidate = Join-Path $env:CONDA_PREFIX "python.exe"
    if (Test-Path $candidate) {
        $python = $candidate
    }
}

if ($python) {
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 *>&1 |
        Tee-Object -FilePath (Join-Path $PSScriptRoot "uvicorn.combined.log")
} else {
    conda run -n matb python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 *>&1 |
        Tee-Object -FilePath (Join-Path $PSScriptRoot "uvicorn.combined.log")
}
