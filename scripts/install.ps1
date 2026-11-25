$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'
    }
    $env:UV_PROJECT_ENVIRONMENT = Join-Path (Get-Location).Path '.venv'
    & uv run --frozen python scripts/setup.py install
    if ($LASTEXITCODE -ne 0) { throw "Setup failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
